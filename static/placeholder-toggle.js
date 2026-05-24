// Inputs/textareas with data-placeholder get focus/blur toggling: clear on
// focus, restore on blur. Replaces inline onfocus/onblur attrs (CSP).
(() => {
  document.querySelectorAll("[data-placeholder]").forEach((el) => {
    const original = el.dataset.placeholder;
    if (!el.placeholder) el.placeholder = original;
    el.addEventListener("focus", () => {
      el.placeholder = "";
    });
    el.addEventListener("blur", () => {
      el.placeholder = original;
    });
  });
})();
