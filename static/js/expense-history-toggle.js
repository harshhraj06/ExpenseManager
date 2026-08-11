document.addEventListener(
    "DOMContentLoaded",
    function () {

        const button =
            document.getElementById(
                "toggle-expense-history"
            );

        const table =
            document.getElementById(
                "expense-history-table"
            );

        if (!button || !table) {
            console.warn(
                "Expense History toggle not available."
            );

            return;
        }

        // History visible by default
        table.classList.remove(
            "is-hidden"
        );

        function update() {

            const hidden =
                table.classList.contains(
                    "is-hidden"
                );

            button.textContent =
                hidden
                    ? "Show Expense History"
                    : "Hide Expense History";

            button.setAttribute(
                "aria-expanded",
                String(!hidden)
            );

            button.classList.toggle(
                "history-hidden",
                hidden
            );
        }

        button.addEventListener(
            "click",
            function () {

                table.classList.toggle(
                    "is-hidden"
                );

                update();
            }
        );

        update();
    }
);
