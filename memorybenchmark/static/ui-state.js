'use strict';
window.setAppLoading = (id, busy, label) => {
  const indicator = document.getElementById(id);
  if (!indicator) return;
  indicator.hidden = !busy;
  if (label) indicator.querySelector('[data-loading-text]').textContent = label;
  const target = document.getElementById(indicator.dataset.loadingTarget);
  target?.setAttribute('aria-busy', String(busy));
};
document.querySelectorAll('form[data-loading-submit]').forEach(form => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type=submit]');
    button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = '登录中';
  });
});
