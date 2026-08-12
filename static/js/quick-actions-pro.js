(() => {
    "use strict";


    const actions = {

        expense: {
            className:
                "qa-expense",

            title:
                "Add Expense",

            description:
                "Record new spending",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path d="M12 5v14"></path>
                    <path d="M7 14l5 5 5-5"></path>
                    <path d="M5 4h14"></path>
                </svg>
            `
        },


        income: {
            className:
                "qa-income",

            title:
                "Add Income",

            description:
                "Record money received",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path d="M12 19V5"></path>
                    <path d="M7 10l5-5 5 5"></path>
                    <path d="M5 20h14"></path>
                </svg>
            `
        },


        bills: {
            className:
                "qa-bills",

            title:
                "Bills",

            description:
                "Manage scheduled payments",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path
                        d="M6 3h12v18
                           l-3-2-3 2-3-2-3 2z">
                    </path>
                    <path d="M9 8h6"></path>
                    <path d="M9 12h6"></path>
                </svg>
            `
        },


        budget: {
            className:
                "qa-budget",

            title:
                "Budgets",

            description:
                "Set spending limits",

            icon: `
                <svg viewBox="0 0 24 24">
                    <rect
                        x="3"
                        y="6"
                        width="18"
                        height="13"
                        rx="2">
                    </rect>
                    <path d="M16 11h5v4h-5a2 2 0 0 1 0-4z"></path>
                    <path d="M6 6V4h11"></path>
                </svg>
            `
        },


        goals: {
            className:
                "qa-goals",

            title:
                "Goals",

            description:
                "Track saving targets",

            icon: `
                <svg viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="8"></circle>
                    <circle cx="12" cy="12" r="4"></circle>
                    <circle cx="12" cy="12" r="1"></circle>
                </svg>
            `
        },


        subscription: {
            className:
                "qa-subscription",

            title:
                "Subscriptions",

            description:
                "Watch recurring services",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path d="M7 7h10"></path>
                    <path d="M17 7l-2-2"></path>
                    <path d="M17 7l-2 2"></path>

                    <path d="M17 17H7"></path>
                    <path d="M7 17l2-2"></path>
                    <path d="M7 17l2 2"></path>
                </svg>
            `
        },


        reports: {
            className:
                "qa-reports",

            title:
                "Reports",

            description:
                "Review financial insights",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path d="M5 20V11"></path>
                    <path d="M12 20V4"></path>
                    <path d="M19 20v-6"></path>
                </svg>
            `
        },


        recurring: {
            className:
                "qa-recurring",

            title:
                "Recurring",

            description:
                "Manage repeat transactions",

            icon: `
                <svg viewBox="0 0 24 24">
                    <path d="M20 7v5h-5"></path>
                    <path d="M4 17v-5h5"></path>
                    <path
                        d="M6 8
                           a7 7 0 0 1
                           12-1l2 5">
                    </path>
                    <path
                        d="M18 16
                           a7 7 0 0 1
                           -12 1l-2-5">
                    </path>
                </svg>
            `
        },


        split: {
            className:
                "qa-split",

            title:
                "Split Expense",

            description:
                "Share costs with groups",

            icon: `
                <svg viewBox="0 0 24 24">
                    <circle cx="8" cy="8" r="3"></circle>
                    <circle cx="17" cy="9" r="2"></circle>
                    <path d="M2 20c0-4 2.6-6 6-6s6 2 6 6"></path>
                    <path d="M15 15c3 0 5 1.7 5 5"></path>
                </svg>
            `
        },


        apps: {
            className:
                "qa-apps",

            title:
                "Connected Apps",

            description:
                "Manage automatic imports",

            icon: `
                <svg viewBox="0 0 24 24">
                    <rect x="4" y="4" width="6" height="6" rx="1"></rect>
                    <rect x="14" y="4" width="6" height="6" rx="1"></rect>
                    <rect x="4" y="14" width="6" height="6" rx="1"></rect>
                    <rect x="14" y="14" width="6" height="6" rx="1"></rect>
                </svg>
            `
        }

    };


    function identify(
        element
    ) {

        const href =
            (
                element.getAttribute(
                    "href"
                )
                || ""
            )
            .toLowerCase();


        const label =
            (
                element.textContent
                || ""
            )
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();


        if (
            href.includes(
                "connected_apps"
            )
            ||
            label.includes(
                "connected app"
            )
        ) {
            return "apps";
        }


        if (
            href.includes(
                "subscription"
            )
            ||
            label.includes(
                "subscription"
            )
        ) {
            return "subscription";
        }


        if (
            href.includes(
                "recurring"
            )
            ||
            label.includes(
                "recurring"
            )
        ) {
            return "recurring";
        }


        if (
            href.includes(
                "report"
            )
            ||
            label.includes(
                "report"
            )
        ) {
            return "reports";
        }


        if (
            href.includes(
                "budget"
            )
            ||
            label.includes(
                "budget"
            )
        ) {
            return "budget";
        }


        if (
            href.includes(
                "goal"
            )
            ||
            label.includes(
                "goal"
            )
        ) {
            return "goals";
        }


        if (
            href.includes(
                "group"
            )
            ||
            label.includes(
                "split"
            )
            ||
            label.includes(
                "group"
            )
        ) {
            return "split";
        }


        if (
            href.includes(
                "bill"
            )
            ||
            label.includes(
                "bill"
            )
        ) {
            return "bills";
        }


        if (
            href.includes(
                "income"
            )
            ||
            label.includes(
                "income"
            )
        ) {
            return "income";
        }


        if (
            href.includes(
                "expense"
            )
            ||
            label.includes(
                "expense"
            )
        ) {
            return "expense";
        }


        return null;
    }


    document.querySelectorAll(
        ".pro-actions .pro-action"
    )
    .forEach((element) => {

        const type =
            identify(
                element
            );

        if (!type) {
            return;
        }


        const config =
            actions[type];


        element.classList.add(
            "qa-action",
            config.className
        );


        element.innerHTML = `
            <span class="qa-action-icon">
                ${config.icon}
            </span>

            <span class="qa-action-copy">

                <span class="qa-action-title">
                    ${config.title}
                </span>

                <span class="qa-action-description">
                    ${config.description}
                </span>

            </span>
        `;

    });

})();
