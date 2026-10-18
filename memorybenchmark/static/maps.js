/* Presentation only. Never included in agent observations or memory. */
window.Cartography = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  function atlas(frames) {
    const nodes = new Map(), edges = new Map();
    if (!frames.length || !frames.at(-1).observation.success) return {nodes:[],edges:[],surveyed:[]};
    frames.forEach(f => {
      const n = f.observation.location; nodes.set(n.id,n);
      if (f.moved) { const pair=[f.source,f.target].sort(); edges.set(pair.join('|'),pair); }
    });
    return {nodes:[...nodes.values()],edges:[...edges.values()],surveyed:[...nodes.keys()]};
  }
  function merge(current, ...previous) {
    const nodes=new Map(), edges=new Map(), submitted=new Set();
    previous.filter(Boolean).forEach(a=> {
      (a.nodes||[]).forEach(n=>nodes.set(n.id,n));
      (a.edges||[]).forEach(e=>edges.set([...e].sort().join('|'),e));
      (a.surveyed||[]).forEach(n=>submitted.add(n));
    });
    current.nodes.forEach(n=>nodes.set(n.id,n));
    current.edges.forEach(e=>edges.set([...e].sort().join('|'),e));
    return {nodes:[...nodes.values()],edges:[...edges.values()],surveyed:current.surveyed,submitted};
  }
  function prepare(svg,o) {
    let terrain=svg.querySelector('.terrain');
    const ness=o.environment?.id==='loch-ness';
    if(ness&&!terrain) {
      terrain=document.createElementNS(NS,'image'); terrain.setAttribute('href','/loch-ness.svg');
      terrain.setAttribute('width','1200'); terrain.setAttribute('height','800');
      terrain.setAttribute('class','terrain'); terrain.setAttribute('aria-hidden','true');
      svg.querySelector('rect').after(terrain);
    } else if(!ness&&terrain) terrain.remove();
    const base=ness?[0,0,1200,800]:(svg.dataset.originalView||svg.getAttribute('viewBox')).split(' ').map(Number);
    const key=ness?'loch-ness':'legacy';
    if(!svg.dataset.originalView) svg.dataset.originalView=svg.getAttribute('viewBox');
    if(svg._mapKey!==key) {
      svg._mapKey=key;svg._base=base;svg._box=[...base];svg.setAttribute('viewBox',base.join(' '));
      if(svg._syncMap)svg._syncMap();
    }
    svg._focus=o.location?[o.location.x,o.location.y]:[base[2]/2,base[3]/2];
    svg.classList.toggle('ness-map',ness);
    const compass=svg.querySelector('.compass');
    if(compass)compass.setAttribute('transform',ness?'translate(1140 750)':(svg.id==='map'?'translate(755 66)':'translate(756 42)'));
    return ness;
  }
  function labels(svg,n,o) {
    const targets=o.objective?.targets.map(t=>t.id)||[];
    return !svg.classList.contains('ness-map') || n.id===o.location.id || n.kind==='camp' || targets.includes(n.id);
  }
  function controls(svg,prefix) {
    const apply=()=>{
      svg.setAttribute('viewBox',svg._box.join(' '));
      svg.classList.toggle('map-detail',svg._base[2]/svg._box[2]>=1.5);
      svg.classList.toggle('map-zoomed',svg._base[2]>svg._box[2]);
      const label=document.getElementById(prefix+'-zoom-label');
      if(label)label.textContent=Math.round(100*svg._base[2]/svg._box[2])+'%';
    };
    const clamp=()=>{
      const [x,y,w,h]=svg._base,b=svg._box;
      b[0]=Math.max(x,Math.min(x+w-b[2],b[0]));b[1]=Math.max(y,Math.min(y+h-b[3],b[1]));
    };
    function zoom(factor){
      if(!svg._box)return;
      const b=svg._box,base=svg._base,w=Math.max(base[2]/4,Math.min(base[2],b[2]*factor)),ratio=w/b[2];
      const focus=factor<1&&b[2]===base[2]?svg._focus:[b[0]+b[2]/2,b[1]+b[3]/2];
      svg._box=[focus[0]-w/2,focus[1]-b[3]*ratio/2,w,b[3]*ratio];clamp();apply();
    }
    document.getElementById(prefix+'-zoom-in').onclick=()=>zoom(1/1.4);
    document.getElementById(prefix+'-zoom-out').onclick=()=>zoom(1.4);
    document.getElementById(prefix+'-zoom-reset').onclick=()=>{if(svg._base){svg._box=[...svg._base];apply();}};
    let drag;
    svg.addEventListener('pointerdown',e=>{
      if(e.button!==0||!svg._box||svg._box[2]===svg._base[2])return;
      drag={x:e.clientX,y:e.clientY,box:[...svg._box]};svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener('pointermove',e=>{
      if(!drag)return;const rect=svg.getBoundingClientRect();
      const scale=Math.min(rect.width/drag.box[2],rect.height/drag.box[3]);
      svg._box=[drag.box[0]-(e.clientX-drag.x)/scale,drag.box[1]-(e.clientY-drag.y)/scale,drag.box[2],drag.box[3]];clamp();apply();
    });
    svg.addEventListener('pointerup',()=>{drag=null;});svg.addEventListener('pointercancel',()=>{drag=null;});
    svg._syncMap=apply;
  }
  return {atlas,merge,prepare,labels,controls};
})();
