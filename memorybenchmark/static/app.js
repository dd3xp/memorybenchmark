/* Human presentation over the same public game protocol used by agents. */
const $ = id => document.getElementById(id), svgNS = 'http://www.w3.org/2000/svg';
const storageKey = 'cartography.play.v2';
let instance = null, observation = null, busy = false, loaded = false;
let submittedAtlas = {nodes:[], edges:[], surveyed:[]};
let scenario = 'lake-easy', taskCount = 8, selection = null, journal = [], confirmAction;

function html(type, className, text) {
  const item = document.createElement(type);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function svg(type, attrs, text) {
  const item = document.createElementNS(svgNS, type);
  Object.entries(attrs).forEach(([key,value]) => item.setAttribute(key, value));
  if (text !== undefined) item.textContent = text;
  return item;
}
function remember() {
  try { sessionStorage.setItem(storageKey, JSON.stringify({instance, journal, taskRun:observation?.task_run_id})); } catch (_) { /* Storage is optional. */ }
}
function notice(message = '') { $('error').textContent=message; $('error').hidden=!message; }
async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (response.status === 401) { location.assign('/login?next=/play'); throw new Error('登录已失效，请重新登录后继续。'); }
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || '连接失败，请稍后重试。');
  return result;
}
function defaultHint() {
  if (!observation) return '从营地出发，点击地图上的相邻地点探索。';
  return observation.done ? '本次探索已结束，可以查看地图或接下一个委托。' : '点击描边突出的相邻地点，直接前往。';
}
function pickNode(node) {
  if (busy) return;
  const neighbor = observation?.neighbors.find(n => n.target === node.id);
  if (neighbor && !observation.done) { act('move', node.id); return; }
  selection = node.id;
  $('selection-name').textContent = `${node.name} ${node.id}`;
  $('selection-description').textContent = node.id === observation?.location.id
    ? '你正在这里。可在地点面板观察、等待或进行此处的操作。'
    : observation?.done ? '这是已经发现的地点。本次探索已结束。' : '这是已发现的地点，目前不能直接抵达。请选择与当前位置相连的地点行走。';
  $('map-selection').hidden=false; draw(observation);
}
function draw(o) {
  if (!o) return;
  const focused=document.activeElement?.dataset?.mapNode, mapSvg=$('map');
  Cartography.prepare(mapSvg,o);
  const map=Cartography.merge(Cartography.current(o.map),$('show-atlas').checked?submittedAtlas:null);
  const nodes=Object.fromEntries(map.nodes.map(n=>[n.id,n])), neighbors=new Map(o.neighbors.map(n=>[n.target,n]));
  const goals=new Set((o.objective?.targets||[]).map(n=>n.id));
  $('edges').replaceChildren(); $('nodes').replaceChildren();
  map.edges.forEach(([a,b])=>{
    if (!nodes[a] || !nodes[b]) return;
    const adjacent=!o.done && (a===o.location.id || b===o.location.id);
    $('edges').append(WorldScene.route(nodes[a],nodes[b],adjacent));
    const route=adjacent && neighbors.get(a===o.location.id?b:a);
    if (route) $('edges').append(svg('text',{x:(nodes[a].x+nodes[b].x)/2+10,y:(nodes[a].y+nodes[b].y)/2-8,class:'distance-label'},`路程 ${route.distance}`));
  });
  Cartography.recovery(mapSvg,$('recovery-edges'),o.recovery?.history,nodes);
  [...map.nodes].sort((a,b)=>Number(a.id===o.location.id)-Number(b.id===o.location.id)).forEach(n=>{
    const here=n.id===o.location.id, neighbor=!o.done && neighbors.get(n.id), measured=o.map.surveyed.includes(n.id);
    const label=neighbor?`前往${n.name} ${n.id}，路程 ${neighbor.distance}`:`${n.name} ${n.id}，${here?'当前位置':'查看地点'}`;
    const group=svg('g',{transform:`translate(${n.x} ${n.y})`,class:`map-node${here?' is-current':''}${neighbor?' is-neighbor':''}${goals.has(n.id)?' is-goal':''}${selection===n.id?' selected':''}`,
      role:'button',tabindex:0,'aria-label':label,'aria-disabled':String(busy),'data-map-node':n.id});
    group.append(svg('title',{},label),svg('circle',{r:10,class:'node-hit'}));
    if (neighbor) group.append(svg('circle',{r:17,class:'node-halo'}));
    if (n.kind==='camp') group.append(svg('path',{d:'M-12 10 L0 -14 L12 10Z',class:'camp-mark'}));
    group.append(svg('circle',{r:here?8:6,class:`node-circle${here?' here':''}${measured?' surveyed':''}${map.submitted.has(n.id)?' submitted':''}`}));
    if (here) group.append(svg('circle',{r:14,class:'player-ring'}));
    if (goals.has(n.id) && !measured) group.append(svg('path',{d:'M14 -20 L21 -13 L14 -6 L7 -13Z',class:'goal-marker'}));
    const visibleLabel=here || neighbor || goals.has(n.id) || selection===n.id || Cartography.labels(mapSvg,n,o);
    group.append(svg('text',{x:0,y:32,'text-anchor':'middle',class:`node-label${visibleLabel?'':' detail-label'}`},n.name));
    group.append(svg('text',{x:0,y:-23,'text-anchor':'middle',class:`node-id${visibleLabel?'':' detail-label'}`},n.id));
    group.addEventListener('click',()=>pickNode(n));
    group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(!event.repeat)pickNode(n);}});
    const hint=()=>{$('map-hint').textContent=neighbor?`点击前往${n.name} · 路程 ${neighbor.distance}`:here?`当前位置：${n.name}`:`查看${n.name}的地理信息`;};
    group.addEventListener('mouseenter',hint); group.addEventListener('focus',()=>{if(group.matches(':focus-visible'))mapSvg._revealPoint?.(n.x,n.y);hint();});
    group.addEventListener('mouseleave',()=>$('map-hint').textContent=defaultHint()); group.addEventListener('blur',()=>$('map-hint').textContent=defaultHint());
    WorldScene.decorate(group,n,map.submitted.has(n.id));$('nodes').append(group);
  });
  if (focused) [...$('nodes').children].find(n=>n.dataset.mapNode===focused)?.focus({preventScroll:true});
  $('map-caption').textContent=`本次测绘 ${o.map.surveyed.length} 处，累计点亮 ${submittedAtlas.surveyed.length} 处`;
  WorldScene.sync(mapSvg,o,map);
}
function renderInventory(o) {
  $('inventory-count').textContent=o.inventory.length; $('inventory').replaceChildren();
  if(!o.inventory.length)$('inventory').append(html('p','empty-state','背包还是空的。探索时留意沿途可取用的工具。'));
  o.inventory.forEach(tool=>{const item=html('article','inventory-item');item.append(html('h3','',tool.name),html('p','',tool.description));$('inventory').append(item);});
}
function renderJournal() {
  $('log').replaceChildren(); $('empty-log').hidden=journal.length>0;
  [...journal].reverse().forEach(entry=>{const item=html('li');item.append(html('time','',`${entry.task} · 游戏时间 ${entry.time}`),document.createTextNode(entry.feedback));$('log').append(item);});
}
function syncControls() {
  document.querySelectorAll('[data-game]').forEach(button=>button.disabled=busy || !loaded);
  $('begin').disabled=busy || !loaded; $('abandon').disabled=busy || !observation || observation.done;
  $('submit').disabled=busy || !observation || observation.done || Boolean(observation.objective && !observation.objective.ready);
  $('map').closest('.map-stage').setAttribute('aria-busy',String(busy));
  document.querySelectorAll('[data-map-node]').forEach(node=>node.setAttribute('aria-disabled',String(busy)));
}
function update(result,{addEntry=true}={}) {
  const previous=observation; observation=result.observation; instance=result.instance_id;
  const o=observation, objective=o.objective;
  document.body.classList.add('is-playing');
  document.body.classList.toggle('has-stock',Boolean(o.available_tools.length));
  document.body.classList.toggle('can-submit',Boolean(objective?.at_submission_camp));
  document.body.classList.toggle('task-ended',o.done);
  $('task-name').textContent=o.task_name; $('instruction').textContent=o.instruction; $('task-stage').textContent=`${o.task_id.replace(/^T/,'')} / ${taskCount}`;
  $('objectives').replaceChildren();
  (objective?.targets||[]).forEach(target=>{const item=html('li',target.recorded?'recorded':'');item.append(html('span','objective-icon',target.recorded?'✓':'○'),document.createTextNode(target.name));item.setAttribute('aria-label',`${target.name}，${target.recorded?'已测绘':'待测绘'}`);$('objectives').append(item);});
  const allRecorded=objective?.targets.every(n=>n.recorded), campNames=objective?.submission_camps.map(n=>n.name).join('、');
  $('camp-status').textContent=o.done?(o.success?'记录已入册，本项委托完成。':'本项委托已结束。'):objective?(objective.ready?'已抵达提交营地，可以交付记录。':`${allRecorded?'测绘完成，返回':'提交营地：'}${campNames}${allRecorded?'交付记录。':''}`):'完成测绘后提交记录。';
  $('camp-status').classList.toggle('ready',Boolean(objective?.ready));
  $('begin').hidden=true; $('play').hidden=o.done; $('ending').hidden=!o.done;
  $('place').textContent=o.location.name; $('place-id').textContent=o.location.id;
  $('location-hint').textContent=o.location.kind==='camp'?'营地。点击地图上相邻的地点继续探索。':'已自动记录此处地理。点击相邻地点继续探索。';
  $('conditions').textContent=`${{rain:'下雨',clear:'晴朗',snow:'下雪'}[o.conditions.weather]||o.conditions.weather} / ${{night:'夜间',day:'白天'}[o.conditions.period]||o.conditions.period}`;
  $('weather-icon').textContent={rain:'☂',clear:o.conditions.period==='night'?'☾':'☀',snow:'❄'}[o.conditions.weather]||'◌';
  $('time').textContent=`游戏时间 ${o.world_time}`; $('distance').textContent=`路程 ${o.distance}`; $('steps').textContent=`操作 ${o.steps} / ${o.max_steps}`;
  $('stamina').textContent=`${o.stamina} / ${o.initial_stamina}`; $('energy').setAttribute('aria-valuemax',o.initial_stamina); $('energy').setAttribute('aria-valuenow',o.stamina);
  $('energy-fill').style.width=`${Math.max(0,Math.min(100,100*o.stamina/o.initial_stamina))}%`;
  $('energy-panel').classList.toggle('low-stamina',o.stamina<=o.initial_stamina*.35);
  $('energy-panel').querySelector('div>span').textContent=o.stamina<=o.initial_stamina*.35?'体力偏低':'体力';
  $('recovery-status').hidden=!o.recovery?.deaths;
  if(o.recovery?.deaths)$('recovery-status').textContent=`复活 ${o.recovery.deaths} 次，累计惩罚 ${o.recovery.penalty}。测绘进度保留，操作预算不重置。`;
  renderInventory(o); $('stock-section').hidden=!o.available_tools.length; $('stock').replaceChildren();
  o.available_tools.forEach(tool=>{const button=html('button','tool-pickup');button.dataset.game='';button.dataset.tool=tool.id;const name=html('strong','',tool.name);name.append(html('span','','取用 ＋'));button.append(name,html('small','',tool.description));button.onclick=()=>act('take',tool.id);$('stock').append(button);});
  $('camp-actions').hidden=Boolean(objective && !objective.at_submission_camp);
  $('submit-hint').textContent=objective && !allRecorded?'还有测绘目标未完成，完成后再来提交。':'提交后，本次走过的地点会在地图上点亮。';
  $('result').textContent=o.success?'委托完成，记录已入册。':'本次探索已结束。'; $('result').classList.toggle('failed',!o.success);
  $('result-detail').textContent=`测绘 ${o.map.surveyed.length} 处 · 路程 ${o.distance}${o.recovery?.deaths?` · 复活 ${o.recovery.deaths} 次`:''}`;
  $('next').textContent=o.next_task_id?'接下一个委托':'重新探索这片湖区';
  if(addEntry)journal.push({task:o.task_id,time:o.world_time,feedback:result.feedback});
  journal=journal.slice(-150); renderJournal(); $('feedback').textContent=result.feedback||'已恢复当前探索。'; $('map-hint').textContent=defaultHint();
  selection=null; $('map-selection').hidden=true; draw(o);
  if(!previous || previous.task_run_id!==o.task_run_id)$('map')._locate?.(); else $('map')._revealPoint?.(o.location.x,o.location.y);
  syncControls(); remember();
}
async function run(action) {
  if(busy)return; busy=true;notice();syncControls();
  try{await action();}catch(error){notice(error.message||'连接失败，请稍后重试。');}finally{busy=false;syncControls();}
}
async function receive(result,options) {
  const before=observation;
  // Do not lose an executed action if the separate atlas request fails.
  if(instance!==result.instance_id || result.observation.success){try{submittedAtlas=await request('/api/atlas?instance_id='+encodeURIComponent(result.instance_id));}catch(_){notice('已收到游戏结果，累计地图暂时无法更新。刷新页面可重试。');}}
  update(result,options);
  if(options?.addEntry!==false)await WorldScene.transition($('map'),before,result);
}
function start(task,fresh=false) {
  return run(async()=>{const result=await request('/api/start',{task_id:task,scenario,...(!fresh&&instance?{instance_id:instance}:{})});journal=[];await receive(result);});
}
function act(type,target) {
  if(!instance || !observation || observation.done)return;
  return run(async()=>{
    const body={instance_id:instance,request_id:crypto.randomUUID(),expected_revision:observation.revision,action:{type,...(target?{target}:{})}};
    try{await receive(await request('/api/action',body));}catch(error){
      // A lost response may hide an applied action: reconcile before the next one.
      try{await receive(await request('/api/observation?instance_id='+encodeURIComponent(instance)));}catch(_){/* Keep the original error. */}
      throw error;
    }
  });
}
function openNotebook(page) {
  $('menu').close();
  ['inventory','journal','help'].forEach(name=>{$(`tab-${name}`).setAttribute('aria-selected',String(name===page));$(`tab-${name}`).tabIndex=name===page?0:-1;$(`${name}-page`).hidden=name!==page;});
  if(!$('notebook').open)$('notebook').showModal(); $(`tab-${page}`).focus();
}
function confirmChange(title,description,label,action) {
  if(busy)return; $('menu').close();confirmAction=action;
  $('confirm-title').textContent=title; $('confirm-description').textContent=description; $('confirm-accept').textContent=label;
  $('confirm-dialog').showModal(); $('confirm-cancel').focus();
}
$('begin').onclick=()=>start('T1');
$('next').onclick=()=>observation?.next_task_id?start(observation.next_task_id):start('T1',true);
$('fresh').onclick=()=>confirmChange('重新开始探索？','当前探索将被放下，累计点亮的地图也会清空，从第一项委托重新出发。','重新开始',()=>start('T1',true));
$('abandon').onclick=()=>confirmChange('结束本次探索？','本项委托将结束，已经发生的行动与代价仍会被记录。之后可以接下一个委托。','结束探索',()=>act('abandon'));
$('confirm-accept').onclick=()=>{$('confirm-dialog').close();confirmAction?.();};
$('confirm-cancel').onclick=()=>{$('confirm-dialog').close();confirmAction=null;};
$('open-inventory').onclick=()=>openNotebook('inventory'); $('open-journal').onclick=$('view-log').onclick=()=>openNotebook('journal');
$('help').onclick=()=>openNotebook('help'); $('open-menu').onclick=()=>$('menu').showModal();
$('sound-toggle').onclick=WorldScene.toggleSound;
$('fullscreen-toggle').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(_){notice('当前浏览器不支持全屏，可以继续在此窗口探索。');}};
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>$(button.dataset.close).close());
document.querySelectorAll('[data-action]').forEach(button=>button.onclick=()=>act(button.dataset.action));
document.querySelectorAll('[role=tab]').forEach(button=>{
  button.onclick=()=>openNotebook(button.id.replace('tab-',''));
  button.onkeydown=event=>{const names=['inventory','journal','help'],index=names.indexOf(button.id.replace('tab-',''));let next;
    if(event.key==='ArrowRight')next=names[(index+1)%3];if(event.key==='ArrowLeft')next=names[(index+2)%3];if(event.key==='Home')next=names[0];if(event.key==='End')next=names[2];
    if(next){event.preventDefault();openNotebook(next);}
  };
});
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{
  if(event.target!==dialog)return;const box=dialog.getBoundingClientRect();
  if(event.clientX<box.left || event.clientX>box.right || event.clientY<box.top || event.clientY>box.bottom)dialog.close();
}));
$('clear-selection').onclick=()=>{selection=null;$('map-selection').hidden=true;draw(observation);};
$('show-atlas').onchange=()=>draw(observation);
document.addEventListener('keydown',event=>{
  if(event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.target.closest('input,textarea,select,[contenteditable=true]') || document.querySelector('dialog[open]'))return;
  const key=event.key.toLowerCase();
  if(key==='i'){event.preventDefault();openNotebook('inventory');}if(key==='j'){event.preventDefault();openNotebook('journal');}
  if(key==='o' && observation && !observation.done){event.preventDefault();act('observe');}if(key==='w' && observation && !observation.done){event.preventDefault();act('wait');}
  if(key==='escape'){
    event.preventDefault();
    if(selection){selection=null;$('map-selection').hidden=true;draw(observation);}
    else $('menu').showModal();
  }
});
Cartography.controls($('map'),'play'); Cartography.prepare($('map'),{environment:{id:'lake-easy'}});
if(matchMedia('(max-width:760px)').matches)$('brief').open=false;
async function boot() {
  try{
    const data=await request('/api/tasks');scenario=data.scenario;taskCount=data.tasks.length;
    $('map-design-link').href='/design?scenario='+encodeURIComponent(scenario);
    const name=scenario==='lake-easy'?'雾汀湖':(data.name||'勘测区域');
    $('region-name').replaceChildren(document.createTextNode(name),html('span','',data.difficulty==='Easy'?'初级勘测':'地理勘测'));
    $('sheet-title').textContent=name;$('task-name').textContent=data.tasks[0].name;$('instruction').textContent=data.tasks[0].instruction;$('task-stage').textContent=`1 / ${taskCount}`;
    Cartography.prepare($('map'),{environment:{id:scenario}});loaded=true;
    let saved;try{saved=JSON.parse(sessionStorage.getItem(storageKey));}catch(_){/* Optional storage. */}
    if(saved?.instance){try{
      const result=await request('/api/observation?instance_id='+encodeURIComponent(saved.instance));
      journal=saved.taskRun===result.observation.task_run_id && Array.isArray(saved.journal)?saved.journal.filter(entry=>entry && typeof entry.feedback==='string').slice(-150):[];
      await receive(result,{addEntry:false});
    }catch(_){try{sessionStorage.removeItem(storageKey);}catch(_){/* Optional. */}$('feedback').textContent='上次探索已不可用。接下委托，开始一次新的探索。';}}
  }catch(error){notice(error.message);}syncControls();
}
boot();
