'use strict';
(() => {
  const $=id=>document.getElementById(id), view=new WorldAtlasView($('catalog-map'));
  let maps=[],selected=new URLSearchParams(location.search).get('id'),current,sequence=0,difficulty='',node=null;
  const layers={terrain:true,roads:true,stations:true,labels:true};
  const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  async function api(path) {
    const r=await fetch(path);
    if(r.status===401){location.assign('/login?next=/maps');throw Error('请先登录。');}
    const data=await r.json();if(!r.ok)throw Error(data.message||'无法读取地图，请刷新重试。');return data;
  }
  function mapButton(map,world=false) {
    const b=el('button',undefined,'map-choice'+(world?' world-choice':''));b.setAttribute('aria-pressed',String(map.id===selected));
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('class','icon');
    icon.innerHTML=world?'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>':'<use href="/cottage-icons.svg#i-map"/>';
    icon.setAttribute('viewBox','0 0 24 24');b.append(icon,el('strong',map.name));b.onclick=()=>select(map.id);return b;
  }
  function choices() {
    const list=$('catalog-list'),query=$('map-search').value.trim().toLowerCase();list.replaceChildren();
    if(!query||'世界地图'.includes(query))list.append(mapButton({id:'world',name:'世界地图'},true));
    let group;
    for(const map of maps.filter(m=>(!difficulty||m.difficulty===difficulty)&&(!query||(m.name+' '+m.difficulty).toLowerCase().includes(query)))) {
      if(group!==map.difficulty){group=map.difficulty;list.append(el('div',group,'group-label'));}
      list.append(mapButton(map));
    }
    if(!list.children.length)list.append(el('p','没有找到地图','subtle'));
  }
  function paint() {
    if(current)view.setRegion(current.id,current.map,{layers,selected:node,onSelect:selectNode,onMapSelect:selectWorldRegion});
  }
  function selectNode(id) {
    node=id;const place=current.map.locations[id];if(!place)return;
    $('location-sheet').hidden=false;
    $('location-name').textContent=place.name+(place.region_category?' · '+current.map.processing_regions[place.region_category]:'');
    $('location-id').textContent=id;const neighbors=$('neighbors');neighbors.replaceChildren();
    for(const[a,b,w]of current.map.edges) {
      const to=a===id?b:b===id?a:null;if(!to)continue;
      const button=el('button',`${to} · ${w}`);button.title=current.map.locations[to]?.name||to;
      button.onclick=()=>{selectNode(to);view.locate(to);};neighbors.append(button);
    }
    paint();
  }
  function selectWorldRegion(id,place) {
    if(current?.id!=='world')return;
    const region=view.atlas.regions.find(r=>r.id===id);if(!region)return;
    $('location-sheet').hidden=false;$('location-name').textContent=region.name;$('location-id').textContent=region.difficulty+(place?' · '+place:'');
    const open=el('button','打开地区地图');open.onclick=()=>select(id);
    const focus=el('button','定位地区');focus.onclick=()=>view.focusRegion(id);
    $('neighbors').replaceChildren(focus,open);
  }
  async function select(id) {
    selected=id;node=null;choices();const token=++sequence;
    setAppLoading('catalog-loading', true); $('catalog-content').inert = true;
    try {
      await WorldCartography.ready;
      let data;
      if(id==='world') {
        const atlas=await WorldCartography.ready;
        data={id:'world',name:'世界地图',difficulty:'12 个地区',node_count:atlas.regions.reduce((n,r)=>n+Object.keys(r.map.locations).length,0),
          edge_count:atlas.regions.reduce((n,r)=>n+r.map.edges.length,0),task_count:maps.reduce((n,r)=>n+r.task_count,0),
          trigger_nodes:atlas.regions.flatMap(r=>Object.values(r.map.locations).filter(n=>n.kind==='station')),
          version:'世界地理总览',map:{locations:{},edges:[]},regions:atlas.regions};
      } else data=await api('/api/maps/detail?id='+encodeURIComponent(id));
      if(token!==sequence)return;current=data;history.replaceState(null,'','?id='+encodeURIComponent(id));
      $('map-name').textContent=data.name;$('map-difficulty').textContent=data.difficulty;
      $('fact-nodes').textContent=data.node_count;$('fact-edges').textContent=data.edge_count;$('fact-tasks').textContent=data.task_count;$('fact-stations').textContent=data.trigger_nodes.length;
      $('materials-title').textContent=id==='world'?'地区地图':'资料';
      $('materials').replaceChildren();
      if(id==='world')for(const region of data.regions) {
        const b=el('button',region.name,'region-shortcut');b.onclick=()=>{view.focusRegion(region.id);selectWorldRegion(region.id);};$('materials').append(b);
      } else $('materials').append(...(data.materials||[]).map(m=>el('span',m)));
      $('map-version').textContent=data.version||data.variant;
      $('play-map').hidden=id==='world';$('inspect-map').hidden=id==='world';
      if(id!=='world'){$('play-map').href=data.play_url;$('inspect-map').href=data.play_url+'&inspect=1';}
      $('fit').setAttribute('aria-label',id==='world'?'回到世界总览':'回到当前地图范围');
      $('fit').title=id==='world'?'回到世界总览':'回到当前地图范围';
      $('location-sheet').hidden=true; $('catalog-content').hidden=false; paint(); $('catalog-error').hidden=true; $('catalog-retry').hidden=true;
    } catch(e) { if (token !== sequence) return; $('catalog-error').textContent=e.message; $('catalog-error').hidden=false; $('catalog-retry').hidden=false; }
    finally { if (token === sequence) { setAppLoading('catalog-loading', false); $('catalog-content').inert=false; } }
  }
  $('catalog-retry').onclick=()=>current ? select(selected) : location.reload();
  $('map-search').oninput=choices;
  for(const button of $('difficulty-filters').querySelectorAll('button'))button.onclick=()=>{
    difficulty=button.dataset.difficulty;for(const b of $('difficulty-filters').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b===button));choices();
  };
  $('layers-toggle').onclick=()=>{const open=$('layers-menu').hidden;$('layers-menu').hidden=!open;$('layers-toggle').setAttribute('aria-expanded',String(open));};
  for(const checkbox of document.querySelectorAll('[data-layer]'))checkbox.onchange=()=>{layers[checkbox.dataset.layer]=checkbox.checked;paint();};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('layers-menu').hidden=true;$('layers-toggle').setAttribute('aria-expanded','false');}});
  $('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('map-viewport').requestFullscreen();}catch(e){$('catalog-error').textContent=e.message;$('catalog-error').hidden=false;}};
  $('zoom-in').onclick=()=>view.zoom(1.5);$('zoom-out').onclick=()=>view.zoom(1/1.5);$('fit').onclick=()=>view.fit();$('world-extent').onclick=()=>view.showWorld();
  (async()=>{try{maps=(await api('/api/maps')).maps;if(selected!=='world'&&!maps.some(m=>m.id===selected))selected=(maps.find(m=>m.current)||maps[0]).id;await select(selected);}catch(e){setAppLoading('catalog-loading',false);$('catalog-error').textContent=e.message;$('catalog-error').hidden=false;$('catalog-retry').hidden=false;}})();
})();
