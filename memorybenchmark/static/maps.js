/* Presentation only. Never included in agent observations or memory. */
window.Cartography = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  function atlas(frames) {
    const nodes = new Map(), edges = new Map();
    if (!frames.length || !frames.at(-1).observation.success) return {nodes:[],edges:[],surveyed:[]};
    frames.forEach(f => {
      const n = f.observation.location; nodes.set(n.id,n);
      if (f.moved) {
        const pair=[f.source,f.target].sort(); edges.set(pair.join('|'),pair);
        f.observation.map.nodes.filter(n=>pair.includes(n.id)).forEach(n=>nodes.set(n.id,n));
      }
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
    const lake=o.environment?.id==='lake-easy';
    if(lake&&!terrain&&svg.dataset.world!=='true') {
      terrain=document.createElementNS(NS,'image'); terrain.setAttribute('href','/lake.svg');
      terrain.setAttribute('width','1200'); terrain.setAttribute('height','800');
      terrain.setAttribute('class','terrain'); terrain.setAttribute('aria-hidden','true');
      svg.querySelector('rect').after(terrain);
    } else if(!lake&&terrain) terrain.remove();
    const base=lake?[0,0,1200,800]:(o.environment?.view_box||(svg.dataset.originalView||svg.getAttribute('viewBox')).split(' ').map(Number));
    const key=lake?'lake-easy':'legacy';
    if(!svg.dataset.originalView) svg.dataset.originalView=svg.getAttribute('viewBox');
    if(svg._mapKey!==key) {
      svg._mapKey=key;svg._base=base;svg._box=[...base];svg.setAttribute('viewBox',base.join(' '));
      if(svg._syncMap)svg._syncMap();
    }
    svg._focus=o.location?[o.location.x,o.location.y]:[base[2]/2,base[3]/2];
    svg.classList.toggle('lake-map',lake);
    if(svg.dataset.world==='true')window.WorldScene?.prepare(svg,o);
    const compass=svg.querySelector('.compass');
    if(compass)compass.setAttribute('transform',lake?'translate(1140 750)':(svg.id==='map'?'translate(755 66)':'translate(756 42)'));
    return lake;
  }
  function labels(svg,n,o) {
    const targets=o.objective?.targets.map(t=>t.id)||[];
    return !svg.classList.contains('lake-map') || n.id===o.location.id || n.kind==='camp' || targets.includes(n.id);
  }
  function controls(svg,prefix) {
    const apply=()=>{
      svg.setAttribute('viewBox',svg._box.join(' '));
      svg.classList.toggle('map-detail',svg._base[2]/svg._box[2]>=1.5);
      svg.classList.toggle('map-zoomed',svg._base[2]>svg._box[2]);
      const label=document.getElementById(prefix+'-zoom-label');
      if(label)label.textContent=Math.round(100*svg._base[2]/svg._box[2])+'%';
      if(prefix==='play'){
        const scale=svg.getScreenCTM()?.a;
        if(scale>0){
          // Map geometry zooms; interactive labels and hit targets stay readable.
          svg.style.setProperty('--map-label-size',14/scale+'px');
          svg.style.setProperty('--map-id-size',10/scale+'px');
          svg.style.setProperty('--map-distance-size',11/scale+'px');
          svg.style.setProperty('--map-label-y',28/scale+'px');
          svg.style.setProperty('--map-id-y',-23/scale+'px');
          svg.style.setProperty('--map-hit-radius',22/scale+'px');
          svg.style.setProperty('--map-marker-scale',1/scale);
        }
      }
    };
    const clamp=()=>{
      const [x,y,w,h]=svg._base,b=svg._box;
      const px=prefix==='play'?b[2]*.45:0,py=prefix==='play'?b[3]*.45:0;
      b[0]=Math.max(x-px,Math.min(x+w-b[2]+px,b[0]));b[1]=Math.max(y-py,Math.min(y+h-b[3]+py,b[1]));
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
    // Exposed camera helpers are presentation only and never choose a route.
    svg._revealPoint=(x,y)=>{
      if(!svg._box||svg._box[2]>=svg._base[2])return;
      const b=svg._box,margin=.17;
      if(x<b[0]+b[2]*margin || x>b[0]+b[2]*(1-margin) || y<b[1]+b[3]*margin || y>b[1]+b[3]*(1-margin)){
        svg._box=[x-b[2]/2,y-b[3]/2,b[2],b[3]];clamp();apply();
      }
    };
    svg._locate=()=>{
      if(!svg._base||!svg._focus)return;
      const [x,y]=svg._focus,w=svg.dataset.world==='true'?(innerWidth<760?480:600):svg._base[2]/2;
      const h=svg.dataset.world==='true'?w*svg.clientHeight/svg.clientWidth:svg._base[3]/2;
      svg._box=[x-w/2,y-h/2,w,h];clamp();apply();
    };
    const locate=document.getElementById(prefix+'-locate');
    if(locate)locate.onclick=svg._locate;
    let drag,suppressClick=false;
    svg.addEventListener('pointerdown',e=>{
      suppressClick=false;
      if(e.button!==0||!svg._box||svg._box[2]===svg._base[2])return;
      drag={x:e.clientX,y:e.clientY,box:[...svg._box],id:e.pointerId,moved:false};
    });
    svg.addEventListener('pointermove',e=>{
      if(!drag||drag.id!==e.pointerId)return;
      if(!drag.moved && Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<8)return;
      if(!drag.moved){drag.moved=true;svg.setPointerCapture(e.pointerId);svg.classList.add('map-dragging');}
      suppressClick=true;
      const rect=svg.getBoundingClientRect();
      const scale=svg.getScreenCTM()?.a||Math.min(rect.width/drag.box[2],rect.height/drag.box[3]);
      svg._box=[drag.box[0]-(e.clientX-drag.x)/scale,drag.box[1]-(e.clientY-drag.y)/scale,drag.box[2],drag.box[3]];clamp();apply();
    });
    const endDrag=()=>{drag=null;svg.classList.remove('map-dragging');};
    svg.addEventListener('pointerup',endDrag);svg.addEventListener('pointercancel',()=>{endDrag();suppressClick=false;});
    svg.addEventListener('lostpointercapture',endDrag);
    svg.addEventListener('click',e=>{if(suppressClick){e.preventDefault();e.stopImmediatePropagation();suppressClick=false;}},true);
    // Opt in for the human map; read-only viewers keep their normal page scrolling.
    if(prefix==='play')svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.18:1/1.18);},{passive:false});
    svg._syncMap=apply;
    if(prefix==='play')new ResizeObserver(()=>{
      if(!svg._box)return;
      if(svg.dataset.world==='true'&&svg._box[2]<svg._base[2]){
        const b=svg._box,h=b[2]*svg.clientHeight/svg.clientWidth;
        svg._box=[b[0],b[1]+(b[3]-h)/2,b[2],h];clamp();
      }
      apply();
    }).observe(svg);
  }
  function current(map) {
    if(!map.current_nodes)return map;
    const ids=new Set(map.current_nodes);
    return {...map,nodes:map.nodes.filter(n=>ids.has(n.id)),edges:map.current_edges};
  }
  function recovery(svg,group,history,nodes) {
    group.replaceChildren();
    if(!history?.length)return;
    function item(type,attrs,text){const n=document.createElementNS(NS,type);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
    const markerId=svg.id+'-respawn-arrow';
    if(!svg.querySelector('#'+markerId)){
      const marker=item('marker',{id:markerId,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto'});
      marker.append(item('path',{d:'M0 0 L10 5 L0 10Z',fill:'#9d4340'}));svg.querySelector('defs').append(marker);
    }
    const seen={};
    history.forEach(r=>{
      const a=nodes[r.source],b=nodes[r.target];if(!a||!b)return;
      const key=r.source+'|'+r.target,ordinal=seen[key]||0;seen[key]=ordinal+1;
      const dx=b.x-a.x,dy=b.y-a.y,length=Math.max(1,Math.hypot(dx,dy)),offset=38+ordinal*23;
      const mx=(a.x+b.x)/2-dy/length*offset,my=(a.y+b.y)/2+dx/length*offset;
      const d=r.source===r.target?`M${a.x} ${a.y-8} C${a.x+55} ${a.y-65} ${a.x-55} ${a.y-65} ${a.x} ${a.y-8}`:`M${a.x} ${a.y} Q${mx} ${my} ${b.x} ${b.y}`;
      const path=item('path',{d,class:'respawn-line','marker-end':`url(#${markerId})`});path.append(item('title',{},`复活 ${r.source} → ${r.target}，权重 ${r.weight}`));group.append(path);
      group.append(item('text',{x:r.source===r.target?a.x:mx,y:r.source===r.target?a.y-55:my-8,'text-anchor':'middle',class:'respawn-label'},`复活 +${r.weight}`));
    });
  }
  return {atlas,merge,current,prepare,labels,controls,recovery};
})();
