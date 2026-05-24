// index page: button that navigates to the add-goal route.
(() => {
  const btn = document.getElementById("add-goal-button");
  if (!btn || !btn.dataset.href) return;
  btn.addEventListener("click", () => {
    window.location.href = btn.dataset.href;
  });
})();
