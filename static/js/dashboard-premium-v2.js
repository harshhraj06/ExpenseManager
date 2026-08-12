(() => {
    "use strict";

    document.body.classList.add(
        "dashboard-premium-v2"
    );


    /* ======================================================
       PROFESSIONAL ASK EXPENSE MANAGER ICON
       ====================================================== */

    const aiIcon =
        document.querySelector(
            ".ai-banner-icon"
        );

    if (aiIcon) {

        /*
         * Professional AI / intelligence orbit icon.
         * Replaces the robot emoji.
         */
        aiIcon.innerHTML = `
            <svg
                viewBox="0 0 24 24"
                aria-hidden="true">

                <circle
                    cx="12"
                    cy="12"
                    r="3.2">
                </circle>

                <path
                    d="M4.6 8.4
                       C6.6 5.4 10 4.1 13.1 4.7
                       C16.2 5.3 18.5 7.7 19.2 10.5">
                </path>

                <path
                    d="M19.4 15.6
                       C17.4 18.6 14 19.9 10.9 19.3
                       C7.8 18.7 5.5 16.3 4.8 13.5">
                </path>

                <circle
                    cx="4.4"
                    cy="8"
                    r="1.1">
                </circle>

                <circle
                    cx="19.6"
                    cy="16"
                    r="1.1">
                </circle>

            </svg>
        `;

        aiIcon.setAttribute(
            "aria-label",
            "AI assistant"
        );
    }


    /* ======================================================
       FINANCIAL CONTROL CENTER ICONS
       ====================================================== */

    const icons = {

        expense: `
            <svg viewBox="0 0 24 24">
                <path d="M12 5v14"></path>
                <path d="M5 12h14"></path>
            </svg>
        `,

        income: `
            <svg viewBox="0 0 24 24">
                <path d="M12 19V5"></path>
                <path d="M7 10l5-5 5 5"></path>
            </svg>
        `,

        bills: `
            <svg viewBox="0 0 24 24">
                <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"></path>
                <path d="M9 8h6"></path>
                <path d="M9 12h6"></path>
            </svg>
        `,

        groups: `
            <svg viewBox="0 0 24 24">
                <circle cx="9" cy="8" r="3"></circle>
                <circle cx="17" cy="9" r="2"></circle>
                <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5"></path>
                <path d="M15 15c3 0 5 1.5 5 4"></path>
            </svg>
        `,

        apps: `
            <svg viewBox="0 0 24 24">
                <rect x="4" y="4" width="6" height="6" rx="1"></rect>
                <rect x="14" y="4" width="6" height="6" rx="1"></rect>
                <rect x="4" y="14" width="6" height="6" rx="1"></rect>
                <rect x="14" y="14" width="6" height="6" rx="1"></rect>
            </svg>
        `,

        budget: `
            <svg viewBox="0 0 24 24">
                <rect x="3" y="6" width="18" height="13" rx="2"></rect>
                <path d="M16 11h5v4h-5a2 2 0 0 1 0-4z"></path>
                <path d="M6 6V4h10"></path>
            </svg>
        `,

        goal: `
            <svg viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8"></circle>
                <circle cx="12" cy="12" r="4"></circle>
                <path d="M12 2v4"></path>
            </svg>
        `,

        report: `
            <svg viewBox="0 0 24 24">
                <path d="M5 20V10"></path>
                <path d="M12 20V4"></path>
                <path d="M19 20v-7"></path>
            </svg>
        `,

        recurring: `
            <svg viewBox="0 0 24 24">
                <path d="M20 7v5h-5"></path>
                <path d="M4 17v-5h5"></path>
                <path d="M6.1 8a7 7 0 0 1 11.6-1L20 12"></path>
                <path d="M17.9 16a7 7 0 0 1-11.6 1L4 12"></path>
            </svg>
        `,

        default: `
            <svg viewBox="0 0 24 24">
                <path d="M5 12h14"></path>
                <path d="M13 6l6 6-6 6"></path>
            </svg>
        `
    };


    function iconForAction(
        action,
        text
    ) {

        const href =
            (
                action.getAttribute("href")
                || ""
            ).toLowerCase();

        const value =
            text.toLowerCase();


        if (
            href.includes("expense")
            || value.includes("expense")
        ) {
            return icons.expense;
        }


        if (
            href.includes("income")
            || value.includes("income")
        ) {
            return icons.income;
        }


        if (
            href.includes("bill")
            || value.includes("bill")
        ) {
            return icons.bills;
        }


        if (
            href.includes("group")
            || value.includes("split")
            || value.includes("group")
        ) {
            return icons.groups;
        }


        if (
            href.includes("connected_apps")
            || value.includes("connected")
            || value.includes("apps")
        ) {
            return icons.apps;
        }


        if (
            href.includes("budget")
            || value.includes("budget")
        ) {
            return icons.budget;
        }


        if (
            href.includes("goal")
            || value.includes("goal")
        ) {
            return icons.goal;
        }


        if (
            href.includes("report")
            || value.includes("report")
        ) {
            return icons.report;
        }


        if (
            href.includes("recurring")
            || value.includes("recurring")
        ) {
            return icons.recurring;
        }


        return icons.default;
    }


    document.querySelectorAll(
        ".pro-action"
    ).forEach((action) => {

        if (
            action.querySelector(
                ".pro-action-icon"
            )
        ) {
            return;
        }


        const original =
            (
                action.textContent
                || ""
            )
            .replace(/\s+/g, " ")
            .trim();


        /*
         * Remove the old leading +
         * because the icon now communicates
         * the action more professionally.
         */
        const label =
            original.replace(
                /^\+\s*/,
                ""
            );


        const icon =
            document.createElement(
                "span"
            );

        icon.className =
            "pro-action-icon";

        icon.innerHTML =
            iconForAction(
                action,
                label
            );


        const labelElement =
            document.createElement(
                "span"
            );

        labelElement.className =
            "pro-action-label";

        labelElement.textContent =
            label;


        action.textContent = "";

        action.appendChild(icon);
        action.appendChild(
            labelElement
        );

    });

})();
