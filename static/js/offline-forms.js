(() => {
    function uuid() {
        if (crypto && typeof crypto.randomUUID === "function") {
            return crypto.randomUUID();
        }

        return (
            Date.now().toString(36) +
            "-" +
            Math.random().toString(36).slice(2)
        );
    }


    function showOfflineToast(message, type = "success") {
        let container =
            document.getElementById("offline-toast-container");

        if (!container) {
            container = document.createElement("div");
            container.id = "offline-toast-container";
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");

        toast.className =
            `offline-toast offline-toast-${type}`;

        const icon = document.createElement("span");
        icon.className = "offline-toast-icon";
        icon.textContent = type === "success" ? "✓" : "!";

        const text = document.createElement("span");
        text.textContent = message;

        toast.append(icon, text);
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


    async function queueOperation(type, data) {
        const operation = {
            operation_id: uuid(),
            type,
            data
        };

        const id =
            await ExpenseOfflineDB.add(operation);

        window.dispatchEvent(
            new CustomEvent("expense-offline-created", {
                detail: {
                    id,
                    ...operation
                }
            })
        );

        if (window.ExpenseSync) {
            await ExpenseSync.updateStatus();
        }

        return id;
    }


    async function queueExpense(form) {
        const formData = new FormData(form);

        const data = {
            amount: Number(formData.get("amount")),
            category:
                String(formData.get("category") || "").trim(),
            description:
                String(formData.get("description") || "").trim(),
            date:
                String(formData.get("date") || "").trim()
        };

        if (
            !Number.isFinite(data.amount) ||
            data.amount <= 0 ||
            !data.category ||
            !data.date
        ) {
            showOfflineToast(
                "Please complete the required expense fields.",
                "error"
            );

            return;
        }

        await queueOperation("expense", data);

        form.reset();

        showOfflineToast(
            "Expense saved offline. It will sync automatically."
        );
    }


    async function queueIncome(form) {
        const formData = new FormData(form);

        const data = {
            amount: Number(formData.get("amount")),
            source:
                String(formData.get("source") || "").trim(),
            date:
                String(formData.get("date") || "").trim()
        };

        if (
            !Number.isFinite(data.amount) ||
            data.amount <= 0 ||
            !data.source ||
            !data.date
        ) {
            showOfflineToast(
                "Please complete the required income fields.",
                "error"
            );

            return;
        }

        await queueOperation("income", data);

        form.reset();

        showOfflineToast(
            "Income saved offline. It will sync automatically."
        );
    }


    function bindExpenseForm() {
        const form =
            document.getElementById("expense-entry-form");

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
                console.error(error);

                showOfflineToast(
                    "Could not save expense offline.",
                    "error"
                );
            }
        });
    }


    function bindIncomeForm() {
        const form =
            document.getElementById("income-entry-form");

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
                console.error(error);

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
