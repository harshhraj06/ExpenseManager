const ExpenseSync = (() => {
    let syncing = false;

    async function sync() {
        if (syncing || !navigator.onLine) {
            return;
        }

        syncing = true;

        window.dispatchEvent(
            new CustomEvent("expense-sync-start")
        );

        try {
            const operations = await ExpenseOfflineDB.all();

            if (!operations.length) {
                updateStatus();
                return;
            }

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

                        window.dispatchEvent(
                            new CustomEvent("expense-sync-operation", {
                                detail: {
                                    operation
                                }
                            })
                        );
                    } else if (response.status === 401 || response.status === 403) {
                        console.warn(
                            "Offline operation rejected because authentication is required."
                        );

                        break;
                    } else {
                        console.warn(
                            "Offline operation failed:",
                            response.status
                        );

                        break;
                    }
                } catch (error) {
                    console.warn(
                        "Sync interrupted:",
                        error
                    );

                    break;
                }
            }
        } finally {
            syncing = false;

            window.dispatchEvent(
                new CustomEvent("expense-sync-complete")
            );

            await updateStatus();
        }
    }

    async function updateStatus() {
        const pending = await ExpenseOfflineDB.count();

        window.dispatchEvent(
            new CustomEvent("expense-sync-status", {
                detail: {
                    pending,
                    online: navigator.onLine,
                    syncing
                }
            })
        );
    }

    window.addEventListener("online", () => {
        updateStatus();
        sync();
    });

    window.addEventListener("offline", updateStatus);

    window.addEventListener("load", () => {
        updateStatus();

        if (navigator.onLine) {
            sync();
        }
    });

    return {
        sync,
        updateStatus
    };
})();
