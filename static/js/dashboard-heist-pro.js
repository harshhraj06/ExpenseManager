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
                    "finance-intelligence-panel"
                )
            ) {
                return;
            }


            financeMap.classList.add(
                "finance-intelligence-panel"
            );


            financeMap.remove();

        }
    );

})();
