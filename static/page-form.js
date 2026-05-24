// Shared by add.html + edit.html: toggle specific-date container based on
// the time_span radio selection.
(() => {
  const container = document.getElementById("specific-date-container");
  if (!container) return;
  document.querySelectorAll('input[name="time_span"]').forEach((input) => {
    input.addEventListener("change", () => {
      container.style.display = input.value === "specific_date" ? "block" : "none";
    });
  });
})();
