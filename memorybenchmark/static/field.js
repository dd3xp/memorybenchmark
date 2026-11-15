'use strict';
const $ = id => document.getElementById(id);
const ns = 'http://www.w3.org/2000/svg';
const node = (tag, attrs={}, text) => { const e=document.createElementNS(ns,tag); Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v)); if(text!==undefined)e.textContent=text; return e; };
const html = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let state, instance, selected, busy=false, showTrace=false, panel=null, previousFocus=null, designView=null;
let camera={x:0,y:0,w:1200,h:900}, initialized=false;
const viewport=$('viewport'), map=$('field-map'), fieldView=new WorldAtlasView(map);
let gesture=null;
let restoringFocus=false;
const mapId=new URLSearchParams(location.search).get('map')||'capulin-easy';
const storageKey='survey-play-'+mapId;
document.querySelector('.identity h1').textContent='准备地图';$('place-name').textContent='营地';
function visualEnvironment(){return state?.presentation?.geographic_map?{...state.observation.environment,...state.presentation.geographic_map}:state?.observation.environment;}
function save(){if(!instance)return;try{sessionStorage.setItem(storageKey,JSON.stringify({instance,camera:{projection:'world-atlas-1',box:fieldView.box}}));}catch(_){}}
function uuid(){return crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(16).slice(2)}`;}
function vocabulary(p){return {survey:'测绘点',station:'处理站',collect:'采集',process:'处理',item:'资料',submit:'交件',...p.vocabulary};}
function capabilityLabel(p,value){if(value&&typeof value==='object'&&!Array.isArray(value))return Object.entries(value).map(([r,k])=>`${p.requirements?.[r]||r}：${capabilityLabel(p,k)}`).join('；');return (Array.isArray(value)?value:[value]).map(k=>p.kinds[k]||k).join('、');}
function requirementLabel(p,stage){return (stage.requirement?` · ${p.requirements[stage.requirement]}`:'')+(stage.required_region?` · 在${p.processing_regions[stage.required_region]}处理`:'');}
function terrainHref(p){return p.terrain_asset||{'long-lake-normal':'/long-lake-normal-terrain.svg','forest-valley':'/forest-valley-terrain.svg','cascade-lakes':'/cascade-lakes-terrain.svg','volcanic-cone':'/volcanic-cone-terrain.svg','fjord-peninsulas':'/fjord-peninsulas-terrain.svg','steppe-corridors':'/steppe-corridors-terrain.svg','andean-passes':'/andean-passes-terrain.svg','sand-coast':'/sand-coast-terrain.svg','boar-woodland':'/boar-woodland-terrain.svg','hill-country':'/hill-country-terrain.svg','rock-river':'/rock-river-terrain.svg','reservoir-plain':'/reservoir-plain-terrain.svg'}[p.terrain]||'/volcanic-cone-terrain.svg';}
async function api(path, body){
  path+=(path.includes('?')?'&':'?')+'map='+encodeURIComponent(mapId);
  const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  let response;
  for(let i=0;i<2;i++){
    try{response=await fetch(path,options);break;}catch(error){if(i||!body?.request_id)throw Error('连接中断，请重试读取当前观察。');}
  }
  if(response.status===401){location.href='/login?next=/play';throw Error('请先登录。');}
  const data=await response.json();if(!response.ok||data.error)throw Error(data.message||'操作未完成，请读取当前观察。');return data;
}
function setBusy(value){busy=value;setAppLoading('play-loading',value);viewport.setAttribute('aria-busy',String(value));if(state){$('abandon').disabled=value||state.observation.done;renderPlace();}}
function feedbackText(data){
  const f=data.feedback,o=data.observation,p=o.environment,v=vocabulary(p);
  if(f.kind==='started')return `已领取 ${o.task.id}`;
  if(f.kind==='submitted')return data.stream_finished?'全部委托已完成。':v.submit+'成功';
  if(f.termination==='budget_exhausted')return '操作次数已用尽';
  if(f.kind==='abandoned')return '已放弃委托';
  if(f.kind==='wrong_processing_region')return `该站位于${p.processing_regions[f.station_region]}，本段要求在${p.processing_regions[f.required_region]}处理。本次未处理，原始${v.item}保留，未揭示站型能力。`;
  if(f.kind==='station_information')return `${f.station}${f.station_type?`（${f.station_type} 型）`:''}${requirementLabel(p,f)} 支持${capabilityLabel(p,f.capability)}。${f.next_stage?`第 ${f.stage_completed} 段完成，现在前往 ${o.task.target} 完成第 ${f.next_stage} 段。`:f.result==='processed'?`本段已${v.process}，回营地${v.submit}。`:f.result==='unsupported'?`本次不匹配，原始${v.item}保留。`:'查询已计入一次操作。'}`;
  if(f.kind==='surveyed')return `勘探完成，已采集${p.kinds[f.required_kind]}。`;
  if(f.kind==='arrived'&&p.manual_survey_required&&o.location===o.task.target&&!o.raw)return '已到达目标，请勘探采集资料。';
  if(f.kind==='arrived')return f.raw_collected?`已记录本段${v.item}，请选择匹配的${v.station}。`:`已到达${p.locations[o.location].name}。`;
  return o.done?'本项委托已结束。':'当前观察已更新。';
}
function apply(data){
  if(state?.instance_id===data.instance_id&&data.task_index<state.task_index)return;
  const fresh=state?.task_run_id!==data.task_run_id;
  if(!fresh&&state&&data.observation.revision<state.observation.revision)return;
  state=data;instance=data.instance_id;selected=data.observation.location;
  $('error').hidden=true;$('feedback').textContent=feedbackText(data);render();save();
}
async function run(fn){if(busy)return;setBusy(true);try{apply(await fn());}catch(error){$('error-text').textContent=error.message;$('error').hidden=false;}finally{setBusy(false);}}
async function action(type,target){
  if(!state||state.observation.done)return;
  const body={instance_id:instance,task_run_id:state.task_run_id,request_id:uuid(),expected_revision:state.observation.revision,action:{type,...(target?{target}:{})}};
  await run(()=>api('/api/field/action',body));
}
function button(text,fn,disabled=false){const b=html('button',text);b.disabled=disabled||busy;b.addEventListener('click',fn);return b;}
function render(){
  const o=state.observation,p=visualEnvironment(),t=o.task,places=p.locations,v=vocabulary(p);
  const displayName=state.display_name||p.name;
  document.querySelector('.identity h1').textContent=displayName.split(' · ')[0];
  document.title=displayName+' · 测绘手记';document.body.dataset.theme=p.terrain||'field';$('difficulty-label').textContent=p.difficulty||'Easy';
  $('task-number').textContent=`委托 ${state.task_index} / ${state.task_count}${t.stages?` · ${o.stages_completed===o.stage_count?'两段已完成':`行程 ${o.stage_index+1}/${o.stage_count}`}`:''}`;
  $('mission-title').textContent=t.name;
  $('mission-instruction').textContent=`${t.stages?`第 ${Math.min(o.stage_index+1,o.stage_count)}/${o.stage_count} 段　`:''}${places[t.target].name}（${t.target}）${v.collect}${p.kinds[t.required_kind]}${requirementLabel(p,t)} → 匹配站${v.process}${t.stages&&o.stage_index+1<o.stage_count?'':` → ${t.submit_at} ${v.submit}`}`;
  $('mission-short').textContent=t.stages?t.stages.map((s,i)=>`${i<o.stages_completed?'✓':`${i+1}.`} ${s.target}·${p.kinds[s.required_kind]}${requirementLabel(p,s)}`).join(' → ')+` → ${t.submit_at} ${v.submit}`:`${t.target} ${v.collect}${p.kinds[t.required_kind]} → 对应站${v.process} → ${t.submit_at} ${v.submit}`;
  $('stage-raw').textContent=t.stages?`第 ${o.stage_index+1} 段${v.collect}`:v.collect+v.item;$('stage-process').textContent=t.stages?`第 ${o.stage_index+1} 段${v.process}`:'到站'+v.process;$('stage-submit').textContent=v.submit;
  $('steps').textContent=`${o.steps} / ${t.max_steps}`;$('distance').textContent=o.distance;
  $('stage-raw').classList.toggle('done',o.raw);$('stage-process').classList.toggle('done',o.processed);$('stage-submit').classList.toggle('done',o.success);
  $('completion').textContent=`已${v.submit} ${state.completed.filter(t=>t.success).length} / ${state.task_count}`;
  $('rules').replaceChildren(...p.rules.map(r=>html('p',r)));
  $('finished-list').replaceChildren(...state.completed.map(t=>html('div',`${t.success?'✓':'○'} ${t.id} ${t.name}　路程 ${t.distance}`)));
  if(!state.completed.length)$('finished-list').textContent='暂无记录';
  $('action-log').replaceChildren(...state.current_actions.map(e=>html('li',eventText(e,p))));
  if(!state.current_actions.length)$('action-log').append(html('li',`从${places[t.start].name}出发。`));
  $('abandon').disabled=busy||o.done;
  initialized=true;draw();renderPlace();
}
function eventText(e,p){
  const f=e.delivered.feedback,v=vocabulary(p);
  if(e.moved)return `${e.from} → ${e.to}　路程 ${e.movement_cost}${f.raw_collected?`，记录${v.item}`:''}`;
  if(f.kind==='surveyed')return `${e.from} 勘探：已采集${p.kinds[f.required_kind]}`;
  if(f.kind==='wrong_processing_region')return `${e.from} 处理失败：所在${p.processing_regions[f.station_region]}，本段要求${p.processing_regions[f.required_region]}`;
  if(f.kind==='station_information')return `${e.from} ${e.action.type==='inspect'?'查询':v.process}${requirementLabel(p,f)}：${capabilityLabel(p,f.capability)}${f.result==='processed'?`，${v.process}成功`:f.result==='unsupported'?'，不匹配':''}${f.next_stage?`，进入第 ${f.next_stage} 段`:''}`;
  return f.kind==='submitted'?`回营${v.submit}成功`:f.kind==='abandoned'?'放弃当前委托':`尝试${v.submit}，资料尚未完成`;
}
function currentCapability(id){
  const type=visualEnvironment().locations[id]?.station_type,requirement=state.observation.task.requirement;
  return state.current_actions.filter(e=>e.delivered.feedback.kind==='station_information'&&e.delivered.feedback.requirement===requirement&&(e.delivered.feedback.station===id||(type&&e.delivered.feedback.station_type===type))).at(-1)?.delivered.feedback.capability;
}
function renderPlace(){
  const o=state.observation,p=visualEnvironment(),id=selected||o.location,n=p.locations[id],here=id===o.location,v=vocabulary(p);
  const names={camp:'营地',station:v.station,survey:v.survey,junction:'路口'};
  $('place-type').textContent=n.station_type?`${n.station_type} 型${v.station}${here?' · 当前位置':''}`:here?'当前位置':names[n.kind];$('place-id').textContent=id;$('place-name').textContent=n.name;
  const local=$('local-actions'),near=$('neighbors');local.replaceChildren();near.replaceChildren();
  if(!here){$('place-description').textContent='未抵达';local.append(button('返回当前位置',()=>{selected=o.location;renderPlace();draw();}));return;}
  if(o.done){
    $('place-description').textContent=o.success?`本项记录已${v.submit}。`:'委托已结束';
    if(!state.stream_finished)local.append(button('领取下一项委托',()=>run(()=>api('/api/field/next',{instance_id:instance,request_id:uuid(),task_run_id:state.task_run_id,expected_revision:o.revision}))));
    else local.append(button('重新探索',newGame));return;
  }
  const capability=currentCapability(id);
  $('place-description').textContent=capability?`支持${capabilityLabel(p,capability)}`:n.kind==='station'?'能力未确认':n.kind==='survey'?(p.manual_survey_required?(id!==o.task.target?'非当前勘探目标':o.raw?'已采集本段'+v.item:'待勘探'):(o.raw?'已记录'+v.item:'到达目标自动记录')):n.kind==='camp'?(o.processed?'可以'+v.submit:'营地'):'';
  if(n.region_category)$('place-description').textContent=`${p.processing_regions[n.region_category]} · `+$('place-description').textContent;
  if(n.kind==='survey'&&p.manual_survey_required)local.append(button(o.raw&&id===o.task.target?'已勘探':'勘探',()=>action('survey'),!o.available_actions.some(a=>a.type==='survey')));
  if(n.kind==='station'){
    if(o.available_actions.some(a=>a.type==='inspect'))local.append(button('查询',()=>action('inspect')));
    local.append(button(v.process,()=>action('process'),!o.available_actions.some(a=>a.type==='process')));
  }
  if(n.kind==='camp')local.append(button(v.submit,()=>action('submit'),!o.raw||!o.processed));
  const routes=p.edges.filter(([a,b])=>a===id||b===id);
  for(const [a,b,w] of routes){const to=a===id?b:a;near.append(button(`去 ${to}　路程 ${w}`,()=>action('move',to)));}
}
function roadPath(a,b){const env=visualEnvironment(),p=env.locations[a],q=env.locations[b],points=env.edge_paths?.[[a,b].sort().join('|')];if(points)return 'M'+points.map(v=>v.join(' ')).join('L');return env.processing_regions?`M${p.x} ${p.y}L${q.x} ${q.y}`:`M${p.x} ${p.y}Q${(p.x+q.x)/2+8} ${(p.y+q.y)/2-8} ${q.x} ${q.y}`;}
function draw(){
  if(!state)return;
  const o=state.observation;
  const frames=[{location:o.task.start},...state.current_actions.map(e=>({location:e.to||e.from,action:e.action}))];
  fieldView.setRegion(mapId,visualEnvironment(),{location:o.location,target:o.task.target,selected,
    neighbors:o.available_actions.filter(a=>a.type==='move').map(a=>a.target),
    layers:{terrain:true,roads:true,stations:true,labels:true,trace:showTrace},frames,
    onSelect:activate,onCameraChange:save});
}
function activate(id){
  if(busy||panel)return;selected=id;
  if(state.observation.available_actions.some(a=>a.type==='move'&&a.target===id))action('move',id);
  else{renderPlace();draw();}
}
function worldBounds(){return visualEnvironment()?.view_box||[0,0,1200,900];}
function fit(){fieldView.fit();save();}
function zoom(factor,x,y){fieldView.zoom(factor,x,y);}
function openPanel(id){if(!panel)previousFocus=document.activeElement;if(panel)$(panel).hidden=true;panel=id;$(id).hidden=false;viewport.inert=true;document.querySelector('.field-sidebar').inert=true;document.querySelector('.appbar').inert=true;$('journal-open').setAttribute('aria-expanded',String(id==='journal'));$(id).querySelector('button')?.focus();}
function closePanel(){if(panel)$(panel).hidden=true;if(panel==='design')for(const id of ['design-groups','design-tasks','design-experience','design-version'])$(id).replaceChildren();panel=null;viewport.inert=false;document.querySelector('.field-sidebar').inert=false;document.querySelector('.appbar').inert=false;$('journal-open').setAttribute('aria-expanded','false');if(previousFocus?.getClientRects().length)previousFocus.focus();else $('journal-open').focus();}
async function showDesign(){
  if(busy)return; openPanel('design'); setAppLoading('design-loading',true);
  try{const data=await api(`/api/field/design?instance_id=${encodeURIComponent(instance)}`); if(panel==='design')renderDesign(data);}
  catch(e){if(panel==='design')closePanel();$('error-text').textContent=e.message;$('error').hidden=false;}
  finally{setAppLoading('design-loading',false);}
}
function renderDesign(data){
  const p=visualEnvironment(),b=worldBounds(),activeRequirement=state.observation.task.requirement;
  $('design-version').textContent=`地图版本：${data.design_id}${activeRequirement?` · 图上能力按“${p.requirements[activeRequirement]}”显示`:''}`;
  if(!designView)designView=new WorldAtlasView($('design-map'));
  const nodeNotes=Object.fromEntries(Object.entries(data.capabilities).map(([id,cap])=>[id,capabilityLabel(p,activeRequirement?cap[activeRequirement]:cap)]));
  designView.setRegion(mapId,p,{location:state.observation.location,target:state.observation.task.target,nodeNotes,layers:{terrain:true,roads:true,stations:true,labels:true},onSelect:id=>{designView.options.selected=id;designView.paint();}});
  designView.fit();
  $('design-groups').replaceChildren();for(const group of Object.values(p.station_types||p.capability_groups)){const box=html('section',undefined,'design-group');box.append(html('h3',group.name));for(const s of group.stations)box.append(html('p',`${s} → ${capabilityLabel(p,data.capabilities[s])}`));$('design-groups').append(box);}
  $('design-experience').replaceChildren();for(const s of data.experience_opportunities?.stages||[]){const box=html('section',undefined,'design-group');const sources=s.direct_matching_feedback.map(f=>`${f.task_id} 第${f.stage_index+1}段 ${f.station}${f.station_type?` / ${f.station_type}型`:''}（${f.operation}${f.result==='processed'?' 成功':f.result==='unsupported'?' 不匹配':''}）`);box.append(html('h3',`第${s.stage_index+1}段 · ${p.kinds[s.required_kind]}`),html('p',sources.length?`此前实际反馈：${sources.join('；')}`:'此前没有直接交付过匹配站能力。'),html('p',s.matching_stations_known_from_type?.length?`同型站均适用：${s.matching_stations_known_from_type.join('、')}`:'尚无已观测匹配站型。'),html('p',s.matching_stations_known_only_by_inference.length?`可由一一对应规则推断：${s.matching_stations_known_only_by_inference.join('、')}`:'无额外推断匹配站。'),html('p',s.first_branch_choice?`本次首次支路选择：${s.first_branch_choice.station}${s.first_branch_choice.new_station_of_previously_observed_type?'（此前未到过的同型站）':''}；这不单独证明使用记忆。`:'本段尚无选站记录。'));$('design-experience').append(box);}
  $('design-tasks').replaceChildren();for(const task of data.tasks){const tr=html('tr'),stages=task.stage_options;
    const requirements=stages?stages.map((s,i)=>`${i+1}. ${s.target} ${p.kinds[s.required_kind]}${requirementLabel(p,s)}`).join('；'):`${task.target} ${p.kinds[task.required_kind]}`;
    const groups=stages?stages.map(s=>s.group).join(' → '):task.group;
    const deps=task.experience_dependencies?.stages;
    const inheritance=deps?deps.map((s,i)=>`第${i+1}段：${s.earlier_same_kind_stages.length?s.earlier_same_kind_stages.map(r=>`${r.task_id}.${r.stage_index+1}`).join('、')+' 任一成功处理后可用':'首次需求；也可能用到此前探索反馈'}`).join('；'):'—';
    const gaps=deps?deps.map((s,i)=>`第${i+1}段：${s.intervening_tasks_since_same_kind_requirement??'首次'}`).join('；'):'—';
    const options=stages?stages.map((s,i)=>`第${i+1}段：`+s.options.map(c=>`${c.station} ${c.matches?'匹配':'不匹配'}，至下一目标/营地 ${c.completion_distance}`).join('；')).join(' / '):(task.station_options||[]).map(s=>`${s.station}：${s.matches?'匹配':'不匹配'}，总路程 ${s.completion_distance}`).join('；');
    for(const value of [`${task.id} ${task.name}`,requirements,groups,inheritance,gaps,options,`${task.known_world_route.join(' → ')}　路程 ${task.known_world_distance}`])tr.append(html('td',value));$('design-tasks').append(tr);}
}
async function newGame(){closePanel();await run(()=>api('/api/field/start',{}));}
$('journal-open').onclick=()=>openPanel('journal');$('journal-close').onclick=closePanel;$('design-close').onclick=closePanel;$('design-open').onclick=showDesign;
for(const[id,factor]of [['design-zoom-in',1.25],['design-zoom-out',.8]])$(id).onclick=()=>designView?.zoom(factor);
$('design-fit').onclick=()=>designView?.fit();$('design-world').onclick=()=>designView?.showWorld();
$('trace-toggle').onclick=()=>{showTrace=!showTrace;$('trace-toggle').setAttribute('aria-pressed',String(showTrace));$('trace-toggle').textContent=showTrace?'隐藏本次轨迹':'显示本次轨迹';draw();};
$('restart').onclick=newGame;$('error-new').onclick=newGame;$('retry').onclick=()=>state ? run(()=>api(`/api/field/observation?instance_id=${encodeURIComponent(instance)}`)) : location.reload();
$('abandon').onclick=async()=>{closePanel();await action('abandon');};
$('fit').onclick=fit;$('world-extent').onclick=()=>fieldView.showWorld();$('locate').onclick=()=>{if(state){selected=state.observation.location;fieldView.locate(selected);renderPlace();}};
for(const [id,factor] of [['zoom-in',1.25],['zoom-out',.8]])$(id).onclick=()=>{const r=viewport.getBoundingClientRect();zoom(factor,r.left+r.width/2,r.top+r.height/2);};
document.addEventListener('keydown',e=>{
  if(e.defaultPrevented)return;
  if(e.key==='Escape'){closePanel();return;}
  if(panel&&e.key==='Tab'){const items=[...$(panel).querySelectorAll('button,a,summary')].filter(el=>!el.disabled&&!el.hidden),first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}return;}
  if(panel||e.ctrlKey||e.metaKey||e.altKey||e.target.closest('input,select,textarea'))return;if(e.key.toLowerCase()==='f')$('locate').click();if(e.key==='Home'){e.preventDefault();fit();}if(e.key==='+'||e.key==='=')$('zoom-in').click();if(e.key==='-')$('zoom-out').click();
});
(async()=>{try{await WorldCartography.ready;const old=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(old?.instance){instance=old.instance;const result=await api(`/api/field/observation?instance_id=${encodeURIComponent(instance)}`);apply(result);if(old.camera?.projection==='world-atlas-1'&&old.camera.box?.length===4&&old.camera.box.every(Number.isFinite)){fieldView.box=old.camera.box;fieldView.overview=false;fieldView.paint();}}else await newGame();if(new URLSearchParams(location.search).get('inspect')==='1')await showDesign();}catch(e){$('error-text').textContent=e.message;$('error').hidden=false;}finally{setAppLoading('play-loading',false);}})();
