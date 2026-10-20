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
    if(prefix==='play' && svg.dataset.world==='true')return worldControls(svg);
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
  // The human world has its own camera. It never creates game actions, discovers
  // locations, or changes the graph shown by the public observation.
  function worldControls(svg) {
    const pointers=new Map(), reduced=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;
    const locate=document.getElementById('play-locate'), label=document.getElementById('play-zoom-label');
    let following=true, gesture=null, suppressUntil=0, animation=0, overview=false;
    let queued=null, frame=0;
    const aspect=()=>Math.max(1,svg.clientWidth)/Math.max(1,svg.clientHeight);
    const fitWidth=()=>Math.max(svg._base[2],svg._base[3]*aspect());
    const minWidth=()=>svg._base[2]/4;
    function clamp(box) {
      const [x,y,w,h]=svg._base;
      // Limit the camera centre, not the pointer's original displacement. The
      // next reversed pixel works immediately, including at the world boundary.
      box[0]=Math.max(x-box[2]/2,Math.min(x+w-box[2]/2,box[0]));
      box[1]=Math.max(y-box[3]/2,Math.min(y+h-box[3]/2,box[1]));
      return box;
    }
    function render() {
      if(!svg._box)return;
      const b=svg._box, scale=svg.clientWidth/b[2];
      svg.setAttribute('viewBox',b.join(' '));
      svg.classList.toggle('map-detail',svg._base[2]/b[2]>=1.5);
      svg.classList.toggle('map-zoomed',b[2]<fitWidth()-.1);
      svg.dataset.camera=following?'follow':'free';
      label.textContent=Math.round(100*fitWidth()/b[2])+'%';
      locate.setAttribute('aria-pressed',String(following));
      locate.title=following?'镜头跟随中 · F 重新定位':'自由查看中 · F 回到角色并跟随';
      locate.setAttribute('aria-label',locate.title);
      document.getElementById('camera-mode').textContent=following?'跟随':'定位';
      document.getElementById('play-zoom-in').disabled=b[2]<=minWidth()+.1;
      document.getElementById('play-zoom-out').disabled=b[2]>=fitWidth()-.1;
      svg.style.setProperty('--map-label-size',14/scale+'px');
      svg.style.setProperty('--map-id-size',10/scale+'px');
      svg.style.setProperty('--map-distance-size',11/scale+'px');
      svg.style.setProperty('--map-label-y',28/scale+'px');
      svg.style.setProperty('--map-id-y',-23/scale+'px');
      svg.style.setProperty('--map-hit-radius',22/scale+'px');
      svg.style.setProperty('--map-marker-scale',1/scale);
    }
    function stop() {cancelAnimationFrame(animation);animation=0;queued=null;}
    function set(box) {svg._box=clamp(box);render();}
    function animate(box,immediate=false) {
      stop();box=clamp(box);
      if(immediate || reduced()){set(box);return;}
      const from=[...svg._box], start=performance.now();queued=box;
      const tick=now=>{
        const t=Math.min(1,(now-start)/180), ease=1-(1-t)**3;
        set(from.map((v,i)=>v+(box[i]-v)*ease));
        if(t<1)animation=requestAnimationFrame(tick);else{animation=0;queued=null;}
      };
      animation=requestAnimationFrame(tick);
    }
    function manual() {stop();following=false;overview=false;}
    function clientPoint(x,y,box=svg._box) {
      const rect=svg.getBoundingClientRect(),scale=rect.width/box[2];
      return [box[0]+(x-rect.left)/scale,box[1]+(y-rect.top)/scale];
    }
    function zoom(factor,x,y,smooth=false) {
      if(!svg._box)return;
      const rect=svg.getBoundingClientRect(), b=[...(queued||svg._box)];
      x??=rect.left+rect.width/2;y??=rect.top+rect.height/2;
      const point=clientPoint(x,y,b),w=Math.max(minWidth(),Math.min(fitWidth(),b[2]*factor)),ratio=w/b[2];
      overview=false;
      animate([point[0]-(point[0]-b[0])*ratio,point[1]-(point[1]-b[1])*ratio,w,w/aspect()],!smooth);
    }
    function safeRect() {
      const rect=svg.getBoundingClientRect(),w=rect.width,h=rect.height;
      let left=24,right=w-24,top=24,bottom=h-100;
      const bounds=selector=>{const e=document.querySelector(selector);return e && e.getClientRects().length?e.getBoundingClientRect():null;};
      const field=bounds('.field-bar'),quest=bounds('.quest-panel'),dock=bounds('.location-panel');
      if(field)top=Math.max(top,field.bottom-rect.top+20);
      if(quest){if(w<=760)top=Math.max(top,quest.bottom-rect.top+20);else right=Math.min(right,quest.left-rect.left-24);}
      if(dock)bottom=Math.min(bottom,dock.top-rect.top-26);
      // Keep a usable camera window even in a short landscape phone viewport.
      if(right-left<160){left=16;right=w-16;}
      if(bottom-top<140){top=h*.27;bottom=h*.7;}
      return {left,right,top,bottom};
    }
    function centred(x,y,w) {
      const safe=safeRect(),scale=svg.clientWidth/w;
      return [x-(safe.left+safe.right)/2/scale,y-(safe.top+safe.bottom)/2/scale,w,w/aspect()];
    }
    function reveal(x,y,{force=false,immediate=false}={}) {
      if(!svg._box || gesture || (!following && !force))return;
      const safe=safeRect(),b=svg._box,scale=svg.clientWidth/b[2],px=(x-b[0])*scale,py=(y-b[1])*scale;
      if(px<safe.left+32 || px>safe.right-32 || py<safe.top+32 || py>safe.bottom-32){
        if(force)manual();
        animate(centred(x,y,b[2]),immediate);
      }
    }
    svg._locate=({immediate=false}={})=>{
      if(!svg._base||!svg._focus)return;
      stop();following=true;overview=false;
      const w=Math.min(fitWidth(),svg.clientWidth<=760?480:600);
      animate(centred(...svg._focus,w),immediate);
    };
    // Keyboard focus deliberately reveals a node; restoring focus after redraw
    // must not steal the camera back from a player inspecting somewhere else.
    svg._revealPoint=(x,y)=>reveal(x,y,{force:true,immediate:true});
    svg._followPoint=(x,y,immediate=false)=>reveal(x,y,{immediate});
    svg._syncMap=()=>{
      if(!svg._box)return;
      stop();const b=svg._box,h=b[2]/aspect();svg._box=[b[0],b[1]+(b[3]-h)/2,b[2],h];render();
    };
    svg._getCamera=()=>svg._box?{box:[...svg._box],following,overview,key:svg._mapKey}:null;
    svg._restoreCamera=camera=>{
      if(!camera || camera.key!==svg._mapKey || !Array.isArray(camera.box) || camera.box.length!==4 || !camera.box.every(Number.isFinite))return;
      const b=camera.box;
      if(b[2]<minWidth() || b[2]>fitWidth()+1 || b[3]<=0)return;
      stop();following=camera.following===true;overview=camera.overview===true;
      set([b[0],b[1]+(b[3]-b[2]/aspect())/2,b[2],b[2]/aspect()]);
    };
    locate.onclick=()=>svg._locate();
    document.getElementById('play-zoom-in').onclick=()=>zoom(1/1.35,undefined,undefined,true);
    document.getElementById('play-zoom-out').onclick=()=>zoom(1.35,undefined,undefined,true);
    document.getElementById('play-zoom-reset').onclick=()=>{
      if(!svg._base)return;
      manual();overview=true;
      const [x,y,w,h]=svg._base,width=fitWidth();animate([x+(w-width)/2,y+(h-width/aspect())/2,width,width/aspect()]);
    };
    const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
    function beginGesture() {
      const points=[...pointers.values()];
      if(!points.length){gesture=null;return;}
      gesture={moved:false,last:points[0],origin:points[0]};
      if(points.length>=2){
        manual();gesture.moved=true;gesture.pinch=true;gesture.span=distance(...points.slice(0,2));
        gesture.last={x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2};
        for(const id of pointers.keys())svg.setPointerCapture(id);
        suppressUntil=performance.now()+500;svg.classList.add('map-dragging');
      }
    }
    svg.addEventListener('pointerdown',e=>{
      if(!svg._box || (e.pointerType==='mouse' && ![0,1,2].includes(e.button)))return;
      stop();
      if(!pointers.size)suppressUntil=0;
      pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      // Capture the original node so an ordinary tap still clicks that node.
      // Capturing only after crossing the threshold loses fast exit/release.
      const owner=e.target.closest('[data-map-node]')||svg;
      owner.setPointerCapture(e.pointerId);
      beginGesture();
      if(e.button===1)e.preventDefault();
    });
    svg.addEventListener('pointermove',e=>{
      if(!pointers.has(e.pointerId)||!gesture)return;
      pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      const points=[...pointers.values()];
      if(points.length>=2){
        const mid={x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2},span=Math.max(1,distance(...points.slice(0,2)));
        const anchor=clientPoint(gesture.last.x,gesture.last.y),rect=svg.getBoundingClientRect();
        const w=Math.max(minWidth(),Math.min(fitWidth(),svg._box[2]*gesture.span/span)),scale=rect.width/w;
        set([anchor[0]-(mid.x-rect.left)/scale,anchor[1]-(mid.y-rect.top)/scale,w,w/aspect()]);
        gesture.span=span;gesture.last=mid;
      }else{
        const point=points[0];
        if(!gesture.moved && distance(point,gesture.origin)<(e.pointerType==='touch'?9:5))return;
        if(!gesture.moved){manual();gesture.moved=true;svg.setPointerCapture(e.pointerId);svg.classList.add('map-dragging');}
        const b=svg._box,scale=svg.clientWidth/b[2];
        set([b[0]-(point.x-gesture.last.x)/scale,b[1]-(point.y-gesture.last.y)/scale,b[2],b[3]]);
        gesture.last=point;
      }
      suppressUntil=performance.now()+500;
    });
    function release(e) {
      if(!pointers.has(e.pointerId))return;
      const moved=gesture?.moved;
      pointers.delete(e.pointerId);
      if(moved)suppressUntil=performance.now()+500;
      if(pointers.size){beginGesture();gesture.moved=true;}
      else{gesture=null;svg.classList.remove('map-dragging');}
    }
    svg.addEventListener('pointerup',release);
    svg.addEventListener('pointercancel',release);
    svg.addEventListener('lostpointercapture',e=>{if(!svg.hasPointerCapture(e.pointerId))release(e);});
    svg.addEventListener('click',e=>{
      if(e.detail>0 && performance.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}
    },true);
    svg.addEventListener('contextmenu',e=>e.preventDefault());
    // Some touch browsers still feed a completed pinch into their native tap
    // recognizer. Consume map touch-moves so the following HUD tap stays a tap.
    svg.addEventListener('touchmove',e=>e.preventDefault(),{passive:false});
    function cancel() {
      if(gesture?.moved)suppressUntil=performance.now()+500;
      const ids=[...pointers.keys()];pointers.clear();gesture=null;
      for(const id of ids){
        const owner=svg.hasPointerCapture(id)?svg:[...svg.querySelectorAll('[data-map-node]')].find(n=>n.hasPointerCapture(id));
        if(owner)owner.releasePointerCapture(id);
      }
      svg.classList.remove('map-dragging');stop();
    }
    window.addEventListener('blur',cancel);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();});
    document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(()=>{if(dialog.open)cancel();}).observe(dialog,{attributes:true,attributeFilter:['open']}));
    svg.addEventListener('wheel',e=>{
      e.preventDefault();if(gesture || !e.deltaY)return;
      // Exponential, bounded deltas work for both mouse notches and trackpads.
      const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?svg.clientHeight:1);
      following=false;zoom(Math.exp(Math.max(-160,Math.min(160,delta))*.0025),e.clientX,e.clientY);
    },{passive:false});
    new ResizeObserver(()=>{
      cancelAnimationFrame(frame);
      frame=requestAnimationFrame(()=>{
        if(!svg._base || !svg._box)return;
        stop();
        if(overview){const [x,y,w,h]=svg._base,width=fitWidth();set([x+(w-width)/2,y+(h-width/aspect())/2,width,width/aspect()]);}
        else{const b=svg._box,w=Math.max(minWidth(),Math.min(fitWidth(),b[2])),h=w/aspect();set([b[0]+(b[2]-w)/2,b[1]+(b[3]-h)/2,w,h]);if(following && svg._focus)reveal(...svg._focus,{immediate:true});}
      });
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
