(() => {
  const box = document.querySelector('#trade-status');
  if (!box) return;
  const existing = new Map([...box.querySelectorAll('.action-state')].map(e => [Number(e.dataset.id), e.dataset.state]));
  let running = false;
  async function refresh() {
    if (running || document.hidden) return;
    running = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch(box.dataset.statusUrl, {cache: 'no-store', signal: controller.signal, headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error('status');
      const data = await response.json();
      if (data.state !== box.dataset.state || String(data.revision) !== box.dataset.revision || data.actions.some(a => existing.get(a.id) !== a.state)) {
        location.reload();
        return;
      }
      document.querySelector('#status-network').textContent = 'آخرین بررسی وضعیت: ' + new Date().toLocaleTimeString('fa-IR');
    } catch (_) {
      document.querySelector('#status-network').textContent = 'ارتباط برقرار نیست؛ وضعیت نمایش‌داده‌شده ممکن است قدیمی باشد. اجرای Worker مستقل ادامه دارد.';
    } finally {
      clearTimeout(timer);
      running = false;
    }
  }
  setInterval(refresh, 5000);
  document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
})();
