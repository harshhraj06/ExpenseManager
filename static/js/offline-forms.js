(() => {
    function showOfflineToast(message, type = "success") {
        let container = document.getElementById("offline-toast-container");

        if (!container) {
            container = document.createElement("div");
            container.id = "offline-toast-container";
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.className = `offline-toast offline-toast-${type}`;

        toast.innerHTML = `
            <span class="offline-toast-icon">
                ${type === "success" ? "✓" : "!"}
            </span>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add("show");
        });

        setTimeout(() => {
            toast.classList.remove("show");

            setTimeout(() => {
                toast.remove();
            }, 250);
        }, 3200);
    }


    async function queueExpense(form) {
        const formData = new FormData(form);

        const data = {
            amount: formData.get("amount"),
            category: formData.get("category"),
            description: formData.get("description") || "",
            date: formData.get("date")
        };

        if (!data.amount || !data.category || !data.date) {
            showOfflineToast(
                "Please complete the required expense fields.",
                "error"
            );

            return;
        }

        await ExpenseOfflineDB.add({
            type: "expense",
            data
        });

        form.reset();

        showOfflineToast(
            "Expense saved offline. It will sync automatically."
        );

        if (window.ExpenseSync) {
            await ExpenseSync.updateStatus();
        }
    }


    async function queueIncome(form) {
        const formData = new FormData(form);

        const data = {
            amount: formData.get("amount"),
            source: formData.get("source"),
            date: formData.get("date")
        };

        if (!data.amount || !data.source || !data.date) {
            showOfflineToast(
                "Please complete the required income fields.",
                "error"
            );

            return;
        }

        await ExpenseOfflineDB.add({
            type: "income",
            data
        });

        form.reset();

        showOfflineToast(
            "Income saved offline. It will sync automatically."
        );

        if (window.ExpenseSync) {
            await ExpenseSync.updateStatus();
        }
    }


    function findIncomeForm() {
        return Array.from(document.forms).find(form => {
            return (
                form.querySelector('[name="source"]') &&
                form.querySelector('[name="amount"]') &&
                form.querySelector('[name="date"]')
            );
        });
    }


    function bindExpenseForm() {
        const form =
            document.querySelector('form[action="/add"]');

        if (!form || form.dataset.offlineBound === "true") {
            return;
        }

        form.dataset.offlineBound = "true";

        form.addEventListener("submit", async event => {
            if (navigator.onLine) {
                return;
            }

            event.preventDefault();

            try {
                await queueExpense(form);
            } catch (error) {
                console.error(
                    "Failed to save expense offline:",
                    error
                );

                showOfflineToast(
                    "Could not save expense offline.",
                    "error"
                );
            }
        });
    }


    function bindIncomeForm() {
        const form = findIncomeForm();

        if (!form || form.dataset.offlineBound === "true") {
            return;
        }

        form.dataset.offlineBound = "true";

        form.addEventListener("submit", async event => {
            if (navigator.onLine) {
                return;
            }

            event.preventDefault();

            try {
                await queueIncome(form);
            } catch (error) {
                console.error(
                    "Failed to save income offline:",
                    error
                );

                showOfflineToast(
                    "Could not save income offline.",
                    "error"
                );
            }
        });
    }


    document.addEventListener("DOMContentLoaded", () => {
        bindExpenseForm();
        bindIncomeForm();
    });


    window.ExpenseOfflineForms = {
        showOfflineToast
    };
})();
