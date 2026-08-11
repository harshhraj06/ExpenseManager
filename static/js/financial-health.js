(() => {
    function createCard() {
        if (
            document.getElementById(
                "financial-health-card"
            )
        ) {
            return;
        }

        const controlCenter =
            document.getElementById(
                "financial-health-zone"
            );

        if (!controlCenter) {
            return;
        }

        const card =
            document.createElement("article");

        card.id =
            "financial-health-card";

        card.className =
            "financial-health-card loading";

        card.innerHTML = `
            <div class="financial-health-score-wrap">

                <div class="financial-health-ring">

                    <span
                        class="financial-health-score"
                        id="financial-health-score">
                        —
                    </span>

                    <small>
                        /100
                    </small>

                </div>

            </div>

            <div class="financial-health-content">

                <span class="financial-health-eyebrow">
                    Financial Health
                </span>

                <div class="financial-health-title-row">

                    <h3
                        id="financial-health-label">
                        Calculating...
                    </h3>

                    <span
                        class="financial-health-status"
                        id="financial-health-status">
                        Live
                    </span>

                </div>

                <p
                    id="financial-health-insight">
                    Analyzing this month's finances.
                </p>

                <div class="financial-health-metrics">

                    <span>
                        Savings
                        <strong id="health-savings-rate">
                            —
                        </strong>
                    </span>

                    <span>
                        Budget
                        <strong id="health-budget-usage">
                            —
                        </strong>
                    </span>

                    <span>
                        Subs
                        <strong id="health-subscriptions">
                            —
                        </strong>
                    </span>

                    <span>
                        Bills
                        <strong id="health-bills">
                            —
                        </strong>
                    </span>

                </div>

            </div>
        `;

        controlCenter.appendChild(card);
    }


    function setStatus(status) {
        const card =
            document.getElementById(
                "financial-health-card"
            );

        if (!card) {
            return;
        }

        card.classList.remove(
            "loading",
            "excellent",
            "good",
            "fair",
            "poor"
        );

        card.classList.add(status);
    }


    async function loadFinancialHealth() {
        createCard();

        try {
            const response =
                await fetch(
                    "/api/financial-health",
                    {
                        credentials: "same-origin"
                    }
                );

            if (!response.ok) {
                throw new Error(
                    `HTTP ${response.status}`
                );
            }

            const data =
                await response.json();

            const metrics =
                data.metrics || {};

            const score =
                document.getElementById(
                    "financial-health-score"
                );

            const label =
                document.getElementById(
                    "financial-health-label"
                );

            const status =
                document.getElementById(
                    "financial-health-status"
                );

            const insight =
                document.getElementById(
                    "financial-health-insight"
                );

            const savingsRate =
                document.getElementById(
                    "health-savings-rate"
                );

            const budgetUsage =
                document.getElementById(
                    "health-budget-usage"
                );

            const subscriptions =
                document.getElementById(
                    "health-subscriptions"
                );

            const bills =
                document.getElementById(
                    "health-bills"
                );


            score.textContent =
                data.score ?? "—";

            label.textContent =
                data.label || "Unavailable";

            status.textContent =
                data.label || "Live";

            insight.textContent =
                data.insights?.[0]
                || "Financial health data is ready.";

            savingsRate.textContent =
                `${metrics.savings_rate ?? 0}%`;

            budgetUsage.textContent =
                metrics.budget_usage > 0
                    ? `${metrics.budget_usage}%`
                    : "Not set";

            subscriptions.textContent =
                `${metrics.subscription_burden ?? 0}%`;

            bills.textContent =
                metrics.overdue_bills > 0
                    ? `${metrics.overdue_bills} overdue`
                    : "Clear";


            setStatus(
                data.status || "fair"
            );

        } catch (error) {
            console.warn(
                "Financial health unavailable:",
                error
            );

            const label =
                document.getElementById(
                    "financial-health-label"
                );

            const insight =
                document.getElementById(
                    "financial-health-insight"
                );

            if (label) {
                label.textContent =
                    "Unavailable";
            }

            if (insight) {
                insight.textContent =
                    "Connect to refresh your financial score.";
            }

            setStatus("fair");
        }
    }


    document.addEventListener(
        "DOMContentLoaded",
        loadFinancialHealth
    );


    window.addEventListener(
        "expense-sync-complete",
        loadFinancialHealth
    );


    window.addEventListener(
        "online",
        loadFinancialHealth
    );
})();
