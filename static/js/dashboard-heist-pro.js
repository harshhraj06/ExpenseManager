(() => {
    "use strict";

    document.addEventListener(
        "DOMContentLoaded",
        () => {

            const financeMap =
                document.querySelector(
                    ".hero-finance-map"
                );

            if (!financeMap) {
                return;
            }


            if (
                financeMap.classList.contains(
                    "professor-strategy-panel"
                )
            ) {
                return;
            }


            financeMap.classList.add(
                "professor-strategy-panel"
            );


            financeMap.innerHTML = `

                <div class="professor-panel-inner">

                    <div class="professor-panel-head">

                        <div>

                            <span class="professor-panel-label">
                                Strategic Finance Desk
                            </span>

                            <strong class="professor-panel-title">
                                ExpenseX Intelligence
                            </strong>

                        </div>


                        <span class="professor-panel-live">
                            Monitoring
                        </span>

                    </div>



                    <div class="professor-main">

                        <div
                            class="professor-portrait"
                            aria-hidden="true">

                            <div class="professor-head"></div>

                            <div class="professor-glasses">
                                <span></span>
                            </div>

                            <div class="professor-beard"></div>

                            <div class="professor-body"></div>

                        </div>


                        <div class="professor-copy">

                            <small>
                                Professor Mode
                            </small>

                            <h3>
                                Every rupee needs a plan.
                            </h3>

                            <p>
                                Observe spending.
                                Understand the pattern.
                                Control the next move.
                            </p>

                        </div>

                    </div>



                    <div class="professor-strategy-line">

                        <div class="professor-step">

                            <div class="professor-step-icon">
                                01
                            </div>

                            <span>
                                Track
                            </span>

                        </div>


                        <div class="professor-step">

                            <div class="professor-step-icon">
                                02
                            </div>

                            <span>
                                Analyze
                            </span>

                        </div>


                        <div class="professor-step">

                            <div class="professor-step-icon">
                                03
                            </div>

                            <span>
                                Decide
                            </span>

                        </div>


                        <div class="professor-step">

                            <div class="professor-step-icon">
                                04
                            </div>

                            <span>
                                Grow
                            </span>

                        </div>

                    </div>



                    <div class="professor-panel-footer">

                        <span class="professor-quote">
                            “The strongest plan starts
                            with knowing the numbers.”
                        </span>

                        <span class="professor-mode-chip">
                            Strategy active
                        </span>

                    </div>

                </div>
            `;

        }
    );

})();
