(() => {
    const renderedOperations = new Set();


    function numberFromElement(id) {
        const element = document.getElementById(id);

        if (!element) {
            return 0;
        }

        const value =
            element.dataset.value ??
            element.textContent.replace(/[₹,\s]/g, "");

        const parsed = Number(value);

        return Number.isFinite(parsed) ? parsed : 0;
    }


    function money(value) {
        return Number(value).toLocaleString("en-IN", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }


    function setMoney(id, value) {
        const element = document.getElementById(id);

        if (!element) {
            return;
        }

        element.dataset.value = String(value);
        element.textContent = `₹${money(value)}`;
    }


    function adjustStats(type, amount) {
        let income =
            numberFromElement("total-income-value");

        let expense =
            numberFromElement("total-expense-value");

        let balance =
            numberFromElement("balance-value");

        if (type === "expense") {
            expense += amount;
            balance -= amount;
        }

        if (type === "income") {
            income += amount;
            balance += amount;
        }

        setMoney("total-income-value", income);
        setMoney("total-expense-value", expense);
        setMoney("balance-value", balance);
    }


    function statusCell(operationId) {
        const cell = document.createElement("td");

        const badge = document.createElement("span");

        badge.className = "offline-row-status pending";
        badge.textContent = "Pending sync";

        cell.appendChild(badge);

        return cell;
    }


    function createExpenseRow(operation) {
        const table =
            document.getElementById("expense-history-table");

        if (!table) {
            return;
        }

        const row = table.insertRow(1);

        row.className = "offline-transaction-row";
        row.dataset.offlineOperationId =
            String(operation.id);

        const amount = row.insertCell();
        const category = row.insertCell();
        const description = row.insertCell();
        const date = row.insertCell();

        amount.textContent =
            `₹${money(operation.data.amount)}`;

        category.textContent =
            operation.data.category;

        description.textContent =
            operation.data.description || "—";

        date.textContent =
            operation.data.date;

        row.appendChild(statusCell(operation.id));
    }


    function createIncomeRow(operation) {
        const table =
            document.getElementById("income-history-table");

        if (!table) {
            return;
        }

        const row = table.insertRow(1);

        row.className = "offline-transaction-row";
        row.dataset.offlineOperationId =
            String(operation.id);

        const amount = row.insertCell();
        const source = row.insertCell();
        const date = row.insertCell();

        amount.textContent =
            `₹${money(operation.data.amount)}`;

        source.textContent =
            operation.data.source;

        date.textContent =
            operation.data.date;

        row.appendChild(statusCell(operation.id));

        const finalCell = row.insertCell();

        const badge = document.createElement("span");

        badge.className = "offline-local-badge";
        badge.textContent = "Local";

        finalCell.appendChild(badge);
    }


    function renderOperation(operation, updateStats = true) {
        if (
            !operation ||
            renderedOperations.has(operation.id)
        ) {
            return;
        }

        if (
            operation.type !== "expense" &&
            operation.type !== "income"
        ) {
            return;
        }

        renderedOperations.add(operation.id);

        if (operation.type === "expense") {
            createExpenseRow(operation);
        } else {
            createIncomeRow(operation);
        }

        if (updateStats) {
            adjustStats(
                operation.type,
                Number(operation.data.amount) || 0
            );
        }
    }


    function markSynced(operation) {
        if (!operation) {
            return;
        }

        const row =
            document.querySelector(
                `[data-offline-operation-id="${operation.id}"]`
            );

        if (!row) {
            return;
        }

        row.classList.remove("offline-transaction-row");
        row.classList.add("offline-transaction-synced");

        const badge =
            row.querySelector(".offline-row-status");

        if (badge) {
            badge.classList.remove("pending");
            badge.classList.add("synced");
            badge.textContent = "Synced";
        }

        const localBadge =
            row.querySelector(".offline-local-badge");

        if (localBadge) {
            localBadge.textContent = "Synced";
        }
    }


    async function restorePendingOperations() {
        try {
            const operations =
                await ExpenseOfflineDB.all();

            operations.forEach(operation => {
                renderOperation(operation, true);
            });
        } catch (error) {
            console.warn(
                "Could not restore pending dashboard rows:",
                error
            );
        }
    }


    window.addEventListener(
        "expense-offline-created",
        event => {
            renderOperation(event.detail, true);
        }
    );


    window.addEventListener(
        "expense-sync-operation",
        event => {
            markSynced(event.detail.operation);
        }
    );


    document.addEventListener(
        "DOMContentLoaded",
        restorePendingOperations
    );
})();
