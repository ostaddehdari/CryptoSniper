(() => {
  const panel = document.querySelector('#dashboard-panels');
  const state = document.querySelector('#dashboard-live-state');
  if (!panel || !state) return;
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(panel.dataset.refreshUrl, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!response.ok || response.redirected) throw new Error('unavailable');
      panel.innerHTML = await response.text();
      panel.classList.remove('dashboard-stale');
      state.textContent = 'متصل · به‌روزرسانی خودکار هر ۱۵ ثانیه';
      state.classList.remove('notice');
    } catch (_) {
      state.textContent = 'ارتباط قطع شده؛ اطلاعات نمایش‌داده‌شده ممکن است قدیمی باشد. تلاش مجدد خودکار انجام می‌شود.';
      state.classList.add('notice'); panel.classList.add('dashboard-stale');
    } finally {
      clearTimeout(timeout); busy = false; panel.setAttribute('aria-busy', 'false');
    }
  }
  refresh(); setInterval(refresh, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
