'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const dialog = $('experiment-dialog');
  if (!dialog) return;
  let options = null, initializing = null, review = null, generation = 0;
  let submitting = false, submitted = false;
  const newId = () => crypto.randomUUID?.() || `experiment-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  let requestId = newId();
  const modelPicker = new AppSelect($('create-model'), {
    label: '模型', labelledBy: 'create-model-label', placeholder: '选择模型',
    floating: true, onChange: selectionChanged,
  });
  const mapPicker = new AppSelect($('create-map'), {
    label: '地图', labelledBy: 'create-map-label', placeholder: '选择地图',
    floating: true, onChange: selectionChanged,
  });

  function selectionChanged() { requestId = newId(); preview(); }

  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    if (response.status === 401) {
      location.assign('/login?next=/experiments');
      throw Error('请先登录。');
    }
    const data = await response.json();
    if (!response.ok) throw Error(data.message || '操作失败，请重试。');
    return data;
  }

  function showError(error) {
    $('create-error-text').textContent = error.message || '连接失败，请重试。';
    $('create-error').hidden = false;
  }

  function selection() {
    return {model: modelPicker.value, map: mapPicker.value,
      movement_mode: dialog.querySelector('[name=movement_mode]:checked').value};
  }

  function budgetLine(label, value) {
    const row = document.createElement('div'), term = document.createElement('dt'), detail = document.createElement('dd');
    term.textContent = label; detail.textContent = value; row.append(term, detail);
    return row;
  }

  function applyMovementRule() {
    const hard = options.maps.find(row => row.id === mapPicker.value)?.difficulty === 'Hard';
    $('create-route').disabled = hard;
    if (hard) dialog.querySelector('[name=movement_mode][value=step]').checked = true;
    const multi = selection().movement_mode === 'route';
    $('create-movement-note').hidden = !hard && !multi;
    $('create-movement-note').textContent = hard ? 'Hard使用单步移动。' : '每次最多32个相邻地点。';
  }

  async function preview() {
    if (!options || submitting) return;
    const current = ++generation;
    review = null; $('create-launch').disabled = true;
    $('create-summary').textContent = '更新中';
    $('create-summary').setAttribute('aria-busy', 'true');
    applyMovementRule();
    try {
      const next = await api('/api/experiments/preview', selection());
      if (current !== generation) return;
      review = next;
      $('create-summary').textContent = `保留记忆和清除记忆各${next.tasks_per_condition}项任务`;
      $('create-budget').replaceChildren(
        budgetLine('上下文', `${next.context_tokens.toLocaleString()} tokens`),
        budgetLine('推理', next.reasoning_effort === 'high' ? '高' : next.reasoning_effort),
        budgetLine('每任务调用', `${next.main_model_calls} + ${next.final_model_calls}次收尾`),
        budgetLine('每任务操作', `${next.game_steps}步`),
      );
      $('create-error').hidden = true;
      $('create-launch').disabled = submitted;
    } catch (error) {
      if (current !== generation) return;
      $('create-summary').textContent = '';
      showError(error);
    } finally {
      if (current === generation) $('create-summary').setAttribute('aria-busy', 'false');
    }
  }

  async function initialize() {
    if (options) return;
    if (initializing) return initializing;
    setAppLoading('create-loading', true);
    $('create-fields').hidden = true; $('create-error').hidden = true;
    initializing = (async () => {
      try {
        const data = await api('/api/experiments/options');
        if (!data.models?.length || !data.maps?.length) throw Error('暂无可用的模型或地图。');
        options = data;
        for (const [picker, rows, label] of [
          [modelPicker, data.models, row => row.id],
          [mapPicker, data.maps, row => `${row.name}（${row.difficulty}）`],
        ]) {
          picker.setOptions(rows.map(row => ({value: row.id, label: label(row)})));
          picker.setValue(rows[0].id);
        }
        $('create-fields').hidden = false;
        await preview();
      } catch (error) { showError(error); }
      finally { setAppLoading('create-loading', false); initializing = null; }
    })();
    return initializing;
  }

  async function open() {
    if (submitted) { submitted = false; requestId = newId(); }
    if (!dialog.open) dialog.showModal();
    if (options) { if (!submitting) await preview(); }
    else await initialize();
  }

  $('new-experiment').addEventListener('click', open);
  dialog.addEventListener('close', () => { modelPicker.close(); mapPicker.close(); });
  for (const id of ['create-close', 'create-cancel']) $(id).onclick = () => dialog.close();
  dialog.addEventListener('click', event => {
    const box = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
  });
  $('create-retry').onclick = () => options ? preview() : initialize();
  $('experiment-form').addEventListener('change', selectionChanged);
  $('experiment-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!review || submitting || submitted) return;
    submitting = true;
    modelPicker.close(); mapPicker.close();
    $('create-fields').disabled = true; $('create-launch').disabled = true;
    $('create-launch').setAttribute('aria-busy', 'true');
    $('create-launch-text').textContent = '启动中';
    try {
      const pair = await api('/api/experiments/create', {...selection(), request_id: requestId});
      submitted = true; $('create-error').hidden = true;
      dialog.close();
      $('live-notice').textContent = '实验已创建'; $('live-notice').hidden = false;
      document.dispatchEvent(new CustomEvent('experiment-created', {detail: pair}));
    } catch (error) { showError(error); }
    finally {
      submitting = false; $('create-fields').disabled = false; applyMovementRule();
      $('create-launch').disabled = submitted || !review;
      $('create-launch').setAttribute('aria-busy', 'false');
      $('create-launch-text').textContent = '启动实验';
    }
  });
  if (location.pathname === '/experiments/new' || new URLSearchParams(location.search).has('create')) {
    const query = new URLSearchParams(location.search); query.delete('create');
    history.replaceState(null, '', '/experiments' + (query.size ? `?${query}` : ''));
    open();
  }
})();
