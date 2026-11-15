'use strict';
// Continuous camera styling, including fractional zoom levels.
const atlasBlend=(value,low,high)=>{const t=Math.max(0,Math.min(1,(value-low)/(high-low)));return t*t*(3-2*t);};
async function atlasText(asset) {
  if(typeof DecompressionStream!=='undefined') {
    const response=await fetch(asset+'.gz');
    if(response.ok)return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text();
  }
  const response=await fetch(asset);if(!response.ok)throw Error(asset);return response.text();
}
// Human display only. Game IDs, observations and action targets remain local.
window.WorldCartography = {
  ready: atlasText('/world-atlas.json').then(JSON.parse)
};

window.WorldAtlasView = class extends AtlasView {
  constructor(svg) {
    super(svg);
    this.detailImages = new Map();
    this.contextLayers = new Map();
    this.credit = document.createElement('div');
    this.credit.className = 'world-credit';
    this.credit.innerHTML = '<span class="world-scale"></span><span>Natural Earth · © OpenStreetMap contributors</span>';
    this.legend=document.createElement('span');this.legend.className='world-region-legend';this.legend.hidden=true;
    this.legend.innerHTML='<i style="background:#7c9a75"></i>自然区域 <i style="background:#bd9971"></i>人类聚居区 <i style="background:#a192b4"></i>动物栖息区';
    this.credit.prepend(this.legend);
    svg.parentElement.append(this.credit);
    WorldCartography.ready.then(atlas => {
      this.atlas = atlas;
      if (this.pending) this.setRegion(...this.pending);
    }).catch(error => { this.credit.textContent = error.message; });
  }

  setRegion(id, data, options = {}) {
    this.pending = [id, data, options];
    if (!this.atlas) return;
    this.options = options;
    let region = this.atlas.regions.find(r => r.id === id);
    if (id !== 'world' && !region) return;
    if (region && data?.projection === 'world-atlas-1') region = {...region, map:data, view_box:data.view_box};
    this.activeId = id;
    this.data = region?.map || {locations:{}, edges:[]};
    this.base = region?.view_box || this.atlas.world_box;
    this.homeRegion = region;
    // AtlasView's keyboard and pointer handlers dispatch through this callback.
    this.options = {...options, onSelect: value => {
      if (value.startsWith('map:')) {
        const target = value.slice(4);
        this.focusRegion(target);
        options.onMapSelect?.(target);
      } else if (id === 'world') {
        const [target, node] = value.split('/');
        options.onMapSelect?.(target, node);
      } else options.onSelect?.(value);
    }};
    const cameraKey=options.cameraKey||id;
    if (this.key !== cameraKey) { this.key = cameraKey; this.annotationKey=null; this.fit(); }
    else this.paint();
  }

  limits() {
    const smallest = this.homeRegion?.view_box[2] || 15;
    const aspect = this.svg.clientWidth / Math.max(1, this.svg.clientHeight);
    return [smallest / 16, Math.max(360000, 360000 * aspect) * 1.1];
  }

  zoom(factor, x, y) {
    if (!this.box) return;
    const r = this.svg.getBoundingClientRect(), b = this.box;
    const a = (x ?? r.left+r.width/2)-r.left, c = (y ?? r.top+r.height/2)-r.top;
    const [minimum, maximum] = this.limits();
    const w = Math.max(minimum, Math.min(maximum, b[2]/factor)), h = w*r.height/Math.max(1,r.width);
    this.box = [b[0]+a/r.width*(b[2]-w), b[1]+c/r.height*(b[3]-h), w, h];
    this.overview = false; this.paint();
  }

  showWorld() { this.fitBox(this.atlas?.world_box); }
  focusRegion(id) { this.fitBox(this.atlas?.regions.find(r => r.id === id)?.view_box); }
  fitBox(box) {
    if (!box) return;
    const previous = this.base;
    this.base = box; super.fit(); this.base = previous;
    this.overview = false;
  }
  locate(id) {
    const n = this.homeRegion?.map.locations[id || this.options.location];
    if (!n) return;
    const w = this.homeRegion.view_box[2] * .35;
    const aspect = this.svg.clientWidth / Math.max(1,this.svg.clientHeight);
    this.box = [n.x-w/2,n.y-w/aspect/2,w,w/aspect];
    this.overview = false; this.paint();
  }

  pickNode(event) {
    const explicit=event.target.closest('[data-node]')?.dataset.node;
    if(explicit?.startsWith('map:')||event.target.localName==='text')return explicit;
    const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(this.svg.getScreenCTM().inverse());
    const u=this.box[2]/this.svg.clientWidth;
    let selected=null,distance=15;
    for(const region of this.expandedRegions||[])for(const[id,n]of Object.entries(region.map.locations)) {
      const candidate=Math.hypot(n.x-point.x,n.y-point.y)/u;
      if(candidate<distance){distance=candidate;selected=this.activeId==='world'?region.id+'/'+id:id;}
    }
    return selected||explicit;
  }

  setup() {
    if(this.worldDrawing)return;
    try {
      this.gpu=new AtlasGpu(this.svg,()=>this.paint());
      this.worldGround=this.el('rect',{fill:'#a9c7ca'});this.worldNames=this.el('g',{'aria-hidden':'true'});
      this.worldDrawing=this.el('g');this.worldPins=this.el('g');this.svg.classList.add('world-atlas','world-gpu');
      this.svg.replaceChildren(this.worldGround,this.worldNames,this.worldDrawing,this.worldPins);
    } catch(error) {this.svg.parentElement.querySelector('.atlas-gpu')?.remove();this.gpu=null;this.setupVector();}
  }

  setupVector() {
    if (this.worldDrawing) return;
    this.worldGround = this.el('rect', {fill:'#a9c7ca'});
    this.svg.classList.add('world-atlas');
    this.worldImage = this.el('g');
    atlasText(this.atlas.world_asset).then(text=>{
      const documentRoot=new DOMParser().parseFromString(text,'image/svg+xml').documentElement;
      for(const path of documentRoot.querySelectorAll('path')) {
        const copy=document.importNode(path,true);
        copy.setAttribute('stroke-width','.65');copy.setAttribute('vector-effect','non-scaling-stroke');
        this.worldImage.append(copy);
      }
    }).catch(()=>{this.credit.textContent='世界底图暂不可用，请刷新重试。';});
    this.coastImage=this.el('g',{'data-ready':'false'});
    this.coastImage.setAttribute('data-basemap','coast');
    this.physicalLayer=this.el('g',{'data-ready':'false'});
    this.worldContexts=this.el('g');
    this.worldDetails = this.el('g');
    this.worldNames = this.el('g', {'aria-hidden':'true'});
    this.worldDrawing = this.el('g');
    this.worldPins = this.el('g');
    this.svg.replaceChildren(this.worldGround,this.worldImage,this.coastImage,this.physicalLayer,this.worldContexts,this.worldDetails,this.worldNames,this.worldDrawing,this.worldPins);
  }

  loadVector(asset,key) {
    const group=this.el('g',{'data-geography-layer':key,'aria-hidden':'true'});
    group.style.opacity='0';group.dataset.ready='false';
    atlasText(asset).then(text=>{
      const root=new DOMParser().parseFromString(text,'image/svg+xml').documentElement;
      // Each inline reference window owns its masks, even on the combined map.
      const prefix='geo-'+key+'-';
      for(const element of root.querySelectorAll('*')) {
        if(element.id)element.id=prefix+element.id;
        for(const attr of ['fill','clip-path','mask'])if(element.getAttribute(attr)?.includes('url(#'))element.setAttribute(attr,element.getAttribute(attr).replaceAll('url(#','url(#'+prefix));
      }
      for(const child of [...root.children])if(!['title','desc'].includes(child.localName))group.append(document.importNode(child,true));
      group.dataset.ready='true';this.paint();
    }).catch(()=>{group.dataset.failed='true';});
    return group;
  }

  styleLayer(group,opacity) {
    group.style.opacity=group.dataset.ready==='false'?'0':String(opacity);
    group.style.visibility=opacity>.001?'visible':'hidden';
  }

  paint() {
    if(this.pendingFrame)return;
    this.pendingFrame=requestAnimationFrame(()=>{this.pendingFrame=0;this.render();});
  }

  render() {
    if (!this.atlas || !this.box || !this.svg.clientWidth) return;
    const started=performance.now();
    this.setup();
    const b=this.box, o=this.options || {}, u=b[2]/this.svg.clientWidth;
    const centreY=b[1]+b[3]/2;
    b[3]=b[2]*this.svg.clientHeight/this.svg.clientWidth;b[1]=centreY-b[3]/2;
    // Keep panning bounded to the planet, including while zoomed out.
    const cx=Math.max(0,Math.min(360000,b[0]+b[2]/2)),cy=Math.max(0,Math.min(360000,b[1]+b[3]/2));
    b[0]=cx-b[2]/2;b[1]=cy-b[3]/2;
    this.svg.setAttribute('viewBox',b.join(' '));
    for (const [k,v] of Object.entries({x:b[0],y:b[1],width:b[2],height:b[3]})) this.worldGround.setAttribute(k,v);
    const regions=this.activeId==='world'?this.atlas.regions:[this.homeRegion];
    const zoom=Math.log2(360000/(u*512)),terrain=o.layers?.terrain!==false;
    if(this.gpu) {
      this.gpu.sync(b,regions,terrain);
      this.worldGround.style.display=terrain?'none':'';
    } else {
    this.worldImage.setAttribute('visibility',terrain?'visible':'hidden');
    this.worldDetails.setAttribute('visibility',terrain?'visible':'hidden');
    if(zoom>3.1&&!this.globalDetailsStarted) {
      this.globalDetailsStarted=true;
      const coast=this.loadVector(this.atlas.layers.coast.asset,'coast');coast.setAttribute('data-basemap','coast');
      this.coastImage.replaceWith(coast);this.coastImage=coast;
      const physical=this.loadVector(this.atlas.layers.physical.asset,'physical');
      this.physicalLayer.replaceWith(physical);this.physicalLayer=physical;
    }
    this.styleLayer(this.coastImage,terrain?atlasBlend(zoom,3.3,5.3):0);
    this.styleLayer(this.physicalLayer,terrain?atlasBlend(zoom,3.8,5.6):0);
    this.worldContexts.setAttribute('visibility',terrain?'visible':'hidden');
    }
    const annotationKey=[this.key,this.activeId,u.toPrecision(4),o.selected,o.location,o.target,o.frames?.length,...Object.values(o.layers||{}),...(o.neighbors||[]),JSON.stringify(o.nodeNotes||{})].join('|');
    const old=this.annotationBox;
    if(annotationKey===this.annotationKey&&old&&Math.abs(old[0]-b[0])<70*u&&Math.abs(old[1]-b[1])<70*u){this.finishFrame(started);return;}
    this.annotationKey=annotationKey;this.annotationBox=[...b];
    this.annotationBuilds=(this.annotationBuilds||0)+1;
    const focused=document.activeElement?.getAttribute('data-node');
    this.worldNames.replaceChildren();this.worldDrawing.replaceChildren();this.worldPins.replaceChildren();
    for (const image of this.detailImages.values()) this.styleLayer(image,0);
    for (const layer of this.contextLayers.values()) this.styleLayer(layer,0);
    this.expandedRegions=[];
    for (const region of regions) {
      const [x,y,w,h]=region.view_box;
      const visible=x+w>b[0]&&x<b[0]+b[2]&&y+h>b[1]&&y<b[1]+b[3];
      const span=Math.max(w/u,h/u),detailOpacity=atlasBlend(span,100,340);
      const context=region.context;
      if(context&&!this.gpu) {
        const [a,c,d,e]=context.view_box;
        if(a+d>b[0]&&a<b[0]+b[2]&&c+e>b[1]&&c<b[1]+b[3]&&zoom>5) {
          let layer=this.contextLayers.get(region.id);
          if(!layer){layer=this.loadVector(context.asset,region.id+'-context');this.contextLayers.set(region.id,layer);this.worldContexts.append(layer);}
          this.styleLayer(layer,atlasBlend(zoom,5.2,7.3));
        }
      }
      const expanded=visible&&detailOpacity>.02;
      if (expanded) {
        this.expandedRegions.push(region);
        if(!this.gpu) {
        let image=this.detailImages.get(region.id);
        if (!image) {
          image=this.loadVector(region.terrain_asset,region.id+'-detail');
          image.setAttribute('data-detail-map',region.id);
          this.detailImages.set(region.id,image);this.worldDetails.append(image);
        }
        this.styleLayer(image,detailOpacity);
        }
        const drawing=this.el('g',{'data-network-map':region.id,opacity:detailOpacity});this.worldDrawing.append(drawing);
        if(detailOpacity>.15)this.drawRegion(region,u,drawing);
      }
    }
    if (o.layers?.labels!==false) {this.drawCountryNames(u);this.drawPlaceNames(u,zoom);}
    this.drawRegionPins(regions,u);
    this.legend.hidden=!this.expandedRegions.some(r=>Object.keys(r.map.processing_regions).length);
    if(focused)this.svg.querySelector('[data-node="'+CSS.escape(focused)+'"]')?.focus({preventScroll:true});
    const latitude=Math.atan(Math.sinh((180-(b[1]+b[3]/2)/1000)*Math.PI/180));
    const metres=u*111.195*Math.cos(latitude), target=metres*80;
    const power=10**Math.floor(Math.log10(Math.max(.001,target)));
    const distance=[1,2,5,10].map(n=>n*power).filter(n=>n<=target).at(-1)||power;
    const scale=this.credit.querySelector('.world-scale');
    if(scale) { scale.style.width=(distance/metres)+'px';scale.textContent=distance>=1000?(distance/1000)+' km':Math.round(distance)+' m'; }
    this.finishFrame(started);
  }

  finishFrame(started) {
    this.frameCount=(this.frameCount||0)+1;
    this.svg.dataset.renderCount=String(this.frameCount);this.svg.dataset.annotationBuilds=String(this.annotationBuilds||0);
    this.svg.dataset.lastRenderMs=(performance.now()-started).toFixed(2);
    clearTimeout(this.cameraSaveTimer);this.cameraSaveTimer=setTimeout(()=>this.options.onCameraChange?.([...this.box]),180);
  }

  drawCountryNames(u) {
    const b=this.box;
    if(b[2]<100000&&b[2]>1500) for(const c of this.atlas.countries) {
      if(c.rank> (b[2]<20000?7:3)||c.x<b[0]||c.x>b[0]+b[2]||c.y<b[1]||c.y>b[1]+b[3])continue;
      this.worldNames.append(this.el('text',{x:c.x,y:c.y,'text-anchor':'middle','font-size':12*u,class:'world-country'},c.name));
    }
    if(b[2]>110000) for(const [name,lon,lat] of [['北美洲',-110,60],['南美洲',-48,-6],['欧洲',-8,64],['非洲',20,0],['亚洲',92,26],['大洋洲',130,-15]]) {
      const x=(lon+180)*1000,y=(180-Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))*180/Math.PI)*1000;
      this.worldNames.append(this.el('text',{x,y,'text-anchor':'middle','font-size':13*u,class:'world-continent'},name));
    }
  }

  drawPlaceNames(u,zoom) {
    if(zoom<5.6)return;
    const b=this.box,occupied=[],candidates=this.atlas.layers.places.filter(p=>p.name&&p.x>b[0]+35*u&&p.x<b[0]+b[2]-35*u&&p.y>b[1]+25*u&&p.y<b[1]+b[3]-25*u&&p.rank<=(zoom<7?4:zoom<9?6:9));
    candidates.sort((a,c)=>c.population-a.population||a.rank-c.rank);
    for(const p of candidates) {
      const width=Math.max(45,p.name.length*6.8),x=(p.x-b[0])/u,y=(p.y-b[1])/u;
      if(occupied.some(q=>Math.abs(x-q.x)<(width+q.width)/2+16&&Math.abs(y-q.y)<42))continue;
      occupied.push({x,y,width});
      this.worldNames.append(this.el('circle',{cx:p.x,cy:p.y,r:1.6*u,fill:'#8d917d'}));
      this.worldNames.append(this.el('text',{x:p.x,y:p.y-7*u,'text-anchor':'middle','font-size':10*u,class:'world-place',opacity:atlasBlend(zoom,5.6,6.5)},p.name));
      if(occupied.length>=20)break;
    }
  }

  drawRegion(region,u,drawing=this.worldDrawing) {
    const d=region.map,o=this.options,b=this.box;
    const own=this.activeId!=='world', detail=b[2]<region.view_box[2]*.7;
    const dense=Object.keys(d.locations).length>60;
    const path=(a,c)=>'M'+d.edge_paths[[a,c].sort().join('|')].map(p=>p.join(' ')).join('L');
    if(o.layers?.roads!==false) {
      const ferries=new Set(d.ferry_edges.map(e=>[...e].sort().join('|'))),roads=[],water=[];
      for(const[a,c]of d.edges)(ferries.has([a,c].sort().join('|'))?water:roads).push(path(a,c));
      drawing.append(this.el('path',{d:roads.join(''),class:'geo-road'}),this.el('path',{d:water.join(''),class:'geo-road geo-ferry'}));
    }
    if(own&&o.layers?.trace!==false) {
      let last;const trace=[];
      for(const f of o.frames||[]) {if(last&&last!==f.location&&f.action?.type==='move'&&d.edge_paths[[last,f.location].sort().join('|')])trace.push(path(last,f.location));last=f.location;}
      if(trace.length)drawing.append(this.el('path',{d:trace.join(''),class:'geo-trace'}));
    }
    for(const[id,n]of Object.entries(d.locations)) {
      if(n.x<b[0]-150*u||n.x>b[0]+b[2]+150*u||n.y<b[1]-150*u||n.y>b[1]+b[3]+150*u)continue;
      if(n.kind==='station'&&o.layers?.stations===false)continue;
      const here=own&&id===o.location,target=own&&id===o.target,transit=n.transit||n.kind==='junction';
      const selected=own&&id===o.selected,near=own&&o.neighbors?.includes(id);
      const size=(here||target||selected?6:detail?transit?2.2:5:transit?1.2:2.5)*u;
      const g=this.el('g',{transform:`translate(${n.x} ${n.y})`,'data-node':own?id:region.id+'/'+id,role:'button',tabindex:'0','aria-label':`${region.name} ${n.name} ${id}`});
      g.append(this.el('title',{},`${n.name} ${id}${n.region_category?' · '+d.processing_regions[n.region_category]:''}`));
      g.append(this.el('circle',{r:15*u,class:'geo-selected',opacity:selected?'1':'0'}));
      if(here)g.append(this.el('circle',{r:15*u,class:'geo-halo'}));
      const cls=here?'geo-current':target?'geo-goal':n.kind==='station'?'geo-dot geo-station':transit?'geo-transit':'geo-dot';
      if(n.kind==='station')g.append(this.el('rect',{x:-size,y:-size,width:size*2,height:size*2,rx:1.5*u,class:cls,...(n.region_category?{style:'fill:'+({natural:'#7c9a75',settlement:'#bd9971',habitat:'#a192b4'}[n.region_category])}:{})}));
      else if(n.kind==='camp')g.append(this.el('path',{d:`M0 ${-8*u}L${8*u} ${6*u}H${-8*u}Z`,class:cls}));
      else g.append(this.el('circle',{r:size,class:cls}));
      if(o.layers?.labels!==false&&(here||target||selected||near||n.kind==='camp'||(!dense||detail)&&!transit)) {
        g.append(this.el('text',{x:0,y:-12*u,'text-anchor':'middle','font-size':11*u},id));
        if(here||selected||detail&&b[2]<region.view_box[2]*.35)g.append(this.el('text',{x:0,y:22*u,'text-anchor':'middle','font-size':10*u},n.name));
      }
      if(o.nodeNotes?.[id]&&(detail||selected))g.append(this.el('text',{x:0,y:36*u,'text-anchor':'middle','font-size':10*u,class:'world-node-note'},o.nodeNotes[id]));
      drawing.append(g);
    }
  }

  drawRegionPins(regions,u) {
    const b=this.box,occupied=[];
    for(const region of regions) {
      const [x,y,w,h]=region.view_box,cx=x+w/2,cy=y+h/2;
      if(cx<b[0]-80*u||cx>b[0]+b[2]+80*u||cy<b[1]-40*u||cy>b[1]+b[3]+40*u)continue;
      const pinOpacity=1-atlasBlend(Math.max(w/u,h/u),140,340);
      if(pinOpacity<.05)continue;
      const g=this.el('g',{'data-node':'map:'+region.id,role:'button',tabindex:'0','aria-label':`查看${region.name}`,opacity:pinOpacity});
      g.append(this.el('circle',{cx,cy,r:14*u,fill:'transparent','pointer-events':'all'}));
      g.append(this.el('circle',{cx,cy,r:6*u,class:'world-map-pin'}));
      if(this.options.layers?.labels!==false) {
        const width=region.name.length*13+14;
        let dx=12,dy=-12;
        for(const [ox,oy]of [[12,-12],[12,24],[-width-12,-12],[-width-12,24],[12,-40],[12,50],[-width-12,-40],[-width-12,50],[12,-70],[-width-12,80],[12,105]]) {
          dx=ox;dy=oy;
          const box=[cx/u+dx,cy/u+dy-15,width,23];
          const inside=box[0]>=b[0]/u+8&&box[0]+width<=b[0]/u+this.svg.clientWidth-8&&box[1]>=b[1]/u+8&&box[1]+23<=b[1]/u+this.svg.clientHeight-8;
          if(inside&&!occupied.some(p=>box[0]<p[0]+p[2]&&box[0]+box[2]>p[0]&&box[1]<p[1]+p[3]&&box[1]+box[3]>p[1])){occupied.push(box);break;}
        }
        dx=Math.max(b[0]/u+8-cx/u,Math.min(b[0]/u+this.svg.clientWidth-width-8-cx/u,dx));
        dy=Math.max(b[1]/u+23-cy/u,Math.min(b[1]/u+this.svg.clientHeight-8-cy/u,dy));
        const left=Math.min(cx-14*u,cx+dx*u),top=Math.min(cy-14*u,cy+(dy-17)*u);
        const right=Math.max(cx+14*u,cx+(dx+width)*u),bottom=Math.max(cy+14*u,cy+(dy+7)*u);
        g.prepend(this.el('rect',{x:left,y:top,width:right-left,height:bottom-top,fill:'transparent','pointer-events':'all'}));
        g.append(this.el('path',{d:`M${cx} ${cy}L${cx+dx*u} ${cy+dy*u}`,class:'world-pin-leader'}));
        g.append(this.el('text',{x:cx+dx*u,y:cy+dy*u,'font-size':12*u,class:'world-map-name'},region.name));
      }
      this.worldPins.append(g);
    }
  }
};
