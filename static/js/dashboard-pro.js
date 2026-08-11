(() => {
    function formatToday() {
        const element =
            document.getElementById("pro-today");

        if (!element) {
            return;
        }

        element.textContent =
            new Intl.DateTimeFormat("en-IN", {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric"
            }).format(new Date());
    }


    async function updateSyncHealth(detail = {}) {
        const element =
            document.getElementById("pro-sync-health");

        if (!element) {
            return;
        }

        const label =
            element.querySelector(".pro-sync-health-label");

        let pending =
            detail.pending;

        if (
            pending === undefined &&
            window.ExpenseOfflineDB
        ) {
            try {
                pending =
                    await ExpenseOfflineDB.count();
            } catch {
                pending = 0;
            }
        }

        pending = Number(pending || 0);

        const online =
            detail.online !== undefined
                ? detail.online
                : navigator.onLine;

        const syncing =
            Boolean(detail.syncing);

        element.classList.remove(
            "offline",
            "syncing"
        );

        if (!online) {
            element.classList.add("offline");

            label.textContent =
                pending > 0
                    ? `Offline · ${pending} pending`
                    : "Offline";
        } else if (syncing) {
            element.classList.add("syncing");

            label.textContent =
                pending > 0
                    ? `Syncing ${pending}`
                    : "Syncing";
        } else {
            label.textContent =
                pending > 0
                    ? `${pending} pending`
                    : "All synced";
        }
    }


    function smoothActions() {
        document
            .querySelectorAll(
                '.pro-action[href^="#"]'
            )
            .forEach(link => {
                link.addEventListener(
                    "click",
                    event => {
                        const selector =
                            link.getAttribute("href");

                        const target =
                            document.querySelector(
                                selector
                            );

                        if (!target) {
                            return;
                        }

                        event.preventDefault();

                        target.scrollIntoView({
                            behavior: "smooth",
                            block: "center"
                        });
                    }
                );
            });
    }


    window.addEventListener(
        "expense-sync-status",
        event => {
            updateSyncHealth(
                event.detail || {}
            );
        }
    );


    window.addEventListener(
        "expense-sync-start",
        () => {
            updateSyncHealth({
                online: navigator.onLine,
                syncing: true
            });
        }
    );


    window.addEventListener(
        "expense-sync-complete",
        () => {
            updateSyncHealth({
                online: navigator.onLine,
                syncing: false
            });
        }
    );


    window.addEventListener(
        "online",
        () => updateSyncHealth()
    );


    window.addEventListener(
        "offline",
        () => updateSyncHealth()
    );


    document.addEventListener(
        "DOMContentLoaded",
        () => {
            formatToday();
            smoothActions();
            updateSyncHealth();
        }
    );
})();
