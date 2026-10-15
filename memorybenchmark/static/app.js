const $ = id => document.getElementById(id);
let instance = null, observation = null, busy = false;
const svgNS = 'http://www.w3.org/2000/svg';
async function post(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
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
  const nodes = Object.fromEntries(o.map.nodes.map(n=>[n.id,n]));
  o.map.edges.forEach(([a,b])=> $('edges').append(el('line',{x1:nodes[a].x,y1:nodes[a].y,x2:nodes[b].x,y2:nodes[b].y,class:'route-line'})));
  o.map.nodes.forEach(n=> {
    const measured = o.map.surveyed.includes(n.id);
    $('nodes').append(el('circle',{cx:n.x,cy:n.y,r:n.id===o.location.id?10:7,class:`node-circle ${n.id===o.location.id?'here':''} ${measured?'surveyed':''}`}));
    $('nodes').append(el('text',{x:n.x,y:n.y+28,'text-anchor':'middle',class:'node-label'},n.name));
    $('nodes').append(el('text',{x:n.x,y:n.y-18,'text-anchor':'middle',class:'node-id'},n.id));
  });
  $('map-caption').textContent = `已发现 ${o.map.nodes.length} 处地点 · 已测量 ${o.map.surveyed.length} 处`;
}
function update(result) {
  observation = result.observation; instance = result.instance_id;
  const o = observation;
  $('task-name').textContent = o.task_id==='T1'?'渡口勘测':'对岸测绘';
  $('instruction').textContent = o.instruction;
  $('begin').hidden = true; $('play').hidden = o.done; $('ending').hidden = !o.done;
  $('place').textContent = `${o.location.name} ${o.location.id}`;
  $('conditions').textContent = `${{rain:'下雨',clear:'晴朗',snow:'下雪'}[o.conditions.weather]} / ${{night:'夜间',day:'白天'}[o.conditions.period]}`;
  $('time').textContent = `时间 ${o.world_time}`; $('distance').textContent = `路程 ${o.distance}`; $('steps').textContent = `操作 ${o.steps}/${o.max_steps}`;
  $('routes').replaceChildren();
  o.neighbors.forEach(n=> {
    const b = document.createElement('button');
    const label = document.createElement('span'); label.textContent = `前往${n.name} ${n.target}`;
    const distance = document.createElement('small'); distance.textContent = `距离 ${n.distance}`;
    b.append(label,distance); b.onclick=()=>act('move',n.target); $('routes').append(b);
  });
  $('result').textContent = o.success?'本次测绘已完成':'本次探索已结束';
  $('next').textContent = o.task_id==='T1'?'接下一个委托':'再做一次渡口勘测';
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
  finally { busy=false; document.querySelectorAll('button').forEach(b=>b.disabled=false); }
}
function start(task, fresh=false) {
  return run(async()=> {
    const result = await post('/api/start',{task_id:task,...(!fresh&&instance?{instance_id:instance}:{})});
    $('log').replaceChildren(); update(result);
  });
}
function act(type,target) {
  return run(async()=>update(await post('/api/action',{instance_id:instance,request_id:crypto.randomUUID(),expected_revision:observation.revision,action:{type,...(target?{target}:{})}})));
}
$('begin').onclick=()=>start('T1');
$('fresh').onclick=()=> { if(!observation || observation.done || confirm('放弃当前探索，重新从第一项委托开始？')) start('T1',true); };
$('next').onclick=()=>start(observation.task_id==='T1'?'T2':'T1');
$('abandon').onclick=()=>act('abandon');
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>act(b.dataset.action));
