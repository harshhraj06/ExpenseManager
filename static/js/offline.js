(() => {
    function createIndicator() {
        if (document.getElementById("offline-indicator")) {
            return;
        }

        const indicator = document.createElement("div");

        indicator.id = "offline-indicator";

        indicator.innerHTML = `
            <span class="offline-dot"></span>
            <span class="offline-text">Online</span>
            <span class="offline-pending"></span>
        `;

        document.body.appendChild(indicator);
    }

    async function updateIndicator(event = null) {
        const indicator = document.getElementById("offline-indicator");

        if (!indicator) {
            return;
        }

        const text = indicator.querySelector(".offline-text");
        const pending = indicator.querySelector(".offline-pending");
        const dot = indicator.querySelector(".offline-dot");

        const online =
            event?.detail?.online ??
            navigator.onLine;

        const syncing =
            event?.detail?.syncing ??
            false;

        const pendingCount =
            event?.detail?.pending ??
            await ExpenseOfflineDB.count();

        dot.classList.toggle("offline", !online);
        dot.classList.toggle("syncing", syncing);

        if (!online) {
            text.textContent = "Offline";
        } else if (syncing) {
            text.textContent = "Syncing";
        } else {
            text.textContent = "Online";
        }

        pending.textContent =
            pendingCount > 0
                ? `${pendingCount} pending`
                : "";
    }

    window.addEventListener(
        "expense-sync-status",
        event => updateIndicator(event)
    );

    window.addEventListener(
        "expense-sync-start",
        () => updateIndicator()
    );

    window.addEventListener(
        "expense-sync-complete",
        () => updateIndicator()
    );

    window.addEventListener(
        "online",
        () => updateIndicator()
    );

    window.addEventListener(
        "offline",
        () => updateIndicator()
    );

    window.addEventListener("load", async () => {
        createIndicator();

        await updateIndicator();

        if ("serviceWorker" in navigator) {
            try {
                await navigator.serviceWorker.register(
                    "/service-worker.js"
                );
            } catch (error) {
                console.warn(
                    "Service worker registration failed:",
                    error
                );
            }
        }
    });
})();
