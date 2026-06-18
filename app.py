from flask import Flask, render_template, request, redirect
import sqlite3
from collections import defaultdict

app = Flask(__name__)


# =========================
# DASHBOARD
# =========================

@app.route("/")
def home():

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Expenses
    cursor.execute("SELECT * FROM expenses ORDER BY id DESC")
    expenses = cursor.fetchall()

    # Income History
    cursor.execute("SELECT * FROM income ORDER BY id DESC")
    income_history = cursor.fetchall()

    # Total Expense
    cursor.execute("SELECT SUM(amount) FROM expenses")
    total_expense = cursor.fetchone()[0] or 0

    # Total Income
    cursor.execute("SELECT SUM(amount) FROM income")
    total_income = cursor.fetchone()[0] or 0

    # Category Summary
    cursor.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    GROUP BY category
    ORDER BY SUM(amount) DESC
    """)
    category_summary = cursor.fetchall()

    balance = total_income - total_expense

    conn.close()

    return render_template(
        "index.html",
        expenses=expenses,
        income_history=income_history,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        category_summary=category_summary
    )

# =========================
# PERSONAL EXPENSES
# =========================

@app.route("/add", methods=["POST"])
def add_expense():

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO expenses
        (amount, category, description, date)
        VALUES (?, ?, ?, ?)
        """,
        (
            request.form["amount"],
            request.form["category"],
            request.form["description"],
            request.form["date"]
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/delete/<int:id>")
def delete_expense(id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM expenses WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")


# =========================
# INCOME
# =========================

@app.route("/add_income", methods=["POST"])
def add_income():

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO income
        (amount, source, date)
        VALUES (?, ?, ?)
        """,
        (
            request.form["amount"],
            request.form["source"],
            request.form["date"]
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")
@app.route("/delete_income/<int:id>")
def delete_income(id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM income WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")
@app.route("/edit_income/<int:id>")
def edit_income(id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM income WHERE id=?",
        (id,)
    )

    income = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_income.html",
        income=income
    )


@app.route("/update_income/<int:id>", methods=["POST"])
def update_income(id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE income
        SET amount=?,
            source=?,
            date=?
        WHERE id=?
        """,
        (
            request.form["amount"],
            request.form["source"],
            request.form["date"],
            id
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")


# =========================
# GROUPS
# =========================

@app.route("/groups")
def groups():

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM groups_table ORDER BY id DESC"
    )

    groups = cursor.fetchall()
    

    conn.close()

    return render_template(
        "groups.html",
        groups=groups
    )


@app.route("/add_group", methods=["POST"])
def add_group():

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO groups_table(group_name) VALUES(?)",
        (request.form["group_name"],)
    )

    conn.commit()
    conn.close()

    return redirect("/groups")


# =========================
# MEMBERS
# =========================

@app.route("/add_member/<int:group_id>", methods=["POST"])
def add_member(group_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO members
        (group_id, member_name)
        VALUES (?, ?)
        """,
        (
            group_id,
            request.form["member_name"]
        )
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")
@app.route("/delete_member/<int:member_id>/<int:group_id>")
def delete_member(member_id, group_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM members WHERE id=?",
        (member_id,)
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")
@app.route("/delete_group/<int:group_id>")
def delete_group(group_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Delete group expenses
    cursor.execute(
        "DELETE FROM shared_expenses WHERE group_id=?",
        (group_id,)
    )

    # Delete members
    cursor.execute(
        "DELETE FROM members WHERE group_id=?",
        (group_id,)
    )

    # Delete group
    cursor.execute(
        "DELETE FROM groups_table WHERE id=?",
        (group_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/groups")
@app.route("/settle_up/<int:group_id>")
def settle_up(group_id):

    payer = request.args.get("payer")
    receiver = request.args.get("receiver")
    amount = float(request.args.get("amount"))

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO settlements
        (group_id, payer, receiver, amount)
        VALUES (?, ?, ?, ?)
        """,
        (
            group_id,
            payer,
            receiver,
            amount
        )
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")


# =========================
# SHARED EXPENSES
# =========================

@app.route("/add_shared_expense/<int:group_id>", methods=["POST"])
def add_shared_expense(group_id):
    

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO shared_expenses
        (group_id, description, amount, paid_by)
        VALUES (?, ?, ?, ?)
        """,
        (
            group_id,
            request.form["description"],
            float(request.form["amount"]),
            request.form["paid_by"]
        )
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")
@app.route("/delete_shared_expense/<int:expense_id>/<int:group_id>")
def delete_shared_expense(expense_id, group_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM shared_expenses WHERE id=?",
        (expense_id,)
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")
@app.route("/edit_shared_expense/<int:expense_id>")
def edit_shared_expense(expense_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM shared_expenses WHERE id=?",
        (expense_id,)
    )

    expense = cursor.fetchone()

    group_id = expense[1]

    cursor.execute(
        "SELECT * FROM members WHERE group_id=?",
        (group_id,)
    )

    members = cursor.fetchall()

    conn.close()

    return render_template(
        "edit_shared_expense.html",
        expense=expense,
        members=members
    )


@app.route("/update_shared_expense/<int:expense_id>", methods=["POST"])
def update_shared_expense(expense_id):

    description = request.form["description"]
    amount = float(request.form["amount"])
    paid_by = request.form["paid_by"]
    group_id = request.form["group_id"]

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE shared_expenses
        SET description=?,
            amount=?,
            paid_by=?
        WHERE id=?
        """,
        (
            description,
            amount,
            paid_by,
            expense_id
        )
    )

    conn.commit()
    conn.close()

    return redirect(f"/group/{group_id}")

# =========================
# GROUP DETAILS
# =========================

@app.route("/group/<int:group_id>")
def group_details(group_id):

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Group
    cursor.execute(
        "SELECT * FROM groups_table WHERE id=?",
        (group_id,)
    )
    group = cursor.fetchone()

    # Members
    cursor.execute(
        "SELECT * FROM members WHERE group_id=?",
        (group_id,)
    )
    members = cursor.fetchall()

    # Shared Expenses
    cursor.execute(
        "SELECT * FROM shared_expenses WHERE group_id=?",
        (group_id,)
    )
    expenses = cursor.fetchall()

    # Settlement History
    cursor.execute(
        "SELECT * FROM settlements WHERE group_id=? ORDER BY id DESC",
        (group_id,)
    )
    settlement_history = cursor.fetchall()

    member_names = [m[2] for m in members]

    # =========================
    # Expense Breakdown
    # =========================

    expense_breakdown = []

    for expense in expenses:

        amount = expense[3]
        paid_by = expense[4]
        description = expense[2]

        if len(member_names) == 0:
            continue

        share = amount / len(member_names)

        details = []

        for member in member_names:

            if member != paid_by:

                details.append(
                    f"{member} owes {paid_by} ₹{share:.2f}"
                )

        expense_breakdown.append({
            "description": description,
            "amount": amount,
            "paid_by": paid_by,
            "details": details
        })

    # =========================
    # Net Balance Engine
    # =========================

    balances = defaultdict(float)

    for expense in expenses:

        amount = expense[3]
        paid_by = expense[4]

        if len(member_names) == 0:
            continue

        share = amount / len(member_names)

        balances[paid_by] += amount

        for member in member_names:
            balances[member] -= share

    # =========================
    # Apply Settlements
    # =========================

    for settlement in settlement_history:

        payer = settlement[2]
        receiver = settlement[3]
        amount = settlement[4]

        balances[payer] += amount
        balances[receiver] -= amount

    debtors = []
    creditors = []

    for person, amount in balances.items():

        if amount > 0:
            creditors.append([person, amount])

        elif amount < 0:
            debtors.append([person, -amount])

    settlements = []

    i = 0
    j = 0

    while i < len(debtors) and j < len(creditors):

        debtor = debtors[i]
        creditor = creditors[j]

        payment_amount = min(
            debtor[1],
            creditor[1]
        )

        settlements.append({
            "text": f"{debtor[0]} owes {creditor[0]} ₹{payment_amount:.2f}",
            "payer": debtor[0],
            "receiver": creditor[0],
            "amount": round(payment_amount, 2)
        })

        debtor[1] -= payment_amount
        creditor[1] -= payment_amount

        if debtor[1] < 0.01:
            i += 1

        if creditor[1] < 0.01:
            j += 1

    conn.close()

    return render_template(
        "group_details.html",
        group=group,
        members=members,
        expenses=expenses,
        expense_breakdown=expense_breakdown,
        balances=settlements,
        settlement_history=settlement_history
    )

if __name__ == "__main__":
    app.run(debug=True)