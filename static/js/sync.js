const ExpenseSync = (() => {
  let syncing = false;

  async function sync() {
    if (syncing || !navigator.onLine) return;

    syncing = true;

    try {
      const operations = await ExpenseOfflineDB.all();

      for (const operation of operations) {
        try {
          const response = await fetch("/api/offline-sync", {
            method: "POST",
            headers: {
              "Content-Type": "application/json"
            },
            credentials: "same-origin",
            body: JSON.stringify(operation)
          });

          if (response.ok) {
            await ExpenseOfflineDB.remove(operation.id);
          }
        } catch {
          break;
        }
      }

      updateStatus();
    } finally {
      syncing = false;
    }
  }

  async function updateStatus() {
    const count = await ExpenseOfflineDB.count();

    window.dispatchEvent(
      new CustomEvent("expense-sync-status", {
        detail: {
          pending: count,
          online: navigator.onLine
        }
      })
    );
  }

  window.addEventListener("online", sync);

  window.addEventListener("offline", updateStatus);

  window.addEventListener("load", () => {
    updateStatus();
    sync();
  });

  return {
    sync,
    updateStatus
  };
})();
