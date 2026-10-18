const $ = id => document.getElementById(id);
let instance = null, observation = null, busy = false;
let submittedAtlas = {nodes:[],edges:[],surveyed:[]};
let scenario = 'lake-easy', scenarioName='雾汀湖 · Easy', taskCount=4;
const svgNS = 'http://www.w3.org/2000/svg';
async function post(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (response.status===401) location.assign('/login?next=/play');
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || '连接失败，请稍后重试。');
  return result;
}
function el(type, attrs, text) {
  const item = document.createElementNS(svgNS, type);
  Object.entries(attrs).forEach(([k,v])=>item.setAttribute(k,v));
  if (text) item.textContent = text;
  return item;
}
function draw(o) {
  $('edges').replaceChildren(); $('nodes').replaceChildren();
  Cartography.prepare($('map'),o);
  const map=Cartography.merge(Cartography.current(o.map),$('show-atlas').checked?submittedAtlas:null);
  const nodes = Object.fromEntries(map.nodes.map(n=>[n.id,n]));
  map.edges.forEach(([a,b])=> $('edges').append(el('line',{x1:nodes[a].x,y1:nodes[a].y,x2:nodes[b].x,y2:nodes[b].y,class:'route-line'})));
  map.nodes.forEach(n=> {
    const measured = o.map.surveyed.includes(n.id);
    const circle=el('circle',{cx:n.x,cy:n.y,r:n.id===o.location.id?10:7,class:`node-circle ${n.id===o.location.id?'here':''} ${measured?'surveyed':''} ${map.submitted.has(n.id)?'submitted':''}`});
    circle.append(el('title',{},`${n.name} ${n.id}`));$('nodes').append(circle);
    if(n.kind==='camp')$('nodes').append(el('path',{d:`M${n.x-12} ${n.y+10} L${n.x} ${n.y-14} L${n.x+12} ${n.y+10}Z`,class:'camp-mark'}));
    $('nodes').append(el('text',{x:n.x,y:n.y+28,'text-anchor':'middle',class:`node-label ${Cartography.labels($('map'),n,o)?'':'detail-label'}`},n.name));
    $('nodes').append(el('text',{x:n.x,y:n.y-18,'text-anchor':'middle',class:'node-id'},n.id));
  });
  $('map-caption').textContent = `本次记录 ${o.map.surveyed.length} 处 · 累计提交 ${submittedAtlas.surveyed.length} 处`;
}
function update(result) {
  observation = result.observation; instance = result.instance_id;
  const o = observation;
  $('task-name').textContent = o.task_name;
  $('instruction').textContent = o.instruction;
  $('task-stage').textContent=`${scenarioName} · ${o.task_id} / T${taskCount}`;
  $('objectives').replaceChildren();
  (o.objective?.targets||[]).forEach(n=>{const item=document.createElement('li');item.textContent=`${n.recorded?'✓':'○'} ${n.name} ${n.id}`;item.classList.toggle('recorded',n.recorded);$('objectives').append(item);});
  $('camp-status').textContent=o.objective?`提交营地：${o.objective.submission_camps.map(n=>`${n.name} ${n.id}`).join('、')}${o.objective.at_submission_camp?'（已抵达）':''}`:'';
  $('begin').hidden = true; $('play').hidden = o.done; $('ending').hidden = !o.done;
  $('place').textContent = `${o.location.name} ${o.location.id}`;
  $('conditions').textContent = `${{rain:'下雨',clear:'晴朗',snow:'下雪'}[o.conditions.weather]} / ${{night:'夜间',day:'白天'}[o.conditions.period]}`;
  $('time').textContent = `时间 ${o.world_time}`; $('distance').textContent = `路程 ${o.distance}`; $('steps').textContent = `操作 ${o.steps}/${o.max_steps}`;
  $('stamina').textContent = `${o.stamina} / ${o.initial_stamina}`;
  $('energy').max=o.initial_stamina; $('energy').value=o.stamina;
  $('energy').closest('.energy').classList.toggle('low-stamina',o.stamina<=38);
  $('inventory').textContent=o.inventory.map(t=>t.name).join('、') || '尚未携带工具';
  $('stock').replaceChildren();
  if(!o.available_tools.length) {
    const hint=document.createElement('p'); hint.className='muted'; hint.textContent='此处没有可取用的工具。'; $('stock').append(hint);
  }
  o.available_tools.forEach(t=> {
    const b=document.createElement('button'); b.textContent=`取用${t.name}`; b.onclick=()=>act('take',t.id);
    const description=document.createElement('p'); description.className='muted'; description.textContent=t.description;
    $('stock').append(b,description);
  });
  $('routes').replaceChildren();
  o.neighbors.forEach(n=> {
    const b = document.createElement('button');
    const label = document.createElement('span'); label.textContent = `前往${n.name} ${n.target}`;
    const distance = document.createElement('small'); distance.textContent = `距离 ${n.distance}`;
    b.append(label,distance); b.onclick=()=>act('move',n.target); $('routes').append(b);
  });
  $('result').textContent = o.success?'本次测绘已完成':'本次探索已结束';
  $('next').textContent = o.next_task_id?'接下一个委托':'开启新的探索';
  $('empty-log').hidden = true;
  const entry = document.createElement('li'); const time = document.createElement('time');
  time.textContent = `游戏时间 ${o.world_time}`; entry.append(time,document.createTextNode(result.feedback)); $('log').prepend(entry);
  draw(o);
}
async function run(action) {
  if (busy) return;
  busy = true; $('error').textContent = '';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try { await action(); } catch(e) { $('error').textContent=e.message; }
  finally {
    busy=false; document.querySelectorAll('button').forEach(b=>b.disabled=false);
    const submit=document.querySelector('[data-action="submit"]');
    submit.disabled=Boolean(observation?.objective&&!observation.objective.ready);
    submit.textContent=observation?.objective&&!observation.objective.at_submission_camp?'回营地后提交':'提交记录';
  }
}
async function receive(result) {
  if(instance!==result.instance_id || result.observation.success) {
    const response=await fetch('/api/atlas?instance_id='+encodeURIComponent(result.instance_id));
    if(response.status===401)location.assign('/login?next=/play');
    if(!response.ok)throw new Error('无法读取已提交的地图。');
    submittedAtlas=await response.json();
  }
  update(result);
}
function start(task, fresh=false) {
  return run(async()=> {
    const result = await post('/api/start',{task_id:task,scenario,...(!fresh&&instance?{instance_id:instance}:{})});
    $('log').replaceChildren(); await receive(result);
  });
}
function act(type,target) {
  return run(async()=>receive(await post('/api/action',{instance_id:instance,request_id:crypto.randomUUID(),expected_revision:observation.revision,action:{type,...(target?{target}:{})}})));
}
$('begin').onclick=()=>start('T1');
$('fresh').onclick=()=> { if(!observation || observation.done || confirm('放弃当前探索，重新从第一项委托开始？')) start('T1',true); };
$('next').onclick=()=>observation.next_task_id?start(observation.next_task_id):start('T1',true);
$('abandon').onclick=()=>act('abandon');
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>act(b.dataset.action));
$('show-atlas').onchange=()=>{if(observation)draw(observation);};
Cartography.controls($('map'),'play');
Cartography.prepare($('map'),{environment:{id:'lake-easy'}});
async function loadScenario() {
  $('begin').disabled=true;
  try {
    const response=await fetch('/api/tasks');
    if(response.status===401){location.assign('/login?next=/play');return;}
    if(!response.ok)throw new Error('无法读取委托，请刷新页面重试。');
    const data=await response.json();scenario=data.scenario;taskCount=data.tasks.length;
    scenarioName=scenario==='lake-easy'?'雾汀湖 · Easy':(scenario==='valley'?'谷地校准原型':'渡口校准原型');
    $('task-stage').textContent=`${scenarioName} · ${taskCount} 项委托`;
    $('task-name').textContent=data.tasks[0].name;$('instruction').textContent=data.tasks[0].instruction;
    $('sheet-title').textContent=scenario==='lake-easy'?'雾汀湖勘测图':'勘测图';
    Cartography.prepare($('map'),{environment:{id:scenario}});$('begin').disabled=false;
  } catch(e) {$('error').textContent=e.message;}
}
loadScenario();
