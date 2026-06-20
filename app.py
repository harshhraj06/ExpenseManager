import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Flask, render_template, request, redirect, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import database  # ensures all tables exist on startup

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "harsh_secret_key_123")

# ─────────────────────────────────────────────
# YOUR UPI ID – change this to your real UPI ID
# e.g. "harsh@okaxis" or "9876543210@ybl"
# ─────────────────────────────────────────────
UPI_ID = "yourname@upi"


def _next_due_date(due_date_str, recurrence):
    """Given a due date and a recurrence rule, return the next due date."""

    current = datetime.strptime(due_date_str, "%Y-%m-%d").date()

    if recurrence == "weekly":
        return current + timedelta(weeks=1)

    if recurrence == "monthly":
        month = current.month + 1
        year = current.year

        if month > 12:
            month = 1
            year += 1

        day = current.day

        while True:
            try:
                return current.replace(year=year, month=month, day=day)
            except ValueError:
                day -= 1

    return current


def process_due_bills(user_id):
    """
    Finds pending RECURRING bills (weekly/monthly) that are due
    (due_date <= today) for this user, converts each into a real
    expense, and rolls them forward to their next due date.

    One-time bills are intentionally NOT touched here. They only
    become an expense and move to Paid Bills when the user explicitly
    clicks "Pay Now" -> "I've Paid" (see /confirm_payment below).
    This keeps one-time bills sitting in Pending Bills, with a "Due"
    tag once their date arrives, until the user actually pays them.
    """
    today_str = date.today().strftime("%Y-%m-%d")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, amount, category, due_date, recurrence
        FROM bills
        WHERE user_id=? AND status='pending' AND due_date<=?
        AND recurrence IN ('weekly', 'monthly')
        """,
        (user_id, today_str)
    )
    due_bills = cursor.fetchall()

    for bill_id, name, amount, category, due_date_str, recurrence in due_bills:
        cursor.execute(
            """
            INSERT INTO expenses
            (user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, category, f"Bill: {name}", due_date_str)
        )

        next_due = _next_due_date(due_date_str, recurrence)
        cursor.execute(
            """
            UPDATE bills
            SET status='pending',
                due_date=?,
                last_generated_date=?
            WHERE id=?
            """,
            (next_due.strftime("%Y-%m-%d"), today_str, bill_id)
        )

    conn.commit()
    conn.close()


# =========================
# AUTH
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    error = None

    if request.method == "POST":

        username = request.form["username"]
        email    = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn   = sqlite3.connect("expenses.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username,email,password) VALUES (?,?,?)",
                (username, email, password)
            )
            conn.commit()
            conn.close()
            return redirect("/login")

        except sqlite3.IntegrityError:
            conn.close()
            error = "An account with that email already exists."

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":

        email    = request.form["email"]
        password = request.form["password"]

        conn   = sqlite3.connect("expenses.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session["user_id"]  = user[0]
            session["username"] = user[1]
            return redirect("/")

        error = "Invalid email or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# DASHBOARD
# =========================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect("/login")

    process_due_bills(session["user_id"])

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM expenses WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    )
    expenses = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM income WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    )
    income_history = cursor.fetchall()

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=?",
        (session["user_id"],)
    )
    total_expense = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(amount) FROM income WHERE user_id=?",
        (session["user_id"],)
    )
    total_income = cursor.fetchone()[0] or 0

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """, (session["user_id"],))
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

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO expenses
        (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
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

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM expenses WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )

    conn.commit()
    conn.close()
    return redirect("/")


# =========================
# INCOME
# =========================

@app.route("/add_income", methods=["POST"])
def add_income():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO income (user_id, amount, source, date)
        VALUES (?, ?, ?, ?)
        """,
        (
            session["user_id"],
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

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM income WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/edit_income/<int:id>")
def edit_income(id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM income WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )
    income = cursor.fetchone()
    conn.close()

    return render_template("edit_income.html", income=income)


@app.route("/update_income/<int:id>", methods=["POST"])
def update_income(id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE income
        SET amount=?, source=?, date=?
        WHERE id=? AND user_id=?
        """,
        (
            request.form["amount"],
            request.form["source"],
            request.form["date"],
            id,
            session["user_id"]
        )
    )

    conn.commit()
    conn.close()
    return redirect("/")


# =========================
# BILLS
# =========================

@app.route("/bills")
def bills():
    if "user_id" not in session:
        return redirect("/login")

    process_due_bills(session["user_id"])

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Show all manually added pending bills always.
    # Auto-created recurring bills (last_generated_date is set) only appear
    # in this table when their due date is within 7 days, so they don't
    # clutter the list right after payment. One-time bills always show
    # here until paid, since last_generated_date stays NULL for them.
    cursor.execute(
        """
        SELECT * FROM bills
        WHERE user_id=? AND status='pending'
        AND (
            last_generated_date IS NULL
            OR due_date <= date('now', '+7 days')
        )
        ORDER BY due_date ASC
        """,
        (session["user_id"],)
    )
    pending_bills = cursor.fetchall()

    # Recurring bills that exist but aren't due soon yet (hidden from the
    # table above on purpose) -- surfaced as a count/note instead of being
    # silently invisible.
    cursor.execute(
        """
        SELECT COUNT(*), MIN(due_date) FROM bills
        WHERE user_id=? AND status='pending'
        AND last_generated_date IS NOT NULL
        AND due_date > date('now', '+7 days')
        """,
        (session["user_id"],)
    )
    upcoming_row = cursor.fetchone()
    upcoming_count = upcoming_row[0] or 0
    upcoming_next_date = upcoming_row[1]

    cursor.execute(
        """
        SELECT * FROM bills
        WHERE user_id=? AND status='paid'
        ORDER BY id DESC
        """,
        (session["user_id"],)
    )
    paid_bills = cursor.fetchall()

    conn.close()

    today_str = date.today().strftime("%Y-%m-%d")

    return render_template(
        "bills.html",
        pending_bills=pending_bills,
        paid_bills=paid_bills,
        today=today_str,
        upcoming_count=upcoming_count,
        upcoming_next_date=upcoming_next_date
    )


@app.route("/add_bill", methods=["POST"])
def add_bill():
    if "user_id" not in session:
        return redirect("/login")

    recurrence = request.form.get("recurrence", "none")
    if recurrence not in ("none", "weekly", "monthly"):
        recurrence = "none"

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bills
        (user_id, name, amount, category, due_date, recurrence, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            session["user_id"],
            request.form["name"],
            request.form["amount"],
            request.form["category"],
            request.form["due_date"],
            recurrence
        )
    )
    conn.commit()
    conn.close()
    return redirect("/bills")


# ── Payment page – shows PhonePe / Paytm / GPay / UPI options ──
@app.route("/pay_bill_page/<int:bill_id>")
def pay_bill_page(bill_id):
    """Show the payment options page."""
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, amount, category, due_date, recurrence
        FROM bills
        WHERE id=? AND user_id=? AND status='pending'
        """,
        (bill_id, session["user_id"])
    )
    bill = cursor.fetchone()
    conn.close()

    if bill is None:
        return redirect("/bills")

    return render_template("pay_bill_page.html", bill=bill, upi_id=UPI_ID)


# ── Confirm payment – called after user pays in their UPI app ──
@app.route("/confirm_payment/<int:bill_id>", methods=["POST"])
def confirm_payment(bill_id):
    """
    User taps 'I've Paid'. Mark the bill as paid and record it as an
    expense. Recurring bills roll forward to their next due date as a
    new pending row; one-time bills simply move to Paid Bills.
    """
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, amount, category, due_date, recurrence
        FROM bills
        WHERE id=? AND user_id=? AND status='pending'
        """,
        (bill_id, session["user_id"])
    )
    bill = cursor.fetchone()

    if bill is None:
        conn.close()
        return redirect("/bills")

    bill_id_db, name, amount, category, due_date_str, recurrence = bill
    today_str = date.today().strftime("%Y-%m-%d")

    # 1. Record as an expense
    cursor.execute(
        """
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session["user_id"], amount, category, f"Bill: {name}", today_str)
    )

    # 2. Mark the current bill as PAID so it appears in Paid Bills
    cursor.execute(
        """
        UPDATE bills
        SET status='paid', last_generated_date=?
        WHERE id=?
        """,
        (today_str, bill_id_db)
    )

    # 3. If recurring, insert the next cycle as a pending bill (hidden until due soon)
    if recurrence in ("weekly", "monthly"):
        next_due = _next_due_date(due_date_str, recurrence)
        cursor.execute(
            """
            INSERT INTO bills
            (user_id, name, amount, category, due_date, recurrence, status, last_generated_date)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                session["user_id"],
                name,
                amount,
                category,
                next_due.strftime("%Y-%m-%d"),
                recurrence,
                today_str  # marks this as auto-created, hides it until due soon
            )
        )

    conn.commit()
    conn.close()
    return redirect("/bills?paid=1")


# ── KEPT for backwards compatibility (direct pay without payment page) ──
@app.route("/pay_bill/<int:bill_id>")
def pay_bill(bill_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, amount, category, due_date, recurrence
        FROM bills
        WHERE id=? AND user_id=? AND status='pending'
        """,
        (bill_id, session["user_id"])
    )
    bill = cursor.fetchone()

    if bill is None:
        conn.close()
        return redirect("/bills")

    _, name, amount, category, due_date_str, recurrence = bill
    today_str = date.today().strftime("%Y-%m-%d")

    cursor.execute(
        """
        INSERT INTO expenses
        (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session["user_id"], amount, category, f"Bill: {name}", today_str)
    )

    cursor.execute(
        """
        UPDATE bills
        SET status='paid', last_generated_date=?
        WHERE id=?
        """,
        (today_str, bill_id)
    )

    if recurrence in ("weekly", "monthly"):
        next_due = _next_due_date(due_date_str, recurrence)
        cursor.execute(
            """
            INSERT INTO bills
            (user_id, name, amount, category, due_date, recurrence, status, last_generated_date)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                session["user_id"],
                name,
                amount,
                category,
                next_due.strftime("%Y-%m-%d"),
                recurrence,
                today_str
            )
        )

    conn.commit()
    conn.close()
    return redirect("/bills")


@app.route("/bill_receipt/<int:bill_id>")
def bill_receipt(bill_id):
    """Generate and download a PDF receipt for a paid bill."""
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id, name, amount, category, due_date,
               recurrence, status, last_generated_date
        FROM bills
        WHERE id=? AND user_id=? AND status='paid'
        """,
        (bill_id, session["user_id"])
    )
    bill = cursor.fetchone()

    cursor.execute(
        "SELECT username FROM users WHERE id=?",
        (session["user_id"],)
    )
    user = cursor.fetchone()
    conn.close()

    if bill is None:
        return redirect("/bills")

    bill_name = bill[2]
    bill_amount = float(bill[3])
    bill_category = bill[4]
    bill_due_date = bill[5]
    bill_paid_date = bill[8] or date.today().strftime("%Y-%m-%d")
    username = user[0] if user else "User"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title", fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceAfter=2
    )
    sub_style = ParagraphStyle(
        "Sub", fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER, spaceAfter=2
    )
    amount_style = ParagraphStyle(
        "Amount", fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#16a34a"), alignment=TA_CENTER, spaceAfter=2
    )
    paid_style = ParagraphStyle(
        "Paid", fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#16a34a"), alignment=TA_CENTER, spaceAfter=2
    )
    footer_style = ParagraphStyle(
        "Footer", fontSize=8, fontName="Helvetica",
        textColor=colors.HexColor("#9ca3af"), alignment=TA_CENTER
    )

    story = []
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Expense Manager", title_style))
    story.append(Paragraph("Payment Receipt", sub_style))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Rs. {bill_amount:,.2f}", amount_style))
    story.append(Paragraph("PAID", paid_style))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 6 * mm))

    details = [
        ["Bill Name", bill_name],
        ["Category", bill_category],
        ["Due Date", bill_due_date],
        ["Date Paid", bill_paid_date],
        ["Paid By", username],
        ["Receipt No.", f"RCP-{bill_id:05d}"],
    ]
    table = Table(details, colWidths=[55 * mm, 100 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111827")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.HexColor("#f9fafb"), colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    story.append(table)
    story.append(Spacer(1, 8 * mm))

    status_data = [["Payment Status: Completed"]]
    status_table = Table(status_data, colWidths=[155 * mm])
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#dcfce7")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#166534")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 10 * mm))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"Generated on {date.today().strftime('%d %B %Y')} · Expense Manager",
        footer_style
    ))
    story.append(Paragraph(
        "This is a computer-generated receipt and does not require a signature.",
        footer_style
    ))

    doc.build(story)
    buffer.seek(0)

    filename = f"receipt_{bill_name.replace(' ', '_')}_{bill_paid_date}.pdf"
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@app.route("/delete_bill/<int:bill_id>")
def delete_bill(bill_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM bills WHERE id=? AND user_id=?",
        (bill_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect("/bills")


# =========================
# GROUPS
# =========================

@app.route("/groups")
def groups():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM groups_table WHERE user_id=?",
        (session["user_id"],)
    )
    groups = cursor.fetchall()
    conn.close()

    return render_template("groups.html", groups=groups)


@app.route("/add_group", methods=["POST"])
def add_group():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO groups_table (user_id, group_name) VALUES (?, ?)",
        (session["user_id"], request.form["group_name"])
    )

    conn.commit()
    conn.close()
    return redirect("/groups")


# =========================
# MEMBERS
# =========================

@app.route("/add_member/<int:group_id>", methods=["POST"])
def add_member(group_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO members (group_id, member_name) VALUES (?, ?)",
        (group_id, request.form["member_name"])
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/delete_member/<int:member_id>/<int:group_id>")
def delete_member(member_id, group_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM members WHERE id=?", (member_id,))

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/delete_group/<int:group_id>")
def delete_group(group_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM shared_expenses WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM members WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM groups_table WHERE id=?", (group_id,))

    conn.commit()
    conn.close()
    return redirect("/groups")


@app.route("/settle_up/<int:group_id>")
def settle_up(group_id):

    if "user_id" not in session:
        return redirect("/login")

    payer    = request.args.get("payer")
    receiver = request.args.get("receiver")

    try:
        amount = float(request.args.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO settlements (group_id, payer, receiver, amount) VALUES (?, ?, ?, ?)",
        (group_id, payer, receiver, amount)
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


# =========================
# SHARED EXPENSES
# =========================

@app.route("/add_shared_expense/<int:group_id>", methods=["POST"])
def add_shared_expense(group_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO shared_expenses (group_id, description, amount, paid_by)
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

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM shared_expenses WHERE id=?", (expense_id,))

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/edit_shared_expense/<int:expense_id>")
def edit_shared_expense(expense_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shared_expenses WHERE id=?", (expense_id,))
    expense = cursor.fetchone()

    if expense is None:
        conn.close()
        return redirect("/groups")

    group_id = expense[1]

    cursor.execute("SELECT * FROM members WHERE group_id=?", (group_id,))
    members = cursor.fetchall()
    conn.close()

    return render_template(
        "edit_shared_expense.html",
        expense=expense,
        members=members
    )


@app.route("/update_shared_expense/<int:expense_id>", methods=["POST"])
def update_shared_expense(expense_id):

    if "user_id" not in session:
        return redirect("/login")

    description = request.form["description"]
    paid_by     = request.form["paid_by"]
    group_id    = request.form["group_id"]

    try:
        amount = float(request.form["amount"])
    except (TypeError, ValueError):
        amount = 0

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE shared_expenses
        SET description=?, amount=?, paid_by=?
        WHERE id=?
        """,
        (description, amount, paid_by, expense_id)
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


# =========================
# GROUP DETAILS
# =========================

@app.route("/group/<int:group_id>")
def group_details(group_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id=?", (group_id,))
    group = cursor.fetchone()

    cursor.execute("SELECT * FROM members WHERE group_id=?", (group_id,))
    members = cursor.fetchall()

    cursor.execute("SELECT * FROM shared_expenses WHERE group_id=?", (group_id,))
    expenses = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM settlements WHERE group_id=? ORDER BY id DESC",
        (group_id,)
    )
    settlement_history = cursor.fetchall()

    member_names = [m[2] for m in members]

    # Expense Breakdown
    expense_breakdown = []
    for expense in expenses:
        amount      = expense[3]
        paid_by     = expense[4]
        description = expense[2]

        if not member_names:
            continue

        share   = amount / len(member_names)
        details = [
            f"{member} owes {paid_by} ₹{share:.2f}"
            for member in member_names
            if member != paid_by
        ]

        expense_breakdown.append({
            "description": description,
            "amount":      amount,
            "paid_by":     paid_by,
            "details":     details
        })

    # Net Balance Engine
    balances = defaultdict(float)
    for expense in expenses:
        amount  = expense[3]
        paid_by = expense[4]

        if not member_names:
            continue

        share = amount / len(member_names)
        balances[paid_by] += amount
        for member in member_names:
            balances[member] -= share

    # Apply Settlements
    for settlement in settlement_history:
        payer    = settlement[2]
        receiver = settlement[3]
        amount   = settlement[4]
        balances[payer]    += amount
        balances[receiver] -= amount

    debtors   = [[p, -a] for p, a in balances.items() if a < 0]
    creditors = [[p,  a] for p, a in balances.items() if a > 0]

    settlements = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor   = debtors[i]
        creditor = creditors[j]
        payment  = min(debtor[1], creditor[1])

        settlements.append({
            "text":     f"{debtor[0]} owes {creditor[0]} ₹{payment:.2f}",
            "payer":    debtor[0],
            "receiver": creditor[0],
            "amount":   round(payment, 2)
        })

        debtor[1]   -= payment
        creditor[1] -= payment

        if debtor[1]   < 0.01: i += 1
        if creditor[1] < 0.01: j += 1

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)