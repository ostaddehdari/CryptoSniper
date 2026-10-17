/* Static assets only. Financial responses and POST actions are never cached or queued. */
(() => {
  "use strict";
  const banner = document.querySelector("#offline-banner");
  const render = () => {
    if (!banner) return;
    banner.hidden = navigator.onLine;
  };
  window.addEventListener("online", render);
  window.addEventListener("offline", render);
  render();
  document.addEventListener("submit", event => {
    // A form control named "method" shadows HTMLFormElement.method (Smart Paste
    // intentionally has one), so read the attribute instead of the DOM property.
    const method = (event.target.getAttribute("method") || "get").toLowerCase();
    if (method === "post" && !navigator.onLine) {
      event.preventDefault();
      if (banner) {
        banner.hidden = false;
        banner.textContent = "اتصال قطع است؛ درخواست شما ذخیره یا صف نشد. پس از اتصال دوباره، خودتان مجدداً تأیید کنید.";
      }
    }
  });
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", () => navigator.serviceWorker.register(
      document.querySelector('link[rel="manifest"]').href.replace("manifest.webmanifest", "service-worker.js")
    ).catch(() => {}));
  }
})();
