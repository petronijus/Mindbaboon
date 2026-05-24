// Edit page: load and render goal history below the form.
(() => {
  const table = document.getElementById("iteration-history");
  if (!table) return;
  const goalId = table.dataset.goalId;
  if (!goalId) return;

  function formatTimestamp(ts) {
    const date = new Date(ts);
    const dd = String(date.getDate()).padStart(2, "0");
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const yy = String(date.getFullYear()).slice(-2);
    return `${dd}/${mm}/${yy}`;
  }

  fetch(`/goal/${goalId}/history`)
    .then((r) => r.json())
    .then((rows) => {
      const tbody = table.querySelector("tbody");
      tbody.innerHTML = "";
      rows.forEach((row) => {
        const tr = document.createElement("tr");
        const cells = [
          row.timestamp ? formatTimestamp(row.timestamp) : "N/A",
          row.completed || "N/A",
          row.was_done || "N/A",
          row.next_steps || "N/A",
          row.reward || "N/A",
        ];
        cells.forEach((text) => {
          const td = document.createElement("td");
          td.textContent = text;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    })
    .catch((e) => console.error("Error loading goal history:", e));
})();
