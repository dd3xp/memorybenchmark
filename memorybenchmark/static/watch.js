'use strict';
(() => {
  const $ = id => document.getElementById(id), worldView = new WorldAtlasView($('watch-map'));
  let view=worldView, legacyView=null;
  let pendingPairs = [], atlasReady = false, loadedRun = null;
  let runs = [], selected = new URLSearchParams(location.search).get('run');
  let session = null, data = null, follow = true, frame = null, onlyLive = false, loading = false, loadVersion = 0;
  const states = {running:'运行中', network_retry:'网络重试中', maintenance:'恢复核验中', needs_attention:'需要修复', waiting:'等待中', complete:'已完成', auditing:'整理结果', interrupted:'已中断', audit_error:'结果处理中断'};
  const condition = value => value === 'clear' ? '清除记忆' : '保留记忆';
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  let selectedNode=null, timer=null;const layers={terrain:true,roads:true,stations:true,labels:true,trace:true};
  const picker = new AppSelect($('session-select'), {label:'选择任务', onChange:value => chooseSession(value)});

  async function api(path) {
    const response = await fetch(path);
    if (response.status === 401) { location.assign('/login?next=/experiments'); throw Error('请重新登录。'); }
    const body = await response.json();
    if (!response.ok) throw Error(body.message || '读取失败，请刷新重试。');
    return body;
  }

  function renderList() {
    const signature = JSON.stringify([selected, onlyLive, $('run-search').value, runs, pendingPairs]);
    if ($('run-list').dataset.signature === signature) return;
    $('run-list').dataset.signature = signature;
    const list = $('run-list'); list.replaceChildren();
    const query=$('run-search').value.trim().toLowerCase();const visible = runs.filter(run => (!onlyLive || ['running','network_retry','maintenance','needs_attention','waiting','auditing'].includes(run.status))&&(!query||[run.name,run.agent,run.model,run.difficulty,condition(run.condition)].join(' ').toLowerCase().includes(query)));let group;
    const pending = pendingPairs.filter(pair => !query || [pair.map_name, pair.model].join(' ').toLowerCase().includes(query));
    $('list-empty').hidden = !!(visible.length || pending.length);
    $('list-empty').textContent = query ? '未找到实验' : '暂无实验';
    for (const pair of pending) {
      const row = el('div', undefined, 'pending-run');
      row.append(el('strong', pair.map_name), el('span', pair.model));
      const state = el('span');
      const icon = el('i', undefined, 'loading-indicator'); icon.setAttribute('aria-hidden', 'true');
      state.append(icon, document.createTextNode(pair.jobs.map(job => condition(job.condition)).join('／') + ' 准备中'));
      row.append(state); list.append(row);
    }
    for (const run of visible) {
      const date=new Date(run.started_at).toLocaleDateString('zh-CN');if(group!==date){group=date;list.append(el('div',date,'group-label'));}
      const button = el('button', undefined, 'run-item');
      button.setAttribute('aria-pressed', String(run.id === selected));
      button.title = new Date(run.started_at).toLocaleString('zh-CN', {hour12:false});
      const top = el('span', undefined, 'run-item-top');
      top.append(el('strong', run.name || run.agent), el('span', condition(run.condition), 'run-condition'));
      const bottom = el('span', undefined, 'run-item-bottom');
      const status = el('span', states[run.status] || '等待中', 'status' + (run.status === 'running' ? ' live' : ''));
      bottom.append(status, el('span', `${run.completed_sessions} / ${run.total_sessions}`));
      const bar = el('span', undefined, 'mini-progress'), fill = el('i');
      bar.setAttribute('aria-hidden', 'true');
      fill.style.width = `${100 * run.completed_sessions / Math.max(1, run.total_sessions)}%`;
      bar.append(fill);
      button.append(top);
      if (run.model) button.append(el('span', run.model, 'run-item-model'));
      button.append(bottom, bar);
      button.onclick = () => {
        selectRun(run.id);

      };
      list.append(button);
    }
  }

  function render() {
    if (!data) return;
    $('viewer').hidden = false; $('empty').hidden = true;
    $('run-name').textContent = data.name;
    $('run-agent').textContent=data.agent;$('run-model').textContent=data.model;$('run-started').textContent=new Date(data.started_at).toLocaleString('zh-CN',{hour12:false});
    for(const c of ['retain','clear']){const b=$('condition-'+c);b.setAttribute('aria-pressed',String(data.condition===c));b.disabled=!pairedRun(c);}
    $('run-state').textContent = states[data.status] || '等待中';
    $('run-state').className = 'status' + (data.status === 'running' ? ' live' : '');
    $('completion').textContent = `${data.completed_sessions} / ${data.total_sessions}`;
    $('completion-bar').max = Math.max(1, data.total_sessions);
    $('completion-bar').value = data.completed_sessions;
    picker.setOptions(data.sessions.map(row => ({value:row.id, label:row.task_id})));
    picker.setValue(data.session?.id || null);
    const current = data.session;
    $('session-state').textContent = data.status === 'network_retry' ? '网络重试中' : data.status === 'maintenance' ? '恢复核验中' : data.status === 'needs_attention' ? '需要修复' : current?.status === 'complete' ? (current.success ? '已完成' : '未完成') : current?.status === 'error' ? '已中断' : current?.phase || '等待中';
    $('session-state').className = 'status' + (current?.status === 'running' ? ' live' : '');
    $('follow').setAttribute('aria-pressed', String(follow));
    const count = data.frames.length;
    frame = follow || frame === null ? count - 1 : Math.min(frame, count - 1);
    $('frame-slider').max = Math.max(0, count - 1);
    $('frame-slider').value = Math.max(0, frame);
    $('frame-slider').disabled = count < 2;
    $('frame-number').textContent = `${Math.max(0, frame)} / ${Math.max(0, count - 1)}`;
    paintFrame();
    const rows = $('session-rows'); rows.replaceChildren();
    for (const row of data.sessions) {
      const tr = el('tr'); tr.tabIndex = 0;
      tr.setAttribute('aria-label', `查看 ${row.task_id}`);
      for (const value of [row.task_id, row.status === 'complete' ? (row.success ? '成功' : '未完成') : row.status === 'error' ? '中断' : '进行中', row.operations ?? '—', row.distance ?? '—', row.calls ?? '—']) tr.append(el('td', value));
      tr.onclick = () => chooseSession(row.id);
      tr.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); chooseSession(row.id); } };
      rows.append(tr);
    }
  }

  function paintFrame() {
    const current = data.frames[Math.max(0, frame)] || null, places = data.map.locations;
    const options={key:data.experiment_id,cameraKey:data.experiment_id,terrain:data.terrain,location:current?.location,target:current?.task?.target,frames:data.frames.slice(0,Math.max(0,frame)+1),layers,selected:selectedNode,onSelect:selectNode};
    const projected=data.world_map;
    $('map-viewport').dataset.renderer=projected?'world':'legacy';
    $('watch-map').style.display=projected?'':'none';
    if(projected) {
      if(legacyView)legacyView.svg.style.display='none';
      view=worldView;view.setRegion(projected.region_id,projected,options);
    } else {
      if(!legacyView){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('atlas');svg.setAttribute('aria-label','历史实验地图和当前位置');$('watch-map').before(svg);legacyView=new AtlasView(svg);}
      view=legacyView;view.svg.style.display='';view.set(data.map,options);
    }
    $('world-extent').disabled=!projected;
    $('place').textContent = current ? `${places[current.location]?.name || current.location} ${current.location}` : '等待中';
    $('stage').textContent = current?.stage_count ? `${Math.min((current.stage_index || 0) + 1, current.stage_count)}/${current.stage_count} 段` : '';
    $('task-title').textContent = current?.task?.name || '准备任务';
    $('metric-steps').textContent = current ? `${current.steps} / ${current.task?.max_steps || '—'}` : '—';
    $('metric-distance').textContent = current?.distance ?? '—';
    $('metric-calls').textContent = data.session?.calls ?? '—';
    renderJournal();
  }

  function chooseSession(value) { stopReplay();selectedNode=null; session = value; follow = false; frame = null; loadRun(true); }
  async function loadRun(explicit = false) {
    if (!selected) return;
    const version = ++loadVersion, showLoading = explicit || !data || loadedRun !== selected;
    if (showLoading) { setAppLoading('viewer-loading', true, '加载中'); $('viewer').inert = true; $('empty').hidden = true; }
    try {
      const [next] = await Promise.all([
        api('/api/experiments/run?id=' + encodeURIComponent(selected) + (!follow && session ? '&session=' + encodeURIComponent(session) : '')),
        WorldCartography.ready,
      ]);
      if (version !== loadVersion) return;
      data = next; loadedRun = selected;
      if (!follow) session = data.session?.id || null;
      render(); $('page-error').hidden = true; $('viewer-retry').hidden = true;
    } catch (error) {
      if (version !== loadVersion) return;
      $('page-error').textContent = error.message; $('page-error').hidden = false;
      $('viewer-retry').hidden = false;
    } finally {
      if (version === loadVersion) { setAppLoading('viewer-loading', false); $('viewer').inert = false; }
    }
  }

  async function poll() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const [result, managed] = await Promise.all([
        api('/api/experiments/runs'), api('/api/experiments/managed').catch(() => ({pairs: []})),
      ]);
      runs = result.runs;
      pendingPairs = managed.pairs.map(pair => ({...pair, jobs: pair.jobs.filter(job =>
        !runs.some(run => run.comparison_key === pair.comparison_key && run.condition === job.condition)
        && ['queued', 'preparing', 'running', 'waiting_for_gateway'].includes(job.phase)
      )})).filter(pair => pair.jobs.length);
      if (selected && !runs.some(run => run.id === selected) && runs.some(run => run.id === selected + '-retain')) selected += '-retain';
      if (!selected || !runs.some(run => run.id === selected)) selected = runs.find(run => ['running','network_retry','maintenance','needs_attention','auditing'].includes(run.status))?.id || runs[0]?.id;
      renderList();
      if (selected) await loadRun();
      else {
        $('viewer').hidden = true;
        $('empty').hidden = !!pendingPairs.length;
        setAppLoading('viewer-loading', !!pendingPairs.length, '正在准备实验');
        $('page-error').hidden = true; $('viewer-retry').hidden = true;
      }
      $('connection').textContent = '已连接'; $('connection').className = 'status live';
    } catch (error) {
      $('connection').textContent = '连接中断'; $('connection').className = 'status error';
      $('page-error').textContent = error.message; $('page-error').hidden = false;
      $('viewer-retry').hidden = false;
      setAppLoading('viewer-loading', false);
    } finally { loading = false; setAppLoading('list-loading', false); }
  }

  function selectRun(id){stopReplay();selected=id;session=null;follow=true;frame=null;selectedNode=null;$('location-sheet').hidden=true;history.replaceState(null,'','?run='+encodeURIComponent(id));renderList();loadRun(true);}
  function pairedRun(c){if(!data)return null;if(data.condition===c)return data;return runs.find(r=>r.condition===c&&r.experiment_id===data.experiment_id)||runs.find(r=>r.condition===c&&r.comparison_key&&r.comparison_key===data.comparison_key);}
  for(const c of ['retain','clear'])$('condition-'+c).onclick=()=>{const r=pairedRun(c);if(r)selectRun(r.id);};
  function selectNode(id){selectedNode=id;const n=data?.map.locations[id];if(!n)return;$('location-sheet').hidden=false;$('location-name').textContent=n.name;$('location-id').textContent=id;$('neighbors').replaceChildren();for(const[a,b,w]of data.map.edges){const to=a===id?b:b===id?a:null;if(!to)continue;const button=el('button',`${to} · ${w}`);button.title=data.map.locations[to]?.name||to;button.onclick=()=>{selectNode(to);view.locate(to);};$('neighbors').append(button);}paintFrame();}
  function renderJournal(){const list=$('journal-events');list.replaceChildren();const names={move:'前往',collect:'采集',process:'处理',submit:'交件',observe:'观察',finish:'结束',abandon:'放弃'};const frames=data.frames.slice(0,Math.max(0,frame)+1);let prior=0;for(const[fIndex,f]of frames.entries()){if(!f.action?.type){prior=f.distance||0;continue;}const row=el('div',undefined,'journal-entry'),body=el('div');const to=f.action.target||f.location;body.append(el('span',`${names[f.action.type]||f.action.type} · ${data.map.locations[to]?.name||to}`));const details=[to,f.feedback?.result,f.feedback?.kind?data.kinds?.[f.feedback.kind]||f.feedback.kind:null].filter(Boolean);body.append(el('small',details.join(' · ')));row.append(el('span',String(fIndex)),body,el('span',`+${Math.max(0,(f.distance||0)-prior)}`,'entry-distance'));list.append(row);prior=f.distance||0;}if(!list.children.length)list.append(el('p','尚无操作记录','subtle'));}
  function stopReplay(){clearInterval(timer);timer=null;$('replay-play').textContent='▶';$('replay-play').setAttribute('aria-label','播放轨迹');}
  $('replay-play').onclick=()=>{if(timer){stopReplay();return;}if(!data?.frames.length)return;follow=false;session=data.session?.id;if(frame>=data.frames.length-1)frame=0;$('follow').setAttribute('aria-pressed','false');$('replay-play').textContent='Ⅱ';$('replay-play').setAttribute('aria-label','暂停轨迹');timer=setInterval(()=>{if(frame>=data.frames.length-1){stopReplay();return;}frame++;$('frame-slider').value=frame;$('frame-number').textContent=`${frame} / ${data.frames.length-1}`;paintFrame();},650);};
  $('run-search').oninput=renderList;
  $('layers-toggle').onclick=()=>{const open=$('layers-menu').hidden;$('layers-menu').hidden=!open;$('layers-toggle').setAttribute('aria-expanded',String(open));};
  for(const checkbox of document.querySelectorAll('[data-layer]'))checkbox.onchange=()=>{layers[checkbox.dataset.layer]=checkbox.checked;if(data)paintFrame();};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('layers-menu').hidden=true;$('layers-toggle').setAttribute('aria-expanded','false');}});
  $('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('map-viewport').requestFullscreen();}catch(e){$('page-error').textContent='此窗口不支持全屏，可使用放大按钮查看地图。';$('page-error').hidden=false;}};

  $('follow').onclick = () => { stopReplay();follow = true; frame = null; session = null; loadRun(); };
  $('frame-slider').oninput = event => {
    stopReplay();follow = false; session = data.session?.id; frame = Number(event.target.value);
    $('follow').setAttribute('aria-pressed', 'false');
    $('frame-number').textContent = `${frame} / ${Math.max(0, data.frames.length - 1)}`;
    paintFrame();
  };
  $('refresh').onclick = poll;
  $('viewer-retry').onclick = () => atlasReady ? (selected ? loadRun(true) : poll()) : location.reload();
  document.addEventListener('experiment-created', poll);
  for (const [id, value] of [['filter-all',false],['filter-live',true]]) $(id).onclick = () => {
    onlyLive = value; $('filter-all').setAttribute('aria-pressed', String(!value)); $('filter-live').setAttribute('aria-pressed', String(value)); renderList();
  };
  $('zoom-in').onclick = () => view.zoom(1.25);
  $('zoom-out').onclick = () => view.zoom(.8);
  $('fit').onclick = () => view.fit();
  $('world-extent').onclick = () => worldView.showWorld();
  $('locate').onclick = () => view.locate();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  WorldCartography.ready.then(() => { atlasReady = true; }).catch(() => {});
  poll(); setInterval(poll, 4000);
})();
