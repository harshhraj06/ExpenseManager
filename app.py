import os
import re
import json
import secrets
import db_compat as sqlite3
import requests
from html import escape
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from flask import Flask, render_template, request, redirect, session, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# DATABASE: now stored in a free Render PostgreSQL database instead of a
# local SQLite file. Render's web service filesystem is wiped on every
# deploy/restart (no persistent disk on the Free plan), so any local
# file -- including the old expenses.db -- would be lost. Postgres data
# lives in Render's separate managed database service and survives
# redeploys independently of the web service. DATABASE_URL is provided
# automatically by Render once a PostgreSQL database is created and its
# connection string is added as an env var on this service. db_compat
# is a thin wrapper (see db_compat.py) that lets the rest of this file's
# query code keep using sqlite3-style "?" placeholders and cursor calls
# while actually talking to Postgres underneath.
DB_PATH = os.environ.get("DATABASE_URL")

# UPLOAD_FOLDER: receipt images still need a writable folder. Locally
# this is just a folder next to app.py. On Render this still resets on
# every deploy (uploaded receipts aren't covered by this Postgres
# migration), which only matters for the receipt-scanner feature, not
# for any of your account/expense/income data, which now all lives in
# Postgres.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "receipts")
ALLOWED_RECEIPT_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf"}
os.chdir(BASE_DIR)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# ─────────────────────────────────────────────
# YOUR UPI ID – change this to your real UPI ID
# e.g. "harsh@okaxis" or "9876543210@ybl"
# ─────────────────────────────────────────────
UPI_ID = "yourname@upi"

# ─────────────────────────────────────────────
# RESEND SETTINGS -- needed to send "Forgot Password" reset emails.
#
# Render blocks outbound SMTP (port 587/465), so raw Gmail SMTP cannot
# work from a deployed Render web service -- only from localhost. We
# send mail over Resend's HTTPS API instead, which is not blocked.
#
# >>> SET THESE AS ENVIRONMENT VARIABLES (Render dashboard -> Environment) <<<
#   RESEND_API_KEY     - from https://resend.com/api-keys (starts with "re_")
#   RESEND_FROM_ADDRESS - e.g. "onboarding@resend.dev" to start (Resend's
#                          shared test sender, no domain setup needed), or
#                          "noreply@yourdomain.com" once you verify a domain
#                          at https://resend.com/domains
#
# No secrets are hardcoded here -- if RESEND_API_KEY is missing, reset
# emails fail with a clear error printed to the console instead of
# crashing the app.
# ─────────────────────────────────────────────
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
print("RESEND_API_KEY:", RESEND_API_KEY)
RESEND_FROM_ADDRESS = os.environ.get("RESEND_FROM_ADDRESS", "onboarding@resend.dev")
RESEND_API_URL = "https://api.resend.com/emails"

# Base URL used to build the reset link inside the email, e.g.
# "https://yourapp.com" in production. Defaults to localhost for
# local development/testing.
APP_BASE_URL = os.environ.get(
    "APP_BASE_URL",
    "https://expensemanager-th5g.onrender.com"
)
PASSWORD_RESET_TOKEN_VALID_MINUTES = 30

# ─────────────────────────────────────────────
# GROQ SETTINGS -- needed for the "Ask Expense Manager" AI chat.
#
# Groq gives reliable free API access to open models (Llama, etc.) with
# no billing setup required. Switched to this after Google's Gemini
# free tier kept returning 0 quota for this account/project, which
# Google allocates per-account and isn't something fixable from a
# config setting on our end.
#
# >>> SET THIS AS AN ENVIRONMENT VARIABLE (Render dashboard -> Environment) <<<
#   GROQ_API_KEY - from https://console.groq.com/keys (free, no card)
#
# No secret is hardcoded here -- if GROQ_API_KEY is missing, the chat
# route returns a clear error message instead of crashing the app.
# ─────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _normalise_email(email):
    return email.strip().lower()


def _get_selected_split_members(form):
    members = []
    seen = set()
    for member_name in form.getlist("split_members"):
        cleaned_name = member_name.strip()
        if cleaned_name and cleaned_name not in seen:
            members.append(cleaned_name)
            seen.add(cleaned_name)
    return members


def _split_members_from_expense(expense, fallback_member_names):
    if len(expense) > 5 and expense[5]:
        try:
            split_members = json.loads(expense[5])
        except (TypeError, ValueError):
            split_members = []
        split_members = [
            member for member in split_members
            if isinstance(member, str) and member
        ]
        if split_members:
            return split_members
    return fallback_member_names


def _send_password_reset_email(to_email, reset_link):
    """
    Sends the password reset email via Resend's HTTPS API. Raises
    RuntimeError with a clear message if Resend isn't configured yet,
    or if Resend itself rejects the request, rather than letting a raw
    requests exception bubble up to the user.

    Why not SMTP: Render (and most PaaS hosts) block outbound SMTP
    ports (587/465) on web services, so smtplib connections to Gmail
    fail there with "Network is unreachable" even though they work
    fine from a local machine. Resend's API runs over normal HTTPS
    (port 443), which is never blocked.
    """
    if not RESEND_API_KEY:
        raise RuntimeError(
            "Email is not configured yet -- RESEND_API_KEY is missing. "
            "Sign up free at https://resend.com, create an API key at "
            "https://resend.com/api-keys, and set RESEND_API_KEY as an "
            "environment variable (Render dashboard -> Environment), "
            "then redeploy."
        )

    text_body = (
        "We received a request to reset your Expense Manager password.\n\n"
        f"Click this link to set a new password:\n{reset_link}\n\n"
        f"This link expires in {PASSWORD_RESET_TOKEN_VALID_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email."
    )

    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": RESEND_FROM_ADDRESS,
            "to": [to_email],
            "subject": "Reset your Expense Manager password",
            "text": text_body,
        },
        timeout=20,
    )

    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"Resend rejected the request ({response.status_code}): {detail}. "
            "If this mentions the 'from' address or domain, verify a domain "
            "at https://resend.com/domains, or use the default "
            "'onboarding@resend.dev' sender while testing."
        )


# =========================
# GROUP ACCESS CONTROL
# =========================
# These helpers are the single source of truth for "can this logged-in
# user see/use this group". Every group-related route must call
# get_group_for_user (or user_can_access_group) before reading or
# writing group data. This is what scopes a member's access to ONLY
# the groups they were added to -- never the owner's personal
# expenses, income, bills, or other groups.

def user_can_access_group(user_id, group_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?",
        (group_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def user_is_group_owner(user_id, group_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND role='owner'",
        (group_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def require_group_access(group_id):
    """
    Call at the top of any group route. Returns the user_id on success.
    Aborts with 403 if the logged-in user has no membership row for
    this group, so members can only ever reach groups they were
    explicitly added to.
    """
    user_id = session["user_id"]
    if not user_can_access_group(user_id, group_id):
        abort(403)
    return user_id


def require_group_owner(group_id):
    user_id = session["user_id"]
    if not user_is_group_owner(user_id, group_id):
        abort(403)
    return user_id


def _build_upi_links(payee_upi_id, payee_name, amount, note):
    """
    Generic UPI deep-link builder. Used for both bill payments (payee is
    YOU, the app owner) and settlement payments (payee is whichever
    group member is owed money, using THEIR own upi_id).
    """
    payment_params = {
        "pa": payee_upi_id,
        "pn": payee_name,
        "am": f"{float(amount):.2f}",
        "cu": "INR",
        "tn": note,
    }
    query = urlencode(payment_params)

    return {
        "phonepe": f"phonepe://pay?{query}",
        "gpay": f"tez://upi/pay?{query}",
        "paytm": f"paytmmp://pay?{query}",
        "upi": f"upi://pay?{query}",
    }


def _build_upi_payment_links(bill):
    bill_id, name, amount, category, due_date, recurrence = bill
    return _build_upi_links(UPI_ID, "Expense Manager", amount, f"Bill payment: {name}")


def _allowed_receipt_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_RECEIPT_EXTENSIONS
    )


def _extract_image_receipt_text(image_path):
    """
    Sends the image to Groq's vision model (llama-3.2-11b-vision-preview)
    as a base64-encoded data URL. This replaces the old pytesseract path,
    which required a native Tesseract binary that is not available on most
    PaaS hosts (Render, Railway, etc.) and caused every JPEG/PNG scan to
    silently fail with 'ocr_missing'. The Groq key is already required for
    the AI chat feature, so no new credential is needed.
    """
    import base64, mimetypes

    if not GROQ_API_KEY:
        raise RuntimeError(
            "Receipt scanning via AI needs GROQ_API_KEY. "
            "Get a free key at https://console.groq.com/keys and set it "
            "as an environment variable, then redeploy."
        )

    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = mimetypes.types_map.get(f".{ext}", "image/jpeg")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    data_url = f"data:{mime};base64,{b64}"

    response = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "This is a receipt or bill image. "
                                "Extract ALL visible text from it exactly as it appears, "
                                "including amounts, dates, item names, store name, and totals. "
                                "Return only the raw extracted text, no commentary."
                            ),
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 800,
        },
        timeout=40,
    )

    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Groq vision API error ({response.status_code}): {detail}")

    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def _extract_pdf_receipt_text(pdf_path):
    text_parts = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        for page in reader.pages[:3]:
            text_parts.append(page.extract_text() or "")
    except ImportError:
        pass

    extracted_text = "\n".join(text_parts).strip()
    if extracted_text:
        return extracted_text

    try:
        import fitz
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "PDF receipt scanning needs pypdf for text PDFs, or PyMuPDF, Pillow, and pytesseract for scanned PDFs."
        ) from exc

    doc = fitz.open(pdf_path)
    ocr_text = []
    for page in doc[:3]:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        ocr_text.append(pytesseract.image_to_string(image))
    doc.close()

    return "\n".join(ocr_text)


def _extract_receipt_text(file_path):
    if file_path.lower().endswith(".pdf"):
        return _extract_pdf_receipt_text(file_path)

    return _extract_image_receipt_text(file_path)


def _money_to_float(value):
    return float(value.replace(",", "").strip())


def _guess_receipt_amount(text):
    priority_patterns = [
        r"(?:grand\s+total|net\s+total|amount\s+due|total\s+amount|total)\D{0,20}(\d[\d,]*\.?\d{0,2})",
        r"(?:rs\.?|inr|₹)\s*(\d[\d,]*\.?\d{0,2})",
    ]

    for pattern in priority_patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            return _money_to_float(matches[-1])

    amounts = re.findall(r"\b\d{2,}(?:,\d{3})*(?:\.\d{1,2})?\b", text)
    if not amounts:
        return None

    return max(_money_to_float(amount) for amount in amounts)


def _guess_receipt_date(text):
    date_patterns = [
        (r"\b(\d{4}-\d{1,2}-\d{1,2})\b", ["%Y-%m-%d"]),
        (r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"]),
    ]

    for pattern, formats in date_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            for date_format in formats:
                try:
                    return datetime.strptime(match, date_format).strftime("%Y-%m-%d")
                except ValueError:
                    continue

    return date.today().strftime("%Y-%m-%d")


def _guess_receipt_category(text):
    lowered = text.lower()
    category_keywords = {
        "Food": ["restaurant", "cafe", "food", "pizza", "burger", "swiggy", "zomato", "hotel"],
        "Travel": ["uber", "ola", "railway", "train", "flight", "bus", "metro", "fuel", "petrol"],
        "Shopping": ["mall", "store", "fashion", "amazon", "flipkart", "myntra", "market"],
        "Bills": ["electricity", "water", "mobile", "internet", "recharge", "gas", "bill"],
        "Entertainment": ["movie", "cinema", "netflix", "spotify", "game", "ticket"],
        "Education": ["school", "college", "course", "book", "tuition", "exam"],
    }

    for category, keywords in category_keywords.items():
        if any(keyword in lowered for keyword in keywords):
            return category

    return "Shopping"


def _guess_receipt_description(text, filename):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        return f"Receipt: {lines[0][:80]}"

    return f"Receipt: {filename}"


# ─────────────────────────────────────────────
# CURRENCY DETECTION & LIVE CONVERSION TO INR
# ─────────────────────────────────────────────

# Symbols / keywords that are clearly INR -- skip conversion for these.
_INR_MARKERS = {"inr", "₹", "rs.", "rs ", "rupee", "rupees"}

def _detect_receipt_currency_and_amount(text):
    """
    Asks Groq (text model) to identify the currency code and total amount
    on the receipt. Returns (currency_code: str, amount: float) where
    currency_code is an ISO-4217 code like 'USD', 'EUR', 'AED', or 'INR'.
    Falls back to ('INR', None) if detection fails so the caller can use
    the regex-based amount guesser as a safe fallback.
    """
    if not GROQ_API_KEY:
        return "INR", None

    prompt = (
        "Look at this receipt text and answer ONLY with a JSON object "
        "containing two fields:\n"
        '  "currency": the ISO-4217 currency code (e.g. "USD", "EUR", "AED", "INR", "GBP")\n'
        '  "amount": the final total amount as a plain number (e.g. 42.50)\n'
        "If you cannot determine the currency, use \"INR\". "
        "If you cannot find a total, use null for amount. "
        "Return ONLY the JSON, no explanation.\n\n"
        f"Receipt text:\n{text[:1500]}"
    )

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 60,
            },
            timeout=15,
        )
        raw = response.json()["choices"][0]["message"]["content"].strip()
        # Strip possible ```json fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)
        currency = str(parsed.get("currency") or "INR").upper().strip()
        amount_raw = parsed.get("amount")
        amount = float(amount_raw) if amount_raw is not None else None
        return currency, amount
    except Exception as exc:
        print(f"[currency detect] failed: {exc}")
        return "INR", None


def _fetch_inr_rate(from_currency):
    """
    Fetches the live exchange rate from `from_currency` to INR using the
    free Frankfurter API (https://api.frankfurter.app). No API key needed.
    Returns the rate as a float, or None on failure.
    Frankfurter doesn't cover INR directly for all currencies, so we go
    through USD as a bridge when a direct quote isn't available.
    """
    if from_currency == "INR":
        return 1.0

    try:
        url = f"https://api.frankfurter.app/latest?from={from_currency}&to=INR"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            rate = data.get("rates", {}).get("INR")
            if rate:
                return float(rate)
    except Exception as exc:
        print(f"[exchange rate] direct fetch failed: {exc}")

    # Bridge through USD if direct quote failed
    try:
        r1 = requests.get(
            f"https://api.frankfurter.app/latest?from={from_currency}&to=USD",
            timeout=8,
        ).json()
        r2 = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=INR",
            timeout=8,
        ).json()
        usd_rate  = r1.get("rates", {}).get("USD")
        inr_rate  = r2.get("rates", {}).get("INR")
        if usd_rate and inr_rate:
            return float(usd_rate) * float(inr_rate)
    except Exception as exc:
        print(f"[exchange rate] bridge fetch failed: {exc}")

    return None


def _is_inr(currency_code, text):
    """Returns True if the currency is Indian Rupee (by code or symbol)."""
    if currency_code.upper() == "INR":
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in _INR_MARKERS)


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

    conn = sqlite3.connect(DB_PATH)
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


def generate_due_bill_notifications(user_id):
    """
    Checks this user's PENDING bills for ones due today or tomorrow and
    creates a notification row for each, so the bell in the navbar can
    show them. Called on login/dashboard load (see home()).

    Idempotent on purpose: it only inserts a notification for a given
    (bill, due_date) pair if one doesn't already exist, so refreshing
    the dashboard 10 times in a row doesn't create 10 duplicate
    notifications for the same bill.
    """
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, amount, due_date
        FROM bills
        WHERE user_id=? AND status='pending'
        AND due_date IN (?, ?)
        """,
        (user_id, today_str, tomorrow_str)
    )
    due_bills = cursor.fetchall()

    for bill_id, name, amount, due_date_str in due_bills:
        when = "today" if due_date_str == today_str else "tomorrow"
        title = f"{name} due {when}"
        message = f"{name} ₹{amount:.2f} is due {when}."

        # De-dupe: skip if a notification for this exact bill+due_date
        # already exists, regardless of read state.
        cursor.execute(
            """
            SELECT 1 FROM notifications
            WHERE user_id=? AND title=? AND due_date=?
            """,
            (user_id, title, due_date_str)
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            INSERT INTO notifications (user_id, title, message, due_date, is_read)
            VALUES (?, ?, ?, ?, 0)
            """,
            (user_id, title, message, due_date_str)
        )

    conn.commit()
    conn.close()


def get_navbar_notifications(user_id):
    """
    Fetches recent notifications for the navbar bell: unread count plus
    the most recent rows (read or unread) to show in the dropdown.
    Shared by every route that renders a page with the navbar.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
        (user_id,)
    )
    unread_count = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT id, title, message, due_date, is_read, created_at
        FROM notifications
        WHERE user_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT 10
        """,
        (user_id,)
    )
    recent_notifications = cursor.fetchall()

    conn.close()
    return unread_count, recent_notifications


def _build_financial_context(user_id):
    """
    Pulls a compact summary of this user's data to ground the AI's
    answer in real numbers instead of letting it guess. Keeping this
    summarized (not raw row dumps) keeps the prompt small and cheap.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    this_start, this_end = _month_bounds(0)

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date>=? AND date<?",
        (user_id, this_start, this_end)
    )
    expense_this_month = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(amount) FROM income WHERE user_id=? AND date>=? AND date<?",
        (user_id, this_start, this_end)
    )
    income_this_month = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT category, SUM(amount) FROM expenses
        WHERE user_id=? AND date>=? AND date<?
        GROUP BY category ORDER BY SUM(amount) DESC
        """,
        (user_id, this_start, this_end)
    )
    category_breakdown = cursor.fetchall()

    cursor.execute(
        """
        SELECT amount, category, description, date FROM expenses
        WHERE user_id=? ORDER BY id DESC LIMIT 5
        """,
        (user_id,)
    )
    last_5_expenses = cursor.fetchall()

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=?",
        (user_id,)
    )
    total_expense_all_time = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(amount) FROM income WHERE user_id=?",
        (user_id,)
    )
    total_income_all_time = cursor.fetchone()[0] or 0

    conn.close()

    top_category = category_breakdown[0] if category_breakdown else None
    balance_all_time = total_income_all_time - total_expense_all_time
    balance_this_month = income_this_month - expense_this_month

    lines = [
        f"Current overall balance (all-time income minus all-time expenses): ₹{balance_all_time:,.2f}",
        f"All-time income: ₹{total_income_all_time:,.2f}",
        f"All-time expenses: ₹{total_expense_all_time:,.2f}",
        f"This month's income: ₹{income_this_month:,.2f}",
        f"This month's expenses: ₹{expense_this_month:,.2f}",
        f"This month's net (income minus expenses, for this calendar month only): ₹{balance_this_month:,.2f}",
    ]

    if top_category:
        lines.append(f"Highest spending category this month: {top_category[0]} (₹{top_category[1]:,.2f})")

    if category_breakdown:
        lines.append("This month's spending by category:")
        for category, amount in category_breakdown:
            lines.append(f"  - {category}: ₹{amount:,.2f}")

    if last_5_expenses:
        lines.append("Last 5 expenses:")
        for amount, category, description, expense_date in last_5_expenses:
            desc = description or "(no description)"
            lines.append(f"  - {expense_date}: ₹{amount:,.2f} on {category} ({desc})")

    return "\n".join(lines)


def ask_expense_manager_ai(user_id, question):
    """
    Sends the user's question plus a summary of their own financial
    data to Groq's chat completions API (OpenAI-compatible format,
    running open models like Llama for free) and returns the answer
    text. Raises RuntimeError with a clear message if GROQ_API_KEY
    isn't set or if Groq rejects the request, mirroring the pattern
    used for Resend above.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "AI chat isn't configured yet -- GROQ_API_KEY is missing. "
            "Get a free key at https://console.groq.com/keys (no card "
            "needed) and set GROQ_API_KEY as an environment variable "
            "(Render dashboard -> Environment), then redeploy."
        )

    context = _build_financial_context(user_id)

    system_prompt = (
        "You are 'Ask Expense Manager', a helpful assistant inside a personal "
        "finance app. Answer the user's question ONLY using the financial data "
        "provided below -- never invent numbers that aren't in it. If the data "
        "doesn't contain what's needed to answer, say so plainly. Keep answers "
        "short (2-4 sentences or a short list), friendly, and in INR (₹).\n\n"
        "IMPORTANT: if the user asks a general question like 'how much do I have', "
        "'what's my balance', or 'how much money do I have', use the 'Current "
        "overall balance' figure -- this matches what they see on their dashboard. "
        "Only use 'this month's net' if they specifically ask about this month, "
        "this period, or savings for the current month. Always be clear in your "
        "answer about whether a number is all-time or for the current month, so "
        "the user is never confused about which balance you mean.\n\n"
        f"User's financial data:\n{context}"
    )

    response = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Groq rejected the request ({response.status_code}): {detail}")

    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


# =========================
# AUTH
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    error = None

    if request.method == "POST":

        username = request.form["username"]
        email    = _normalise_email(request.form["email"])
        password = generate_password_hash(request.form["password"])

        conn   = sqlite3.connect(DB_PATH)
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

        email    = _normalise_email(request.form["email"])
        password = request.form["password"]

        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session.permanent = True
            session["user_id"]  = user[0]
            session["username"] = user[1]
            session["email"] = user[2]
            generate_due_bill_notifications(user[0])
            return redirect("/")

        error = "Invalid email or password."

    return render_template("login.html", error=error)


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """
    Step 1 of password reset: user enters their email. We always show
    the same confirmation message whether or not that email is
    registered, so this page can't be used to discover which emails
    have accounts.
    """
    message = None
    error = None

    if request.method == "POST":
        email = _normalise_email(request.form["email"])

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email=?", (email,))
        user = cursor.fetchone()

        if user:
            user_id = user[0]
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(minutes=PASSWORD_RESET_TOKEN_VALID_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at)
            )
            conn.commit()

            base_url = os.environ.get("APP_BASE_URL") or request.host_url.rstrip("/")
            reset_link = f"{base_url}/reset_password/{token}"

            try:
                _send_password_reset_email(email, reset_link)
                message = "If an account exists with that email, a password reset link has been sent."
            except RuntimeError as exc:
                print(f"[forgot_password] Could not send reset email: {exc}")
                error = str(exc)
            except Exception as exc:
                print(f"[forgot_password] Failed to send reset email: {exc}")
                error = (
                    "Could not send the reset email. Check your internet "
                    "connection and Resend configuration, then try again."
                )
        else:
            message = "If an account exists with that email, a password reset link has been sent."

        conn.close()

    return render_template("forgot_password.html", message=message, error=error)


@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Step 2: user arrives via the emailed link and sets a new password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, expires_at, used FROM password_resets WHERE token=?",
        (token,)
    )
    reset_row = cursor.fetchone()

    if reset_row is None:
        conn.close()
        return render_template("reset_password.html", token=token, error="This reset link is invalid.", expired=True)

    reset_id, user_id, expires_at, used = reset_row
    is_expired = datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")

    if used or is_expired:
        conn.close()
        return render_template(
            "reset_password.html",
            token=token,
            error="This reset link has expired or was already used. Please request a new one.",
            expired=True
        )

    error = None

    if request.method == "POST":
        new_password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            error = "Passwords do not match."
        elif len(new_password) < 6:
            error = "Password must be at least 6 characters."
        else:
            cursor.execute(
                "UPDATE users SET password=? WHERE id=?",
                (generate_password_hash(new_password), user_id)
            )
            cursor.execute(
                "UPDATE password_resets SET used=1 WHERE id=?",
                (reset_id,)
            )
            conn.commit()
            conn.close()
            return redirect("/login?reset=1")

    conn.close()
    return render_template("reset_password.html", token=token, error=error, expired=False)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect("/login")


# =========================
# AI INSIGHTS (rule-based, no LLM call needed)
# =========================

def _month_bounds(months_ago=0):
    """Returns (first_day_str, first_day_of_next_month_str) for the
    month that is `months_ago` months before the current one, so a
    BETWEEN-style range query can use [start, end)."""
    today = date.today()
    month = today.month - months_ago
    year = today.year
    while month <= 0:
        month += 12
        year -= 1

    start = date(year, month, 1)

    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1
    end = date(next_year, next_month, 1)

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def build_monthly_trend(user_id, months=12):
    """
    Returns the last `months` calendar months of income/expense totals
    for this user, oldest first, ready to feed straight into a Chart.js
    line chart. Months with no activity show as 0, not missing, so the
    x-axis stays a continuous, evenly-spaced timeline rather than
    skipping gaps -- a real trend line needs that continuity to read
    correctly.

    Returns a list of dicts: [{"label": "Jan 2026", "income": 0, "expense": 0}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    trend = []
    for months_ago in range(months - 1, -1, -1):
        start, end = _month_bounds(months_ago)

        cursor.execute(
            "SELECT SUM(amount) FROM income WHERE user_id=? AND date>=? AND date<?",
            (user_id, start, end)
        )
        income = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date>=? AND date<?",
            (user_id, start, end)
        )
        expense = cursor.fetchone()[0] or 0

        month_date = datetime.strptime(start, "%Y-%m-%d").date()
        trend.append({
            "label": month_date.strftime("%b %Y"),
            "income": round(income, 2),
            "expense": round(expense, 2),
        })

    conn.close()
    return trend


def build_ai_insights(user_id):
    """
    Compares this month's spending to last month's, category by
    category, and estimates potential savings. Pure arithmetic on the
    user's own data -- no LLM call, so it's instant and free, and the
    numbers are always exactly traceable to real rows.

    Returns a list of short strings ready to render as bullet points
    on the dashboard, e.g.:
      "Food spending increased by 15% (₹2,300 -> ₹2,645)"
    """
    this_start, this_end = _month_bounds(0)
    last_start, last_end = _month_bounds(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT category, SUM(amount) FROM expenses
        WHERE user_id=? AND date>=? AND date<?
        GROUP BY category
        """,
        (user_id, this_start, this_end)
    )
    this_month = dict(cursor.fetchall())

    cursor.execute(
        """
        SELECT category, SUM(amount) FROM expenses
        WHERE user_id=? AND date>=? AND date<?
        GROUP BY category
        """,
        (user_id, last_start, last_end)
    )
    last_month = dict(cursor.fetchall())

    cursor.execute(
        "SELECT SUM(amount) FROM income WHERE user_id=? AND date>=? AND date<?",
        (user_id, this_start, this_end)
    )
    income_this_month = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=? AND date>=? AND date<?",
        (user_id, this_start, this_end)
    )
    expense_this_month = cursor.fetchone()[0] or 0

    conn.close()

    insights = []

    # Category trend: only compare categories that had spending last
    # month, since "infinite % increase" on a brand-new category isn't
    # a useful insight.
    all_categories = set(this_month) | set(last_month)
    for category in sorted(all_categories):
        this_amt = this_month.get(category, 0)
        last_amt = last_month.get(category, 0)

        if last_amt <= 0:
            continue

        change_pct = ((this_amt - last_amt) / last_amt) * 100
        if abs(change_pct) < 5:
            continue  # ignore noise, only surface meaningful shifts

        direction = "increased" if change_pct > 0 else "decreased"
        insights.append(
            f"{category} spending {direction} by {abs(change_pct):.0f}% "
            f"(₹{last_amt:,.0f} → ₹{this_amt:,.0f})"
        )

    # Potential savings: simple heuristic -- if expenses exceed a
    # sensible share of income, flag the gap; otherwise show how much
    # of this month's income is unspent so far.
    if income_this_month > 0:
        potential_savings = income_this_month - expense_this_month
        if potential_savings > 0:
            insights.append(f"Potential savings this month: ₹{potential_savings:,.0f}")
        else:
            insights.append(
                f"Spending has exceeded income this month by ₹{abs(potential_savings):,.0f}"
            )

    if not insights:
        insights.append("Not enough data yet -- add a few more expenses to see trends.")

    return insights[:5]  # keep the card short


# =========================
# DASHBOARD
# =========================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect("/login")

    # Sessions created before this feature existed won't have 'email' yet --
    # backfill it once from the DB rather than forcing everyone to log out.
    if "email" not in session:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE id=?", (session["user_id"],))
        row = cursor.fetchone()
        conn.close()
        session["email"] = row[0] if row else ""

    process_due_bills(session["user_id"])
    generate_due_bill_notifications(session["user_id"])
    unread_count, recent_notifications = get_navbar_notifications(session["user_id"])

    conn   = sqlite3.connect(DB_PATH)
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

    ai_insights = build_ai_insights(session["user_id"])
    monthly_trend = build_monthly_trend(session["user_id"])

    receipt_error_code = request.args.get("receipt_error", "")
    receipt_error_msg  = _RECEIPT_ERRORS.get(receipt_error_code, "")
    receipt_added      = request.args.get("receipt_added") == "1"
    receipt_amount     = request.args.get("receipt_amount", "")
    receipt_cat        = request.args.get("receipt_cat", "")
    receipt_orig       = request.args.get("receipt_orig", "")   # e.g. "USD 12.50"
    receipt_rate       = request.args.get("receipt_rate", "")   # e.g. "84.2500"

    return render_template(
        "index.html",
        expenses=expenses,
        income_history=income_history,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        category_summary=category_summary,
        ai_insights=ai_insights,
        monthly_trend=monthly_trend,
        unread_count=unread_count,
        recent_notifications=recent_notifications,
        receipt_error_msg=receipt_error_msg,
        receipt_added=receipt_added,
        receipt_amount=receipt_amount,
        receipt_cat=receipt_cat,
        receipt_orig=receipt_orig,
        receipt_rate=receipt_rate,
    )


# =========================
# PERSONAL EXPENSES
# =========================

@app.route("/add", methods=["POST"])
def add_expense():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect(DB_PATH)
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


_RECEIPT_ERRORS = {
    "no_file":          "⚠️ No file selected. Please choose a receipt image or PDF.",
    "bad_file":         "⚠️ Unsupported file type. Please upload a JPG, PNG, WEBP, or PDF.",
    "ocr_missing":      "⚠️ Could not read the receipt. Make sure GROQ_API_KEY is set and try again.",
    "ocr_failed":       "⚠️ The AI could not read this receipt. Try a clearer photo with good lighting.",
    "amount_not_found": "⚠️ Could not detect a total amount in the receipt. Please add the expense manually.",
    "fx_failed":        "⚠️ Detected a foreign currency but could not fetch the live exchange rate. Please add the expense manually.",
}


@app.route("/scan_receipt", methods=["POST"])
def scan_receipt():
    if "user_id" not in session:
        return redirect("/login")

    receipt = request.files.get("receipt")

    if not receipt or receipt.filename == "":
        return redirect("/?receipt_error=no_file#receipt-scanner")

    if not _allowed_receipt_file(receipt.filename):
        return redirect("/?receipt_error=bad_file#receipt-scanner")

    original_filename = secure_filename(receipt.filename)
    saved_filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{original_filename}"
    image_path = os.path.join(UPLOAD_FOLDER, saved_filename)
    receipt.save(image_path)

    try:
        receipt_text = _extract_receipt_text(image_path)
    except RuntimeError as exc:
        print(f"[scan_receipt] OCR error: {exc}")
        err_code = "ocr_missing" if "GROQ_API_KEY" in str(exc) else "ocr_failed"
        return redirect(f"/?receipt_error={err_code}#receipt-scanner")
    except Exception as exc:
        print(f"[scan_receipt] Unexpected OCR error: {exc}")
        return redirect("/?receipt_error=ocr_failed#receipt-scanner")

    # ── Step 1: Detect currency and get the AI-parsed amount ──────────────
    detected_currency, ai_amount = _detect_receipt_currency_and_amount(receipt_text)

    # ── Step 2: Get the numeric amount (AI first, then regex fallback) ────
    amount_in_original = ai_amount if (ai_amount and ai_amount > 0) else _guess_receipt_amount(receipt_text)
    if amount_in_original is None or amount_in_original <= 0:
        return redirect("/?receipt_error=amount_not_found#receipt-scanner")

    # ── Step 3: Convert to INR if foreign currency ────────────────────────
    converted_note = ""
    final_amount   = amount_in_original

    if not _is_inr(detected_currency, receipt_text):
        rate = _fetch_inr_rate(detected_currency)
        if rate is None:
            return redirect("/?receipt_error=fx_failed#receipt-scanner")
        final_amount   = round(amount_in_original * rate, 2)
        converted_note = f"{detected_currency} {amount_in_original:.2f} @ ₹{rate:.4f} = ₹{final_amount:.2f}"
        print(f"[scan_receipt] Currency conversion: {converted_note}")

    # ── Step 4: Guess category / description / date ───────────────────────
    category     = _guess_receipt_category(receipt_text)
    description  = _guess_receipt_description(receipt_text, original_filename)
    expense_date = _guess_receipt_date(receipt_text)

    # Append conversion note to description so it's visible in expense list
    if converted_note:
        description = f"{description} [{converted_note}]"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO expenses
        (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session["user_id"], final_amount, category, description, expense_date)
    )
    conn.commit()
    conn.close()

    # Build success redirect with enough info for a helpful banner
    from urllib.parse import quote
    extra = ""
    if converted_note:
        extra = f"&receipt_orig={quote(detected_currency + ' ' + str(round(amount_in_original,2)))}&receipt_rate={rate:.4f}"

    return redirect(
        f"/?receipt_added=1&receipt_amount={final_amount:.2f}&receipt_cat={category}{extra}#expense-form"
    )


@app.route("/delete/<int:id>")
def delete_expense(id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM expenses WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/expenses_bill")
def expenses_bill():
    """Download a PDF bill/statement for all expenses of the logged-in user."""
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT amount, category, description, date
        FROM expenses
        WHERE user_id=?
        ORDER BY date DESC, id DESC
        """,
        (session["user_id"],)
    )
    expenses = cursor.fetchall()

    cursor.execute(
        """
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY category
        ORDER BY SUM(amount) DESC
        """,
        (session["user_id"],)
    )
    category_totals = cursor.fetchall()

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=?",
        (session["user_id"],)
    )
    total_expense = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT username FROM users WHERE id=?",
        (session["user_id"],)
    )
    user = cursor.fetchone()
    conn.close()

    username = user[0] if user else session.get("username", "User")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExpenseBillTitle",
        fontSize=16,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#111827"),
        alignment=TA_CENTER,
        spaceAfter=6
    )
    sub_style = ParagraphStyle(
        "ExpenseBillSub",
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.HexColor("#6b7280"),
        alignment=TA_CENTER,
        spaceAfter=8
    )
    total_style = ParagraphStyle(
        "ExpenseBillTotal",
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#16a34a"),
        alignment=TA_RIGHT,
        spaceAfter=8
    )
    small_style = ParagraphStyle(
        "ExpenseBillSmall",
        fontSize=8,
        fontName="Helvetica",
        textColor=colors.HexColor("#6b7280"),
        alignment=TA_CENTER
    )

    story = [
        Paragraph("Expense Manager", title_style),
        Paragraph(f"Expense Bill for {escape(username)}", sub_style),
        Paragraph(f"Generated on {date.today().strftime('%d %B %Y')}", sub_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")),
        Spacer(1, 5 * mm),
        Paragraph(f"Total Expense: Rs. {float(total_expense):,.2f}", total_style),
    ]

    if category_totals:
        category_rows = [["Category", "Total"]]
        for category, amount in category_totals:
            category_rows.append([
                escape(str(category)),
                f"Rs. {float(amount):,.2f}"
            ])

        category_table = Table(category_rows, colWidths=[110 * mm, 55 * mm])
        category_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([
            Paragraph("Category Summary", styles["Heading3"]),
            category_table,
            Spacer(1, 7 * mm)
        ])

    expense_rows = [["Date", "Category", "Description", "Amount"]]
    for amount, category, description, expense_date in expenses:
        expense_rows.append([
            escape(str(expense_date)),
            escape(str(category)),
            Paragraph(escape(str(description)), styles["BodyText"]),
            f"Rs. {float(amount):,.2f}"
        ])

    if len(expense_rows) == 1:
        expense_rows.append(["-", "-", "No expenses recorded.", "Rs. 0.00"])

    expense_table = Table(expense_rows, colWidths=[28 * mm, 38 * mm, 70 * mm, 29 * mm])
    expense_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story.extend([
        Paragraph("Expense Details", styles["Heading3"]),
        expense_table,
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")),
        Spacer(1, 4 * mm),
        Paragraph("This is a computer-generated expense statement.", small_style)
    ])

    doc.build(story)
    buffer.seek(0)

    filename = f"expense_bill_{date.today().strftime('%Y_%m_%d')}.pdf"
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# =========================
# INCOME
# =========================

@app.route("/add_income", methods=["POST"])
def add_income():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect(DB_PATH)
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

    conn   = sqlite3.connect(DB_PATH)
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

    conn   = sqlite3.connect(DB_PATH)
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

    conn   = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Show all manually added pending bills always.
    # Auto-created recurring bills (last_generated_date is set) only appear
    # in this table when their due date is within 7 days, so they don't
    # clutter the list right after payment. One-time bills always show
    # here until paid, since last_generated_date stays NULL for them.
    #
    # NOTE: due_date is stored as TEXT (see database.py), and this app now
    # runs on Postgres rather than SQLite (see DB_PATH comment above), so
    # we can't use SQLite's date('now', '+7 days') here -- that's invalid
    # syntax in Postgres and was the cause of the 500 error on this page.
    # due_date::date casts the TEXT column to a real date so it can be
    # compared against CURRENT_DATE + INTERVAL '7 days', which is the
    # Postgres-native way to express "7 days from today".
    cursor.execute(
        """
        SELECT * FROM bills
        WHERE user_id=? AND status='pending'
        AND (
            last_generated_date IS NULL
            OR due_date::date <= CURRENT_DATE + INTERVAL '7 days'
        )
        ORDER BY due_date ASC
        """,
        (session["user_id"],)
    )
    pending_bills = cursor.fetchall()

    # Recurring bills that exist but aren't due soon yet (hidden from the
    # table above on purpose) -- surfaced as a count/note instead of being
    # silently invisible. Same Postgres date-cast fix applied here.
    cursor.execute(
        """
        SELECT COUNT(*), MIN(due_date) FROM bills
        WHERE user_id=? AND status='pending'
        AND last_generated_date IS NOT NULL
        AND due_date::date > CURRENT_DATE + INTERVAL '7 days'
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
    unread_count, recent_notifications = get_navbar_notifications(session["user_id"])

    return render_template(
        "bills.html",
        pending_bills=pending_bills,
        paid_bills=paid_bills,
        today=today_str,
        upcoming_count=upcoming_count,
        upcoming_next_date=upcoming_next_date,
        unread_count=unread_count,
        recent_notifications=recent_notifications
    )


@app.route("/add_bill", methods=["POST"])
def add_bill():
    if "user_id" not in session:
        return redirect("/login")

    recurrence = request.form.get("recurrence", "none")
    if recurrence not in ("none", "weekly", "monthly"):
        recurrence = "none"

    conn = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
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

    payment_links = _build_upi_payment_links(bill)

    return render_template(
        "pay_bill_page.html",
        bill=bill,
        upi_id=UPI_ID,
        payment_links=payment_links
    )


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

    conn = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
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

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Show every group this user has access to -- groups they own AND
    # groups they were added to as a member. This is the only listing
    # query that should ever return groups, since it goes through
    # group_members (the access-control table) rather than filtering
    # on groups_table.user_id alone, which would hide groups a member
    # was invited into but doesn't own.
    cursor.execute(
        """
        SELECT g.*, gm.role
        FROM groups_table g
        JOIN group_members gm ON gm.group_id = g.id
        WHERE gm.user_id=?
        ORDER BY g.id DESC
        """,
        (session["user_id"],)
    )
    groups = cursor.fetchall()
    conn.close()

    return render_template("groups.html", groups=groups)


@app.route("/add_group", methods=["POST"])
def add_group():

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO groups_table (user_id, group_name) VALUES (?, ?)",
        (session["user_id"], request.form["group_name"])
    )
    new_group_id = cursor.lastrowid

    # The creator is automatically the owner of their own group.
    cursor.execute(
        "INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'owner')",
        (new_group_id, session["user_id"])
    )

    conn.commit()
    conn.close()
    return redirect("/groups")


# =========================
# GROUP USER ACCESS (invite / remove real accounts)
# =========================

@app.route("/group/<int:group_id>/invite", methods=["POST"])
def invite_group_user(group_id):
    """
    Owner-only. Adds an EXISTING registered user (looked up by email)
    as a member of this group, granting them access to view this
    group and pay/settle within it -- and nothing else (no access to
    the owner's personal expenses, income, bills, or other groups).
    Also creates a matching row in `members` so the invited user shows
    up as a split participant, linked to their real account.
    """
    if "user_id" not in session:
        return redirect("/login")

    require_group_owner(group_id)

    invite_email = request.form["email"].strip().lower()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, username FROM users WHERE email=?", (invite_email,))
    invited_user = cursor.fetchone()

    if invited_user is None:
        conn.close()
        # No account with that email -- per your chosen flow, we don't
        # auto-create one. Surface this back to the group page.
        return redirect(f"/group/{group_id}?invite_error=no_account")

    invited_user_id, invited_username = invited_user

    cursor.execute(
        """
        INSERT OR IGNORE INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'member')
        """,
        (group_id, invited_user_id)
    )

    # Add them as a split participant too, linked to their real account,
    # unless a member row for this person already exists in this group.
    cursor.execute(
        "SELECT 1 FROM members WHERE group_id=? AND user_id=?",
        (group_id, invited_user_id)
    )
    already_a_split_member = cursor.fetchone() is not None

    if not already_a_split_member:
        cursor.execute(
            "INSERT INTO members (group_id, member_name, user_id) VALUES (?, ?, ?)",
            (group_id, invited_username, invited_user_id)
        )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}?invited=1")


@app.route("/group/<int:group_id>/remove_user/<int:target_user_id>")
def remove_group_user(group_id, target_user_id):
    """Owner-only. Revokes a user's access to this group entirely."""
    if "user_id" not in session:
        return redirect("/login")

    owner_id = require_group_owner(group_id)

    if target_user_id == owner_id:
        # Owners can't remove themselves this way -- use delete_group instead.
        return redirect(f"/group/{group_id}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM group_members WHERE group_id=? AND user_id=?",
        (group_id, target_user_id)
    )
    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


# =========================
# MEMBERS
# =========================

@app.route("/add_member/<int:group_id>", methods=["POST"])
def add_member(group_id):

    if "user_id" not in session:
        return redirect("/login")

    # Any group member can add a free-text split participant (e.g. someone
    # who isn't on the app). Only the OWNER can grant real account access
    # -- that happens exclusively through /group/<id>/invite above.
    require_group_access(group_id)

    conn   = sqlite3.connect(DB_PATH)
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

    require_group_access(group_id)

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Scoped to this group_id so a member can't delete a member row in a
    # DIFFERENT group just by guessing/incrementing member_id in the URL.
    cursor.execute(
        "DELETE FROM members WHERE id=? AND group_id=?",
        (member_id, group_id)
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/delete_group/<int:group_id>")
def delete_group(group_id):

    if "user_id" not in session:
        return redirect("/login")

    # Only the owner can delete the whole group.
    require_group_owner(group_id)

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM shared_expenses WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM settlements WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM members WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))
    cursor.execute("DELETE FROM groups_table WHERE id=?", (group_id,))

    conn.commit()
    conn.close()
    return redirect("/groups")


def _get_upi_id_for_member_name(group_id, member_name):
    """
    Resolve a split-participant name (as stored on settlements/expenses,
    which are free text) to the UPI ID on that person's real account --
    but ONLY if that name corresponds to a member row that's linked to
    a real, invited user (members.user_id is set). Free-text-only
    participants with no linked account have no UPI ID to pay to.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.upi_id
        FROM members m
        JOIN users u ON u.id = m.user_id
        WHERE m.group_id=? AND m.member_name=? AND m.user_id IS NOT NULL
        """,
        (group_id, member_name)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


@app.route("/settle_up_pay/<int:group_id>")
def settle_up_pay(group_id):
    """
    Shows the payment options page (PhonePe / GPay / Paytm / UPI) for a
    settlement, same pattern as pay_bill_page for bills -- except the
    payee here is the RECEIVER's own UPI ID, since settlement money is
    owed to a specific group member, not to the app owner.
    """
    if "user_id" not in session:
        return redirect("/login")

    require_group_access(group_id)

    payer    = request.args.get("payer", "")
    receiver = request.args.get("receiver", "")

    try:
        amount = float(request.args.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0

    receiver_upi_id = _get_upi_id_for_member_name(group_id, receiver)

    if not receiver_upi_id:
        # Receiver hasn't set a UPI ID (or isn't a linked account) --
        # nothing to pay to, so send back with a clear reason instead
        # of generating a broken/empty payment link.
        return redirect(f"/group/{group_id}?settle_error=no_upi&receiver={receiver}")

    payment_links = _build_upi_links(receiver_upi_id, receiver, amount, f"Settlement: {payer} to {receiver}")

    return render_template(
        "settle_up_pay.html",
        group_id=group_id,
        payer=payer,
        receiver=receiver,
        amount=amount,
        receiver_upi_id=receiver_upi_id,
        payment_links=payment_links
    )


@app.route("/update_upi_id", methods=["POST"])
def update_upi_id():
    """Lets the logged-in user set/update their own UPI ID, so others can pay them via settlements."""
    if "user_id" not in session:
        return redirect("/login")

    upi_id = request.form.get("upi_id", "").strip()
    redirect_to = request.form.get("redirect_to") or "/groups"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET upi_id=? WHERE id=?",
        (upi_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(redirect_to)


@app.route("/settle_up/<int:group_id>")
def settle_up(group_id):

    if "user_id" not in session:
        return redirect("/login")

    require_group_access(group_id)

    payer    = request.args.get("payer")
    receiver = request.args.get("receiver")

    try:
        amount = float(request.args.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0

    conn   = sqlite3.connect(DB_PATH)
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

    require_group_access(group_id)

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    split_members = _get_selected_split_members(request.form)
    if not split_members:
        conn.close()
        return redirect(f"/group/{group_id}?split_error=no_members")

    cursor.execute(
        """
        INSERT INTO shared_expenses (group_id, description, amount, paid_by, split_members)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            group_id,
            request.form["description"],
            float(request.form["amount"]),
            request.form["paid_by"],
            json.dumps(split_members)
        )
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/delete_shared_expense/<int:expense_id>/<int:group_id>")
def delete_shared_expense(expense_id, group_id):

    if "user_id" not in session:
        return redirect("/login")

    require_group_access(group_id)

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Scoped to this group_id, same reasoning as delete_member above.
    cursor.execute(
        "DELETE FROM shared_expenses WHERE id=? AND group_id=?",
        (expense_id, group_id)
    )

    conn.commit()
    conn.close()
    return redirect(f"/group/{group_id}")


@app.route("/edit_shared_expense/<int:expense_id>")
def edit_shared_expense(expense_id):

    if "user_id" not in session:
        return redirect("/login")

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shared_expenses WHERE id=?", (expense_id,))
    expense = cursor.fetchone()

    if expense is None:
        conn.close()
        return redirect("/groups")

    group_id = expense[1]

    # The expense itself doesn't tell us who's allowed to see it -- this
    # check is what stops a member of Group A from editing an expense_id
    # belonging to Group B by guessing the numeric id in the URL.
    if not user_can_access_group(session["user_id"], group_id):
        conn.close()
        abort(403)

    cursor.execute("SELECT * FROM members WHERE group_id=?", (group_id,))
    members = cursor.fetchall()
    selected_split_members = _split_members_from_expense(expense, [member[2] for member in members])
    conn.close()

    return render_template(
        "edit_shared_expense.html",
        expense=expense,
        members=members,
        selected_split_members=selected_split_members
    )


@app.route("/update_shared_expense/<int:expense_id>", methods=["POST"])
def update_shared_expense(expense_id):

    if "user_id" not in session:
        return redirect("/login")

    description = request.form["description"]
    paid_by     = request.form["paid_by"]
    group_id    = int(request.form["group_id"])
    split_members = _get_selected_split_members(request.form)

    require_group_access(group_id)

    if not split_members:
        return redirect(f"/edit_shared_expense/{expense_id}?split_error=no_members")

    try:
        amount = float(request.form["amount"])
    except (TypeError, ValueError):
        amount = 0

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Scoped to group_id too, so the group_id submitted in the form must
    # match the expense's actual group, not just any group the user
    # happens to belong to.
    cursor.execute(
        """
        UPDATE shared_expenses
        SET description=?, amount=?, paid_by=?, split_members=?
        WHERE id=? AND group_id=?
        """,
        (description, amount, paid_by, json.dumps(split_members), expense_id, group_id)
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

    current_user_id = require_group_access(group_id)
    is_owner = user_is_group_owner(current_user_id, group_id)

    conn   = sqlite3.connect(DB_PATH)
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

    # Real user accounts that currently have access to this group, so the
    # template can show "who's in this group" and let the owner remove them.
    cursor.execute(
        """
        SELECT u.id, u.username, u.email, gm.role, u.upi_id
        FROM group_members gm
        JOIN users u ON u.id = gm.user_id
        WHERE gm.group_id=?
        ORDER BY gm.role DESC, u.username ASC
        """,
        (group_id,)
    )
    group_users = cursor.fetchall()

    # The logged-in user's own UPI ID, so the template can prompt them to
    # set one if it's missing (needed so others can pay THEM via settle-up).
    cursor.execute("SELECT upi_id FROM users WHERE id=?", (current_user_id,))
    my_upi_row = cursor.fetchone()
    my_upi_id = my_upi_row[0] if my_upi_row else None

    member_names = [m[2] for m in members]
    split_labels = {}
    for expense in expenses:
        if len(expense) > 5 and expense[5]:
            split_labels[expense[0]] = ", ".join(_split_members_from_expense(expense, member_names))
        else:
            split_labels[expense[0]] = "All members"

    # Map each split-participant name to their UPI ID (if they're a real
    # linked account that has set one), so the template can show "Pay Now"
    # where an actual UPI ID exists.
    cursor.execute(
        """
        SELECT m.member_name, u.upi_id
        FROM members m
        JOIN users u ON u.id = m.user_id
        WHERE m.group_id=? AND m.user_id IS NOT NULL
        """,
        (group_id,)
    )
    name_to_upi = dict(cursor.fetchall())

    # Expense Breakdown
    expense_breakdown = []
    for expense in expenses:
        amount      = expense[3]
        paid_by     = expense[4]
        description = expense[2]
        split_members = _split_members_from_expense(expense, member_names)

        if not split_members:
            continue

        share   = amount / len(split_members)
        details = [
            {
                "text": f"{member} owes {paid_by} ₹{share:.2f}",
                "payer": member,
                "receiver": paid_by,
                "amount": round(share, 2),
                "receiver_upi_id": name_to_upi.get(paid_by)
            }
            for member in split_members
            if member != paid_by
        ]

        expense_breakdown.append({
            "description": description,
            "amount":      amount,
            "paid_by":     paid_by,
            "split_members": split_members,
            "details":     details
        })

    # Net Balance Engine
    balances = defaultdict(float)
    for expense in expenses:
        amount  = expense[3]
        paid_by = expense[4]
        split_members = _split_members_from_expense(expense, member_names)

        if not split_members:
            continue

        share = amount / len(split_members)
        balances[paid_by] += amount
        for member in split_members:
            balances[member] -= share

    # Apply Settlements
    for settlement in settlement_history:
        payer    = settlement[2]
        receiver = settlement[3]
        amount   = settlement[4]
        balances[payer]    += amount
        balances[receiver] -= amount

    debtors   = [[p, -a] for p, a in balances.items() if a < -0.01]
    creditors = [[p,  a] for p, a in balances.items() if a > 0.01]

    settlements = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor   = debtors[i]
        creditor = creditors[j]
        payment  = min(debtor[1], creditor[1])

        if payment < 0.01:
            if debtor[1] < 0.01: i += 1
            if creditor[1] < 0.01: j += 1
            continue

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

    for settlement in settlements:
        settlement["receiver_upi_id"] = name_to_upi.get(settlement["receiver"])

    conn.close()

    return render_template(
        "group_details.html",
        group=group,
        members=members,
        expenses=expenses,
        expense_breakdown=expense_breakdown,
        balances=settlements,
        settlement_history=settlement_history,
        split_labels=split_labels,
        group_users=group_users,
        is_owner=is_owner,
        my_upi_id=my_upi_id
    )


# =========================
# NOTIFICATIONS
# =========================

@app.route("/notifications/mark_read/<int:notification_id>", methods=["POST"])
def mark_notification_read(notification_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Scoped to user_id so a user can't mark someone else's notification
    # read by guessing the id in the URL.
    cursor.execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (notification_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    return ("", 204)


@app.route("/notifications/mark_all_read", methods=["POST"])
def mark_all_notifications_read():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
        (session["user_id"],)
    )
    conn.commit()
    conn.close()

    return ("", 204)


# =========================
# ASK EXPENSE MANAGER (AI CHAT)
# =========================

@app.route("/api/monthly_trend")
def api_monthly_trend():
    """
    Returns this user's last-12-months income/expense trend as JSON.
    Used by the chart toggle button on the Ask Expense Manager page so
    it can render the same trend chart shown on the dashboard without
    a full page reload.
    """
    if "user_id" not in session:
        return {"error": "not logged in"}, 401

    trend = build_monthly_trend(session["user_id"])
    return {"trend": trend}


@app.route("/ask_ai")
def ask_ai_page():
    if "user_id" not in session:
        return redirect("/login")

    unread_count, recent_notifications = get_navbar_notifications(session["user_id"])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, question, answer, created_at FROM ai_chats
        WHERE user_id=? ORDER BY id ASC
        """,
        (session["user_id"],)
    )
    chat_history = cursor.fetchall()
    conn.close()

    return render_template(
        "ask_ai.html",
        chat_history=chat_history,
        unread_count=unread_count,
        recent_notifications=recent_notifications
    )


@app.route("/ask_ai", methods=["POST"])
def ask_ai_submit():
    if "user_id" not in session:
        return redirect("/login")

    question = request.form.get("question", "").strip()
    if not question:
        return redirect("/ask_ai")

    try:
        answer = ask_expense_manager_ai(session["user_id"], question)
    except RuntimeError as exc:
        answer = f"⚠️ {exc}"
    except Exception as exc:
        print(f"[ask_ai_submit] Unexpected error: {exc}")
        answer = "⚠️ Something went wrong answering that. Please try again."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ai_chats (user_id, question, answer) VALUES (?, ?, ?)",
        (session["user_id"], question, answer)
    )
    conn.commit()
    conn.close()

    return redirect("/ask_ai")


@app.route("/ask_ai/clear", methods=["POST"])
def ask_ai_clear():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ai_chats WHERE user_id=?", (session["user_id"],))
    conn.commit()
    conn.close()

    return redirect("/ask_ai")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)