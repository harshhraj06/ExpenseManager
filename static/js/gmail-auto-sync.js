(() => {
    "use strict";

    const STORAGE_KEY =
        "expense_manager_gmail_auto_sync";

    const SIX_HOURS =
        6 * 60 * 60 * 1000;

    function shouldCheck() {
        const previous =
            Number(
                localStorage.getItem(
                    STORAGE_KEY
                )
            ) || 0;

        return (
            Date.now() - previous
        ) >= SIX_HOURS;
    }

    async function autoSyncGmail() {
        if (!shouldCheck()) {
            return;
        }

        /*
         * Save immediately so rapid reloads do not create
         * several simultaneous Gmail requests.
         */
        localStorage.setItem(
            STORAGE_KEY,
            String(Date.now())
        );

        try {
            const response = await fetch(
                "/api/gmail/auto-sync",
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-Requested-With":
                            "XMLHttpRequest"
                    }
                }
            );

            if (!response.ok) {
                /*
                 * Allow a retry on the next page visit if
                 * this attempt genuinely failed.
                 */
                localStorage.removeItem(
                    STORAGE_KEY
                );

                return;
            }

            const result =
                await response.json();

            console.debug(
                "Gmail auto-sync:",
                result.status
            );

        } catch (error) {
            localStorage.removeItem(
                STORAGE_KEY
            );

            console.debug(
                "Gmail auto-sync unavailable"
            );
        }
    }

    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            autoSyncGmail
        );
    } else {
        autoSyncGmail();
    }
})();
