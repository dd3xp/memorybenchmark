/* Visual game world. Geography and events come only from public observations.
   Decorative vegetation is fixed scenery, never an experience or a game rule. */
window.WorldScene = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const lakePath = 'M240 580 C300 550 340 500 400 470 L930 190 Q1000 150 1040 205 L1010 280 Q890 370 800 405 L390 600 Q290 650 240 580Z';
  let audio, soundEnabled = false;
  try{soundEnabled=localStorage.getItem('cartography.sound')==='on';}catch(_){/* Optional preference. */}
  document.getElementById('sound-toggle').textContent=`音效：${soundEnabled?'开':'关'}`;
  const reduced = () => matchMedia('(prefers-reduced-motion:reduce)').matches;
  function make(tag, attrs={}, text) {
    const node=document.createElementNS(NS,tag);
    Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));
    if(text!==undefined)node.textContent=text;
    return node;
  }
  function path(d,fill,extra={}) { return make('path',{d,fill,...extra}); }
  function tree(x,y,size,kind) {
    const group=make('g',{transform:`translate(${x} ${y}) scale(${size})`});
    group.append(make('ellipse',{cx:4,cy:3,rx:14,ry:6,fill:'#173a2a',opacity:.3}),path('M-2 3 L-2 -22 L3 -22 L3 3Z','#675337'));
    if(kind) {
      group.append(path('M-16 -9 L0 -43 L18 -9Z','#294f36'),path('M-13 -18 L0 -49 L14 -18Z','#3b6440'),path('M-10 -28 L0 -53 L10 -28Z','#5c7f43'));
      group.append(path('M0 -49 L-10 -28 L0 -31Z','#82984f',{opacity:.6}));
    } else {
      group.append(path('M-13 -9 C-27 -19 -17 -33 -12 -32 C-18 -47 1 -55 10 -42 C26 -46 32 -27 21 -21 C29 -8 10 -2 2 -9 C-3 -2 -11 -3 -13 -9Z','#355839'));
      group.append(path('M-13 -22 C-23 -30 -9 -40 -3 -36 C-4 -49 11 -46 12 -36 C25 -36 24 -23 16 -22 C9 -13 -1 -20 -5 -16Z','#648344'));
      group.append(make('ellipse',{cx:0,cy:-35,rx:6,ry:4,fill:'#91a157',opacity:.5}));
    }
    return group;
  }
  function rock(x,y,size=1) {
    const group=make('g',{transform:`translate(${x} ${y}) scale(${size})`});
    group.append(make('ellipse',{cx:2,cy:3,rx:16,ry:6,fill:'#203b2f',opacity:.3}),path('M-16 0 L-12 -14 L-2 -21 L12 -15 L17 -3 L7 3Z','#899183'),path('M-12 -14 L-2 -21 L12 -15 L1 -10 L-16 0Z','#b2b5a0'),path('M1 -10 L12 -15 L17 -3 L7 3Z','#657269'));
    return group;
  }
  function camp() {
    const group=make('g',{class:'landmark-art camp-art'});
    group.append(make('ellipse',{cx:0,cy:6,rx:29,ry:10,fill:'#1a3528',opacity:.35}));
    group.append(path('M-27 2 L-12 -31 L17 -25 L29 3 L-5 7Z','#bd8b43'),path('M-12 -31 L17 -25 L3 4 L-27 2Z','#ead59a'),path('M17 -25 L29 3 L3 4Z','#9e7138'));
    group.append(path('M-12 -26 L-22 1 L-4 4Z','#3e4a36'),path('M-12 -26 L-4 4 L-11 1Z','#bfac72'));
    group.append(path('M-12 -36 L-12 -27 M19 -30 L19 -20','#fff',{stroke:'#745b32','stroke-width':2}));
    group.append(path('M-33 -35 L-33 4','#fff',{stroke:'#665038','stroke-width':2}),path('M-32 -35 L-17 -31 L-32 -26Z','#e2c67b'));
    const fire=make('g',{class:'camp-fire',transform:'translate(27 12)'});
    fire.append(make('ellipse',{rx:9,ry:5,fill:'#1c3325'}),path('M-6 2 L6 -2 M-5 -3 L6 3','none',{stroke:'#947246','stroke-width':3}),path('M-5 -2 Q-8 -8 -2 -12 Q-2 -6 2 -15 Q10 -5 5 -2Z','#db8840'),path('M-2 -2 Q-4 -7 1 -9 Q6 -4 2 -2Z','#ffda7b'));
    group.append(fire); return group;
  }
  function waypoint(node) {
    const group=make('g',{class:'landmark-art waypoint-art'});
    group.append(make('ellipse',{cy:5,rx:16,ry:6,fill:'#1b3428',opacity:.4}));
    if(/岩|坡|岭|肩/.test(node.name)) {const stone=rock(-10,0,.7);group.append(stone);}
    group.append(path('M-2 4 L-2 -21 L2 -21 L2 4Z','#8c6f45'),path('M-12 -26 L11 -26 L15 -21 L11 -16 L-12 -16Z','#c7b487',{stroke:'#705d3c','stroke-width':1.2}),path('M-8 -22 L6 -22','none',{stroke:'#85734e','stroke-width':1}));
    return group;
  }
  function explorer() {
    const art=make('g',{class:'explorer-art'});
    art.append(make('ellipse',{class:'hero-shadow',cy:4,rx:12,ry:5,fill:'#102e26',opacity:.5}));
    const body=make('g',{class:'hero-body'});
    body.append(path('M-9 -24 Q-17 -18 -14 -8 L-8 -8 L-5 -24Z','#7c5d32'));
    body.append(path('M-7 -12 L-7 -1 L-1 0 L1 -13Z','#3c4937',{class:'hero-leg left-leg'}),path('M2 -13 L3 0 L9 0 L8 -14Z','#304335',{class:'hero-leg right-leg'}));
    body.append(path('M-8 -2 L-9 2 L-1 2 L-1 -2Z','#493e30'),path('M3 -2 L3 2 L11 2 L9 -2Z','#493e30'));
    body.append(path('M-9 -29 Q0 -34 10 -28 L10 -12 Q0 -7 -10 -13Z','#d3aa59'),path('M1 -30 L9 -28 L9 -13 L1 -10Z','#a9813c'));
    body.append(path('M-9 -27 L-15 -18 L-12 -15 L-5 -23Z','#d6b678',{class:'hero-arm'}),path('M9 -27 L15 -17 L12 -14 L5 -23Z','#e7c18c'));
    body.append(path('M15 -18 L18 3','none',{stroke:'#795a37','stroke-width':2.4}));
    body.append(make('ellipse',{cx:0,cy:-38,rx:9,ry:10,fill:'#e8c491'}),path('M-9 -41 Q-9 -51 0 -51 Q12 -49 9 -38 L5 -43Z','#564638'));
    body.append(make('ellipse',{cx:-1,cy:-46,rx:15,ry:4,fill:'#795e39'}),path('M-10 -47 L-8 -56 Q-1 -60 6 -55 L9 -47Z','#ba9955'),path('M-9 -48 Q0 -45 9 -48','none',{stroke:'#4e6340','stroke-width':3}));
    body.append(path('M-5 -30 L4 -29 L6 -24 L-1 -25Z','#bb6346'));
    art.append(body);return art;
  }
  function prepare(svg,o) {
    if(svg.dataset.world!=='true')return;
    const key=o.environment?.id==='lake-easy'?'lake':'legacy';
    if(svg._worldBuilt===key)return;
    if(svg._worldBuilt){
      ['scene-ground','scene-water','scene-fog-fade','scene-fog-mask','scene-lake-clip','explorer'].forEach(id=>svg.querySelector('#'+id)?.remove());
      svg.querySelector('.world-fog')?.remove();document.querySelector('#portrait')?.replaceChildren();
    }
    svg.querySelector('.terrain')?.remove();
    const defs=svg.querySelector('defs');
    const ground=make('pattern',{id:'scene-ground',patternUnits:'userSpaceOnUse',width:600,height:400});
    ground.append(make('image',{href:'/terrain-ground.png',width:600,height:400})); defs.append(ground);
    const water=make('linearGradient',{id:'scene-water',x1:'0',y1:'0',x2:'0',y2:'1'});
    water.append(make('stop',{offset:'0%','stop-color':'#5a9795'}),make('stop',{offset:'65%','stop-color':'#386f79'}),make('stop',{offset:'100%','stop-color':'#234e63'}));defs.append(water);
    const fogFade=make('radialGradient',{id:'scene-fog-fade'});
    fogFade.append(make('stop',{offset:'0%','stop-color':'black'}),make('stop',{offset:'65%','stop-color':'black'}),make('stop',{offset:'100%','stop-color':'black','stop-opacity':0}));defs.append(fogFade);
    const mask=make('mask',{id:'scene-fog-mask',maskUnits:'userSpaceOnUse',x:-1200,y:-800,width:3600,height:2400});
    mask.append(make('rect',{x:-1200,y:-800,width:3600,height:2400,fill:'white'}),make('g',{id:'scene-revealed'}));defs.append(mask);
    const scenery=make('g',{class:'terrain world-terrain','aria-hidden':'true'});
    scenery.append(make('rect',{x:-1200,y:-800,width:3600,height:2400,fill:'url(#scene-ground)'}),make('rect',{x:-1200,y:-800,width:3600,height:2400,fill:'#6d8c50',opacity:.2}));
    // Fixed terrain decorations are independent of all hidden location metadata.
    let seed=1703; const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
    const lakeTest=make('path',{d:lakePath});
    for(let i=0;i<380;i++){
      const x=-400+random()*2000,y=-300+random()*1400;
      if(o.environment?.id==='lake-easy' && lakeTest.isPointInFill(new DOMPoint(x,y)))continue;
      if(random()<.82)scenery.append(tree(x,y,.6+random()*.8,random()>.35)); else scenery.append(rock(x,y,.5+random()*.65));
    }
    if(o.environment?.id==='lake-easy'){
      scenery.append(path(lakePath,'#577057',{stroke:'#526d40','stroke-width':16,'stroke-linejoin':'round'}),path(lakePath,'url(#scene-water)',{stroke:'#a8be87','stroke-width':4,'stroke-linejoin':'round'}));
      const clip=make('clipPath',{id:'scene-lake-clip'});clip.append(path(lakePath,'white'));defs.append(clip);
      const waves=make('g',{'clip-path':'url(#scene-lake-clip)',class:'lake-ripples'});
      for(let i=0;i<45;i++){const x=250+random()*800,y=180+random()*450;waves.append(path(`M${x} ${y} q12 4 25 -1 t24 0`,'none',{stroke:'#b9d9b7','stroke-width':1.2,opacity:.22}));}
      scenery.append(waves);
    }
    scenery.append(make('rect',{id:'scene-night',x:-1200,y:-800,width:3600,height:2400,fill:'#0d2234',opacity:0}));
    svg.querySelector(':scope > rect').after(scenery);
    const fog=make('rect',{class:'world-fog',x:-1200,y:-800,width:3600,height:2400,fill:'#132f31',opacity:.65,mask:'url(#scene-fog-mask)','aria-hidden':'true'});
    svg.querySelector('#edges').before(fog);
    const hero=make('g',{id:'explorer','aria-hidden':'true'});hero.append(explorer());svg.querySelector('#nodes').after(hero);
    const portrait=document.querySelector('#portrait');if(portrait)portrait.append(explorer());
    svg._worldBuilt=key;
  }
  function decorate(group,node,submitted) {
    group.classList.add('world-location');group.append(node.kind==='camp'?camp():waypoint(node));
    if(submitted){
      const stamp=make('g',{class:'chart-stamp'});
      stamp.append(make('circle',{cx:17,cy:-11,r:6,fill:'#a5bc79',stroke:'#f0e2b1','stroke-width':1}),path('M14 -11 L16 -9 L20 -13','none',{stroke:'#344d36','stroke-width':1.5}));
      group.append(stamp);
    }
  }
  function route(a,b,reachable) {
    const dx=b.x-a.x,dy=b.y-a.y,offset=Math.min(11,Math.hypot(dx,dy)*.07);
    const midx=(a.x+b.x)/2-dy/Math.max(1,Math.hypot(dx,dy))*offset,midy=(a.y+b.y)/2+dx/Math.max(1,Math.hypot(dx,dy))*offset;
    return make('path',{d:`M${a.x} ${a.y} Q${midx} ${midy} ${b.x} ${b.y}`,class:`route-line${reachable?' reachable':''}`,'data-from':a.id,'data-to':b.id});
  }
  function position(svg,x,y) {svg.querySelector('#explorer')?.setAttribute('transform',`translate(${x} ${y})`);}
  function sync(svg,o,map) {
    const reveal=svg.querySelector('#scene-revealed');reveal.replaceChildren();
    map.nodes.forEach(n=>reveal.append(make('circle',{cx:n.x,cy:n.y,r:115,fill:'url(#scene-fog-fade)'})));
    svg.querySelector('#scene-night').setAttribute('opacity',o.conditions.period==='night'?.24:0);
    document.body.classList.toggle('is-night',o.conditions.period==='night');
    document.body.classList.toggle('is-raining',o.conditions.weather==='rain');
    position(svg,o.location.x,o.location.y);
  }
  function tone(kind) {
    if(!soundEnabled)return;
    try{
      audio ||= new (window.AudioContext||window.webkitAudioContext)();audio.resume();
      const notes=kind==='success'?[440,554,659]:kind==='take'?[523,784]:kind==='danger'?[180,140]:[260];
      notes.forEach((frequency,index)=>{const oscillator=audio.createOscillator(),gain=audio.createGain(),at=audio.currentTime+index*.1;oscillator.type='sine';oscillator.frequency.value=frequency;gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(.035,at+.01);gain.gain.exponentialRampToValueAtTime(.001,at+.16);oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(at);oscillator.stop(at+.18);});
    }catch(_){/* Audio is an optional presentation layer. */}
  }
  function showEvent(title,detail,kind) {
    const event=document.getElementById('scene-event');
    document.getElementById('event-title').textContent=title;document.getElementById('event-detail').textContent=detail;
    event.className=`scene-event ${kind||''}`;event.hidden=false;
    event.getAnimations().forEach(animation=>animation.cancel());
    if(!reduced())event.animate([{opacity:0,transform:'translate(-50%,-10px)'},{opacity:1,transform:'translate(-50%,0)'}],{duration:220,fill:'both'});
    clearTimeout(event._timer);event._timer=setTimeout(()=>event.hidden=true,kind==='success'?4200:2600);
  }
  async function transition(svg,before,result) {
    const o=result.observation,hero=svg.querySelector('#explorer');
    if(!before || before.task_run_id!==o.task_run_id){tone('start');return;}
    const moved=before.location.id!==o.location.id,death=result.outcome==='respawned';
    const spent=before.stamina-o.stamina;
    if(moved && !death && !reduced()){
      const line=[...svg.querySelectorAll('.route-line')].find(p=>[p.dataset.from,p.dataset.to].includes(before.location.id)&&[p.dataset.from,p.dataset.to].includes(o.location.id));
      const length=line?.getTotalLength(),reverse=line?.dataset.from!==before.location.id;
      position(svg,before.location.x,before.location.y);hero.classList.add('walking');line?.classList.add('travelling');tone('move');
      await new Promise(resolve=>{
        let start;
        const tick=now=>{start??=now;const t=Math.min(1,(now-start)/380);let point;
          if(line)point=line.getPointAtLength(length*(reverse?1-t:t));else point={x:before.location.x+(o.location.x-before.location.x)*t,y:before.location.y+(o.location.y-before.location.y)*t};
          position(svg,point.x,point.y);
          if(t<1)requestAnimationFrame(tick);else resolve();};requestAnimationFrame(tick);
      });
      hero.classList.remove('walking');line?.classList.remove('travelling');position(svg,o.location.x,o.location.y);
    }
    if(death){tone('danger');showEvent('返回营地','体力耗尽，工具丢失；测绘进度保留。','danger');}
    else if(result.outcome==='success'){tone('success');showEvent('委托完成','这次旅途的地理记录，已经写入手记。','success');}
    else if(o.inventory.length>before.inventory.length){tone('take');showEvent('工具已装入背包',o.inventory.filter(t=>!before.inventory.some(p=>p.id===t.id)).map(t=>t.name).join('、'),'pickup');}
    else if(spent>10){tone('danger');showEvent('途中遇险',`本次消耗 ${spent} 体力，详情已记入现场记录。`,'danger');}
    else if(o.objective?.targets.some(t=>t.recorded&&!before.objective?.targets.find(n=>n.id===t.id)?.recorded))showEvent('测绘完成',`已记录${o.location.name}，请到指定营地提交。`,'discovery');
    if(spent>10 || death){document.body.classList.remove('hurt');void document.body.offsetWidth;document.body.classList.add('hurt');}
  }
  function toggleSound(){soundEnabled=!soundEnabled;try{localStorage.setItem('cartography.sound',soundEnabled?'on':'off');}catch(_){/* Optional preference. */}document.getElementById('sound-toggle').textContent=`音效：${soundEnabled?'开':'关'}`;tone('take');}
  return {prepare,decorate,route,sync,transition,toggleSound};
})();
