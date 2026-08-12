(() => {
    "use strict";

    const heading = [...document.querySelectorAll("h1, h2, h3")]
        .find((el) =>
            (el.textContent || "")
                .trim()
                .toLowerCase() === "expense history"
        );

    if (!heading) {
        console.debug("Expense History heading not found");
        return;
    }

    const container =
        heading.closest(".card")
        || heading.parentElement;

    if (!container) {
        return;
    }

    /*
     * Find the Expense History table that occurs AFTER
     * the Expense History heading.
     */
    const historyTable =
        [...container.querySelectorAll("table")]
            .find((table) => {
                return Boolean(
                    heading.compareDocumentPosition(table)
                    & Node.DOCUMENT_POSITION_FOLLOWING
                );
            });

    if (!historyTable) {
        console.debug("Expense History table not found");
        return;
    }

    /*
     * Remove every old history toggle so competing
     * scripts cannot leave us with "Hide History".
     */
    container.querySelectorAll(
        ".expense-history-toggle-btn," +
        ".history-toggle-btn," +
        "#expenseHistoryToggle"
    ).forEach((button) => {
        button.remove();
    });

    let header =
        heading.closest(".section-header");

    if (!header) {
        header =
            heading.parentElement;
    }

    /*
     * Create action area.
     */
    let actions =
        header.querySelector(
            ".expense-history-header-actions"
        );

    if (!actions) {
        actions =
            document.createElement("div");

        actions.className =
            "expense-history-header-actions";

        /*
         * Move Download Expense Bill into
         * the action area if present.
         */
        const download =
            [...header.querySelectorAll("a")]
                .find((link) =>
                    (link.textContent || "")
                        .toLowerCase()
                        .includes("download expense bill")
                )
            ||
            [...container.querySelectorAll("a")]
                .find((link) =>
                    (link.textContent || "")
                        .toLowerCase()
                        .includes("download expense bill")
                );

        if (download) {
            actions.appendChild(download);
        }

        header.appendChild(actions);
    }

    const button =
        document.createElement("button");

    button.type = "button";

    button.id =
        "expenseHistoryToggle";

    button.className =
        "expense-history-toggle-btn";

    const eyeIcon = `
        <svg
            viewBox="0 0 24 24"
            aria-hidden="true">

            <path
                d="M2.5 12s3.5-6 9.5-6
                   9.5 6 9.5 6
                   -3.5 6-9.5 6
                   -9.5-6-9.5-6">
            </path>

            <circle
                cx="12"
                cy="12"
                r="2.7">
            </circle>
        </svg>
    `;

    let opened = false;

    function hideHistory() {
        opened = false;

        historyTable.hidden = true;

        historyTable.style.setProperty(
            "display",
            "none",
            "important"
        );

        container.classList.remove(
            "expense-history-open"
        );

        button.innerHTML =
            eyeIcon +
            "<span>Show History</span>";

        button.setAttribute(
            "aria-expanded",
            "false"
        );
    }

    function showHistory() {
        opened = true;

        historyTable.hidden = false;

        historyTable.style.setProperty(
            "display",
            "table",
            "important"
        );

        container.classList.add(
            "expense-history-open"
        );

        button.innerHTML =
            eyeIcon +
            "<span>Hide History</span>";

        button.setAttribute(
            "aria-expanded",
            "true"
        );
    }

    button.addEventListener(
        "click",
        () => {
            if (opened) {
                hideHistory();
            } else {
                showHistory();
            }
        }
    );

    actions.appendChild(button);

    /*
     * CRITICAL:
     * Always start hidden after every page refresh.
     */
    hideHistory();

})();
