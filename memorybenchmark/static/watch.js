const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
let currentRun='', snapshot=null, selected='', index=0, follow=true, replayTimer=null, polling=false, pinnedRun=false;
const conditionName={prefix:'历史任务',retain:'保留记忆',clear:'恢复基线'};
const phaseName={thinking:'模型调用中',acting:'执行动作',playing:'任务开始',finalizing:'自主整理',finished:'会话结束'};
const runName={running:'实验进行中',complete:'实验已完成',interrupted:'实验已中断'};
function node(type,attrs={},text){const n=document.createElementNS(NS,type);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function textElement(type,text,cls){const n=document.createElement(type);n.textContent=text;if(cls)n.className=cls;return n;}
function clock(at){return at?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(at)):'';}
function session(){return snapshot?.sessions.find(s=>s.id===selected);}
function stopReplay(){if(replayTimer)clearInterval(replayTimer);replayTimer=null;$('replay-toggle').textContent='回放';}
async function get(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw new Error('无法读取实验记录');return r.json();}
function chooseRun(id){stopReplay();currentRun=id;selected='';follow=true;snapshot=null;index=0;}
async function poll(){
 if(polling)return;polling=true;
 try{
  const listing=await get('/api/watch/runs');const runs=listing.runs;
  $('run-select').replaceChildren();
  runs.forEach(r=>{const option=document.createElement('option');option.value=r.id;option.textContent=`${r.id.slice(0,8)} · ${runName[r.status]||r.status}`;$('run-select').append(option);});
  if(!runs.length){$('run-select').append(new Option('暂无实验记录',''));$('connection').textContent='已连接，等待实验';$('connection').classList.remove('offline');return;}
  if(!currentRun||!runs.some(r=>r.id===currentRun))chooseRun(runs[0].id);
  // Select a newly launched run automatically only until the user chooses one.
  const active=runs.find(r=>r.status==='running');
  if(!pinnedRun&&active&&active.id!==currentRun)chooseRun(active.id);
  $('run-select').value=currentRun;
  snapshot=await get('/api/watch/run?id='+encodeURIComponent(currentRun));
  if(!selected||!snapshot.sessions.some(s=>s.id===selected)||(follow&&snapshot.active_session_id))selected=snapshot.active_session_id||snapshot.sessions.at(-1)?.id||'';
  const s=session();if(s&&follow)index=Math.max(0,s.frames.length-1);
  $('connection').textContent='已连接 · 自动更新';$('connection').classList.remove('offline');render();
 }catch(e){$('connection').textContent='连接中断，正在重连';$('connection').classList.add('offline');}
 finally{polling=false;}
}
function render(){
 if(!snapshot)return;
 $('run-meta').textContent=`GenericAgent / ${snapshot.model}${snapshot.kind.includes('scripted')?' · 脚本化联调':''}`;
 $('run-state').textContent=runName[snapshot.status]||snapshot.status;
 $('completion').textContent=`${snapshot.completed_sessions} / ${snapshot.total_sessions}`;
 $('completion-bar').max=Math.max(1,snapshot.total_sessions);$('completion-bar').value=snapshot.completed_sessions;
 $('run-id').textContent='实验 '+snapshot.id;
 $('sessions').replaceChildren();
 snapshot.sessions.forEach(s=>{const b=document.createElement('button');b.className=`session-row ${s.status}${s.id===selected?' selected':''}`;b.setAttribute('aria-pressed',String(s.id===selected));
  b.append(textElement('span','','dot'));const label=textElement('span',`${s.task_id} ${s.task_name||''}`,'label');label.append(textElement('small',conditionName[s.condition]||s.condition));b.append(label,textElement('span',s.status==='error'?'中断':(s.status==='complete'?(s.success?'成功':'未完成'):'运行中'),'result'));
  b.onclick=()=>{stopReplay();selected=s.id;follow=false;index=Math.max(0,s.frames.length-1);render();};$('sessions').append(b);
 });
 const s=session();const ready=s&&s.frames.length;
 $('empty').hidden=Boolean(ready);$('viewer').hidden=!ready;$('details').hidden=!ready;if(!ready)return;
 index=Math.max(0,Math.min(index,s.frames.length-1));const f=s.frames[index],o=f.observation;
 $('task-title').textContent=o.task_name;$('session-caption').textContent=`${s.task_id} / ${conditionName[s.condition]||s.condition}`;
 $('session-state').textContent=s.status==='complete'?(s.success?'任务成功':'任务未完成'):(s.status==='error'?'运行中断':(phaseName[s.phase]||'运行中'));
 $('session-state').classList.toggle('error',s.status==='error');
 $('map-meta').textContent=`已发现 ${o.map.nodes.length} 处 · 已记录 ${o.map.surveyed.length} 处`;
 $('frame-mode').textContent=follow?'跟随运行':(index===s.frames.length-1?'会话末尾':'历史回放');
 $('frame-slider').max=Math.max(0,s.frames.length-1);$('frame-slider').value=index;$('frame-number').textContent=`动作 ${index} / ${s.frames.length-1}`;
 $('metric-distance').textContent=o.distance;$('metric-effort').textContent=o.effort;$('metric-stamina').textContent=`${o.stamina} / ${o.initial_stamina}`;$('metric-calls').textContent=s.calls;
 $('instruction').textContent=o.instruction;$('place').textContent=`${o.location.name} ${o.location.id}`;
 $('weather').textContent=`${{clear:'晴朗',rain:'下雨',snow:'下雪'}[o.conditions.weather]||o.conditions.weather} / ${{day:'白天',night:'夜间'}[o.conditions.period]||o.conditions.period}`;
 $('game-time').textContent=o.world_time;$('inventory').textContent=o.inventory.map(t=>t.name).join('、')||'未携带工具';
 $('memory-status').textContent=s.memory.final?'结算快照':'运行中';$('memory-summary').textContent=s.memory.changed.length?`本会话有 ${s.memory.changed.length} 个记忆文件发生变化。`:'本会话尚未观察到记忆内容变化。';
 $('memory-files').replaceChildren();s.memory.changed.forEach(p=>$('memory-files').append(textElement('li',p)));
 $('phase').textContent=phaseName[s.phase]||'';$('activity-log').replaceChildren();
 [...s.activity].reverse().forEach(a=>{const li=textElement('li',a.label,a.kind==='error'?'error':'');if(a.at)li.append(textElement('time',clock(a.at)));$('activity-log').append(li);});
 if(!s.activity.length)$('activity-log').append(textElement('li',snapshot.historical?'历史记录，可通过动作滑块回放。':'等待下一项执行动态。'));
 $('last-updated').textContent=snapshot.updated_at?'更新于 '+clock(snapshot.updated_at):'历史记录';
 $('action-log').replaceChildren();s.frames.slice(0,index+1).map((v,i)=>({v,i})).reverse().forEach(({v,i})=>{const li=document.createElement('li');li.append(textElement('span',String(i).padStart(2,'0'),'index'));const body=document.createElement('div');body.append(textElement('p',v.feedback));body.append(textElement('time',`游戏时间 ${v.observation.world_time}${v.at?' / '+clock(v.at):''}`));li.append(body);$('action-log').append(li);});
 draw(s.frames.slice(0,index+1),o);
}
function draw(frames,o){
 $('roads').replaceChildren();$('trace').replaceChildren();$('places').replaceChildren();
 const places=Object.fromEntries(o.map.nodes.map(n=>[n.id,n]));
 o.map.edges.forEach(([a,b])=>{if(places[a]&&places[b])$('roads').append(node('line',{x1:places[a].x,y1:places[a].y,x2:places[b].x,y2:places[b].y,class:'road-line'}));});
 const seen={},moves=frames.filter(f=>f.moved);
 moves.forEach((f,i)=>{const a=places[f.source],b=places[f.target];if(!a||!b)return;const key=[f.source,f.target].sort().join('-');const count=seen[key]||0;seen[key]=count+1;
  const dx=b.x-a.x,dy=b.y-a.y,length=Math.max(1,Math.hypot(dx,dy)),offset=count?16*Math.ceil(count/2)*(count%2?1:-1):0;
  const mx=(a.x+b.x)/2-dy/length*offset,my=(a.y+b.y)/2+dx/length*offset;
  $('trace').append(node('path',{d:`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`,class:'trace-line',opacity:0.35+0.65*(i+1)/moves.length}));
  $('trace').append(node('text',{x:mx+6,y:my-9,class:'step-label','text-anchor':'middle'},i+1));
 });
 o.map.nodes.forEach(n=>{const current=n.id===o.location.id,visited=o.map.surveyed.includes(n.id);$('places').append(node('circle',{cx:n.x,cy:n.y,r:current?10:6,class:`node${visited?' visited':''}${current?' current':''}`}));$('places').append(node('text',{x:n.x,y:n.y+31,'text-anchor':'middle',class:'place-label'},n.name));$('places').append(node('text',{x:n.x,y:n.y-18,'text-anchor':'middle',class:'place-id'},n.id));});
}
$('run-select').onchange=e=>{pinnedRun=true;chooseRun(e.target.value);poll();};$('refresh').onclick=poll;
$('frame-slider').oninput=e=>{stopReplay();follow=false;index=Number(e.target.value);render();};
$('follow').onclick=()=>{stopReplay();follow=true;if(snapshot?.active_session_id)selected=snapshot.active_session_id;const s=session();if(s)index=s.frames.length-1;render();};
$('replay-toggle').onclick=()=>{if(replayTimer){stopReplay();return;}const s=session();if(!s)return;follow=false;if(index>=s.frames.length-1)index=0;$('replay-toggle').textContent='暂停';render();replayTimer=setInterval(()=>{const current=session();if(!current||index>=current.frames.length-1){stopReplay();return;}index++;render();},1000);};
poll();setInterval(poll,1500);
