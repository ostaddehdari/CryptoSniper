(() => {
  const badge = document.querySelector('[data-notification-count]');
  if (!badge) return;
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  let running = false;
  async function poll() {
    if (running || document.hidden) return;
    running = true;
    try {
      const result = await fetch(badge.dataset.listUrl, {credentials: 'same-origin'});
      if (!result.ok) return;
      const data = await result.json();
      badge.textContent = data.unread ? String(data.unread) : '0';
      if (!csrf || !('Notification' in window) || Notification.permission !== 'granted') return;
      const response = await fetch(badge.dataset.claimUrl, {
        method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': csrf}
      });
      if (!response.ok) return;
      for (const item of (await response.json()).items) {
        try { new Notification(item.title, {body: item.body, tag: 'cs-' + item.id}); }
        catch (_) { /* In-app notification remains available on unsupported browsers. */ }
      }
    } catch (_) { /* A temporary outage must not interrupt the page. */ }
    finally { running = false; }
  }
  document.querySelector('#browser-permission')?.addEventListener('click', async () => {
    const label = document.querySelector('#browser-permission-status');
    if (!('Notification' in window)) { label.textContent = 'این مرورگر پشتیبانی نمی‌کند.'; return; }
    try {
      const permission = await Notification.requestPermission();
      label.textContent = permission === 'granted' ? 'اجازه داده شد؛ ترجیحات را ذخیره کنید.' : 'اجازه داده نشد؛ اعلان درون برنامه قابل استفاده است.';
    } catch (_) { label.textContent = 'اعلان درون برنامه قابل استفاده است.'; }
  });
  poll(); setInterval(poll, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
