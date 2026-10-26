'use strict';
const $ = id => document.getElementById(id);
const ns = 'http://www.w3.org/2000/svg';
const node = (tag, attrs={}, text) => { const e=document.createElementNS(ns,tag); Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v)); if(text!==undefined)e.textContent=text; return e; };
const html = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let state, instance, selected, busy=false, showTrace=false, panel=null, previousFocus=null;
let camera={x:0,y:0,w:1200,h:900}, initialized=false;
const viewport=$('viewport'), map=$('field-map'), pointers=new Map();
let gesture=null;
let restoringFocus=false;
const storageKey='survey-lanting-easy20';
function save(){try{sessionStorage.setItem(storageKey,JSON.stringify({instance,camera}));}catch(_){}}
function uuid(){return crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(16).slice(2)}`;}
async function api(path, body){
  const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
  let response;
  for(let i=0;i<2;i++){
    try{response=await fetch(path,options);break;}catch(error){if(i||!body?.request_id)throw Error('连接中断，请重试读取当前观察。');}
  }
  if(response.status===401){location.href='/login?next=/easy20';throw Error('请先登录。');}
  const data=await response.json();if(!response.ok||data.error)throw Error(data.message||'操作未完成，请读取当前观察。');return data;
}
function setBusy(value){busy=value;viewport.setAttribute('aria-busy',String(value));if(state)renderPlace();}
function feedbackText(data){
  const f=data.feedback,o=data.observation,p=o.environment;
  if(f.kind==='started')return `已领取 ${o.task.id}。点击相邻地点出发，到达目标会自动采集。`;
  if(f.kind==='submitted')return data.stream_finished?'二十项委托已结束，记录已入册。':'交件成功。可以在营地领取下一项委托。';
  if(f.termination==='budget_exhausted')return '操作次数已用尽。本次反馈仍已获得，可以继续下一项委托。';
  if(f.kind==='abandoned')return '本项委托已放弃。已经观察到的信息仍可成为以后的经验。';
  if(f.kind==='station_information')return `${f.station} 支持${p.kinds[f.capability]}。${f.result==='processed'?'本次资料已处理，回营地交件。':f.result==='unsupported'?'本次不匹配，原始资料保留。':'查询已计入一次操作。'}`;
  if(f.kind==='arrived')return f.raw_collected?'已自动采集本次资料。选择处理站，完成后回营交件。':`已到达${p.locations[o.location].name}。`;
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
  const o=state.observation,p=o.environment,t=o.task,places=p.locations;
  $('task-number').textContent=`委托 ${state.task_index} / ${state.task_count}`;
  $('mission-title').textContent=t.name;
  $('mission-instruction').textContent=`到${places[t.target].name}（${t.target}）采集${p.kinds[t.required_kind]}，在支持该资料的站处理，再回营地 C 交件。`;
  $('mission-short').textContent=`${t.target} 采集${p.kinds[t.required_kind]} → 对应站处理 → C 交件`;
  $('steps').textContent=`${o.steps} / ${t.max_steps}`;$('distance').textContent=o.distance;
  $('stage-raw').classList.toggle('done',o.raw);$('stage-process').classList.toggle('done',o.processed);$('stage-submit').classList.toggle('done',o.success);
  $('completion').textContent=`已交件 ${state.completed.filter(t=>t.success).length} / ${state.task_count}`;
  $('rules').replaceChildren(...p.rules.map(r=>html('p',r)));
  $('finished-list').replaceChildren(...state.completed.map(t=>html('div',`${t.success?'✓':'○'} ${t.id} ${t.name}　路程 ${t.distance}`)));
  if(!state.completed.length)$('finished-list').textContent='第一封委托正在路上。';
  $('action-log').replaceChildren(...state.current_actions.map(e=>html('li',eventText(e,p))));
  if(!state.current_actions.length)$('action-log').append(html('li','从手记营地出发。'));
  $('abandon').disabled=busy||o.done;
  if(!initialized){initialized=true;fit();if(viewport.clientWidth<600){const a=places[o.location],b=places[t.target],r=viewport.getBoundingClientRect(),z=.48;setCamera({x:(a.x+b.x)/2-r.width/z/2,y:(a.y+b.y)/2-r.height/z/2,w:r.width/z,h:r.height/z});}}else draw();renderPlace();
}
function eventText(e,p){
  const f=e.delivered.feedback;
  if(e.moved)return `${e.from} → ${e.to}　路程 ${e.movement_cost}${f.raw_collected?'，自动采集':''}`;
  if(f.kind==='station_information')return `${e.from} ${e.action.type==='inspect'?'查询':'处理'}：${p.kinds[f.capability]}${f.result==='processed'?'，处理成功':f.result==='unsupported'?'，不匹配':''}`;
  return f.kind==='submitted'?'回营交件成功':f.kind==='abandoned'?'放弃当前委托':'尝试交件，资料尚未完成';
}
function currentCapability(id){
  return state.current_actions.filter(e=>e.delivered.feedback.kind==='station_information'&&e.delivered.feedback.station===id).at(-1)?.delivered.feedback.capability;
}
function renderPlace(){
  const o=state.observation,p=o.environment,id=selected||o.location,n=p.locations[id],here=id===o.location;
  const names={camp:'营地',station:'处理站',survey:'测绘点',junction:'路口'};
  $('place-type').textContent=here?'当前位置':names[n.kind];$('place-id').textContent=id;$('place-name').textContent=n.name;
  const local=$('local-actions'),near=$('neighbors');local.replaceChildren();near.replaceChildren();
  if(!here){$('place-description').textContent='查看地点。请沿道路逐段前往；点击相邻地点可直接移动。';local.append(button('返回当前位置',()=>{selected=o.location;renderPlace();draw();}));return;}
  if(o.done){
    $('place-description').textContent=o.success?'本项记录已交件。':'本项已结束，已获得的反馈仍然有效。';
    if(!state.stream_finished)local.append(button('领取下一项委托',()=>run(()=>api('/api/field/next',{instance_id:instance,request_id:uuid(),task_run_id:state.task_run_id,expected_revision:o.revision}))));
    else local.append(button('二十项已结束 · 重新探索',newGame));return;
  }
  const capability=currentCapability(id);
  $('place-description').textContent=capability?`本次已确认：支持${p.kinds[capability]}。`:n.kind==='station'?'能力尚未在本次确认。查询和处理各占一次操作。':n.kind==='survey'?(o.raw?'本次资料已采集，前往处理站。':'到达委托目标会自动采集资料。'):n.kind==='camp'?(o.processed?'资料已处理，可以交件。':'处理完资料后回到这里交件。'):'选择一条相邻道路继续前行。';
  if(n.kind==='station'){
    local.append(button('查询能力',()=>action('inspect')));
    local.append(button(o.processed?'再次处理':'处理资料',()=>action('process'),!o.raw));
  }
  if(n.kind==='camp')local.append(button('提交本项记录',()=>action('submit'),!o.raw||!o.processed));
  const routes=p.edges.filter(([a,b])=>a===id||b===id);
  for(const [a,b,w] of routes){const to=a===id?b:a;near.append(button(`去 ${to}　路程 ${w}`,()=>action('move',to)));}
}
function roadPath(a,b){const p=state.observation.environment.locations[a],q=state.observation.environment.locations[b];return `M${p.x} ${p.y}Q${(p.x+q.x)/2+8} ${(p.y+q.y)/2-8} ${q.x} ${q.y}`;}
function scale(){return viewport.getBoundingClientRect().width/camera.w;}
function draw(){
  if(!state)return;const focusedNode=document.activeElement?.closest?.('[data-node]')?.dataset.node;map.setAttribute('viewBox',`${camera.x} ${camera.y} ${camera.w} ${camera.h}`);
  const o=state.observation,p=o.environment,z=scale(),inv=1/z;
  $('roads').replaceChildren();$('places').replaceChildren();$('trace').replaceChildren();$('region-labels').replaceChildren();
  for(const r of state.presentation.regions||[])$('region-labels').append(node('text',{x:r.x,y:r.y,class:'region-label'},r.name));
  for(const [a,b,w] of p.edges){
    const d=roadPath(a,b);$('roads').append(node('path',{d,class:'road-back'}),node('path',{d,class:`road${a===o.location||b===o.location?' road-near':''}`}));
    if(a===o.location||b===o.location){const x=(p.locations[a].x+p.locations[b].x)/2,y=(p.locations[a].y+p.locations[b].y)/2;
      const g=node('g',{transform:`translate(${x} ${y}) scale(${inv})`});g.append(node('text',{x:6,y:-7,class:'road-label'},w));$('roads').append(g);}
  }
  if(showTrace)for(const edge of state.trace.edges){$('trace').append(node('path',{d:roadPath(edge.source,edge.target),class:'trace-line'}));}
  const neighbors=new Set(o.available_actions.filter(a=>a.type==='move').map(a=>a.target));
  for(const [id,n] of Object.entries(p.locations)){
    const here=id===o.location,adj=neighbors.has(id),goal=id===o.task.target;
    const g=node('g',{transform:`translate(${n.x} ${n.y})`,class:`place-node ${here?'current':adj?'neighbor':'distant'}${id===selected?' selected':''}`,role:'button',tabindex:'0','data-node':id,'aria-label':`${id} ${n.name}${here?'，当前位置':adj?'，可直接前往':'，查看地点'}`});
    g.append(node('title',{},`${n.name} ${id}`));const marker=node('g',{transform:`scale(${inv})`});
    marker.append(node('circle',{r:24,class:'node-hit'}),node('circle',{r:21,class:'selection-ring'}));
    marker.append(n.kind==='station'?node('rect',{x:-13,y:-13,width:26,height:26,rx:3,class:'node-mark'}):node('circle',{r:n.kind==='junction'?10:15,class:'node-mark'}));
    const icon=n.kind==='camp'?'M-10 7 0-9 10 7Z M0-4V7':n.kind==='station'?'M-6 6V-6H6V6Z M-6 0H6':n.kind==='survey'?'M-5 1 0-6 5 1 0 8Z':'';
    if(icon)marker.append(node('path',{d:icon,class:'node-symbol'}));
    marker.append(node('text',{x:0,y:n.kind==='junction'?-18:-22,class:'node-id'},id));
    if(z>.58||here||id===selected)marker.append(node('text',{x:0,y:33,class:'node-name'},n.name));
    if(goal&&!o.raw)marker.append(node('path',{d:'M19-28 27-19 19-10 11-19Z',class:'goal-flag'}));
    if(here)marker.append(node('circle',{cx:18,cy:14,r:5,class:'current-dot'}));
    g.append(marker);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate(id);}});
    g.addEventListener('click',e=>{if(e.detail===0)activate(id);});
    g.addEventListener('focus',()=>{if(restoringFocus)return;const r=g.getBoundingClientRect(),v=viewport.getBoundingClientRect();if(r.left<v.left||r.right>v.right||r.top<v.top||r.bottom>v.bottom)center(n.x,n.y);});
    $('places').append(g);
  }
  if(focusedNode&&!panel){restoringFocus=true;[...$('places').children].find(e=>e.dataset.node===focusedNode)?.focus({preventScroll:true});restoringFocus=false;}
}
function activate(id){
  if(busy||panel)return;selected=id;
  if(state.observation.available_actions.some(a=>a.type==='move'&&a.target===id))action('move',id);
  else{renderPlace();draw();}
}
function setCamera(value){camera=value;const cx=Math.max(-80,Math.min(1280,camera.x+camera.w/2)),cy=Math.max(-80,Math.min(980,camera.y+camera.h/2));camera.x=cx-camera.w/2;camera.y=cy-camera.h/2;draw();save();}
function fit(){const r=viewport.getBoundingClientRect();if(!r.width||!r.height)return;const z=Math.min(r.width/1340,r.height/1020);camera={x:600-r.width/z/2,y:450-r.height/z/2,w:r.width/z,h:r.height/z};draw();save();}
function center(x,y){setCamera({...camera,x:x-camera.w/2,y:y-camera.h/2});}
function worldPoint(x,y){const m=map.getScreenCTM();return new DOMPoint(x,y).matrixTransform(m.inverse());}
function zoom(factor,x,y){const r=viewport.getBoundingClientRect(),old=scale(),min=Math.min(r.width/1340,r.height/1020)*.7;
  const next=Math.min(2.5,Math.max(min,old*factor)),point=worldPoint(x,y),w=r.width/next,h=r.height/next;
  setCamera({x:point.x-(point.x-camera.x)*w/camera.w,y:point.y-(point.y-camera.y)*h/camera.h,w,h});}
function gestureStart(){const points=[...pointers.values()];gesture={camera:{...camera},points:points.map(p=>({...p})),moved:points.length>1,node:points[0]?.node};}
viewport.addEventListener('pointerdown',e=>{
  if(panel||e.button>0)return;viewport.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,node:e.target.closest('[data-node]')?.dataset.node});gestureStart();
});
viewport.addEventListener('pointermove',e=>{
  if(!pointers.has(e.pointerId)||!gesture)return;pointers.set(e.pointerId,{...pointers.get(e.pointerId),x:e.clientX,y:e.clientY});const points=[...pointers.values()];
  if(points.length===1){const dx=points[0].x-gesture.points[0].x,dy=points[0].y-gesture.points[0].y;if(Math.hypot(dx,dy)<6&&!gesture.moved)return;gesture.moved=true;viewport.classList.add('dragging');const z=viewport.getBoundingClientRect().width/gesture.camera.w;setCamera({...gesture.camera,x:gesture.camera.x-dx/z,y:gesture.camera.y-dy/z});}
  else if(points.length===2&&gesture.points.length===2){const [a,b]=points,[a0,b0]=gesture.points,r=viewport.getBoundingClientRect();const ratio=Math.hypot(a.x-b.x,a.y-b.y)/Math.max(1,Math.hypot(a0.x-b0.x,a0.y-b0.y));const initial=gesture.camera,w0=initial.w;const min=Math.min(r.width/1340,r.height/1020)*.7,z=Math.min(2.5,Math.max(min,r.width/w0*ratio));const anchor={x:initial.x+((a0.x+b0.x)/2-r.left)*initial.w/r.width,y:initial.y+((a0.y+b0.y)/2-r.top)*initial.h/r.height};setCamera({x:anchor.x-((a.x+b.x)/2-r.left)/z,y:anchor.y-((a.y+b.y)/2-r.top)/z,w:r.width/z,h:r.height/z});gesture.moved=true;}
});
function pointerEnd(e,cancel=false){
  if(!pointers.has(e.pointerId))return;const click=!cancel&&pointers.size===1&&!gesture?.moved,target=gesture?.node;
  pointers.delete(e.pointerId);viewport.classList.remove('dragging');if(pointers.size){gestureStart();gesture.moved=true;}else gesture=null;
  if(click&&target)activate(target);
}
viewport.addEventListener('pointerup',e=>pointerEnd(e));viewport.addEventListener('pointercancel',e=>pointerEnd(e,true));viewport.addEventListener('lostpointercapture',e=>pointerEnd(e,true));
viewport.addEventListener('wheel',e=>{if(panel)return;e.preventDefault();zoom(Math.exp(-e.deltaY*.0015),e.clientX,e.clientY);},{passive:false});
function openPanel(id){previousFocus=document.activeElement;if(panel)$(panel).hidden=true;panel=id;$(id).hidden=false;viewport.inert=true;$('journal-open').setAttribute('aria-expanded',String(id==='journal'));$(id).querySelector('button')?.focus();}
function closePanel(){if(panel)$(panel).hidden=true;if(panel==='design')for(const id of ['design-map','design-groups','design-tasks'])$(id).replaceChildren();panel=null;viewport.inert=false;$('journal-open').setAttribute('aria-expanded','false');if(previousFocus?.getClientRects().length)previousFocus.focus();else $('journal-open').focus();}
async function showDesign(){
  if(busy)return;try{const data=await api(`/api/field/design?instance_id=${encodeURIComponent(instance)}`);renderDesign(data);openPanel('design');}catch(e){$('error-text').textContent=e.message;$('error').hidden=false;}
}
function renderDesign(data){
  const p=state.observation.environment;const svg=$('design-map');svg.replaceChildren(node('image',{href:'/field-terrain.svg',width:1200,height:900}));
  for(const [a,b] of p.edges)svg.append(node('path',{d:roadPath(a,b),class:'road'}));
  for(const [id,n] of Object.entries(p.locations)){svg.append(node('circle',{cx:n.x,cy:n.y,r:15,fill:'#f4f1dc',stroke:'#3a5b48','stroke-width':2}),node('text',{x:n.x,y:n.y+5,'text-anchor':'middle','font-size':17,fill:'#294637'},id));
    if(data.capabilities[id])svg.append(node('text',{x:n.x,y:n.y+36,'text-anchor':'middle','font-size':19,fill:'#725020'},p.kinds[data.capabilities[id]]));}
  $('design-groups').replaceChildren();for(const group of Object.values(p.capability_groups)){const box=html('section',undefined,'design-group');box.append(html('h3',group.name));for(const s of group.stations)box.append(html('p',`${s} → ${p.kinds[data.capabilities[s]]}`));$('design-groups').append(box);}
  $('design-tasks').replaceChildren();for(const task of data.tasks){const tr=html('tr');for(const value of [`${task.id} ${task.name}`,`${task.target} ${p.kinds[task.required_kind]}`,task.group,task.intervening_tasks_since_same_group??'首次',`${task.known_world_route.join(' → ')}　路程 ${task.known_world_distance}`])tr.append(html('td',value));$('design-tasks').append(tr);}
}
async function newGame(){closePanel();await run(()=>api('/api/field/start',{}));}
$('journal-open').onclick=()=>openPanel('journal');$('journal-close').onclick=closePanel;$('design-close').onclick=closePanel;$('design-open').onclick=showDesign;
$('trace-toggle').onclick=()=>{showTrace=!showTrace;$('trace-toggle').setAttribute('aria-pressed',String(showTrace));$('trace-toggle').textContent=showTrace?'隐藏本次轨迹':'显示本次轨迹';draw();};
$('restart').onclick=newGame;$('error-new').onclick=newGame;$('retry').onclick=()=>run(()=>api(`/api/field/observation?instance_id=${encodeURIComponent(instance)}`));
$('abandon').onclick=async()=>{closePanel();await action('abandon');};
$('fit').onclick=fit;$('locate').onclick=()=>{if(state){const n=state.observation.environment.locations[state.observation.location];selected=state.observation.location;center(n.x,n.y);renderPlace();}};
for(const [id,factor] of [['zoom-in',1.25],['zoom-out',.8]])$(id).onclick=()=>{const r=viewport.getBoundingClientRect();zoom(factor,r.left+r.width/2,r.top+r.height/2);};
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){closePanel();return;}
  if(panel&&e.key==='Tab'){const items=[...$(panel).querySelectorAll('button,a,summary')].filter(el=>!el.disabled&&!el.hidden),first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}return;}
  if(panel||e.ctrlKey||e.metaKey||e.altKey)return;if(e.key.toLowerCase()==='f')$('locate').click();if(e.key==='Home'){e.preventDefault();fit();}if(e.key==='+'||e.key==='=')$('zoom-in').click();if(e.key==='-')$('zoom-out').click();
});
let resizeFrame;new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(initialized){const r=viewport.getBoundingClientRect(),cx=camera.x+camera.w/2,cy=camera.y+camera.h/2;camera.h=camera.w*r.height/r.width;camera.y=cy-camera.h/2;camera.x=cx-camera.w/2;draw();}});}).observe(viewport);
(async()=>{try{const old=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(old?.instance){instance=old.instance;const result=await api(`/api/field/observation?instance_id=${encodeURIComponent(instance)}`);apply(result);if(old.camera&&Object.values(old.camera).every(Number.isFinite))setCamera(old.camera);}else await newGame();}catch(e){$('error-text').textContent=e.message;$('error').hidden=false;}})();
