(() => {
  function createIndicator() {
    if (document.getElementById("offline-indicator")) return;

    const indicator = document.createElement("div");
    indicator.id = "offline-indicator";

    indicator.innerHTML = `
      <span class="offline-dot"></span>
      <span class="offline-text">Online</span>
      <span class="offline-pending"></span>
    `;

    document.body.appendChild(indicator);
  }

  function updateIndicator() {
    const indicator = document.getElementById("offline-indicator");
    if (!indicator) return;

    const text = indicator.querySelector(".offline-text");
    const pending = indicator.querySelector(".offline-pending");
    const dot = indicator.querySelector(".offline-dot");

    if (navigator.onLine) {
      text.textContent = "Online";
      dot.classList.remove("offline");
    } else {
      text.textContent = "Offline";
      dot.classList.add("offline");
    }

    ExpenseOfflineDB.count().then(count => {
      pending.textContent =
        count > 0 ? `${count} pending` : "";
    });
  }

  window.addEventListener("online", updateIndicator);
  window.addEventListener("offline", updateIndicator);

  window.addEventListener("expense-sync-status", updateIndicator);

  window.addEventListener("load", () => {
    createIndicator();
    updateIndicator();

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/static/service-worker.js")
        .catch(error =>
          console.warn("Service worker registration failed:", error)
        );
    }
  });
})();
