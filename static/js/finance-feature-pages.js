(() => {
    "use strict";

    const route =
        window.location.pathname
        .replace(/\/+$/, "")
        || "/";


    const configs = {

        "/subscriptions": {
            key: "subscriptions",

            eyebrow:
                "Recurring commitments",

            title:
                "Subscriptions",

            description:
                "See recurring services clearly, understand renewal cycles and keep monthly commitments under control.",

            tags: [
                "Renewals",
                "Monthly cost",
                "Annual impact"
            ],

            visual: `
                <svg viewBox="0 0 260 180">

                    <circle
                        cx="130"
                        cy="90"
                        r="31"
                        class="fp-fill">
                    </circle>

                    <circle
                        cx="130"
                        cy="90"
                        r="65"
                        class="fp-soft-line fp-dash">
                    </circle>

                    <circle
                        cx="130"
                        cy="25"
                        r="10"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="190"
                        cy="116"
                        r="10"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="70"
                        cy="116"
                        r="10"
                        class="fp-node">
                    </circle>

                    <path
                        d="M131 56
                           C165 55 189 70 196 101"
                        class="fp-line">
                    </path>

                    <path
                        d="M104 110
                           C94 116 85 118 80 118"
                        class="fp-line">
                    </path>

                    <text
                        x="130"
                        y="87"
                        text-anchor="middle"
                        class="fp-label">
                        RENEW
                    </text>

                    <text
                        x="130"
                        y="99"
                        text-anchor="middle">
                        cycle
                    </text>

                    <text
                        x="130"
                        y="10"
                        text-anchor="middle">
                        Service
                    </text>

                    <text
                        x="205"
                        y="121">
                        Apps
                    </text>

                    <text
                        x="37"
                        y="121">
                        Media
                    </text>

                </svg>
            `
        },


        "/budgets": {
            key: "budgets",

            eyebrow:
                "Spending architecture",

            title:
                "Budgets",

            description:
                "Create practical spending boundaries and understand how your planned money is distributed.",

            tags: [
                "Limits",
                "Categories",
                "Usage"
            ],

            visual: `
                <svg viewBox="0 0 260 180">

                    <rect
                        x="35"
                        y="42"
                        width="190"
                        height="28"
                        rx="7"
                        class="fp-soft-line">
                    </rect>

                    <rect
                        x="36"
                        y="43"
                        width="92"
                        height="26"
                        rx="6"
                        class="fp-fill">
                    </rect>

                    <rect
                        x="130"
                        y="43"
                        width="55"
                        height="26"
                        rx="6"
                        class="fp-fill">
                    </rect>

                    <rect
                        x="187"
                        y="43"
                        width="37"
                        height="26"
                        rx="6"
                        class="fp-fill">
                    </rect>

                    <path
                        d="M54 112H206"
                        class="fp-soft-line">
                    </path>

                    <circle
                        cx="64"
                        cy="112"
                        r="8"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="130"
                        cy="112"
                        r="8"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="196"
                        cy="112"
                        r="8"
                        class="fp-node">
                    </circle>

                    <path
                        d="M72 112H122"
                        class="fp-line fp-dash">
                    </path>

                    <path
                        d="M138 112H188"
                        class="fp-line fp-dash">
                    </path>

                    <text
                        x="64"
                        y="137"
                        text-anchor="middle">
                        Plan
                    </text>

                    <text
                        x="130"
                        y="137"
                        text-anchor="middle">
                        Spend
                    </text>

                    <text
                        x="196"
                        y="137"
                        text-anchor="middle">
                        Review
                    </text>

                </svg>
            `
        },


        "/goals": {
            key: "goals",

            eyebrow:
                "Future planning",

            title:
                "Savings Goals",

            description:
                "Turn future plans into visible targets and keep progress moving toward the amount you want to reach.",

            tags: [
                "Targets",
                "Progress",
                "Deadlines"
            ],

            visual: `
                <svg viewBox="0 0 260 180">

                    <circle
                        cx="171"
                        cy="89"
                        r="56"
                        class="fp-soft-line">
                    </circle>

                    <circle
                        cx="171"
                        cy="89"
                        r="37"
                        class="fp-soft-line">
                    </circle>

                    <circle
                        cx="171"
                        cy="89"
                        r="19"
                        class="fp-fill">
                    </circle>

                    <circle
                        cx="171"
                        cy="89"
                        r="5"
                        class="fp-node">
                    </circle>

                    <path
                        d="M37 137
                           L82 115
                           L121 101
                           L171 89"
                        class="fp-line">
                    </path>

                    <circle
                        cx="37"
                        cy="137"
                        r="6"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="82"
                        cy="115"
                        r="6"
                        class="fp-node">
                    </circle>

                    <circle
                        cx="121"
                        cy="101"
                        r="6"
                        class="fp-node">
                    </circle>

                    <text
                        x="169"
                        y="18"
                        class="fp-label">
                        TARGET
                    </text>

                </svg>
            `
        },


        "/reports": {
            key: "reports",

            eyebrow:
                "Financial intelligence",

            title:
                "Reports",

            description:
                "Turn transaction history into useful comparisons, patterns and a clearer picture of your finances.",

            tags: [
                "Analytics",
                "Trends",
                "Insights"
            ],

            visual: `
                <svg viewBox="0 0 260 180">

                    <path
                        d="M34 143H226"
                        class="fp-soft-line">
                    </path>

                    <path
                        d="M34 32V143"
                        class="fp-soft-line">
                    </path>

                    <rect
                        x="54"
                        y="96"
                        width="22"
                        height="47"
                        rx="3"
                        class="fp-fill">
                    </rect>

                    <rect
                        x="94"
                        y="68"
                        width="22"
                        height="75"
                        rx="3"
                        class="fp-fill">
                    </rect>

                    <rect
                        x="134"
                        y="82"
                        width="22"
                        height="61"
                        rx="3"
                        class="fp-fill">
                    </rect>

                    <rect
                        x="174"
                        y="50"
                        width="22"
                        height="93"
                        rx="3"
                        class="fp-fill">
                    </rect>

                    <path
                        d="M54 86
                           C79 82 94 56 116 63
                           C141 71 157 44 204 36"
                        class="fp-line">
                    </path>

                    <circle
                        cx="204"
                        cy="36"
                        r="4"
                        class="fp-node">
                    </circle>

                    <text
                        x="35"
                        y="21"
                        class="fp-label">
                        TREND
                    </text>

                </svg>
            `
        },


        "/recurring": {
            key: "recurring",

            eyebrow:
                "Scheduled money flow",

            title:
                "Recurring Transactions",

            description:
                "Keep repeated income and expenses predictable by organizing the transactions that run on a schedule.",

            tags: [
                "Schedules",
                "Next run",
                "Automation"
            ],

            visual: `
                <svg viewBox="0 0 260 180">

                    <circle
                        cx="130"
                        cy="90"
                        r="59"
                        class="fp-soft-line fp-dash">
                    </circle>

                    <path
                        d="M80 61
                           C103 30 145 26 174 51"
                        class="fp-line">
                    </path>

                    <path
                        d="M174 51
                           L164 49
                           M174 51
                           L171 41"
                        class="fp-line">
                    </path>

                    <path
                        d="M178 119
                           C153 150 111 154 82 128"
                        class="fp-line">
                    </path>

                    <path
                        d="M82 128
                           L92 130
                           M82 128
                           L85 138"
                        class="fp-line">
                    </path>

                    <circle
                        cx="130"
                        cy="90"
                        r="27"
                        class="fp-fill">
                    </circle>

                    <text
                        x="130"
                        y="87"
                        text-anchor="middle"
                        class="fp-label">
                        NEXT
                    </text>

                    <text
                        x="130"
                        y="99"
                        text-anchor="middle">
                        run
                    </text>

                </svg>
            `
        }

    };


    const config =
        configs[route];

    if (!config) {
        return;
    }


    document.body.classList.add(
        "finance-feature-ui",
        "fp-" + config.key
    );


    const root =
        document.querySelector(
            ".container"
        )
        || document.querySelector(
            "main"
        )
        || document.body;


    /*
     * Find the old page header.
     * Hide it only when it is really a header card,
     * never when it contains a form/table.
     */
    const possibleHeaders =
        [...root.children];


    const legacyHeader =
        possibleHeaders.find(
            element => {

                return (
                    element.querySelector
                    &&
                    element.querySelector("h1")
                    &&
                    !element.querySelector(
                        "form, table"
                    )
                );

            }
        );


    if (legacyHeader) {

        legacyHeader.classList.add(
            "feature-legacy-header"
        );

    }


    if (
        !root.querySelector(
            ".fp-hero"
        )
    ) {

        const hero =
            document.createElement(
                "section"
            );


        hero.className =
            "fp-hero";


        const tags =
            config.tags
            .map(
                item =>
                    `<span class="fp-tag">${item}</span>`
            )
            .join("");


        hero.innerHTML = `

            <div class="fp-hero-copy">

                <a
                    href="/"
                    class="fp-back">

                    <svg viewBox="0 0 24 24">
                        <path d="M19 12H5"></path>
                        <path d="M11 18l-6-6 6-6"></path>
                    </svg>

                    Dashboard

                </a>


                <span class="fp-eyebrow">
                    ${config.eyebrow}
                </span>


                <h1>
                    ${config.title}
                </h1>


                <p class="fp-description">
                    ${config.description}
                </p>


                <div class="fp-tags">
                    ${tags}
                </div>

            </div>


            <div class="fp-visual">
                ${config.visual}
            </div>

        `;


        if (legacyHeader) {

            legacyHeader.before(
                hero
            );

        } else {

            root.prepend(
                hero
            );

        }

    }


    /*
     * Upgrade existing functional cards only.
     * No backend fields/forms are replaced.
     */

    [...root.children]
    .forEach(
        element => {

            if (
                element.classList
                &&
                element.classList.contains(
                    "fp-hero"
                )
            ) {
                return;
            }


            if (
                element.classList
                &&
                element.classList.contains(
                    "feature-legacy-header"
                )
            ) {
                return;
            }


            if (
                element.matches
                &&
                element.matches(
                    ".card, section"
                )
            ) {

                element.classList.add(
                    "feature-panel"
                );

            }

        }
    );

})();
