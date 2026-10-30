'use strict';
(() => {
  const $ = id => document.getElementById(id), view = new AtlasView($('watch-map'));
  let runs = [], selected = new URLSearchParams(location.search).get('run');
  let session = null, data = null, follow = true, frame = null, onlyLive = false, loading = false, loadVersion = 0;
  const states = {running:'运行中', waiting:'等待中', complete:'已完成', auditing:'整理结果', interrupted:'已中断', audit_error:'归档中断'};
  const condition = value => value === 'clear' ? '清除记忆' : '保留记忆';
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  const picker = new AppSelect($('session-select'), {label:'选择任务', onChange:value => chooseSession(value)});

  async function api(path) {
    const response = await fetch(path);
    if (response.status === 401) { location.assign('/login?next=/experiments'); throw Error('请重新登录。'); }
    const body = await response.json();
    if (!response.ok) throw Error(body.message || '读取失败，请刷新重试。');
    return body;
  }

  function renderList() {
    const signature = JSON.stringify([selected, onlyLive, runs]);
    if ($('run-list').dataset.signature === signature) return;
    $('run-list').dataset.signature = signature;
    const list = $('run-list'); list.replaceChildren();
    const visible = runs.filter(run => !onlyLive || ['running','waiting','auditing'].includes(run.status));
    $('list-empty').hidden = !!visible.length;
    for (const run of visible) {
      const button = el('button', undefined, 'run-item');
      button.setAttribute('aria-pressed', String(run.id === selected));
      button.title = new Date(run.started_at).toLocaleString('zh-CN', {hour12:false});
      const top = el('span', undefined, 'run-item-top');
      top.append(el('strong', run.agent), el('span', condition(run.condition), 'run-condition'));
      const bottom = el('span', undefined, 'run-item-bottom');
      const status = el('span', states[run.status] || '等待中', 'status' + (run.status === 'running' ? ' live' : ''));
      bottom.append(status, el('span', `${run.completed_sessions} / ${run.total_sessions}`));
      const bar = el('span', undefined, 'mini-progress'), fill = el('i');
      bar.setAttribute('aria-hidden', 'true');
      fill.style.width = `${100 * run.completed_sessions / Math.max(1, run.total_sessions)}%`;
      bar.append(fill);
      button.append(top, bottom, bar);
      button.onclick = () => {
        selected = run.id; session = null; follow = true; frame = null;
        history.replaceState(null, '', '?run=' + selected);
        renderList(); loadRun();
      };
      list.append(button);
    }
  }

  function render() {
    if (!data) return;
    $('viewer').hidden = false; $('empty').hidden = true;
    $('run-name').textContent = `${data.agent} · ${condition(data.condition)}`;
    $('run-state').textContent = states[data.status] || '等待中';
    $('run-state').className = 'status' + (data.status === 'running' ? ' live' : '');
    $('completion').textContent = `${data.completed_sessions} / ${data.total_sessions}`;
    $('completion-bar').max = Math.max(1, data.total_sessions);
    $('completion-bar').value = data.completed_sessions;
    picker.setOptions(data.sessions.map(row => ({value:row.id, label:row.task_id})));
    picker.setValue(data.session?.id || null);
    const current = data.session;
    $('session-state').textContent = current?.status === 'complete' ? (current.success ? '已完成' : '未完成') : current?.status === 'error' ? '已中断' : current?.phase || '等待中';
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
    view.set(data.map, {key:data.experiment_id, terrain:data.terrain, location:current?.location, target:current?.task?.target, frames:data.frames.slice(0, Math.max(0, frame) + 1)});
    $('place').textContent = current ? `${places[current.location]?.name || current.location} ${current.location}` : '等待中';
    $('stage').textContent = current?.stage_count ? `${Math.min((current.stage_index || 0) + 1, current.stage_count)}/${current.stage_count} 段` : '';
    $('task-title').textContent = current?.task?.name || '准备任务';
    $('metric-steps').textContent = current ? `${current.steps} / ${current.task?.max_steps || '—'}` : '—';
    $('metric-distance').textContent = current?.distance ?? '—';
    $('metric-calls').textContent = data.session?.calls ?? '—';
  }

  function chooseSession(value) { session = value; follow = false; frame = null; loadRun(); }
  async function loadRun() {
    if (!selected) return;
    const version = ++loadVersion;
    try {
      const next = await api('/api/experiments/run?id=' + encodeURIComponent(selected) + (!follow && session ? '&session=' + encodeURIComponent(session) : ''));
      if (version !== loadVersion) return;
      data = next;
      if (!follow) session = data.session?.id || null;
      render(); $('page-error').hidden = true;
    } catch (error) {
      if (version !== loadVersion) return;
      $('page-error').textContent = error.message; $('page-error').hidden = false;
    }
  }

  async function poll() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      runs = (await api('/api/experiments/runs')).runs;
      // Links from the combined dashboard continue to open the retained run.
      if (selected && !runs.some(run => run.id === selected) && runs.some(run => run.id === selected + '-retain')) selected += '-retain';
      if (!selected || !runs.some(run => run.id === selected)) selected = runs[0]?.id;
      renderList();
      if (selected) await loadRun(); else { $('viewer').hidden = true; $('empty').hidden = false; }
      $('connection').textContent = '已连接'; $('connection').className = 'status live';
    } catch (error) {
      $('connection').textContent = '连接中断'; $('connection').className = 'status error';
      $('page-error').textContent = error.message; $('page-error').hidden = false;
    } finally { loading = false; }
  }

  $('follow').onclick = () => { follow = true; frame = null; session = null; loadRun(); };
  $('frame-slider').oninput = event => {
    follow = false; session = data.session?.id; frame = Number(event.target.value);
    $('follow').setAttribute('aria-pressed', 'false');
    $('frame-number').textContent = `${frame} / ${Math.max(0, data.frames.length - 1)}`;
    paintFrame();
  };
  $('refresh').onclick = poll;
  for (const [id, value] of [['filter-all',false],['filter-live',true]]) $(id).onclick = () => {
    onlyLive = value; $('filter-all').setAttribute('aria-pressed', String(!value)); $('filter-live').setAttribute('aria-pressed', String(value)); renderList();
  };
  $('zoom-in').onclick = () => view.zoom(1.25);
  $('zoom-out').onclick = () => view.zoom(.8);
  $('fit').onclick = () => view.fit();
  $('locate').onclick = () => view.locate();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  poll(); setInterval(poll, 4000);
})();
