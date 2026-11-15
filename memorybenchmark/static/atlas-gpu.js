'use strict';
// A self-hosted, worker-tiled basemap. The SVG foreground retains game IDs.
window.AtlasGpu = class {
  static ready=fetch('/world-gpu.json').then(r=>{if(!r.ok)throw Error('geography unavailable');return r.json();});
  constructor(svg,onReady) {
    this.svg=svg;this.sources=new Map();this.epoch=0;this.visible=new Set();
    this.host=document.createElement('div');this.host.className='atlas-gpu';this.host.setAttribute('aria-hidden','true');svg.before(this.host);
    this.mapElement=document.createElement('div');this.mapElement.style.position='absolute';this.host.append(this.mapElement);
    maplibregl.setWorkerUrl('/maplibre-gl-csp-worker.js');maplibregl.setWorkerCount(2);
    this.map=new maplibregl.Map({container:this.mapElement,interactive:false,attributionControl:false,trackResize:false,renderWorldCopies:false,
      minZoom:-2,maxZoom:22,fadeDuration:100,maxTileCacheSize:96,pixelRatio:Math.min(window.devicePixelRatio||1,1.5),
      style:{version:8,sources:{},layers:[{id:'ocean',type:'background',paint:{'background-color':'#a9c7ca'}}]}});
    this.map.on('error',event=>{this.host.dataset.error=event.error?.message||'map error';});
    this.map.on('idle',()=>{this.host.dataset.idle='true';});
    this.map.on('render',()=>{this.host.dataset.rendered='true';});
    this.map.once('load',()=>{this.loaded=true;this.host.dataset.ready='true';onReady();});
    AtlasGpu.ready.then(value=>{this.metadata=value;onReady();}).catch(error=>{this.host.dataset.error=error.message;});
  }
  source(key,record,opacity,order) {
    this.visible.add(key);let source=this.sources.get(key);
    if(!source) {
      this.host.dataset.idle='false';
      this.map.addSource(key,{type:'geojson',data:record.url,tolerance:.5,buffer:32,maxzoom:14});
      const before=this.map.getStyle().layers.find(layer=>layer.metadata?.atlasOrder>order)?.id;
      const alpha=['*',['get','opacity'],opacity];
      this.map.addLayer({id:key+'-fill',type:'fill',source:key,metadata:{atlasOrder:order},filter:['all',['>=',['zoom'],['get','minZoom']],['==',['geometry-type'],'Polygon'],['!=',['get','fill'],'none']],
        paint:{'fill-color':['get','fill'],'fill-opacity':['*',alpha,['get','fillOpacity']],'fill-antialias':true}},before);
      this.map.addLayer({id:key+'-line',type:'line',source:key,metadata:{atlasOrder:order},filter:['all',['>=',['zoom'],['get','minZoom']],['!=',['get','stroke'],'none']],layout:{'line-cap':'round','line-join':'round'},
        paint:{'line-color':['get','stroke'],'line-opacity':alpha,'line-width':['interpolate',['exponential',2],['zoom'],0,['case',['get','fixed'],['get','width'],['*',['get','width'],512/360000]],22,['case',['get','fixed'],['get','width'],['*',['get','width'],512*2**22/360000]]]}},before);
      source={record,opacity,order,touched:++this.epoch};this.sources.set(key,source);
    } else {
      source.touched=++this.epoch;
      if(source.opacity!==opacity) {
        this.map.setPaintProperty(key+'-fill','fill-opacity',['*',['get','opacity'],['get','fillOpacity'],opacity]);
        this.map.setPaintProperty(key+'-line','line-opacity',['*',['get','opacity'],opacity]);source.opacity=opacity;
      }
    }
  }
  sync(box,regions,terrain) {
    if(!this.loaded||!this.metadata)return;
    const width=this.svg.clientWidth,height=this.svg.clientHeight,u=box[2]/width;
    // At planetary scale, keep the single world inside its real projected
    // rectangle. This avoids the engine's minimum-zoom constraint and wrapping.
    const left=Math.max(0,-box[0]/u),top=Math.max(0,-box[1]/u);
    const mapWidth=Math.max(1,Math.min(width,(360000-box[0])/u)-left),mapHeight=Math.max(1,Math.min(height,(360000-box[1])/u)-top);
    this.offset=[left,top];this.mapElement.style.left=left+'px';this.mapElement.style.top=top+'px';
    if(mapWidth!==this.width||mapHeight!==this.height){this.width=mapWidth;this.height=mapHeight;this.mapElement.style.width=mapWidth+'px';this.mapElement.style.height=mapHeight+'px';this.map.resize();}
    const zoom=Math.log2(360000/(u*512)),x=box[0]+(left+mapWidth/2)*u,y=box[1]+(top+mapHeight/2)*u;
    this.map.jumpTo({center:[x/1000-180,Math.atan(Math.sinh((180-y/1000)*Math.PI/180))*180/Math.PI],zoom});
    this.host.style.visibility=terrain?'visible':'hidden';this.visible.clear();
    if(terrain) {
      this.source('overview',this.metadata.overview,1,1);
      if(zoom>3.1) {
        const opacity=atlasBlend(zoom,3.3,5.3);
        if(!this.map.getLayer('coast-ocean'))this.map.addLayer({id:'coast-ocean',type:'background',metadata:{atlasOrder:1.5},paint:{'background-color':'#a9c7ca','background-opacity':opacity}},this.map.getStyle().layers.find(l=>l.metadata?.atlasOrder>=2)?.id);
        else if(this.coastOpacity!==opacity)this.map.setPaintProperty('coast-ocean','background-opacity',opacity);
        this.coastOpacity=opacity;
        this.source('coast',this.metadata.coast,opacity,2);
      } else if(this.map.getLayer('coast-ocean'))this.map.setPaintProperty('coast-ocean','background-opacity',0);
      if(zoom>3.6)this.source('physical',this.metadata.physical,atlasBlend(zoom,3.8,5.6),3);
      for(const region of regions) {
        const entry=this.metadata.regions[region.id];if(!entry)continue;
        const context=region.context;
        if(context&&zoom>5) {
          const[a,b,w,h]=context.view_box;
          if(a+w>box[0]&&a<box[0]+box[2]&&b+h>box[1]&&b<box[1]+box[3])this.source(region.id+'-context',entry.context,atlasBlend(zoom,5.2,7.3),4);
        }
        const[a,b,w,h]=region.view_box,opacity=atlasBlend(Math.max(w/u,h/u),100,340);
        if(opacity>.02&&a+w>box[0]&&a<box[0]+box[2]&&b+h>box[1]&&b<box[1]+box[3])this.source(region.id+'-detail',entry.detail,opacity,5);
      }
    }
    for(const[key,s]of this.sources)if(!this.visible.has(key)&&s.opacity!==0){this.map.setPaintProperty(key+'-fill','fill-opacity',0);this.map.setPaintProperty(key+'-line','line-opacity',0);s.opacity=0;}
    // Keep at most three inactive regional sources; global sources are reused.
    const inactive=[...this.sources].filter(([k])=>k.includes('-')&&!this.visible.has(k)).sort((a,b)=>a[1].touched-b[1].touched);
    for(const[key]of inactive.slice(0,Math.max(0,inactive.length-3))){this.map.removeLayer(key+'-fill');this.map.removeLayer(key+'-line');this.map.removeSource(key);this.sources.delete(key);}
    this.host.dataset.sources=String(this.sources.size);
  }
};
