const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
let design=null, selectedTask='', selectedTrigger='', loading=0;
function svgNode(type,attrs={},text){const n=document.createElementNS(NS,type);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function element(type,text,cls){const n=document.createElement(type);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function places(){return Object.fromEntries(design.map.nodes.map(n=>[n.id,n]));}
function placeName(id){const n=places()[id];return n?`${n.name} ${id}`:id;}
function task(){return design.tasks.find(t=>t.id===selectedTask);}
function relevantTriggers(){return design.triggers.filter(t=>!selectedTask||!task().reference||t.kind==='passage'||t.opportunities.some(o=>o.task_id===selectedTask));}
function conditionText(conditions){const names={rain:'下雨',clear:'晴朗',snow:'下雪',night:'夜间',day:'白天'};return Object.values(conditions).map(v=>names[v]||v).join('、')||'每次进入时';}
function selectTask(id){selectedTask=id;selectedTrigger='';$('task-select').value=id;render();}
function focusTrigger(id){selectedTrigger=id;$('show-triggers').checked=true;render();}
function renderTasks(){
 const t=task();$('task-heading').textContent=t?`${t.id} ${t.name}`:'全部委托';
 $('task-description').textContent=t?t.instruction:`${design.tasks.length} 项委托。选择一项，可以查看出发点、测绘目标和相关经验。`;
 $('task-facts').replaceChildren();
 if(design.recovery_policy)$('task-facts').append(element('p',`死亡后回本项出发营地复活，清空携带工具；每次复活边权 ${design.recovery_policy.weight}。测绘进度保留，总操作预算不重置。`,'task-fact'));
 if(t){
  const facts=[`出发：${placeName(t.start)}`,`目标：${t.goals.map(placeName).join('、')}`,`提交：${t.submit_at.length?t.submit_at.map(placeName).join('、'):'该原型允许原地提交'}`];
  if(t.reference)facts.push(`无复活参考：${t.reference.distance} 距离，${t.reference.effort} 体力需求，${Object.values(t.reference.encounters).reduce((a,b)=>a+b,0)} 次遇险。`);
  facts.forEach(text=>$('task-facts').append(element('p',text,'task-fact')));
 }
 $('task-list').replaceChildren();
 design.tasks.forEach(t=>{const b=element('button',`${t.id} ${t.name}`);b.setAttribute('aria-pressed',String(t.id===selectedTask));b.onclick=()=>selectTask(t.id);$('task-list').append(b);});
 $('show-reference').disabled=!t?.reference;
 if(!t?.reference)$('show-reference').checked=false;
 $('map-note').textContent=design.reference_scope==='unavailable_dynamic_conditions'?'此图含动态通行条件，不生成静态最优路线；条件触发位置按规则标注。':($('show-reference').checked?'虚线是全知条件下的一条可行参考路线，不是 Agent 轨迹，也不作为记忆复用的判定。':'完整图独立于探索进度；缩放和拖动可查看细节。');
}
function renderTriggers(){
 $('trigger-list').replaceChildren();
 const triggers=relevantTriggers();
 if(!triggers.length)$('trigger-list').append(element('p','当前参考路线没有经过风险触发点。','muted'));
 triggers.forEach(trigger=>{
  const number=design.triggers.indexOf(trigger)+1;
  const card=element('article',undefined,`trigger-card${selectedTrigger===trigger.id?' selected':''}`);
  const title=element('button',undefined,'trigger-title');title.setAttribute('aria-pressed',String(trigger.id===selectedTrigger));
  title.append(element('span',String(number),'trigger-number'),document.createTextNode(trigger.name));title.onclick=()=>focusTrigger(trigger.id);
  const heading=element('h3');heading.append(title);card.append(heading);
  if(trigger.kind==='hazard'){
   card.append(element('p',`风险位置：${placeName(trigger.location)}。${conditionText(trigger.conditions)}，无对应工具额外消耗 ${trigger.extra_effort} 体力。`));
   trigger.tools.forEach(tool=>card.append(element('p',`取用：${tool.depots.map(placeName).join('、')||'无固定取用点'}。${tool.name}可将额外消耗降至 ${tool.effort}。`)));
   const opportunity=trigger.opportunities.find(o=>o.task_id===selectedTask);
   if(opportunity)card.append(element('p',`准备位置：${placeName(opportunity.preparation_at)}；本项参考路线进入风险点 ${opportunity.encounters} 次。`));
   card.append(element('p','观察动作：是否提前取用对应工具、进入时是否携带、遇险后是否折返补取。'));
  }else{
   card.append(element('p',`通路：${trigger.edge.map(placeName).join(' ↔ ')}；触发条件：${conditionText(trigger.conditions)}。`),element('p',trigger.feedback));
   card.append(element('p','观察动作：条件再次满足时，是否避免重复尝试并选择其他通路。'));
  }
  const tags=element('div',undefined,'opportunity-tags');
  trigger.opportunities.forEach(o=>{const b=element('button',`${o.task_id} ${o.role==='first_contact'?'初次接触':'后续机会'}`);b.setAttribute('aria-current',String(o.task_id===selectedTask));b.onclick=()=>selectTask(o.task_id);tags.append(b);});card.append(tags);
  card.append(element('p','实际评测先核验此前是否获得相关经验，再检查当前是否有应用机会。','qualification'));
  $('trigger-list').append(card);
 });
}
function draw(){
 const svg=$('design-map'), nodes=places(), t=task(), triggers=relevantTriggers();
 Cartography.prepare(svg,{environment:{id:design.scenario,view_box:design.view_box}});
 ['design-roads','design-route','design-nodes','design-markers'].forEach(id=>$(id).replaceChildren());
 const path=t?.reference?.path||[], pathEdges=new Set(path.slice(1).map((n,i)=>[n,path[i]].sort().join('|')));
 design.map.distances.forEach(e=>{
  const a=nodes[e.source],b=nodes[e.target];
  $('design-roads').append(svgNode('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:`design-road${pathEdges.has([e.source,e.target].sort().join('|'))?' focus-road':''}`}));
  $('design-roads').append(svgNode('text',{x:(a.x+b.x)/2,y:(a.y+b.y)/2-7,'text-anchor':'middle',class:'design-distance'},e.distance));
 });
 if($('show-reference').checked&&path.length)$('design-route').append(svgNode('polyline',{points:path.map(id=>`${nodes[id].x},${nodes[id].y}`).join(' '),class:'design-reference'}));
 const highlighted=new Set(t?[t.start,...t.goals,...t.submit_at]:[]);
 if($('show-triggers').checked)triggers.forEach(r=>{if(r.location)highlighted.add(r.location);r.tools.forEach(tool=>tool.depots.forEach(n=>highlighted.add(n)));});
 design.map.nodes.forEach(n=>{
  const circle=svgNode('circle',{cx:n.x,cy:n.y,r:t?.goals.includes(n.id)?9:6,class:`design-node${t?.goals.includes(n.id)?' goal':''}`});circle.append(svgNode('title',{},`${n.name} ${n.id}`));$('design-nodes').append(circle);
  if(n.kind==='camp')$('design-nodes').append(svgNode('path',{d:`M${n.x-12} ${n.y+10} L${n.x} ${n.y-14} L${n.x+12} ${n.y+10}Z`,class:'camp-mark'}));
  $('design-nodes').append(svgNode('text',{x:n.x,y:n.y+29,'text-anchor':'middle',class:`node-label${!highlighted.has(n.id)&&n.kind!=='camp'?' detail-label':''}`},n.name));
  $('design-nodes').append(svgNode('text',{x:n.x,y:n.y-18,'text-anchor':'middle',class:'node-id'},n.id));
 });
 if(!$('show-triggers').checked)return;
 const starts=new Set(),depots=new Set();
 triggers.forEach(trigger=>{
  trigger.tools.forEach(tool=>tool.depots.forEach(n=>depots.add(n)));
  trigger.opportunities.filter(o=>!selectedTask||o.task_id===selectedTask).forEach(o=>starts.add(o.preparation_at));
  let x,y;
  if(trigger.location){({x,y}=nodes[trigger.location]);$('design-markers').append(svgNode('circle',{cx:x,cy:y,r:17,class:'risk-halo'}));}
  else{const [a,b]=trigger.edge.map(id=>nodes[id]);x=(a.x+b.x)/2;y=(a.y+b.y)/2;$('design-markers').append(svgNode('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'passage-mark'}));}
  const marker=svgNode('g',{transform:`translate(${x+18} ${y-24})`,class:`risk-marker${selectedTrigger===trigger.id?' selected':''}`,role:'button',tabindex:'0','aria-label':`查看${trigger.name}记忆触发点`});
  marker.append(svgNode('circle',{r:14}),svgNode('text',{},design.triggers.indexOf(trigger)+1),svgNode('title',{},trigger.name));
  marker.onclick=()=>focusTrigger(trigger.id);marker.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focusTrigger(trigger.id);}};$('design-markers').append(marker);
  if(selectedTrigger===trigger.id)svg._focus=[x,y];
 });
 starts.forEach(id=>{const n=nodes[id];$('design-markers').append(svgNode('circle',{cx:n.x,cy:n.y,r:22,class:'prepare-marker'}));});
 depots.forEach(id=>{const n=nodes[id],marker=svgNode('path',{d:`M${n.x} ${n.y-12} L${n.x+12} ${n.y} L${n.x} ${n.y+12} L${n.x-12} ${n.y}Z`,class:'depot-marker'});marker.append(svgNode('title',{},`工具取用：${placeName(id)}`));$('design-markers').append(marker);});
}
function render(){if(!design)return;renderTasks();renderTriggers();draw();}
async function load(scenario){
 const ticket=++loading;$('design-error').textContent='';$('scenario-select').disabled=true;$('task-select').disabled=true;
 try{
  const r=await fetch('/api/design?scenario='+encodeURIComponent(scenario),{cache:'no-store'});
  if(r.status===401){location.assign('/login?next=/design');return;}
  if(!r.ok)throw new Error('无法读取地图设计，请重新选择地图或刷新。');
  const incoming=await r.json();if(ticket!==loading)return;design=incoming;selectedTask='';selectedTrigger='';
  $('scenario-select').replaceChildren();design.maps.forEach(m=>$('scenario-select').append(new Option(m.name,m.id)));$('scenario-select').value=design.scenario;
  $('task-select').replaceChildren(new Option('全部委托',''));design.tasks.forEach(t=>$('task-select').append(new Option(`${t.id} ${t.name}`,t.id)));
  $('design-title').textContent=design.name+'完成图';$('design-meta').textContent=`${design.map.nodes.length} 地点 / ${design.map.edges.length} 通路`;
  $('design-version').textContent=`当前设计 ${design.version}`;history.replaceState(null,'','/design?scenario='+encodeURIComponent(design.scenario));
  $('scenario-select').disabled=false;$('task-select').disabled=false;render();
 }catch(e){if(ticket===loading){$('design-error').textContent=e.message;$('scenario-select').disabled=false;}}
}
$('scenario-select').onchange=e=>load(e.target.value);$('task-select').onchange=e=>selectTask(e.target.value);
$('show-triggers').onchange=render;$('show-reference').onchange=render;
Cartography.controls($('design-map'),'design');
load(new URLSearchParams(location.search).get('scenario')||'lake-easy');
