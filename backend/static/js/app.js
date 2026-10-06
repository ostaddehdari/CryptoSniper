document.addEventListener('alpine:init', () => {
  Alpine.data('workspace', () => ({
    menuOpen: false, profileOpen: false, theme: 'light',
    init() {
      try { this.theme = localStorage.getItem('cs-theme') === 'dark' ? 'dark' : 'light'; }
      catch (_) { this.theme = 'light'; }
      document.documentElement.dataset.theme = this.theme;
      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') { this.menuOpen = false; this.profileOpen = false; }
      });
    },
    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light';
      document.documentElement.dataset.theme = this.theme;
      try { localStorage.setItem('cs-theme', this.theme); } catch (_) {}
    }
  }));
});
document.addEventListener('htmx:responseError', (event) => {
  if (event.detail.xhr.status === 503 && event.detail.target.id === 'probe-result') {
    event.detail.target.textContent = 'ارتباط با صف برقرار نشد. وضعیت سرویس‌ها را بررسی کنید.';
  }
});
