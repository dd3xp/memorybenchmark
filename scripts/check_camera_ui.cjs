/* Real mouse and CDP touch regression checks for the human camera.
   Same optional Playwright setup as check_play_ui.cjs. No model runs.
   Usage: node scripts/check_camera_ui.cjs http://127.0.0.1:8875
   A protected preview can supply MEMORYBENCH_UI_PIN in the environment. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=(process.argv[2]||'http://127.0.0.1:8875').replace(/\/$/,'');
const close=(a,b,tolerance=.05)=>assert.ok(Math.abs(a-b)<tolerance,`${a} != ${b}`);

(async()=>{
  const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const errors=[],page=await context.newPage();let actions=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url().endsWith('/api/action'))actions++;});
  async function open(p){
    await p.goto(base+'/play');
    if(new URL(p.url()).pathname==='/login'){
      assert.ok(process.env.MEMORYBENCH_UI_PIN,'Protected preview requires MEMORYBENCH_UI_PIN');
      await p.locator('#pin').fill(process.env.MEMORYBENCH_UI_PIN);
      await Promise.all([p.waitForURL(base+'/play'),p.locator('button[type=submit]').click()]);
    }
    await p.locator('#begin').click();await p.locator('.map-stage[aria-busy=false]').waitFor();
    await p.locator('[data-map-node=E1]').waitFor();
  }
  const box=()=>page.locator('#map').evaluate(s=>s._box.slice());
  const mode=()=>page.locator('#map').getAttribute('data-camera');
  const worldPoint=(x,y)=>page.locator('#map').evaluate((s,[x,y])=>{
    const p=new DOMPoint(x,y).matrixTransform(s.getScreenCTM().inverse());return [p.x,p.y];
  },[x,y]);
  async function drag(x,y,dx,dy){
    await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+dx,y+dy,{steps:8});await page.mouse.up();
  }
  try{
    await open(page);
    // Full-map pan: the old controller silently refused this gesture.
    await page.locator('#play-zoom-reset').click();
    let before=await box();await drag(650,420,110,65);let after=await box();
    assert.ok(Math.abs(before[0]-after[0])>30,'full-map pan did not move');
    assert.equal(await mode(),'free');assert.equal(actions,0);
    // Crossing a boundary must not accumulate an invisible reversal dead zone.
    await page.mouse.move(650,420);await page.mouse.down();await page.mouse.move(6500,420,{steps:4});
    before=await box();await page.mouse.move(6480,420);after=await box();
    assert.ok(after[0]>before[0]+5,'boundary reverse is stuck');await page.mouse.up();
    assert.equal(await page.locator('.map-dragging').count(),0);
    // Zoom about the cursor, independent of camera centre and player location.
    await page.locator('#play-locate').click();
    const anchor=await worldPoint(700,420);await page.mouse.move(700,420);await page.mouse.wheel(0,-100);
    const anchored=await worldPoint(700,420);close(anchor[0],anchored[0]);close(anchor[1],anchored[1]);
    assert.equal(await mode(),'free');
    // Node-origin drags capture the map without accidentally moving the player.
    await page.locator('#play-locate').click();
    const node=await page.locator('[data-map-node=E1] .node-circle').boundingBox();
    await drag(node.x+node.width/2,node.y+node.height/2,-70,40);assert.equal(actions,0);
    // Cancelling input / leaving the window never leaves a stuck hand cursor.
    await page.mouse.move(650,420);await page.mouse.down();await page.mouse.move(680,430);
    await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.mouse.up();
    assert.equal(await page.locator('.map-dragging').count(),0);
    before=await box();await drag(650,420,-35,20);after=await box();assert.notEqual(before[0],after[0]);
    // Neither an observation nor focus restoration may steal a free camera.
    await page.locator('[data-map-node=E1]').focus();await drag(650,420,55,30);before=await box();
    await page.locator('[data-action=observe]').click();await page.locator('.map-stage[aria-busy=false]').waitFor();
    after=await box();before.forEach((v,i)=>close(v,after[i]));assert.equal(await mode(),'free');
    // The same camera survives a refresh of this tab's active game.
    const count=actions;await page.reload();await page.locator('[data-map-node=E1]').waitFor();
    after=await box();before.forEach((v,i)=>close(v,after[i]));assert.equal(actions,count);assert.equal(await mode(),'free');
    await page.keyboard.press('f');assert.equal(await mode(),'follow');
    await page.keyboard.press('Home');assert.equal(await mode(),'free');
    await page.keyboard.press('+');assert.ok((await box())[2]<before[2]*3);
    // Free camera stays free when a move response redraws the nodes mid-drag.
    await page.locator('#play-locate').click();
    await page.route('**/api/action',async route=>{await new Promise(r=>setTimeout(r,250));await route.continue();},{times:1});
    const result=page.waitForResponse(r=>r.url().endsWith('/api/action'));
    await page.locator('[data-map-node=E1] .node-circle').click();
    await page.mouse.move(650,420);await page.mouse.down();await page.mouse.move(680,440);
    await result;await page.locator('#place-id').filter({hasText:'E1'}).waitFor();
    before=await box();await page.mouse.move(710,460);after=await box();assert.notEqual(before[0],after[0]);await page.mouse.up();
    await page.locator('.map-stage[aria-busy=false]').waitFor();assert.equal(await mode(),'free');
    // Zoom caps and resizing keep square world units and no letterboxed pan area.
    await page.locator('#play-locate').click();
    await page.mouse.move(700,420);
    for(let i=0;i<12;i++)await page.mouse.wheel(0,-160);
    await page.waitForTimeout(80);
    assert.equal(await page.locator('#play-zoom-in').isDisabled(),true);
    for(let i=0;i<18;i++)await page.mouse.wheel(0,160);
    await page.waitForTimeout(80);assert.equal(await page.locator('#play-zoom-out').isDisabled(),true);
    await page.setViewportSize({width:1024,height:768});await page.waitForTimeout(80);
    const resized=await box();close(resized[2]/resized[3],1024/768,.001);
    // Animated camera transitions are interrupted by input, not queued behind it.
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.locator('#play-zoom-reset').click();await page.waitForTimeout(220);
    await page.locator('#play-zoom-in').click();await page.waitForTimeout(35);
    await drag(500,400,55,35);before=await box();await page.waitForTimeout(230);
    after=await box();before.forEach((v,i)=>close(v,after[i]));assert.equal(await mode(),'free');

    const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    // Reuse authorization, if necessary, without retaining it outside this run.
    await mobile.addCookies(await context.cookies());
    const phone=await mobile.newPage();phone.on('pageerror',e=>errors.push(e.message));await open(phone);
    const cdp=await mobile.newCDPSession(phone);
    const touch=async(type,points)=>{
      await cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([id,x,y])=>({id,x,y,radiusX:2,radiusY:2}))});
      await phone.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    };
    let mobileActions=0;phone.on('request',r=>{if(r.url().endsWith('/api/action'))mobileActions++;});
    const mobileBox=()=>phone.locator('#map').evaluate(s=>s._box.slice());
    // Two real touch pointers: pinch about their midpoint, then continue panning
    // with one finger. Neither gesture may dispatch a game move.
    before=await mobileBox();
    await touch('touchStart',[[1,130,390],[2,250,390]]);
    await touch('touchMove',[[1,90,390],[2,290,390]]);after=await mobileBox();
    assert.ok(after[2]<before[2]*.8,'pinch did not zoom in');
    await touch('touchEnd',[[2,290,390]]);before=await mobileBox();
    await touch('touchMove',[[1,120,415]]);after=await mobileBox();assert.notEqual(before[0],after[0]);
    await touch('touchCancel',[]);assert.equal(await phone.locator('.map-dragging').count(),0);assert.equal(mobileActions,0);
    await phone.locator('#play-zoom-reset').tap();before=await mobileBox();
    await touch('touchStart',[[1,180,390]]);await touch('touchMove',[[1,220,430]]);await touch('touchEnd',[]);
    after=await mobileBox();assert.notEqual(before[0],after[0]);assert.equal(mobileActions,0);
    // A normal tap after a drag/cancel is still a single normal game move.
    async function tap(selector,id){
      const b=await phone.locator(selector).boundingBox(),point=[id,b.x+b.width/2,b.y+b.height/2];
      await touch('touchStart',[point]);await touch('touchEnd',[]);
    }
    await tap('#play-locate',9);
    await phone.waitForFunction(()=>document.querySelector('#map').dataset.camera==='follow');
    await tap('[data-map-node=E1] .node-circle',10);
    await phone.locator('#place-id').filter({hasText:'E1'}).waitFor();assert.equal(mobileActions,1);
    assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await mobile.close();assert.deepEqual(errors,[]);
    console.log('PASS: full-map pan, immediate boundary reversal, cursor-anchored wheel, node drag, cancellation, free/follow camera, response during drag, refresh, zoom caps, resize, real touch pinch/pan/cancel and normal tap.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
