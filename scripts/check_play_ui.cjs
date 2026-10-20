/* Optional browser regression check. Requires Playwright and an installed Chrome.
   Start `python -m memorybenchmark --port 8875 --log-dir .runs/ui-review`, then
   `node scripts/check_play_ui.cjs http://127.0.0.1:8875`.
   Uses isolated human game instances; never starts a model experiment. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = (process.argv[2] || 'http://127.0.0.1:8875').replace(/\/$/, '');
const output = path.resolve('.runs/ui-review/screenshots');
fs.mkdirSync(output, {recursive:true});

(async () => {
  const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome',headless:true});
  const errors = [];
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  let last, actions = 0;
  page.on('response', async response => {
    if (response.url().endsWith('/api/action')) actions++;
    if (/\/api\/(start|action|observation)(\?|$)/.test(response.url()) && response.ok()) last=await response.json();
  });
  async function idle() { await page.locator('.map-stage[aria-busy="false"]').waitFor(); }
  async function move(target, keyboard=false) {
    await idle();
    const response = page.waitForResponse(r=>r.url().endsWith('/api/action') && r.request().method()==='POST');
    const node = page.locator(`[data-map-node="${target}"]`);
    if (keyboard) { await node.focus(); await page.keyboard.press('Enter'); }
    else { await page.locator('#play-locate').click(); await node.locator('.node-circle').click(); }
    const result=await (await response).json();
    await idle(); assert.equal(result.observation.location.id,target,`move ${target}`);
    return result;
  }
  async function action(selector) {
    await idle();
    const response=page.waitForResponse(r=>r.url().endsWith('/api/action') && r.request().method()==='POST');
    await page.locator(selector).click(); const result=await (await response).json(); await idle(); return result;
  }
  try {
    await page.goto(base+'/play');
    await page.locator('#begin:not([disabled])').waitFor();
    await page.screenshot({path:path.join(output,'welcome.png'),fullPage:true});
    await page.locator('#begin').click(); await page.locator('#place-id').filter({hasText:'C0'}).waitFor(); await idle();
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    assert.equal(await page.locator('.is-neighbor').count(),3);
    assert.equal(await page.locator('#camp-actions').isVisible(),false);
    // Zoomed dragging from a node must pan without issuing a movement action.
    const beforeDrag=actions;
    const point=await page.locator('[data-map-node="E1"] .node-circle').boundingBox();
    await page.mouse.move(point.x+point.width/2,point.y+point.height/2);
    await page.mouse.down(); await page.mouse.move(point.x-70,point.y+60,{steps:10}); await page.mouse.up();
    await page.waitForTimeout(150); assert.equal(actions,beforeDrag,'drag must not move');
    await page.locator('#play-locate').click();
    // Rapid repeated clicks while a request is pending must be a single action.
    await page.route('**/api/action',async route=>{await new Promise(r=>setTimeout(r,200));await route.continue();});
    const doublePoint=await page.locator('[data-map-node="E1"] .node-circle').boundingBox();
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/action'));
    await page.mouse.dblclick(doublePoint.x+doublePoint.width/2,doublePoint.y+doublePoint.height/2,{delay:30});
    await pending;await idle();await page.unroute('**/api/action');
    assert.equal(actions,beforeDrag+1,'double click issued a duplicate action');
    assert.equal(await page.locator('#place-id').textContent(),'E1');
    await move('E2',true);
    // A non-adjacent known node is inspect-only and never becomes a macro-route.
    const beforeInspect=actions;
    await page.locator('[data-map-node="C0"]').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#map-selection').isVisible(),true);assert.equal(actions,beforeInspect);
    await page.keyboard.press('Escape');
    // Reload resumes this tab's instance, without a fresh start or another step.
    const revision=last.observation.revision;
    await page.reload();await page.locator('#place-id').filter({hasText:'E2'}).waitFor();await idle();
    assert.equal(last.observation.revision,revision);assert.equal(actions,beforeInspect);
    // Simulate an applied action whose response was lost. The UI must read the
    // current revision rather than blindly repeating an action with a new ID.
    await page.route('**/api/action',async route=>{await route.fetch();await route.abort('failed');},{times:1});
    await page.locator('[data-action="observe"]').click();await page.locator('#error:not([hidden])').waitFor();await idle();
    assert.equal(last.observation.revision,revision+1,'lost response was duplicated or not reconciled');
    await move('P1');assert.equal(await page.locator('.objectives .recorded').count(),1);
    assert.equal(await page.locator('#camp-actions').isVisible(),false,'cannot submit at objective');
    await move('C1');assert.equal(await page.locator('#submit').isEnabled(),true);
    const finished=await action('#submit');assert.equal(finished.observation.success,true);
    assert.equal(await page.locator('#ending').isVisible(),true);
    await page.screenshot({path:path.join(output,'completed.png'),fullPage:true});
    await page.locator('#next').click();await idle();
    assert.match(await page.locator('#task-stage').textContent(),/^2 /);
    assert.ok((await page.locator('#map-caption').textContent()).includes('累计点亮 5'));
    await page.locator('#open-inventory').click();assert.equal(await page.locator('#inventory-page').isVisible(),true);
    await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#journal-page').isVisible(),true);
    const beforeModal=actions;await page.keyboard.press('w');assert.equal(actions,beforeModal,'modal shortcut consumed a game step');
    await page.keyboard.press('Escape');
    // T2: two unprotected encounters cause the real engine to respawn us.
    for (const target of ['E1','E2','P1','C1','N1','C1']) await move(target);
    await idle();const deathResponse=page.waitForResponse(r=>r.url().endsWith('/api/action'));
    await page.locator('[data-map-node="P1"]').focus();await page.keyboard.press('Enter');
    const death=await (await deathResponse).json();await idle();
    assert.equal(death.outcome,'respawned');assert.equal(death.observation.location.id,'C0');
    assert.equal(await page.locator('#recovery-edges .respawn-line').count(),1);
    assert.equal(await page.locator('#recovery-status').isVisible(),true);
    // Tools are offered only at the current depot, and taking one populates the bag.
    await move('E1');await move('U1');await move('D1');
    assert.equal(await page.locator('#stock-section').isVisible(),true);
    const took=await action('[data-tool="grip_kit"]');assert.equal(took.observation.inventory.length,1);
    assert.equal(await page.locator('#stock-section').isVisible(),false);
    await page.keyboard.press('i');assert.equal(await page.locator('.inventory-item').count(),1);
    await page.screenshot({path:path.join(output,'inventory.png')});await page.keyboard.press('Escape');
    await page.locator('#open-menu').click();await page.locator('#abandon').click();
    await page.locator('#confirm-cancel').click();assert.equal(last.observation.done,false);
    await page.locator('#open-menu').click();await page.locator('#abandon').click();
    await action('#confirm-accept');assert.equal(last.observation.done,true);
    // Exercise all eight reference routes through visible UI controls, not API mutations.
    if (process.argv[3]) {
      const routes=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
      await page.locator('#open-menu').click();await page.locator('#fresh').click();await page.locator('#confirm-accept').click();await idle();
      for (const [task,steps] of Object.entries(routes)) {
        assert.equal(last.observation.task_id,task);
        for (const step of steps) {
          if(step.type==='move')await move(step.target,true);
          else await action(step.type==='take'?`[data-tool="${step.target}"]`:`[data-action="${step.type}"]`);
        }
        assert.equal(last.observation.success,true,task);assert.equal(last.observation.recovery.deaths,0,task);
        if(last.observation.next_task_id){await page.locator('#next').click();await idle();}
      }
    }
    // Shared map camera changes must not break the designer or read-only viewer.
    const design=await context.newPage();design.on('pageerror',e=>errors.push(e.message));
    await design.goto(base+'/design');await design.locator('.design-node').first().waitFor();
    await design.locator('#design-zoom-in').click();await design.locator('#design-zoom-reset').click();await design.close();
    const watch=await context.newPage();watch.on('pageerror',e=>errors.push(e.message));await watch.goto(base+'/watch');await watch.locator('#run-select').waitFor();await watch.close();
    const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const phone=await mobile.newPage();phone.on('pageerror',e=>errors.push(e.message));
    await phone.goto(base+'/play');await phone.locator('#begin').tap();await phone.locator('[data-map-node="E1"]').waitFor();
    assert.equal(await phone.locator('#brief').getAttribute('open'),null);
    await phone.locator('[data-map-node="E1"] .node-circle').tap();
    await phone.locator('#place-id').filter({hasText:'E1'}).waitFor();
    assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'mobile horizontal overflow');
    const labelSize=await phone.locator('.is-neighbor .node-label').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)*el.getScreenCTM().a);
    assert.ok(labelSize>=13.9,'mobile map labels too small');
    await phone.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    await phone.locator('#open-menu').tap();await phone.screenshot({path:path.join(output,'mobile-menu.png')});
    for(const [width,height] of [[320,740],[768,1024],[1024,768],[1366,768]]){
      await page.setViewportSize({width,height});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow at ${width}`);
    }
    await mobile.close();assert.deepEqual(errors,[],'browser exceptions');
    console.log('PASS: direct map moves, keyboard, drag, duplicate suppression, inspect-only nodes, refresh, camp submission, atlas, respawn, tools, dialogs, mobile and shared viewers.');
    if(process.argv[3])console.log('PASS: all 8 commissions completed through the UI with tools and zero deaths.');
    console.log('Screenshots:',output);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
