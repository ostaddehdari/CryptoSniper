/* Same-history form recovery only: no localStorage, Cache API or offline POST queue. */
(() => {
  "use strict";
  const forms = [...document.querySelectorAll("[data-preserve-form]")];
  if (!forms.length) return;
  const key = `form:${location.pathname}`;
  const state = history.state?.[key];
  if (state) {
    for (const form of forms) {
      for (const field of form.elements) {
        if (!field.name || !(field.name in state) || field.type === "hidden" || field.dataset.noDraft === "1") continue;
        if (field.type === "checkbox" || field.type === "radio") {
          field.checked = state[field.name] === field.value || state[field.name] === true;
        } else if (!field.value) {
          field.value = state[field.name];
        }
      }
    }
  }
  function remember() {
    const draft = {};
    for (const form of forms) {
      for (const field of form.elements) {
        if (!field.name || field.name === "csrfmiddlewaretoken" || field.type === "hidden" || field.dataset.noDraft === "1") continue;
        if (field.type === "checkbox") draft[field.name] = field.checked;
        else if (field.type !== "submit") draft[field.name] = field.value;
      }
    }
    history.replaceState({...history.state, [key]: draft}, "");
  }
  forms.forEach(form => form.addEventListener("input", remember));
  if (window.visualViewport) {
    const viewport = window.visualViewport;
    const updateKeyboard = () => {
      const covered = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      document.documentElement.style.setProperty("--keyboard-offset", `${covered}px`);
    };
    viewport.addEventListener("resize", updateKeyboard);
    viewport.addEventListener("scroll", updateKeyboard);
    updateKeyboard();
  }
})();
