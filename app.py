from flask import redirect, url_for
from flask import flash
import os
import base64
import re
import json
import secrets
import db_compat as sqlite3
import requests
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials as GoogleCredentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from html import escape, unescape
from email.utils import parseaddr
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from flask import Flask, render_template, request, redirect, session, send_file, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

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

from biometric_auth import biometric_bp
app.register_blueprint(biometric_bp)


# ============================================================
# ADMIN ADVERTISING / SPONSORSHIP
# ============================================================
from admin_ads import admin_ads_bp
app.register_blueprint(admin_ads_bp)


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(
        os.path.join(BASE_DIR, "static"),
        "service-worker.js",
        mimetype="application/javascript"
    )

    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"

    return response


@app.route("/offline")
def offline():
    return render_template("offline.html")


@app.route("/api/offline-sync", methods=["POST"])
def offline_sync():
    if "user_id" not in session:
        return {"error": "Authentication required"}, 401

    payload = request.get_json(silent=True) or {}

    operation_type = payload.get("type")
    data = payload.get("data") or {}

    if operation_type not in {"expense", "income"}:
        return {"error": "Unsupported offline operation"}, 400

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if operation_type == "expense":
            cursor.execute(
                """
                INSERT INTO expenses
                (amount, category, description, date, user_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    data.get("amount"),
                    data.get("category"),
                    data.get("description"),
                    data.get("date"),
                    session["user_id"]
                )
            )

        else:
            cursor.execute(
                """
                INSERT INTO income
                (amount, source, date, user_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    data.get("amount"),
                    data.get("source"),
                    data.get("date"),
                    session["user_id"]
                )
            )

        conn.commit()

        return {"success": True}

    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        return {
            "success": False,
            "error": str(exc)
        }, 500

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


SECRET_KEY = os.environ.get("SECRET_KEY")

if not SECRET_KEY:
    if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production."
        )

    SECRET_KEY = "expense-manager-local-development-only"

app.secret_key = SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# DATABASE REQUEST CLEANUP START
@app.teardown_appcontext
def release_request_database_connections(exception=None):
    """
    Safety net for PostgreSQL pooling.

    Every normal DB call should still close its own connection,
    but this guarantees an exception or early return cannot
    permanently exhaust the connection pool.
    """
    sqlite3.release_unclosed_connections()
# DATABASE REQUEST CLEANUP END


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
print("Resend email service configured:", bool(RESEND_API_KEY))
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

    app_identity = (
        "Product name: Expense Manager.\n"
        "Founder, creator and developer: Harsh Raj.\n"
        "Harsh Raj designed and built Expense Manager.\n"
        "If the user asks who built this app, who created it, "
        "who developed it, who the founder is, founder name, "
        "creator name, developer name, or who owns Expense Manager, "
        "answer that Harsh Raj is the founder, creator and developer "
        "of Expense Manager.\n"
        "Do not confuse the AI model provider with the creator "
        "of the Expense Manager application."
    )

    system_prompt = (
        "You are 'Ask Expense Manager', a helpful assistant inside a personal "
        "finance app. You may answer questions about Expense Manager itself using "
        "the App identity section below. For financial questions, answer ONLY using "
        "the financial data "
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
        f"App identity:\n{app_identity}\n\n"
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
        username = request.form.get("username", "").strip()
        email = _normalise_email(request.form.get("email", ""))
        raw_password = request.form.get("password", "")

        if not username or not email or not raw_password:
            error = "Please fill in all fields."
            return render_template("register.html", error=error)

        password = generate_password_hash(raw_password)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            # Check if account already exists
            cursor.execute(
                "SELECT id FROM users WHERE LOWER(email) = LOWER(?)",
                (email,)
            )
            existing_user = cursor.fetchone()

            if existing_user:
                conn.close()

                flash(
                    "An account with this email already exists. Please log in.",
                    "warning"
                )

                return redirect(url_for("login"))

            # Create new account
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, password)
            )

            conn.commit()
            conn.close()

            flash(
                "Account created successfully. Please log in.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()

            flash(
                "An account with this email already exists. Please log in.",
                "warning"
            )

            return redirect(url_for("login"))

        except Exception as e:
            conn.rollback()
            conn.close()

            print("REGISTER ERROR:", repr(e))

            error = "Unable to create account. Please try again."
            return render_template("register.html", error=error)

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

    # PostgreSQL TIMESTAMP columns return datetime objects,
    # while local SQLite may return strings.
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            expires_at = datetime.strptime(
                expires_at,
                "%Y-%m-%d %H:%M:%S"
            )

    is_expired = datetime.now() > expires_at

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



# ============================================================
# USER PROFILE / ACCOUNT SETTINGS
# ============================================================


@app.route("/api/profile")
def profile_api():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, email, profile_image
        FROM users
        WHERE id=?
        """,
        (session["user_id"],)
    )

    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"error": "User not found"}, 404

    return {
        "username": user[0],
        "email": user[1],
        "profile_image": user[2] or ""
    }


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    message = None
    error = None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, username, email, password, upi_id, profile_image
        FROM users
        WHERE id=?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:
        conn.close()
        session.clear()
        return redirect("/login")

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        ).strip()


        # ----------------------------------------------------
        # PROFILE DETAILS
        # ----------------------------------------------------

        if action == "profile":

            username = request.form.get(
                "username",
                ""
            ).strip()

            email = _normalise_email(
                request.form.get(
                    "email",
                    ""
                )
            )

            upi_id = request.form.get(
                "upi_id",
                ""
            ).strip()


            if len(username) < 2:

                error = (
                    "Name must contain at least 2 characters."
                )


            elif (
                not email
                or "@" not in email
            ):

                error = (
                    "Enter a valid email address."
                )


            else:

                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE email=?
                    AND id<>?
                    """,
                    (
                        email,
                        user_id
                    )
                )

                duplicate = cursor.fetchone()


                if duplicate:

                    error = (
                        "That email address is already "
                        "used by another account."
                    )


                else:

                    try:

                        cursor.execute(
                            """
                            UPDATE users
                            SET
                                username=?,
                                email=?,
                                upi_id=?
                            WHERE id=?
                            """,
                            (
                                username,
                                email,
                                upi_id or None,
                                user_id
                            )
                        )

                        conn.commit()

                        session["username"] = username
                        session["email"] = email

                        message = (
                            "Profile updated successfully."
                        )


                    except sqlite3.IntegrityError:

                        conn.rollback()

                        error = (
                            "That email address is already "
                            "used by another account."
                        )


        # ----------------------------------------------------
        # PROFILE PICTURE
        # ----------------------------------------------------

        elif action == "picture":

            import base64

            photo = request.files.get(
                "profile_picture"
            )

            allowed_types = {
                "image/jpeg",
                "image/png",
                "image/webp",
            }

            if not photo or not photo.filename:

                error = (
                    "Choose a profile picture first."
                )

            elif photo.mimetype not in allowed_types:

                error = (
                    "Only JPG, PNG and WEBP images "
                    "are supported."
                )

            else:

                image_bytes = photo.read()

                if len(image_bytes) > 2 * 1024 * 1024:

                    error = (
                        "Profile picture must be "
                        "smaller than 2 MB."
                    )

                else:

                    encoded = base64.b64encode(
                        image_bytes
                    ).decode("utf-8")

                    profile_image = (
                        "data:"
                        + photo.mimetype
                        + ";base64,"
                        + encoded
                    )

                    cursor.execute(
                        """
                        UPDATE users
                        SET profile_image=?
                        WHERE id=?
                        """,
                        (
                            profile_image,
                            user_id
                        )
                    )

                    conn.commit()

                    message = (
                        "Profile picture updated."
                    )


        # ----------------------------------------------------
        # REMOVE PROFILE PICTURE
        # ----------------------------------------------------

        elif action == "remove_picture":

            cursor.execute(
                """
                UPDATE users
                SET profile_image=NULL
                WHERE id=?
                """,
                (user_id,)
            )

            conn.commit()

            message = (
                "Profile picture removed."
            )


        # ----------------------------------------------------
        # PASSWORD
        # ----------------------------------------------------

        elif action == "password":

            current_password = request.form.get(
                "current_password",
                ""
            )

            new_password = request.form.get(
                "new_password",
                ""
            )

            confirm_password = request.form.get(
                "confirm_password",
                ""
            )


            if not check_password_hash(
                user[3],
                current_password
            ):

                error = (
                    "Current password is incorrect."
                )


            elif len(new_password) < 6:

                error = (
                    "New password must contain "
                    "at least 6 characters."
                )


            elif new_password != confirm_password:

                error = (
                    "New passwords do not match."
                )


            else:

                cursor.execute(
                    """
                    UPDATE users
                    SET password=?
                    WHERE id=?
                    """,
                    (
                        generate_password_hash(
                            new_password
                        ),
                        user_id
                    )
                )

                conn.commit()

                message = (
                    "Password changed successfully."
                )


        # ----------------------------------------------------
        # REFRESH USER AFTER UPDATE
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id, username, email, password, upi_id, profile_image
            FROM users
            WHERE id=?
            """,
            (user_id,)
        )

        user = cursor.fetchone()


    profile_data = {
        "username": user[1],
        "email": user[2],
        "upi_id": user[4] or "",
        "profile_image": user[5] or "",
    }


    conn.close()


    return render_template(
        "profile.html",
        profile=profile_data,
        message=message,
        error=error
    )


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
    Build the monthly income/expense chart efficiently.

    Old implementation:
        12 months × 2 SQL queries = 24 database queries.

    New implementation:
        1 income query
        1 expense query

    Aggregation is performed in Python.
    """

    months = max(1, int(months))

    first_start, _ = _month_bounds(months - 1)
    _, final_end = _month_bounds(0)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT amount, date
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        """,
        (
            user_id,
            first_start,
            final_end
        )
    )

    income_rows = cursor.fetchall()

    cursor.execute(
        """
        SELECT amount, date
        FROM expenses
        WHERE user_id=?
          AND date>=?
          AND date<?
        """,
        (
            user_id,
            first_start,
            final_end
        )
    )

    expense_rows = cursor.fetchall()

    conn.close()

    monthly = {}

    for months_ago in range(
        months - 1,
        -1,
        -1
    ):
        start, _ = _month_bounds(
            months_ago
        )

        key = start[:7]

        month_date = datetime.strptime(
            start,
            "%Y-%m-%d"
        ).date()

        monthly[key] = {
            "label":
                month_date.strftime(
                    "%b %Y"
                ),
            "income": 0.0,
            "expense": 0.0,
        }

    for amount, date_value in income_rows:
        if not date_value:
            continue

        key = str(date_value)[:7]

        if key in monthly:
            monthly[key]["income"] += (
                float(amount or 0)
            )

    for amount, date_value in expense_rows:
        if not date_value:
            continue

        key = str(date_value)[:7]

        if key in monthly:
            monthly[key]["expense"] += (
                float(amount or 0)
            )

    trend = []

    for data in monthly.values():
        data["income"] = round(
            data["income"],
            2
        )

        data["expense"] = round(
            data["expense"],
            2
        )

        trend.append(data)

    return trend


def build_ai_insights(user_id):
    """
    Generate dashboard financial insights efficiently.

    Uses only two database queries.
    """

    this_start, this_end = _month_bounds(0)
    last_start, last_end = _month_bounds(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            category,

            SUM(
                CASE
                    WHEN date>=?
                     AND date<?
                    THEN amount
                    ELSE 0
                END
            ),

            SUM(
                CASE
                    WHEN date>=?
                     AND date<?
                    THEN amount
                    ELSE 0
                END
            )

        FROM expenses

        WHERE user_id=?
          AND date>=?
          AND date<?

        GROUP BY category
        """,
        (
            this_start,
            this_end,

            last_start,
            last_end,

            user_id,
            last_start,
            this_end
        )
    )

    rows = cursor.fetchall()

    this_month = {}
    last_month = {}

    for row in rows:
        category = row[0]

        this_month[category] = float(
            row[1] or 0
        )

        last_month[category] = float(
            row[2] or 0
        )

    cursor.execute(
        """
        SELECT SUM(amount)
        FROM income
        WHERE user_id=?
          AND date>=?
          AND date<?
        """,
        (
            user_id,
            this_start,
            this_end
        )
    )

    income_this_month = (
        cursor.fetchone()[0]
        or 0
    )

    conn.close()

    income_this_month = float(
        income_this_month
    )

    expense_this_month = sum(
        this_month.values()
    )

    insights = []

    all_categories = (
        set(this_month)
        | set(last_month)
    )

    for category in sorted(
        all_categories
    ):

        this_amt = this_month.get(
            category,
            0
        )

        last_amt = last_month.get(
            category,
            0
        )

        if last_amt <= 0:
            continue

        change_pct = (
            (
                this_amt
                - last_amt
            )
            / last_amt
        ) * 100

        if abs(change_pct) < 5:
            continue

        direction = (
            "increased"
            if change_pct > 0
            else "decreased"
        )

        insights.append(
            f"{category} spending "
            f"{direction} by "
            f"{abs(change_pct):.0f}% "
            f"(₹{last_amt:,.0f} → "
            f"₹{this_amt:,.0f})"
        )

    if income_this_month > 0:

        potential_savings = (
            income_this_month
            - expense_this_month
        )

        if potential_savings > 0:

            insights.append(
                "Potential savings "
                "this month: "
                f"₹{potential_savings:,.0f}"
            )

        else:

            insights.append(
                "Spending has exceeded "
                "income this month by "
                f"₹{abs(potential_savings):,.0f}"
            )

    if not insights:
        insights.append(
            "Not enough data yet -- "
            "add a few more expenses "
            "to see trends."
        )

    return insights[:5]

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



# ============================================================
# BILL / INVOICE STUDIO
# ============================================================

def _invoice_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_bill_invoice_data(cursor, bill_id, user_id):
    import json

    cursor.execute(
        """
        SELECT
            id,
            user_id,
            name,
            amount,
            category,
            due_date,
            recurrence,
            status,
            last_generated_date
        FROM bills
        WHERE id=? AND user_id=?
        """,
        (bill_id, user_id)
    )

    row = cursor.fetchone()

    if not row:
        return None, None

    bill = {
        "id": row[0],
        "user_id": row[1],
        "name": row[2],
        "amount": float(row[3]),
        "category": row[4],
        "due_date": row[5],
        "recurrence": row[6],
        "status": row[7],
        "paid_date": row[8],
    }

    cursor.execute(
        """
        SELECT username, email
        FROM users
        WHERE id=?
        """,
        (user_id,)
    )

    user_row = cursor.fetchone()

    user = {
        "username": (
            user_row[0]
            if user_row
            else "User"
        ),
        "email": (
            user_row[1]
            if user_row
            else ""
        ),
    }

    cursor.execute(
        """
        SELECT
            document_title,
            business_name,
            business_email,
            business_phone,
            business_address,
            bill_to_name,
            bill_to_email,
            bill_to_address,
            invoice_number,
            issue_date,
            items_json,
            tax_percent,
            discount_amount,
            extra_charges,
            payment_method,
            notes,
            footer_text,
            accent
        FROM bill_invoice_settings
        WHERE bill_id=? AND user_id=?
        """,
        (bill_id, user_id)
    )

    settings_row = cursor.fetchone()

    if settings_row:

        try:
            items = json.loads(
                settings_row[10]
                or "[]"
            )
        except Exception:
            items = []

        settings = {
            "document_title": settings_row[0] or "INVOICE",
            "business_name": settings_row[1] or "Expense Manager",
            "business_email": settings_row[2] or "",
            "business_phone": settings_row[3] or "",
            "business_address": settings_row[4] or "",
            "bill_to_name": settings_row[5] or user["username"],
            "bill_to_email": settings_row[6] or user["email"],
            "bill_to_address": settings_row[7] or "",
            "invoice_number": settings_row[8] or f"INV-{bill_id:05d}",
            "issue_date": settings_row[9] or date.today().strftime("%Y-%m-%d"),
            "items": items,
            "tax_percent": float(settings_row[11] or 0),
            "discount_amount": float(settings_row[12] or 0),
            "extra_charges": float(settings_row[13] or 0),
            "payment_method": settings_row[14] or "",
            "notes": settings_row[15] or "",
            "footer_text": settings_row[16] or "",
            "accent": settings_row[17] or "slate",
        }

    else:

        paid = (
            bill["status"]
            == "paid"
        )

        settings = {
            "document_title": (
                "PAYMENT RECEIPT"
                if paid
                else "INVOICE"
            ),

            "business_name": "Expense Manager",
            "business_email": "",
            "business_phone": "",
            "business_address": "",

            "bill_to_name": user["username"],
            "bill_to_email": user["email"],
            "bill_to_address": "",

            "invoice_number": (
                (
                    "RCP-"
                    if paid
                    else "INV-"
                )
                + f"{bill_id:05d}"
            ),

            "issue_date": (
                bill["paid_date"]
                if paid
                and bill["paid_date"]
                else date.today().strftime(
                    "%Y-%m-%d"
                )
            ),

            "items": [
                {
                    "description": bill["name"],
                    "quantity": 1,
                    "rate": bill["amount"],
                }
            ],

            "tax_percent": 0,
            "discount_amount": 0,
            "extra_charges": 0,

            "payment_method": (
                "Recorded payment"
                if paid
                else "Pending"
            ),

            "notes": "",

            "footer_text": (
                "Generated by Expense Manager. "
                "This is a computer-generated document."
            ),

            "accent": "slate",
        }

    if not settings["items"]:
        settings["items"] = [
            {
                "description": bill["name"],
                "quantity": 1,
                "rate": bill["amount"],
            }
        ]

    return bill, {
        "user": user,
        "settings": settings,
    }


@app.route(
    "/bill_invoice_editor/<int:bill_id>",
    methods=["GET", "POST"]
)
def bill_invoice_editor(bill_id):

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    bill, data = _get_bill_invoice_data(
        cursor,
        bill_id,
        user_id
    )

    if not bill:
        conn.close()
        return redirect("/bills")

    if request.method == "POST":

        import json

        descriptions = request.form.getlist(
            "item_description"
        )

        quantities = request.form.getlist(
            "item_quantity"
        )

        rates = request.form.getlist(
            "item_rate"
        )

        items = []

        count = min(
            max(
                len(descriptions),
                len(quantities),
                len(rates)
            ),
            20
        )

        for index in range(count):

            description = (
                descriptions[index].strip()
                if index < len(descriptions)
                else ""
            )

            if not description:
                continue

            quantity = max(
                _invoice_float(
                    quantities[index]
                    if index < len(quantities)
                    else 1,
                    1
                ),
                0
            )

            rate = max(
                _invoice_float(
                    rates[index]
                    if index < len(rates)
                    else 0
                ),
                0
            )

            items.append({
                "description": description[:180],
                "quantity": quantity,
                "rate": rate,
            })

        if not items:
            items = [
                {
                    "description": bill["name"],
                    "quantity": 1,
                    "rate": bill["amount"],
                }
            ]

        accent = request.form.get(
            "accent",
            "slate"
        )

        if accent not in (
            "slate",
            "blue",
            "sage",
            "copper",
            "plum",
        ):
            accent = "slate"

        values = {
            "document_title": request.form.get(
                "document_title",
                "INVOICE"
            ).strip()[:60],

            "business_name": request.form.get(
                "business_name",
                ""
            ).strip()[:120],

            "business_email": request.form.get(
                "business_email",
                ""
            ).strip()[:160],

            "business_phone": request.form.get(
                "business_phone",
                ""
            ).strip()[:80],

            "business_address": request.form.get(
                "business_address",
                ""
            ).strip()[:800],

            "bill_to_name": request.form.get(
                "bill_to_name",
                ""
            ).strip()[:120],

            "bill_to_email": request.form.get(
                "bill_to_email",
                ""
            ).strip()[:160],

            "bill_to_address": request.form.get(
                "bill_to_address",
                ""
            ).strip()[:800],

            "invoice_number": request.form.get(
                "invoice_number",
                ""
            ).strip()[:80],

            "issue_date": request.form.get(
                "issue_date",
                ""
            ).strip()[:30],

            "items_json": json.dumps(
                items
            ),

            "tax_percent": max(
                _invoice_float(
                    request.form.get(
                        "tax_percent"
                    )
                ),
                0
            ),

            "discount_amount": max(
                _invoice_float(
                    request.form.get(
                        "discount_amount"
                    )
                ),
                0
            ),

            "extra_charges": max(
                _invoice_float(
                    request.form.get(
                        "extra_charges"
                    )
                ),
                0
            ),

            "payment_method": request.form.get(
                "payment_method",
                ""
            ).strip()[:120],

            "notes": request.form.get(
                "notes",
                ""
            ).strip()[:1200],

            "footer_text": request.form.get(
                "footer_text",
                ""
            ).strip()[:500],

            "accent": accent,
        }

        cursor.execute(
            """
            SELECT id
            FROM bill_invoice_settings
            WHERE bill_id=? AND user_id=?
            """,
            (
                bill_id,
                user_id
            )
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute(
                """
                UPDATE bill_invoice_settings
                SET
                    document_title=?,
                    business_name=?,
                    business_email=?,
                    business_phone=?,
                    business_address=?,

                    bill_to_name=?,
                    bill_to_email=?,
                    bill_to_address=?,

                    invoice_number=?,
                    issue_date=?,
                    items_json=?,

                    tax_percent=?,
                    discount_amount=?,
                    extra_charges=?,

                    payment_method=?,
                    notes=?,
                    footer_text=?,
                    accent=?,
                    updated_at=CURRENT_TIMESTAMP

                WHERE
                    bill_id=?
                    AND user_id=?
                """,
                (
                    values["document_title"],
                    values["business_name"],
                    values["business_email"],
                    values["business_phone"],
                    values["business_address"],

                    values["bill_to_name"],
                    values["bill_to_email"],
                    values["bill_to_address"],

                    values["invoice_number"],
                    values["issue_date"],
                    values["items_json"],

                    values["tax_percent"],
                    values["discount_amount"],
                    values["extra_charges"],

                    values["payment_method"],
                    values["notes"],
                    values["footer_text"],
                    values["accent"],

                    bill_id,
                    user_id,
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO bill_invoice_settings
                (
                    bill_id,
                    user_id,

                    document_title,
                    business_name,
                    business_email,
                    business_phone,
                    business_address,

                    bill_to_name,
                    bill_to_email,
                    bill_to_address,

                    invoice_number,
                    issue_date,
                    items_json,

                    tax_percent,
                    discount_amount,
                    extra_charges,

                    payment_method,
                    notes,
                    footer_text,
                    accent
                )

                VALUES
                (
                    ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    bill_id,
                    user_id,

                    values["document_title"],
                    values["business_name"],
                    values["business_email"],
                    values["business_phone"],
                    values["business_address"],

                    values["bill_to_name"],
                    values["bill_to_email"],
                    values["bill_to_address"],

                    values["invoice_number"],
                    values["issue_date"],
                    values["items_json"],

                    values["tax_percent"],
                    values["discount_amount"],
                    values["extra_charges"],

                    values["payment_method"],
                    values["notes"],
                    values["footer_text"],
                    values["accent"],
                )
            )

        conn.commit()
        conn.close()

        if (
            request.form.get(
                "after_save"
            )
            == "download"
        ):
            return redirect(
                f"/bill_invoice/{bill_id}"
            )

        return redirect(
            f"/bill_invoice_editor/{bill_id}?saved=1"
        )

    conn.close()

    return render_template(
        "bill_invoice_editor.html",
        bill=bill,
        invoice_user=data["user"],
        settings=data["settings"],
    )


@app.route(
    "/bill_invoice/<int:bill_id>"
)
def bill_invoice_pdf(bill_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    bill, data = _get_bill_invoice_data(
        cursor,
        bill_id,
        session["user_id"]
    )

    conn.close()

    if not bill:
        return redirect("/bills")

    from invoice_service import (
        build_bill_invoice_pdf
    )

    buffer, filename, _ = (
        build_bill_invoice_pdf(
            bill,
            data["user"],
            data["settings"],
        )
    )

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )



@app.route("/bill_receipt/<int:bill_id>")
def bill_receipt(bill_id):
    """
    Backwards-compatible receipt URL.
    Paid-bill receipt downloads now use the professional
    Bill & Invoice Studio PDF generator.
    """
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM bills
        WHERE id=? AND user_id=?
        """,
        (
            bill_id,
            session["user_id"]
        )
    )

    bill = cursor.fetchone()
    conn.close()

    if not bill:
        return redirect("/bills")

    return redirect(
        f"/bill_invoice/{bill_id}"
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
        """
        INSERT INTO groups_table (user_id, group_name)
        VALUES (?, ?)
        RETURNING id
        """,
        (session["user_id"], request.form["group_name"])
    )
    new_group_id = cursor.fetchone()[0]

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
        INSERT INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'member')
        ON CONFLICT (group_id, user_id) DO NOTHING
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




# =========================================================
# MONTHLY BUDGETS
# =========================================================

@app.route("/budgets", methods=["GET", "POST"])
def budgets():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    categories = [
        "Food",
        "Travel",
        "Shopping",
        "Bills",
        "Entertainment",
        "Education"
    ]

    today = date.today()

    selected_month = (
        request.values.get("month")
        or today.strftime("%Y-%m")
    ).strip()

    try:
        year, month_number = map(
            int,
            selected_month.split("-")
        )

        month_start = date(
            year,
            month_number,
            1
        )

    except Exception:
        selected_month = today.strftime("%Y-%m")

        month_start = date(
            today.year,
            today.month,
            1
        )

    if month_start.month == 12:
        next_month = date(
            month_start.year + 1,
            1,
            1
        )
    else:
        next_month = date(
            month_start.year,
            month_start.month + 1,
            1
        )

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if request.method == "POST":
            category = str(
                request.form.get("category") or ""
            ).strip()

            try:
                monthly_limit = float(
                    request.form.get(
                        "monthly_limit"
                    ) or 0
                )
            except (TypeError, ValueError):
                monthly_limit = 0

            if category not in categories:
                session["budget_notice"] = (
                    "Please choose a valid category."
                )

                return redirect(
                    f"/budgets?month={selected_month}"
                )

            if monthly_limit <= 0:
                session["budget_notice"] = (
                    "Budget must be greater than ₹0."
                )

                return redirect(
                    f"/budgets?month={selected_month}"
                )

            cursor.execute(
                """
                INSERT INTO budgets (
                    user_id,
                    category,
                    monthly_limit,
                    month
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (user_id, category, month)
                DO UPDATE SET
                    monthly_limit = excluded.monthly_limit
                """,
                (
                    session["user_id"],
                    category,
                    monthly_limit,
                    selected_month
                )
            )

            conn.commit()

            session["budget_notice"] = (
                f"{category} budget saved."
            )

            return redirect(
                f"/budgets?month={selected_month}"
            )

        cursor.execute(
            """
            SELECT
                id,
                category,
                monthly_limit
            FROM budgets
            WHERE user_id = ?
              AND month = ?
            ORDER BY category
            """,
            (
                session["user_id"],
                selected_month
            )
        )

        budget_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                category,
                COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            GROUP BY category
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        spent_rows = cursor.fetchall()

        spent_map = {
            row[0]: float(row[1] or 0)
            for row in spent_rows
        }

        budget_items = []

        total_budget = 0.0
        total_spent = 0.0

        for row in budget_rows:
            budget_id = row[0]
            category = row[1]
            limit_value = float(row[2] or 0)

            spent = spent_map.get(
                category,
                0.0
            )

            percentage = (
                (spent / limit_value) * 100
                if limit_value > 0
                else 0
            )

            remaining = (
                limit_value - spent
            )

            if percentage >= 100:
                status = "over"
            elif percentage >= 80:
                status = "warning"
            else:
                status = "good"

            budget_items.append({
                "id": budget_id,
                "category": category,
                "limit": round(
                    limit_value,
                    2
                ),
                "spent": round(
                    spent,
                    2
                ),
                "remaining": round(
                    remaining,
                    2
                ),
                "percentage": round(
                    percentage,
                    1
                ),
                "bar_percentage": min(
                    percentage,
                    100
                ),
                "status": status
            })

            total_budget += limit_value
            total_spent += spent

        total_remaining = (
            total_budget - total_spent
        )

        total_percentage = (
            (total_spent / total_budget) * 100
            if total_budget > 0
            else 0
        )

        notice = session.pop(
            "budget_notice",
            None
        )

        return render_template(
            "budgets.html",
            categories=categories,
            selected_month=selected_month,
            budget_items=budget_items,
            total_budget=round(
                total_budget,
                2
            ),
            total_spent=round(
                total_spent,
                2
            ),
            total_remaining=round(
                total_remaining,
                2
            ),
            total_percentage=round(
                total_percentage,
                1
            ),
            notice=notice
        )

    finally:
        if conn:
            conn.close()


@app.route(
    "/budgets/delete/<int:budget_id>",
    methods=["POST"]
)
def delete_budget(budget_id):
    if "user_id" not in session:
        return redirect("/login")

    selected_month = (
        request.form.get("month")
        or ""
    ).strip()

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM budgets
            WHERE id = ?
              AND user_id = ?
            """,
            (
                budget_id,
                session["user_id"]
            )
        )

        conn.commit()

    finally:
        conn.close()

    session["budget_notice"] = (
        "Budget removed."
    )

    if selected_month:
        return redirect(
            f"/budgets?month={selected_month}"
        )

    return redirect("/budgets")





# =========================================================
# SAVINGS GOALS
# =========================================================

@app.route("/goals", methods=["GET", "POST"])
def savings_goals():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if request.method == "POST":
            name = str(
                request.form.get("name") or ""
            ).strip()

            try:
                target_amount = float(
                    request.form.get("target_amount") or 0
                )
            except (TypeError, ValueError):
                target_amount = 0

            try:
                saved_amount = float(
                    request.form.get("saved_amount") or 0
                )
            except (TypeError, ValueError):
                saved_amount = 0

            target_date_text = str(
                request.form.get("target_date") or ""
            ).strip()

            try:
                target_date = date.fromisoformat(
                    target_date_text
                )
            except ValueError:
                target_date = None

            if not name:
                session["goal_notice"] = (
                    "Enter a goal name."
                )
                return redirect("/goals")

            if target_amount <= 0:
                session["goal_notice"] = (
                    "Target amount must be greater than ₹0."
                )
                return redirect("/goals")

            if saved_amount < 0:
                session["goal_notice"] = (
                    "Saved amount cannot be negative."
                )
                return redirect("/goals")

            if saved_amount > target_amount:
                saved_amount = target_amount

            if not target_date:
                session["goal_notice"] = (
                    "Choose a valid target date."
                )
                return redirect("/goals")

            cursor.execute(
                """
                INSERT INTO savings_goals (
                    user_id,
                    name,
                    target_amount,
                    saved_amount,
                    target_date
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    name,
                    target_amount,
                    saved_amount,
                    target_date.isoformat()
                )
            )

            conn.commit()

            session["goal_notice"] = (
                f"{name} goal created."
            )

            return redirect("/goals")

        cursor.execute(
            """
            SELECT
                id,
                name,
                target_amount,
                saved_amount,
                target_date
            FROM savings_goals
            WHERE user_id = ?
            ORDER BY target_date ASC, id DESC
            """,
            (
                session["user_id"],
            )
        )

        rows = cursor.fetchall()

        today = date.today()

        goals = []

        total_target = 0.0
        total_saved = 0.0

        for row in rows:
            goal_id = row[0]
            name = row[1]
            target_amount = float(row[2] or 0)
            saved_amount = float(row[3] or 0)

            try:
                target_date = date.fromisoformat(
                    str(row[4])
                )
            except ValueError:
                target_date = today

            remaining = max(
                target_amount - saved_amount,
                0
            )

            progress = (
                (saved_amount / target_amount) * 100
                if target_amount > 0
                else 0
            )

            days_remaining = (
                target_date - today
            ).days

            month_difference = (
                (target_date.year - today.year) * 12
                + target_date.month
                - today.month
            )

            if (
                target_date.day > today.day
                and days_remaining > 0
            ):
                month_difference += 1

            months_remaining = max(
                month_difference,
                1
            )

            if remaining <= 0:
                monthly_required = 0
                status = "complete"

            elif days_remaining < 0:
                monthly_required = remaining
                status = "overdue"

            else:
                monthly_required = (
                    remaining / months_remaining
                )

                if progress >= 75:
                    status = "strong"
                elif progress >= 35:
                    status = "progress"
                else:
                    status = "starting"

            goals.append({
                "id": goal_id,
                "name": name,
                "target_amount": round(
                    target_amount,
                    2
                ),
                "saved_amount": round(
                    saved_amount,
                    2
                ),
                "remaining": round(
                    remaining,
                    2
                ),
                "progress": round(
                    progress,
                    1
                ),
                "bar_progress": min(
                    progress,
                    100
                ),
                "target_date": target_date.isoformat(),
                "days_remaining": days_remaining,
                "monthly_required": round(
                    monthly_required,
                    2
                ),
                "status": status
            })

            total_target += target_amount
            total_saved += saved_amount

        total_remaining = max(
            total_target - total_saved,
            0
        )

        overall_progress = (
            (total_saved / total_target) * 100
            if total_target > 0
            else 0
        )

        notice = session.pop(
            "goal_notice",
            None
        )

        return render_template(
            "goals.html",
            goals=goals,
            total_target=round(
                total_target,
                2
            ),
            total_saved=round(
                total_saved,
                2
            ),
            total_remaining=round(
                total_remaining,
                2
            ),
            overall_progress=round(
                overall_progress,
                1
            ),
            notice=notice
        )

    finally:
        if conn:
            conn.close()


@app.route(
    "/goals/<int:goal_id>/contribute",
    methods=["POST"]
)
def contribute_to_goal(goal_id):
    if "user_id" not in session:
        return redirect("/login")

    try:
        amount = float(
            request.form.get("amount") or 0
        )
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        session["goal_notice"] = (
            "Contribution must be greater than ₹0."
        )
        return redirect("/goals")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                target_amount,
                saved_amount,
                name
            FROM savings_goals
            WHERE id = ?
              AND user_id = ?
            """,
            (
                goal_id,
                session["user_id"]
            )
        )

        row = cursor.fetchone()

        if not row:
            session["goal_notice"] = (
                "Savings goal not found."
            )
            return redirect("/goals")

        target_amount = float(row[0] or 0)
        saved_amount = float(row[1] or 0)
        goal_name = row[2]

        new_saved_amount = min(
            target_amount,
            saved_amount + amount
        )

        cursor.execute(
            """
            UPDATE savings_goals
            SET saved_amount = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (
                new_saved_amount,
                goal_id,
                session["user_id"]
            )
        )

        conn.commit()

        if new_saved_amount >= target_amount:
            session["goal_notice"] = (
                f"{goal_name} completed 🎉"
            )
        else:
            session["goal_notice"] = (
                f"₹{amount:.2f} added to {goal_name}."
            )

    finally:
        conn.close()

    return redirect("/goals")


@app.route(
    "/goals/<int:goal_id>/delete",
    methods=["POST"]
)
def delete_savings_goal(goal_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM savings_goals
            WHERE id = ?
              AND user_id = ?
            """,
            (
                goal_id,
                session["user_id"]
            )
        )

        conn.commit()

    finally:
        conn.close()

    session["goal_notice"] = (
        "Savings goal removed."
    )

    return redirect("/goals")





# =========================================================
# SUBSCRIPTIONS
# =========================================================

@app.route("/subscriptions", methods=["GET", "POST"])
def subscriptions():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    categories = [
        "Entertainment",
        "Music",
        "Software",
        "Cloud",
        "Education",
        "Fitness",
        "News",
        "Other"
    ]

    conn = None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if request.method == "POST":
            name = str(
                request.form.get("name") or ""
            ).strip()

            try:
                amount = float(
                    request.form.get("amount") or 0
                )
            except (TypeError, ValueError):
                amount = 0

            billing_cycle = str(
                request.form.get("billing_cycle") or "monthly"
            ).strip().lower()

            category = str(
                request.form.get("category") or "Other"
            ).strip()

            next_renewal_text = str(
                request.form.get("next_renewal") or ""
            ).strip()

            try:
                next_renewal = date.fromisoformat(
                    next_renewal_text
                )
            except ValueError:
                next_renewal = None

            if not name:
                session["subscription_notice"] = (
                    "Enter a subscription name."
                )
                return redirect("/subscriptions")

            if amount <= 0:
                session["subscription_notice"] = (
                    "Subscription amount must be greater than ₹0."
                )
                return redirect("/subscriptions")

            if billing_cycle not in {"monthly", "yearly"}:
                session["subscription_notice"] = (
                    "Choose a valid billing cycle."
                )
                return redirect("/subscriptions")

            if category not in categories:
                category = "Other"

            if not next_renewal:
                session["subscription_notice"] = (
                    "Choose a valid renewal date."
                )
                return redirect("/subscriptions")

            cursor.execute(
                """
                INSERT INTO subscriptions (
                    user_id,
                    name,
                    amount,
                    billing_cycle,
                    category,
                    next_renewal,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    name,
                    amount,
                    billing_cycle,
                    category,
                    next_renewal.isoformat(),
                    "active"
                )
            )

            conn.commit()

            session["subscription_notice"] = (
                f"{name} subscription added."
            )

            return redirect("/subscriptions")

        cursor.execute(
            """
            SELECT
                id,
                name,
                amount,
                billing_cycle,
                category,
                next_renewal,
                status
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY next_renewal ASC, id DESC
            """,
            (
                session["user_id"],
            )
        )

        rows = cursor.fetchall()

        today = date.today()

        items = []

        monthly_total = 0.0
        annual_total = 0.0
        upcoming_count = 0
        active_count = 0

        for row in rows:
            subscription_id = row[0]
            name = row[1]
            amount = float(row[2] or 0)
            billing_cycle = row[3] or "monthly"
            category = row[4] or "Other"

            try:
                next_renewal = date.fromisoformat(
                    str(row[5])
                )
            except ValueError:
                next_renewal = today

            status = row[6] or "active"

            days_until = (
                next_renewal - today
            ).days

            if billing_cycle == "yearly":
                monthly_equivalent = amount / 12
                annual_cost = amount
            else:
                monthly_equivalent = amount
                annual_cost = amount * 12

            is_upcoming = (
                status == "active"
                and 0 <= days_until <= 7
            )

            is_overdue = (
                status == "active"
                and days_until < 0
            )

            if status == "active":
                monthly_total += monthly_equivalent
                annual_total += annual_cost
                active_count += 1

            if is_upcoming:
                upcoming_count += 1

            items.append({
                "id": subscription_id,
                "name": name,
                "amount": round(amount, 2),
                "billing_cycle": billing_cycle,
                "category": category,
                "next_renewal": next_renewal.isoformat(),
                "days_until": days_until,
                "monthly_equivalent": round(
                    monthly_equivalent,
                    2
                ),
                "annual_cost": round(
                    annual_cost,
                    2
                ),
                "status": status,
                "is_upcoming": is_upcoming,
                "is_overdue": is_overdue
            })

        notice = session.pop(
            "subscription_notice",
            None
        )

        return render_template(
            "subscriptions.html",
            subscriptions=items,
            categories=categories,
            monthly_total=round(
                monthly_total,
                2
            ),
            annual_total=round(
                annual_total,
                2
            ),
            active_count=active_count,
            upcoming_count=upcoming_count,
            notice=notice
        )

    finally:
        if conn:
            conn.close()


@app.route(
    "/subscriptions/<int:subscription_id>/toggle",
    methods=["POST"]
)
def toggle_subscription(subscription_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT status, name
            FROM subscriptions
            WHERE id = ?
              AND user_id = ?
            """,
            (
                subscription_id,
                session["user_id"]
            )
        )

        row = cursor.fetchone()

        if not row:
            session["subscription_notice"] = (
                "Subscription not found."
            )
            return redirect("/subscriptions")

        current_status = row[0]
        name = row[1]

        new_status = (
            "paused"
            if current_status == "active"
            else "active"
        )

        cursor.execute(
            """
            UPDATE subscriptions
            SET status = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (
                new_status,
                subscription_id,
                session["user_id"]
            )
        )

        conn.commit()

        session["subscription_notice"] = (
            f"{name} is now {new_status}."
        )

    finally:
        conn.close()

    return redirect("/subscriptions")


@app.route(
    "/subscriptions/<int:subscription_id>/delete",
    methods=["POST"]
)
def delete_subscription(subscription_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM subscriptions
            WHERE id = ?
              AND user_id = ?
            """,
            (
                subscription_id,
                session["user_id"]
            )
        )

        conn.commit()

    finally:
        conn.close()

    session["subscription_notice"] = (
        "Subscription removed."
    )

    return redirect("/subscriptions")





# =========================================================
# FINANCIAL REPORTS
# =========================================================

@app.route("/reports")
def financial_reports():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    today = date.today()

    selected_month = str(
        request.args.get("month")
        or today.strftime("%Y-%m")
    ).strip()

    try:
        year, month_number = map(
            int,
            selected_month.split("-")
        )

        month_start = date(
            year,
            month_number,
            1
        )

    except Exception:
        selected_month = today.strftime("%Y-%m")

        month_start = date(
            today.year,
            today.month,
            1
        )

    if month_start.month == 12:
        next_month = date(
            month_start.year + 1,
            1,
            1
        )
    else:
        next_month = date(
            month_start.year,
            month_start.month + 1,
            1
        )

    if month_start.month == 1:
        previous_month_start = date(
            month_start.year - 1,
            12,
            1
        )
    else:
        previous_month_start = date(
            month_start.year,
            month_start.month - 1,
            1
        )

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM income
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        total_income = float(
            cursor.fetchone()[0] or 0
        )

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        total_expense = float(
            cursor.fetchone()[0] or 0
        )

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM income
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                session["user_id"],
                previous_month_start.isoformat(),
                month_start.isoformat()
            )
        )

        previous_income = float(
            cursor.fetchone()[0] or 0
        )

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                session["user_id"],
                previous_month_start.isoformat(),
                month_start.isoformat()
            )
        )

        previous_expense = float(
            cursor.fetchone()[0] or 0
        )

        cursor.execute(
            """
            SELECT
                category,
                COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            GROUP BY category
            ORDER BY SUM(amount) DESC
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        category_rows = cursor.fetchall()

        category_breakdown = [
            {
                "category": row[0],
                "amount": round(
                    float(row[1] or 0),
                    2
                )
            }
            for row in category_rows
        ]

        top_category = (
            category_breakdown[0]
            if category_breakdown
            else None
        )

        cursor.execute(
            """
            SELECT
                id,
                amount,
                category,
                description,
                date
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            ORDER BY date DESC, id DESC
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        expense_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                id,
                amount,
                source,
                date
            FROM income
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            ORDER BY date DESC, id DESC
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        income_rows = cursor.fetchall()

        transactions = []

        for row in expense_rows:
            transactions.append({
                "id": row[0],
                "type": "Expense",
                "amount": round(
                    float(row[1] or 0),
                    2
                ),
                "label": row[2],
                "description": row[3] or "",
                "date": row[4]
            })

        for row in income_rows:
            transactions.append({
                "id": row[0],
                "type": "Income",
                "amount": round(
                    float(row[1] or 0),
                    2
                ),
                "label": row[2],
                "description": "",
                "date": row[3]
            })

        transactions.sort(
            key=lambda item: (
                str(item["date"]),
                item["id"]
            ),
            reverse=True
        )

        try:
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(monthly_limit), 0)
                FROM budgets
                WHERE user_id = ?
                  AND month = ?
                """,
                (
                    session["user_id"],
                    selected_month
                )
            )

            total_budget = float(
                cursor.fetchone()[0] or 0
            )

        except Exception:
            total_budget = 0.0

        try:
            cursor.execute(
                """
                SELECT
                    COALESCE(
                        SUM(
                            CASE
                                WHEN billing_cycle = 'yearly'
                                THEN amount / 12.0
                                ELSE amount
                            END
                        ),
                        0
                    )
                FROM subscriptions
                WHERE user_id = ?
                  AND status = 'active'
                """,
                (
                    session["user_id"],
                )
            )

            subscription_monthly = float(
                cursor.fetchone()[0] or 0
            )

        except Exception:
            subscription_monthly = 0.0

        savings = (
            total_income - total_expense
        )

        savings_rate = (
            (savings / total_income) * 100
            if total_income > 0
            else 0
        )

        budget_usage = (
            (total_expense / total_budget) * 100
            if total_budget > 0
            else 0
        )

        subscription_burden = (
            (subscription_monthly / total_income) * 100
            if total_income > 0
            else 0
        )

        def percentage_change(
            current,
            previous
        ):
            if previous == 0:
                if current == 0:
                    return 0

                return 100

            return (
                (current - previous)
                / previous
            ) * 100

        income_change = percentage_change(
            total_income,
            previous_income
        )

        expense_change = percentage_change(
            total_expense,
            previous_expense
        )

        report_health = "good"

        if savings < 0:
            report_health = "danger"

        elif savings_rate < 10:
            report_health = "warning"

        return render_template(
            "reports.html",
            selected_month=selected_month,
            total_income=round(
                total_income,
                2
            ),
            total_expense=round(
                total_expense,
                2
            ),
            savings=round(
                savings,
                2
            ),
            savings_rate=round(
                savings_rate,
                1
            ),
            total_budget=round(
                total_budget,
                2
            ),
            budget_usage=round(
                budget_usage,
                1
            ),
            subscription_monthly=round(
                subscription_monthly,
                2
            ),
            subscription_burden=round(
                subscription_burden,
                1
            ),
            income_change=round(
                income_change,
                1
            ),
            expense_change=round(
                expense_change,
                1
            ),
            category_breakdown=category_breakdown,
            top_category=top_category,
            transactions=transactions[:50],
            report_health=report_health
        )

    finally:
        conn.close()


@app.route("/reports/export.csv")
def export_financial_report_csv():
    if "user_id" not in session:
        return redirect("/login")

    import csv
    import io
    from datetime import date
    from flask import Response

    selected_month = str(
        request.args.get("month")
        or date.today().strftime("%Y-%m")
    ).strip()

    try:
        year, month_number = map(
            int,
            selected_month.split("-")
        )

        month_start = date(
            year,
            month_number,
            1
        )

    except Exception:
        selected_month = (
            date.today().strftime("%Y-%m")
        )

        month_start = date(
            date.today().year,
            date.today().month,
            1
        )

    if month_start.month == 12:
        next_month = date(
            month_start.year + 1,
            1,
            1
        )
    else:
        next_month = date(
            month_start.year,
            month_start.month + 1,
            1
        )

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                date,
                amount,
                category,
                description
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            ORDER BY date DESC
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        expenses = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                date,
                amount,
                source
            FROM income
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            ORDER BY date DESC
            """,
            (
                session["user_id"],
                month_start.isoformat(),
                next_month.isoformat()
            )
        )

        incomes = cursor.fetchall()

    finally:
        conn.close()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Type",
        "Amount",
        "Category / Source",
        "Description"
    ])

    for row in incomes:
        writer.writerow([
            row[0],
            "Income",
            row[1],
            row[2],
            ""
        ])

    for row in expenses:
        writer.writerow([
            row[0],
            "Expense",
            row[1],
            row[2],
            row[3] or ""
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    response.headers[
        "Content-Disposition"
    ] = (
        f'attachment; filename="expense-manager-'
        f'{selected_month}-report.csv"'
    )

    return response





# =========================================================
# SMART TRANSACTION SEARCH
# =========================================================

@app.route("/search")
def transaction_search():
    if "user_id" not in session:
        return redirect("/login")

    query = str(
        request.args.get("q") or ""
    ).strip()

    transaction_type = str(
        request.args.get("type") or "all"
    ).strip().lower()

    category = str(
        request.args.get("category") or ""
    ).strip()

    date_from = str(
        request.args.get("from") or ""
    ).strip()

    date_to = str(
        request.args.get("to") or ""
    ).strip()

    try:
        min_amount = float(
            request.args.get("min_amount")
        ) if request.args.get("min_amount") else None
    except (TypeError, ValueError):
        min_amount = None

    try:
        max_amount = float(
            request.args.get("max_amount")
        ) if request.args.get("max_amount") else None
    except (TypeError, ValueError):
        max_amount = None

    if transaction_type not in {
        "all",
        "expense",
        "income"
    }:
        transaction_type = "all"

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT category
            FROM expenses
            WHERE user_id = ?
              AND category IS NOT NULL
              AND category != ''
            ORDER BY category
            """,
            (
                session["user_id"],
            )
        )

        categories = [
            row[0]
            for row in cursor.fetchall()
        ]

        results = []

        if transaction_type in {
            "all",
            "expense"
        }:
            expense_sql = """
                SELECT
                    id,
                    amount,
                    category,
                    description,
                    date
                FROM expenses
                WHERE user_id = ?
            """

            expense_params = [
                session["user_id"]
            ]

            if query:
                expense_sql += """
                    AND (
                        LOWER(COALESCE(category, ''))
                            LIKE ?
                        OR
                        LOWER(COALESCE(description, ''))
                            LIKE ?
                    )
                """

                search_term = (
                    f"%{query.lower()}%"
                )

                expense_params.extend([
                    search_term,
                    search_term
                ])

            if category:
                expense_sql += """
                    AND category = ?
                """

                expense_params.append(
                    category
                )

            if date_from:
                expense_sql += """
                    AND date >= ?
                """

                expense_params.append(
                    date_from
                )

            if date_to:
                expense_sql += """
                    AND date <= ?
                """

                expense_params.append(
                    date_to
                )

            if min_amount is not None:
                expense_sql += """
                    AND amount >= ?
                """

                expense_params.append(
                    min_amount
                )

            if max_amount is not None:
                expense_sql += """
                    AND amount <= ?
                """

                expense_params.append(
                    max_amount
                )

            expense_sql += """
                ORDER BY date DESC, id DESC
                LIMIT 200
            """

            cursor.execute(
                expense_sql,
                tuple(expense_params)
            )

            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "type": "expense",
                    "amount": round(
                        float(row[1] or 0),
                        2
                    ),
                    "title": row[2] or "Expense",
                    "description": row[3] or "",
                    "date": row[4],
                    "category": row[2] or "",
                    "source": ""
                })

        if transaction_type in {
            "all",
            "income"
        }:
            income_sql = """
                SELECT
                    id,
                    amount,
                    source,
                    date
                FROM income
                WHERE user_id = ?
            """

            income_params = [
                session["user_id"]
            ]

            if query:
                income_sql += """
                    AND LOWER(
                        COALESCE(source, '')
                    ) LIKE ?
                """

                income_params.append(
                    f"%{query.lower()}%"
                )

            if date_from:
                income_sql += """
                    AND date >= ?
                """

                income_params.append(
                    date_from
                )

            if date_to:
                income_sql += """
                    AND date <= ?
                """

                income_params.append(
                    date_to
                )

            if min_amount is not None:
                income_sql += """
                    AND amount >= ?
                """

                income_params.append(
                    min_amount
                )

            if max_amount is not None:
                income_sql += """
                    AND amount <= ?
                """

                income_params.append(
                    max_amount
                )

            income_sql += """
                ORDER BY date DESC, id DESC
                LIMIT 200
            """

            cursor.execute(
                income_sql,
                tuple(income_params)
            )

            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "type": "income",
                    "amount": round(
                        float(row[1] or 0),
                        2
                    ),
                    "title": row[2] or "Income",
                    "description": "",
                    "date": row[3],
                    "category": "",
                    "source": row[2] or ""
                })

        results.sort(
            key=lambda item: (
                str(item["date"]),
                item["id"]
            ),
            reverse=True
        )

        total_income = sum(
            item["amount"]
            for item in results
            if item["type"] == "income"
        )

        total_expense = sum(
            item["amount"]
            for item in results
            if item["type"] == "expense"
        )

        net_result = (
            total_income
            - total_expense
        )

        return render_template(
            "search.html",
            results=results,
            categories=categories,
            query=query,
            transaction_type=transaction_type,
            selected_category=category,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            result_count=len(results),
            total_income=round(
                total_income,
                2
            ),
            total_expense=round(
                total_expense,
                2
            ),
            net_result=round(
                net_result,
                2
            )
        )

    finally:
        conn.close()





# =========================================================
# RECURRING TRANSACTIONS
# =========================================================

def _advance_recurring_date(current_date, frequency):
    from datetime import date
    import calendar

    if frequency == "yearly":
        target_year = current_date.year + 1

        target_day = min(
            current_date.day,
            calendar.monthrange(
                target_year,
                current_date.month
            )[1]
        )

        return date(
            target_year,
            current_date.month,
            target_day
        )

    target_year = current_date.year
    target_month = current_date.month + 1

    if target_month == 13:
        target_month = 1
        target_year += 1

    target_day = min(
        current_date.day,
        calendar.monthrange(
            target_year,
            target_month
        )[1]
    )

    return date(
        target_year,
        target_month,
        target_day
    )


def process_due_recurring_transactions(user_id):
    from datetime import date

    today = date.today()

    conn = sqlite3.connect(DB_PATH)

    generated_count = 0

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                name,
                transaction_type,
                amount,
                category,
                source,
                description,
                frequency,
                next_run
            FROM recurring_transactions
            WHERE user_id = ?
              AND status = 'active'
            ORDER BY next_run ASC
            """,
            (
                user_id,
            )
        )

        rows = cursor.fetchall()

        for row in rows:
            recurring_id = row[0]
            name = row[1]
            transaction_type = row[2]
            amount = float(row[3] or 0)
            category = row[4] or ""
            source = row[5] or ""
            description = row[6] or ""
            frequency = row[7] or "monthly"

            try:
                next_run = date.fromisoformat(
                    str(row[8])
                )
            except ValueError:
                continue

            safety_counter = 0

            while (
                next_run <= today
                and safety_counter < 36
            ):
                if transaction_type == "expense":
                    cursor.execute(
                        """
                        INSERT INTO expenses (
                            amount,
                            category,
                            description,
                            date,
                            user_id
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            amount,
                            category,
                            description or name,
                            next_run.isoformat(),
                            user_id
                        )
                    )

                elif transaction_type == "income":
                    cursor.execute(
                        """
                        INSERT INTO income (
                            amount,
                            source,
                            date,
                            user_id
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            amount,
                            source or name,
                            next_run.isoformat(),
                            user_id
                        )
                    )

                else:
                    break

                generated_count += 1

                last_generated = next_run

                next_run = _advance_recurring_date(
                    next_run,
                    frequency
                )

                cursor.execute(
                    """
                    UPDATE recurring_transactions
                    SET
                        next_run = ?,
                        last_generated_at = ?
                    WHERE id = ?
                      AND user_id = ?
                    """,
                    (
                        next_run.isoformat(),
                        last_generated.isoformat(),
                        recurring_id,
                        user_id
                    )
                )

                safety_counter += 1

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return generated_count


@app.before_request
def run_recurring_transactions_once_daily():
    if "user_id" not in session:
        return

    if request.endpoint == "static":
        return

    from datetime import date

    today_key = date.today().isoformat()

    if session.get(
        "recurring_processed_date"
    ) == today_key:
        return

    try:
        process_due_recurring_transactions(
            session["user_id"]
        )

        session[
            "recurring_processed_date"
        ] = today_key

    except Exception as exc:
        print(
            "Recurring processing error:",
            type(exc).__name__,
            str(exc)
        )


@app.route(
    "/recurring",
    methods=["GET", "POST"]
)
def recurring_transactions():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    categories = [
        "Food",
        "Travel",
        "Shopping",
        "Bills",
        "Entertainment",
        "Education",
        "Rent",
        "EMI",
        "Other"
    ]

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        if request.method == "POST":
            name = str(
                request.form.get("name") or ""
            ).strip()

            transaction_type = str(
                request.form.get(
                    "transaction_type"
                ) or ""
            ).strip().lower()

            try:
                amount = float(
                    request.form.get("amount") or 0
                )
            except (TypeError, ValueError):
                amount = 0

            category = str(
                request.form.get("category") or ""
            ).strip()

            source = str(
                request.form.get("source") or ""
            ).strip()

            description = str(
                request.form.get("description") or ""
            ).strip()

            frequency = str(
                request.form.get("frequency")
                or "monthly"
            ).strip().lower()

            next_run_text = str(
                request.form.get("next_run") or ""
            ).strip()

            try:
                next_run = date.fromisoformat(
                    next_run_text
                )
            except ValueError:
                next_run = None

            if not name:
                session["recurring_notice"] = (
                    "Enter a schedule name."
                )
                return redirect("/recurring")

            if transaction_type not in {
                "expense",
                "income"
            }:
                session["recurring_notice"] = (
                    "Choose Income or Expense."
                )
                return redirect("/recurring")

            if amount <= 0:
                session["recurring_notice"] = (
                    "Amount must be greater than ₹0."
                )
                return redirect("/recurring")

            if frequency not in {
                "monthly",
                "yearly"
            }:
                session["recurring_notice"] = (
                    "Choose a valid frequency."
                )
                return redirect("/recurring")

            if not next_run:
                session["recurring_notice"] = (
                    "Choose the first transaction date."
                )
                return redirect("/recurring")

            if (
                transaction_type == "expense"
                and not category
            ):
                session["recurring_notice"] = (
                    "Choose an expense category."
                )
                return redirect("/recurring")

            if (
                transaction_type == "income"
                and not source
            ):
                session["recurring_notice"] = (
                    "Enter an income source."
                )
                return redirect("/recurring")

            cursor.execute(
                """
                INSERT INTO recurring_transactions (
                    user_id,
                    name,
                    transaction_type,
                    amount,
                    category,
                    source,
                    description,
                    frequency,
                    next_run,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    name,
                    transaction_type,
                    amount,
                    category,
                    source,
                    description,
                    frequency,
                    next_run.isoformat(),
                    "active"
                )
            )

            conn.commit()

            session["recurring_notice"] = (
                f"{name} recurring schedule created."
            )

            session.pop(
                "recurring_processed_date",
                None
            )

            return redirect("/recurring")

        cursor.execute(
            """
            SELECT
                id,
                name,
                transaction_type,
                amount,
                category,
                source,
                description,
                frequency,
                next_run,
                status,
                last_generated_at
            FROM recurring_transactions
            WHERE user_id = ?
            ORDER BY
                CASE
                    WHEN status = 'active'
                    THEN 0
                    ELSE 1
                END,
                next_run ASC,
                id DESC
            """,
            (
                session["user_id"],
            )
        )

        rows = cursor.fetchall()

        today = date.today()

        items = []

        monthly_expenses = 0.0
        monthly_income = 0.0
        active_count = 0
        due_count = 0

        for row in rows:
            amount = float(row[3] or 0)

            frequency = (
                row[7] or "monthly"
            )

            monthly_equivalent = (
                amount / 12
                if frequency == "yearly"
                else amount
            )

            try:
                next_run = date.fromisoformat(
                    str(row[8])
                )
            except ValueError:
                next_run = today

            status = row[9] or "active"

            days_until = (
                next_run - today
            ).days

            if status == "active":
                active_count += 1

                if row[2] == "expense":
                    monthly_expenses += (
                        monthly_equivalent
                    )
                else:
                    monthly_income += (
                        monthly_equivalent
                    )

                if next_run <= today:
                    due_count += 1

            items.append({
                "id": row[0],
                "name": row[1],
                "transaction_type": row[2],
                "amount": round(
                    amount,
                    2
                ),
                "category": row[4] or "",
                "source": row[5] or "",
                "description": row[6] or "",
                "frequency": frequency,
                "next_run": next_run.isoformat(),
                "days_until": days_until,
                "status": status,
                "last_generated_at": (
                    row[10] or ""
                ),
                "monthly_equivalent": round(
                    monthly_equivalent,
                    2
                )
            })

        notice = session.pop(
            "recurring_notice",
            None
        )

        return render_template(
            "recurring.html",
            recurring_items=items,
            categories=categories,
            monthly_expenses=round(
                monthly_expenses,
                2
            ),
            monthly_income=round(
                monthly_income,
                2
            ),
            active_count=active_count,
            due_count=due_count,
            notice=notice
        )

    finally:
        conn.close()


@app.route(
    "/recurring/process",
    methods=["POST"]
)
def process_recurring_now():
    if "user_id" not in session:
        return redirect("/login")

    try:
        generated = (
            process_due_recurring_transactions(
                session["user_id"]
            )
        )

        session["recurring_notice"] = (
            f"{generated} transaction"
            f"{'' if generated == 1 else 's'} generated."
        )

        from datetime import date

        session[
            "recurring_processed_date"
        ] = date.today().isoformat()

    except Exception:
        session["recurring_notice"] = (
            "Unable to process recurring transactions."
        )

    return redirect("/recurring")


@app.route(
    "/recurring/<int:recurring_id>/toggle",
    methods=["POST"]
)
def toggle_recurring_transaction(recurring_id):
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                status,
                frequency,
                next_run,
                name
            FROM recurring_transactions
            WHERE id = ?
              AND user_id = ?
            """,
            (
                recurring_id,
                session["user_id"]
            )
        )

        row = cursor.fetchone()

        if not row:
            session["recurring_notice"] = (
                "Recurring schedule not found."
            )
            return redirect("/recurring")

        status = row[0]
        frequency = row[1] or "monthly"
        name = row[3]

        if status == "active":
            new_status = "paused"

            cursor.execute(
                """
                UPDATE recurring_transactions
                SET status = ?
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    new_status,
                    recurring_id,
                    session["user_id"]
                )
            )

        else:
            new_status = "active"

            try:
                next_run = date.fromisoformat(
                    str(row[2])
                )
            except ValueError:
                next_run = date.today()

            while next_run < date.today():
                next_run = _advance_recurring_date(
                    next_run,
                    frequency
                )

            cursor.execute(
                """
                UPDATE recurring_transactions
                SET
                    status = ?,
                    next_run = ?
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    new_status,
                    next_run.isoformat(),
                    recurring_id,
                    session["user_id"]
                )
            )

        conn.commit()

        session["recurring_notice"] = (
            f"{name} is now {new_status}."
        )

    finally:
        conn.close()

    session.pop(
        "recurring_processed_date",
        None
    )

    return redirect("/recurring")


@app.route(
    "/recurring/<int:recurring_id>/delete",
    methods=["POST"]
)
def delete_recurring_transaction(recurring_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM recurring_transactions
            WHERE id = ?
              AND user_id = ?
            """,
            (
                recurring_id,
                session["user_id"]
            )
        )

        conn.commit()

    finally:
        conn.close()

    session["recurring_notice"] = (
        "Recurring schedule deleted."
    )

    return redirect("/recurring")





# =========================================================
# FINANCIAL HEALTH SCORE
# =========================================================

@app.route("/api/financial-health")
def financial_health_api():
    if "user_id" not in session:
        return {
            "error": "Authentication required"
        }, 401

    from datetime import date

    user_id = session["user_id"]
    today = date.today()

    month_start = date(
        today.year,
        today.month,
        1
    )

    if today.month == 12:
        next_month = date(
            today.year + 1,
            1,
            1
        )
    else:
        next_month = date(
            today.year,
            today.month + 1,
            1
        )

    selected_month = today.strftime("%Y-%m")


    def safe_scalar(sql, params=(), default=0):
        conn = None

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute(
                sql,
                tuple(params)
            )

            row = cursor.fetchone()

            if not row:
                return default

            return row[0] if row[0] is not None else default

        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass

            return default

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


    total_income = float(
        safe_scalar(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM income
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                user_id,
                month_start.isoformat(),
                next_month.isoformat()
            )
        )
        or 0
    )


    total_expense = float(
        safe_scalar(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
              AND date >= ?
              AND date < ?
            """,
            (
                user_id,
                month_start.isoformat(),
                next_month.isoformat()
            )
        )
        or 0
    )


    total_budget = float(
        safe_scalar(
            """
            SELECT COALESCE(SUM(monthly_limit), 0)
            FROM budgets
            WHERE user_id = ?
              AND month = ?
            """,
            (
                user_id,
                selected_month
            )
        )
        or 0
    )


    subscription_monthly = float(
        safe_scalar(
            """
            SELECT COALESCE(
                SUM(
                    CASE
                        WHEN billing_cycle = 'yearly'
                        THEN amount / 12.0
                        ELSE amount
                    END
                ),
                0
            )
            FROM subscriptions
            WHERE user_id = ?
              AND status = 'active'
            """,
            (
                user_id,
            )
        )
        or 0
    )


    overdue_bills = int(
        safe_scalar(
            """
            SELECT COUNT(*)
            FROM bills
            WHERE user_id = ?
              AND due_date < ?
              AND LOWER(COALESCE(status, 'pending')) != 'paid'
            """,
            (
                user_id,
                today.isoformat()
            )
        )
        or 0
    )


    savings = (
        total_income
        - total_expense
    )


    savings_rate = (
        (savings / total_income) * 100
        if total_income > 0
        else 0
    )


    budget_usage = (
        (total_expense / total_budget) * 100
        if total_budget > 0
        else 0
    )


    subscription_burden = (
        (subscription_monthly / total_income) * 100
        if total_income > 0
        else (
            100
            if subscription_monthly > 0
            else 0
        )
    )


    # -------------------------
    # Savings score: max 40
    # -------------------------

    if total_income <= 0:
        savings_score = 10

    elif savings_rate >= 20:
        savings_score = 40

    elif savings_rate >= 10:
        savings_score = 32

    elif savings_rate >= 0:
        savings_score = 22

    else:
        savings_score = 5


    # -------------------------
    # Budget score: max 25
    # -------------------------

    if total_budget <= 0:
        budget_score = 15

    elif budget_usage <= 70:
        budget_score = 25

    elif budget_usage <= 85:
        budget_score = 21

    elif budget_usage <= 100:
        budget_score = 14

    else:
        budget_score = 4


    # -------------------------
    # Subscription score: 15
    # -------------------------

    if subscription_burden <= 5:
        subscription_score = 15

    elif subscription_burden <= 10:
        subscription_score = 12

    elif subscription_burden <= 20:
        subscription_score = 8

    else:
        subscription_score = 3


    # -------------------------
    # Bill score: max 20
    # -------------------------

    if overdue_bills == 0:
        bill_score = 20

    elif overdue_bills == 1:
        bill_score = 12

    elif overdue_bills == 2:
        bill_score = 7

    else:
        bill_score = 2


    score = round(
        savings_score
        + budget_score
        + subscription_score
        + bill_score
    )


    score = max(
        0,
        min(
            score,
            100
        )
    )


    if score >= 85:
        label = "Excellent"
        status = "excellent"

    elif score >= 70:
        label = "Good"
        status = "good"

    elif score >= 50:
        label = "Fair"
        status = "fair"

    else:
        label = "Needs attention"
        status = "poor"


    insights = []


    if total_income <= 0:
        insights.append(
            "Add this month's income for a more accurate score."
        )

    elif savings_rate < 0:
        insights.append(
            "Expenses are currently higher than income."
        )

    elif savings_rate < 10:
        insights.append(
            "Try moving your savings rate above 10%."
        )

    elif savings_rate >= 20:
        insights.append(
            "Your savings rate is strong this month."
        )


    if total_budget <= 0:
        insights.append(
            "Set monthly budgets to improve spending control."
        )

    elif budget_usage > 100:
        insights.append(
            "You have exceeded your monthly budget."
        )

    elif budget_usage >= 85:
        insights.append(
            "You are close to your monthly budget limit."
        )


    if subscription_burden > 15:
        insights.append(
            "Recurring subscriptions consume a high share of income."
        )


    if overdue_bills > 0:
        insights.append(
            f"{overdue_bills} overdue bill"
            f"{'' if overdue_bills == 1 else 's'} need attention."
        )

    elif len(insights) < 3:
        insights.append(
            "No overdue bills detected."
        )


    return {
        "score": score,
        "label": label,
        "status": status,
        "metrics": {
            "income": round(
                total_income,
                2
            ),
            "expense": round(
                total_expense,
                2
            ),
            "savings_rate": round(
                savings_rate,
                1
            ),
            "budget_usage": round(
                budget_usage,
                1
            ),
            "subscription_burden": round(
                subscription_burden,
                1
            ),
            "overdue_bills": overdue_bills
        },
        "insights": insights[:3]
    }





# =========================================================
# ABOUT EXPENSE MANAGER
# =========================================================

@app.route("/about")
def about_expense_manager():
    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "about.html"
    )




# =========================
# HEALTH CHECK
# =========================
@app.route("/health")
def health():
    return {"status": "ok"}, 200



# ============================================================
# AUTO EXPENSE SYNC ROUTES START
# ============================================================


# ============================================================
# GMAIL OAUTH CONFIGURATION
# ============================================================

GMAIL_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


def _google_oauth_client_config():
    """
    Build Google OAuth configuration from environment
    variables. Secrets are never stored in source code.
    """

    client_id = os.environ.get(
        "GOOGLE_CLIENT_ID"
    )

    client_secret = os.environ.get(
        "GOOGLE_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        raise RuntimeError(
            "Google OAuth credentials are not configured."
        )

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
        }
    }


def _gmail_oauth_callback_url():
    """
    Use whichever local hostname opened Expense Manager.

    127.0.0.1 -> 127.0.0.1 callback
    localhost -> localhost callback

    Both are already registered in Google Cloud.
    """

    return (
        request.host_url.rstrip("/")
        + "/connected_apps/gmail/callback"
    )


def _prepare_local_google_oauth():
    """
    OAuthlib normally expects HTTPS.

    Google explicitly permits HTTP localhost redirects
    during local development. Never enable insecure
    transport for production hosts.
    """

    hostname = request.host.split(":", 1)[0]

    if hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        os.environ[
            "OAUTHLIB_INSECURE_TRANSPORT"
        ] = "1"


def _integration_fernet():
    key = os.environ.get(
        "INTEGRATION_ENCRYPTION_KEY"
    )

    if not key:
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY "
            "is not configured."
        )

    try:
        return Fernet(
            key.encode("utf-8")
        )

    except Exception as exc:
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY "
            "is invalid."
        ) from exc


def _encrypt_integration_secret(value):
    if not value:
        return None

    return (
        _integration_fernet()
        .encrypt(
            value.encode("utf-8")
        )
        .decode("utf-8")
    )


def _decrypt_integration_secret(value):
    if not value:
        return None

    return (
        _integration_fernet()
        .decrypt(
            value.encode("utf-8")
        )
        .decode("utf-8")
    )


AUTO_SYNC_PROVIDERS = [
    {
        "id": "gmail",
        "name": "Gmail",
        "subtitle": "Purchase email connection",
        "method": "oauth",
        "mode": "Direct connection",
        "description": (
            "Securely scan purchase and receipt emails after "
            "Google authorization."
        ),
    },
    {
        "id": "amazon",
        "name": "Amazon",
        "subtitle": "Shopping orders",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Detect Amazon order confirmations, invoices "
            "and purchase totals."
        ),
    },
    {
        "id": "flipkart",
        "name": "Flipkart",
        "subtitle": "Shopping orders",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Import Flipkart purchases automatically from "
            "order and invoice emails."
        ),
    },
    {
        "id": "swiggy",
        "name": "Swiggy",
        "subtitle": "Food & Instamart",
        "method": "hybrid",
        "mode": "Direct + Email",
        "description": (
            "Prepare food and Instamart transactions for "
            "automatic expense tracking."
        ),
    },
    {
        "id": "zomato",
        "name": "Zomato",
        "subtitle": "Food delivery",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Detect restaurant orders and automatically "
            "categorize them as food expenses."
        ),
    },
    {
        "id": "blinkit",
        "name": "Blinkit",
        "subtitle": "Quick commerce",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Import grocery and quick-commerce order receipts."
        ),
    },
    {
        "id": "zepto",
        "name": "Zepto",
        "subtitle": "Quick commerce",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Detect Zepto purchase confirmations and totals."
        ),
    },
    {
        "id": "myntra",
        "name": "Myntra",
        "subtitle": "Fashion shopping",
        "method": "email",
        "mode": "Via Gmail",
        "description": (
            "Automatically identify fashion orders and "
            "shopping expenses."
        ),
    },
]



def _ensure_sync_activity_hidden_column():
    """
    Add reversible hide support to Sync Activity.
    Safe to call repeatedly on SQLite and PostgreSQL.
    """
    try:
        if sqlite3.column_exists(
            "integration_sync_activity",
            "hidden"
        ):
            return

        conn = sqlite3.connect(DB_PATH)

        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                ALTER TABLE integration_sync_activity
                ADD COLUMN hidden INTEGER DEFAULT 0
                """
            )

            conn.commit()

        finally:
            conn.close()

    except Exception as exc:
        print(
            "Sync activity hidden-column check:",
            type(exc).__name__,
            str(exc)[:200]
        )


@app.route("/connected_apps")
def connected_apps():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    _ensure_sync_activity_hidden_column()

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                provider,
                status,
                account_label,
                auth_method,
                auto_import_enabled,
                last_sync_at,
                connected_at
            FROM integration_connections
            WHERE user_id=?
            """,
            (user_id,)
        )

        connection_rows = cursor.fetchall()

        connection_map = {
            row[0]: {
                "status": row[1],
                "account_label": row[2],
                "auth_method": row[3],
                "auto_import_enabled": bool(row[4]),
                "last_sync_at": row[5],
                "connected_at": row[6],
            }
            for row in connection_rows
        }

        providers = []

        for provider in AUTO_SYNC_PROVIDERS:
            item = dict(provider)

            state = connection_map.get(
                provider["id"],
                {}
            )

            item["status"] = state.get(
                "status",
                "disconnected"
            )

            item["account_label"] = state.get(
                "account_label"
            )

            item["auto_import_enabled"] = state.get(
                "auto_import_enabled",
                True
            )

            item["last_sync_at"] = state.get(
                "last_sync_at"
            )

            providers.append(item)

        cursor.execute(
            """
            SELECT
                id,
                provider,
                merchant,
                amount,
                category,
                description,
                transaction_date,
                status,
                source_type,
                created_at
            FROM integration_sync_activity
            WHERE user_id=?
              AND COALESCE(hidden, 0)=0
            ORDER BY id DESC
            LIMIT 30
            """,
            (user_id,)
        )

        sync_activity = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                id,
                provider,
                merchant,
                amount,
                category,
                description,
                transaction_date,
                status,
                source_type,
                created_at
            FROM integration_sync_activity
            WHERE user_id=?
              AND COALESCE(hidden, 0)=1
            ORDER BY id DESC
            LIMIT 30
            """,
            (user_id,)
        )

        hidden_activity = cursor.fetchall()

    finally:
        conn.close()

    connected_count = sum(
        1
        for provider in providers
        if provider["status"] == "connected"
    )

    enabled_count = sum(
        1
        for provider in providers
        if provider["auto_import_enabled"]
    )

    gmail_connected = any(
        provider["id"] == "gmail"
        and provider["status"] == "connected"
        for provider in providers
    )

    return render_template(
        "connected_apps.html",
        providers=providers,
        sync_activity=sync_activity,
        hidden_activity=hidden_activity,
        connected_count=connected_count,
        enabled_count=enabled_count,
        gmail_connected=gmail_connected,
    )



# ============================================================
# SYNC ACTIVITY ACTIONS
# ============================================================

@app.route(
    "/connected_apps/activity/<int:activity_id>/hide",
    methods=["POST"]
)
def hide_connected_app_activity(activity_id):

    if "user_id" not in session:
        return redirect("/login")

    _ensure_sync_activity_hidden_column()

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE integration_sync_activity
            SET hidden=1
            WHERE id=?
              AND user_id=?
            """,
            (
                activity_id,
                session["user_id"],
            )
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(
        "/connected_apps#sync-activity"
    )


@app.route(
    "/connected_apps/activity/<int:activity_id>/restore",
    methods=["POST"]
)
def restore_connected_app_activity(activity_id):

    if "user_id" not in session:
        return redirect("/login")

    _ensure_sync_activity_hidden_column()

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE integration_sync_activity
            SET hidden=0
            WHERE id=?
              AND user_id=?
            """,
            (
                activity_id,
                session["user_id"],
            )
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(
        "/connected_apps#sync-activity"
    )


@app.route(
    "/connected_apps/activity/<int:activity_id>/delete",
    methods=["POST"]
)
def delete_connected_app_activity(activity_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM integration_sync_activity
            WHERE id=?
              AND user_id=?
            """,
            (
                activity_id,
                session["user_id"],
            )
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(
        "/connected_apps#sync-activity"
    )


@app.route(
    "/connected_apps/toggle/<provider>",
    methods=["POST"]
)
def toggle_connected_app(provider):
    if "user_id" not in session:
        return redirect("/login")

    valid_providers = {
        item["id"]
        for item in AUTO_SYNC_PROVIDERS
    }

    if provider not in valid_providers:
        abort(404)

    user_id = session["user_id"]

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, auto_import_enabled
            FROM integration_connections
            WHERE user_id=? AND provider=?
            """,
            (
                user_id,
                provider
            )
        )

        row = cursor.fetchone()

        if row:
            new_value = 0 if row[1] else 1

            cursor.execute(
                """
                UPDATE integration_connections
                SET
                    auto_import_enabled=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    new_value,
                    row[0]
                )
            )

        else:
            provider_config = next(
                item
                for item in AUTO_SYNC_PROVIDERS
                if item["id"] == provider
            )

            cursor.execute(
                """
                INSERT INTO integration_connections
                (
                    user_id,
                    provider,
                    status,
                    auth_method,
                    auto_import_enabled
                )
                VALUES (?, ?, 'disconnected', ?, 0)
                """,
                (
                    user_id,
                    provider,
                    provider_config["method"]
                )
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return redirect("/connected_apps")


# ============================================================
# GMAIL OAUTH
# ============================================================

@app.route("/connected_apps/gmail/setup")
def gmail_connection_setup():
    if "user_id" not in session:
        return redirect("/login")

    _prepare_local_google_oauth()

    try:
        flow = Flow.from_client_config(
            _google_oauth_client_config(),
            scopes=GMAIL_OAUTH_SCOPES,
            autogenerate_code_verifier=True,
        )

        flow.redirect_uri = (
            _gmail_oauth_callback_url()
        )

        authorization_url, state = (
            flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
        )

        # State protects the OAuth callback
        # against forged requests.
        session["gmail_oauth_state"] = state

        # PKCE: Google receives the challenge during
        # authorization. We must send the matching verifier
        # when exchanging the returned authorization code.
        session["gmail_oauth_code_verifier"] = (
            flow.code_verifier
        )

        return redirect(
            authorization_url
        )

    except Exception as exc:
        print(
            "Gmail OAuth setup error:",
            type(exc).__name__
        )

        return redirect(
            "/connected_apps"
            "?gmail_error=configuration"
        )


@app.route("/connected_apps/gmail/callback")
def gmail_oauth_callback():
    if "user_id" not in session:
        return redirect("/login")

    _prepare_local_google_oauth()

    # User may deny access on Google's screen.
    oauth_error = request.args.get("error")

    if oauth_error:
        session.pop(
            "gmail_oauth_state",
            None
        )

        session.pop(
            "gmail_oauth_code_verifier",
            None
        )

        return redirect(
            "/connected_apps"
            "?gmail_error=denied"
        )

    expected_state = session.pop(
        "gmail_oauth_state",
        None
    )

    code_verifier = session.pop(
        "gmail_oauth_code_verifier",
        None
    )

    returned_state = request.args.get(
        "state",
        ""
    )

    if (
        not expected_state
        or not returned_state
        or not secrets.compare_digest(
            expected_state,
            returned_state
        )
    ):
        abort(
            400,
            description="Invalid OAuth state."
        )

    if not code_verifier:
        print(
            "Gmail OAuth callback error:",
            "Missing stored PKCE code verifier"
        )

        return redirect(
            "/connected_apps"
            "?gmail_error=pkce"
        )

    try:
        flow = Flow.from_client_config(
            _google_oauth_client_config(),
            scopes=GMAIL_OAUTH_SCOPES,
            state=expected_state,
            code_verifier=code_verifier,
        )

        flow.redirect_uri = (
            _gmail_oauth_callback_url()
        )

        flow.fetch_token(
            authorization_response=request.url
        )

        credentials = flow.credentials

        # ----------------------------------------------------
        # Get the Gmail account address
        # ----------------------------------------------------

        gmail_service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        profile = (
            gmail_service
            .users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_address = profile.get(
            "emailAddress"
        )

        if not gmail_address:
            raise RuntimeError(
                "Google did not return "
                "a Gmail address."
            )

        # ----------------------------------------------------
        # We specifically requested offline access because
        # automatic sync later needs a refresh token.
        # ----------------------------------------------------

        refresh_token = (
            credentials.refresh_token
        )

        if not refresh_token:
            print(
                "Google OAuth did not return "
                "a refresh token."
            )

            return redirect(
                "/connected_apps"
                "?gmail_error=no_refresh_token"
            )

        encrypted_refresh_token = (
            _encrypt_integration_secret(
                refresh_token
            )
        )

        scopes_json = json.dumps(
            list(
                credentials.scopes
                or GMAIL_OAUTH_SCOPES
            )
        )

        user_id = session["user_id"]

        conn = sqlite3.connect(DB_PATH)

        try:
            cursor = conn.cursor()

            # ------------------------------------------------
            # Secure OAuth token storage
            # ------------------------------------------------

            cursor.execute(
                """
                INSERT INTO integration_oauth_tokens
                (
                    user_id,
                    provider,
                    encrypted_refresh_token,
                    scopes,
                    updated_at
                )
                VALUES (?, 'gmail', ?, ?, CURRENT_TIMESTAMP)

                ON CONFLICT(user_id, provider)
                DO UPDATE SET
                    encrypted_refresh_token=
                        excluded.encrypted_refresh_token,
                    scopes=excluded.scopes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    encrypted_refresh_token,
                    scopes_json,
                )
            )

            # ------------------------------------------------
            # Update Connected Apps status
            # ------------------------------------------------

            cursor.execute(
                """
                INSERT INTO integration_connections
                (
                    user_id,
                    provider,
                    status,
                    account_label,
                    auth_method,
                    auto_import_enabled,
                    connected_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    'gmail',
                    'connected',
                    ?,
                    'oauth',
                    1,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )

                ON CONFLICT(user_id, provider)
                DO UPDATE SET
                    status='connected',
                    account_label=excluded.account_label,
                    auth_method='oauth',
                    auto_import_enabled=1,
                    connected_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    gmail_address,
                )
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        return redirect(
            "/connected_apps"
            "?gmail_connected=1"
        )

    except Exception as exc:
        print(
            "Gmail OAuth callback error:",
            type(exc).__name__,
            str(exc)[:250]
        )

        return redirect(
            "/connected_apps"
            "?gmail_error=callback"
        )




# ============================================================
# GMAIL PURCHASE SCANNER
# ============================================================

GMAIL_PURCHASE_SEARCH_QUERY = (
    'from:noreply@zomato.com '
    'subject:"Your Zomato order from"'
)


TRUSTED_PURCHASE_SENDERS = {
    "zomato": {
        "noreply@zomato.com",
    },
}


def _trusted_purchase_message(
    provider,
    sender,
    subject
):
    """
    Final safety gate before an email can become an expense.

    Sender must be explicitly trusted and the subject must
    match a verified transaction-email format.
    """

    address = (
        parseaddr(sender or "")[1]
        .strip()
        .lower()
    )

    subject_lower = (
        subject
        or ""
    ).strip().lower()

    trusted_senders = (
        TRUSTED_PURCHASE_SENDERS.get(
            provider,
            set()
        )
    )

    if address not in trusted_senders:
        return False

    if provider == "zomato":
        return subject_lower.startswith(
            "your zomato order from "
        )

    return False


AUTO_SYNC_MERCHANTS = {
    "amazon": {
        "merchant": "Amazon",
        "category": "Shopping",
        "keywords": (
            "amazon",
        ),
    },

    "flipkart": {
        "merchant": "Flipkart",
        "category": "Shopping",
        "keywords": (
            "flipkart",
        ),
    },

    "swiggy": {
        "merchant": "Swiggy",
        "category": "Food",
        "keywords": (
            "swiggy",
        ),
    },

    "zomato": {
        "merchant": "Zomato",
        "category": "Food",
        "keywords": (
            "zomato",
        ),
    },

    "blinkit": {
        "merchant": "Blinkit",
        "category": "Shopping",
        "keywords": (
            "blinkit",
            "grofers",
        ),
    },

    "zepto": {
        "merchant": "Zepto",
        "category": "Shopping",
        "keywords": (
            "zepto",
            "zeptonow",
        ),
    },

    "myntra": {
        "merchant": "Myntra",
        "category": "Shopping",
        "keywords": (
            "myntra",
        ),
    },
}


GMAIL_NON_PURCHASE_SUBJECT_TERMS = (
    "shipped",
    "out for delivery",
    "delivered",
    "delivery update",
    "refund",
    "refunded",
    "return initiated",
    "return accepted",
    "cancelled",
    "canceled",
)


GMAIL_PURCHASE_SUBJECT_TERMS = (
    "order confirmed",
    "order confirmation",
    "order placed",
    "your order",
    "thanks for your order",
    "payment successful",
    "payment received",
    "invoice",
    "receipt",
    "purchase",
)


def _gmail_sync_service(user_id):
    """
    Create an authenticated Gmail API client from the
    encrypted refresh token stored for this Expense Manager
    user.
    """

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT encrypted_refresh_token
            FROM integration_oauth_tokens
            WHERE user_id=?
            AND provider='gmail'
            """,
            (user_id,)
        )

        row = cursor.fetchone()

    finally:
        conn.close()

    if not row or not row[0]:
        raise RuntimeError(
            "Gmail is not connected."
        )

    refresh_token = (
        _decrypt_integration_secret(
            row[0]
        )
    )

    client_config = (
        _google_oauth_client_config()
        ["web"]
    )

    credentials = GoogleCredentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=client_config["token_uri"],
        client_id=client_config["client_id"],
        client_secret=client_config[
            "client_secret"
        ],
        scopes=GMAIL_OAUTH_SCOPES,
    )

    # Refresh immediately so authentication problems are
    # detected before scanning messages.
    credentials.refresh(
        GoogleAuthRequest()
    )

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def _gmail_decode_data(value):
    """
    Decode Gmail API base64url MIME body data safely.
    """

    if not value:
        return ""

    try:
        if isinstance(value, str):
            encoded = value.encode("ascii")

        elif isinstance(
            value,
            (bytes, bytearray)
        ):
            encoded = bytes(value)

        else:
            return ""

        # Gmail uses URL-safe Base64 and padding may
        # be omitted.
        encoded += (
            b"="
            * (-len(encoded) % 4)
        )

        raw = base64.urlsafe_b64decode(
            encoded
        )

        return raw.decode(
            "utf-8",
            errors="replace"
        )

    except Exception as exc:
        print(
            "Gmail body decode error:",
            type(exc).__name__
        )

        return ""


def _gmail_extract_text_from_part(part):
    """
    Recursively collect text/plain and text/html content.

    Attachments are intentionally ignored.
    """

    if not part:
        return ""

    mime_type = (
        part.get("mimeType")
        or ""
    ).lower()

    body = part.get("body") or {}

    chunks = []

    if mime_type in {
        "text/plain",
        "text/html",
    }:

        data = body.get("data")

        if data:
            chunks.append(
                _gmail_decode_data(data)
            )

    for child in (
        part.get("parts")
        or []
    ):
        chunks.append(
            _gmail_extract_text_from_part(
                child
            )
        )

    return "\n".join(
        chunk
        for chunk in chunks
        if chunk
    )


def _gmail_clean_message_text(value):
    """
    Convert email HTML/plain content into compact text
    suitable for merchant and amount extraction.
    """

    value = value or ""

    value = re.sub(
        r"(?is)<script.*?>.*?</script>",
        " ",
        value
    )

    value = re.sub(
        r"(?is)<style.*?>.*?</style>",
        " ",
        value
    )

    value = re.sub(
        r"(?s)<[^>]+>",
        " ",
        value
    )

    value = unescape(value)

    value = re.sub(
        r"[ \t\r\f\v]+",
        " ",
        value
    )

    value = re.sub(
        r"\n{3,}",
        "\n\n",
        value
    )

    return value.strip()


def _gmail_headers(message):
    headers = {}

    payload = (
        message.get("payload")
        or {}
    )

    for header in (
        payload.get("headers")
        or []
    ):

        name = (
            header.get("name")
            or ""
        ).lower()

        value = (
            header.get("value")
            or ""
        )

        if name:
            headers[name] = value

    return headers


def _detect_purchase_provider(
    sender,
    subject,
    body
):
    """
    Prefer sender/subject for merchant detection, then use
    a small body sample as fallback.
    """

    sender = (
        sender
        or ""
    ).lower()

    subject = (
        subject
        or ""
    ).lower()

    body_sample = (
        body
        or ""
    )[:5000].lower()

    strong_text = (
        sender
        + "\n"
        + subject
    )

    fallback_text = (
        strong_text
        + "\n"
        + body_sample
    )

    for provider, config in (
        AUTO_SYNC_MERCHANTS.items()
    ):

        for keyword in config[
            "keywords"
        ]:

            if keyword in strong_text:
                return provider

    for provider, config in (
        AUTO_SYNC_MERCHANTS.items()
    ):

        for keyword in config[
            "keywords"
        ]:

            if keyword in fallback_text:
                return provider

    return None


def _gmail_subject_looks_transactional(
    subject
):
    """
    Never default to True.

    Only subjects matching known transaction patterns are
    eligible for automatic expense creation.
    """

    subject_lower = (
        subject
        or ""
    ).strip().lower()

    if not subject_lower:
        return False

    non_purchase_terms = (
        "refund",
        "refunded",
        "cancelled",
        "canceled",
        "return initiated",
        "return accepted",
        "delivery update",
        "out for delivery",
    )

    if any(
        term in subject_lower
        for term in non_purchase_terms
    ):
        return False

    purchase_terms = (
        "your zomato order from ",
        "order confirmed",
        "order confirmation",
        "order placed",
        "thanks for your order",
        "payment successful",
        "payment received",
        "invoice",
        "receipt",
    )

    return any(
        term in subject_lower
        for term in purchase_terms
    )


def _extract_purchase_amount(text):
    """
    Extract the final amount actually paid.

    Priority:
    1. Total paid
    2. Amount paid / You paid
    3. Paid ₹...
    4. Grand total / Order total
    5. Standalone Total

    Standalone word boundaries prevent matching
    'subtotal'.
    """

    if not text:
        return None

    currency = (
        r"(?:₹|INR\s*|Rs\.?\s*)"
    )

    amount = (
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
    )

    patterns = [
        # Zomato newer format:
        # Total paid - ₹179.49
        rf"""
        \btotal\s+paid\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # Amount paid ₹...
        rf"""
        \bamount\s+paid\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # You paid ₹...
        rf"""
        \byou\s+paid\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # Zomato older format:
        # Paid ₹78.68
        rf"""
        \bpaid\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # Grand Total / Order Total
        rf"""
        \b(?:grand|order)\s+total\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # Other labelled totals
        rf"""
        \b(?:total\s+amount|
           amount\s+payable|
           payment\s+amount|
           bill\s+total)\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,

        # Standalone Total.
        # \b means this cannot match "subtotal".
        rf"""
        \btotal\b
        \s*[-:]?\s*
        {currency}
        {amount}
        """,
    ]

    flags = (
        re.IGNORECASE
        | re.VERBOSE
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=flags,
        )

        if not match:
            continue

        try:
            value = float(
                match.group(1)
                .replace(",", "")
            )

        except (TypeError, ValueError):
            continue

        if 0 < value < 10000000:
            return round(value, 2)

    return None


def _extract_order_id(
    provider,
    text
):
    """
    Extract a stable order identifier when possible.
    """

    value = text or ""

    # Amazon order format:
    # 123-1234567-1234567
    if provider == "amazon":

        match = re.search(
            r"\b\d{3}-\d{7}-\d{7}\b",
            value
        )

        if match:
            return match.group(0)

    # Flipkart order format commonly begins with OD.
    if provider == "flipkart":

        match = re.search(
            r"\bOD\d{10,25}\b",
            value,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(0)

    # Generic order-number patterns used by food /
    # quick-commerce providers.
    pattern = r"""
        \border
        (?:\s*(?:id|number|no\.?))?
        \s*[:#-]\s*
        ([A-Z0-9][A-Z0-9_-]{5,35})
    """

    match = re.search(
        pattern,
        value,
        flags=(
            re.IGNORECASE
            | re.VERBOSE
        )
    )

    if match:

        candidate = (
            match.group(1)
            .strip()
        )

        # Avoid accidentally treating normal words as IDs.
        if any(
            character.isdigit()
            for character in candidate
        ):
            return candidate

    return None


def _gmail_message_date(message):
    """
    Gmail internalDate is milliseconds since epoch.
    """

    internal_date = (
        message.get("internalDate")
    )

    if internal_date:

        try:
            return datetime.fromtimestamp(
                int(internal_date)
                / 1000
            ).strftime(
                "%Y-%m-%d"
            )

        except (
            TypeError,
            ValueError,
            OSError
        ):
            pass

    return date.today().strftime(
        "%Y-%m-%d"
    )


def _provider_auto_import_enabled(
    cursor,
    user_id,
    provider
):
    """
    No preference row means enabled, matching the Connected
    Apps UI default.
    """

    cursor.execute(
        """
        SELECT auto_import_enabled
        FROM integration_connections
        WHERE user_id=?
        AND provider=?
        """,
        (
            user_id,
            provider,
        )
    )

    row = cursor.fetchone()

    if not row:
        return True

    return bool(row[0])


def _gmail_activity_exists(
    cursor,
    user_id,
    provider,
    external_id
):

    cursor.execute(
        """
        SELECT 1
        FROM integration_sync_activity
        WHERE user_id=?
        AND provider=?
        AND external_id=?
        LIMIT 1
        """,
        (
            user_id,
            provider,
            external_id,
        )
    )

    return (
        cursor.fetchone()
        is not None
    )






# ============================================================
# AUTOMATIC GMAIL SYNC
# ============================================================

def _gmail_auto_sync_due(user_id, hours=6):
    """
    Return True only when Gmail is connected, automatic
    importing is enabled, and the previous sync is older
    than the configured interval.
    """

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                status,
                auto_import_enabled,
                last_sync_at
            FROM integration_connections
            WHERE user_id=?
            AND provider='gmail'
            LIMIT 1
            """,
            (user_id,)
        )

        row = cursor.fetchone()

    finally:
        conn.close()

    if not row:
        return False

    status = row[0]
    auto_enabled = bool(row[1])
    last_sync = row[2]

    if (
        status != "connected"
        or not auto_enabled
    ):
        return False

    if not last_sync:
        return True

    if isinstance(last_sync, datetime):
        last_sync_dt = last_sync

    else:
        value = str(last_sync).strip()

        # PostgreSQL may return timezone information.
        # SQLite normally stores a simpler timestamp.
        value = value.replace(
            "Z",
            "+00:00"
        )

        try:
            last_sync_dt = (
                datetime.fromisoformat(value)
            )

        except ValueError:

            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ]

            last_sync_dt = None

            for fmt in formats:
                try:
                    last_sync_dt = (
                        datetime.strptime(
                            value,
                            fmt
                        )
                    )
                    break

                except ValueError:
                    continue

            if last_sync_dt is None:
                return True

    # Convert timezone-aware database values into a simple
    # UTC comparison.
    if last_sync_dt.tzinfo is not None:

        now = datetime.now(
            last_sync_dt.tzinfo
        )

    else:
        now = datetime.now()

    return (
        now - last_sync_dt
    ) >= timedelta(hours=hours)


@app.route(
    "/api/gmail/auto-sync",
    methods=["POST"]
)
def gmail_auto_sync():
    """
    Lightweight background endpoint called by the dashboard.

    Existing gmail_sync_purchases() performs the actual
    Gmail scan and retains duplicate protection.
    """

    if "user_id" not in session:
        return {
            "status": "unauthorized"
        }, 401

    user_id = session["user_id"]

    try:
        due = _gmail_auto_sync_due(
            user_id,
            hours=6
        )

    except Exception as exc:

        print(
            "Gmail auto-sync check error:",
            type(exc).__name__
        )

        return {
            "status": "error"
        }, 500

    if not due:
        return {
            "status": "skipped",
            "reason": "not_due"
        }, 200

    try:
        # Reuse the already-tested Gmail sync engine.
        gmail_sync_purchases()

        return {
            "status": "completed"
        }, 200

    except Exception as exc:

        print(
            "Gmail automatic sync error:",
            type(exc).__name__
        )

        return {
            "status": "error"
        }, 500





# ============================================================
# DISCONNECT GMAIL
# ============================================================

@app.route(
    "/connected_apps/gmail/disconnect",
    methods=["POST"]
)
def gmail_disconnect():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT encrypted_refresh_token
            FROM integration_oauth_tokens
            WHERE user_id=?
            AND provider='gmail'
            LIMIT 1
            """,
            (user_id,)
        )

        row = cursor.fetchone()

        refresh_token = None

        if row and row[0]:
            try:
                refresh_token = (
                    _decrypt_integration_secret(
                        row[0]
                    )
                )
            except Exception:
                refresh_token = None

        # ----------------------------------------------------
        # Revoke Google permission
        # ----------------------------------------------------

        if refresh_token:

            try:
                response = requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    data={
                        "token": refresh_token
                    },
                    headers={
                        "Content-Type":
                        "application/x-www-form-urlencoded"
                    },
                    timeout=10,
                )

                print(
                    "Google OAuth revoke:",
                    response.status_code
                )

            except Exception as exc:
                # Local disconnect still proceeds.
                print(
                    "Google OAuth revoke error:",
                    type(exc).__name__
                )

        # ----------------------------------------------------
        # Permanently remove stored token
        # ----------------------------------------------------

        cursor.execute(
            """
            DELETE FROM integration_oauth_tokens
            WHERE user_id=?
            AND provider='gmail'
            """,
            (user_id,)
        )

        cursor.execute(
            """
            UPDATE integration_connections
            SET
                status='disconnected',
                account_label=NULL,
                auto_import_enabled=0,
                last_sync_at=NULL,
                connected_at=NULL,
                updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?
            AND provider='gmail'
            """,
            (user_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:
        conn.close()

    session.pop(
        "gmail_oauth_state",
        None
    )

    session.pop(
        "gmail_oauth_code_verifier",
        None
    )

    return redirect(
        "/connected_apps"
        "?gmail_disconnected=1"
    )





# ============================================================
# GMAIL SYNC ENGINE START
# ============================================================

def _gmail_sync_decrypt_token(encrypted_value):
    """
    Decrypt the OAuth refresh token that was stored when
    Gmail was connected.
    """
    if not encrypted_value:
        return None

    return (
        _integration_fernet()
        .decrypt(
            encrypted_value.encode("utf-8")
        )
        .decode("utf-8")
    )


def _gmail_sync_message_body(payload):
    """
    Extract readable text from Gmail MIME payloads.
    """
    import base64
    from html import unescape

    if not payload:
        return ""

    collected = []

    mime_type = (
        payload.get("mimeType")
        or ""
    ).lower()

    body = payload.get("body") or {}
    data = body.get("data")

    if data and mime_type in {
        "text/plain",
        "text/html",
    }:
        try:
            padded = data + (
                "=" * (-len(data) % 4)
            )

            decoded = (
                base64.urlsafe_b64decode(
                    padded.encode("utf-8")
                )
                .decode(
                    "utf-8",
                    errors="ignore"
                )
            )

            if mime_type == "text/html":
                decoded = re.sub(
                    r"<script[\s\S]*?</script>",
                    " ",
                    decoded,
                    flags=re.I
                )

                decoded = re.sub(
                    r"<style[\s\S]*?</style>",
                    " ",
                    decoded,
                    flags=re.I
                )

                decoded = re.sub(
                    r"<[^>]+>",
                    " ",
                    decoded
                )

                decoded = unescape(decoded)

            collected.append(decoded)

        except Exception:
            pass

    for part in payload.get("parts") or []:
        child = _gmail_sync_message_body(part)

        if child:
            collected.append(child)

    return "\n".join(collected)


def _gmail_sync_headers(message):
    result = {}

    payload = (
        message.get("payload")
        or {}
    )

    for item in payload.get("headers") or []:
        name = (
            item.get("name")
            or ""
        ).strip().lower()

        value = (
            item.get("value")
            or ""
        ).strip()

        if name:
            result[name] = value

    return result


def _gmail_sync_provider(sender, subject, content=""):
    """
    Detect supported merchants using sender, subject,
    snippet and email body.
    """

    identity = (
        f"{sender}\n{subject}\n{content}"
    ).lower()

    rules = [
        (
            "amazon",
            (
                "amazon.in",
                "amazon.com",
                "@amazon",
                "amazon pay",
                "amazon order",
                "your amazon",
            )
        ),
        (
            "flipkart",
            (
                "flipkart",
                "ekart",
            )
        ),
        (
            "swiggy",
            (
                "swiggy",
                "instamart",
            )
        ),
        (
            "zomato",
            (
                "zomato",
            )
        ),
        (
            "blinkit",
            (
                "blinkit",
                "grofers",
            )
        ),
        (
            "zepto",
            (
                "zepto",
            )
        ),
        (
            "myntra",
            (
                "myntra",
            )
        ),
    ]

    for provider, keywords in rules:
        if any(
            keyword in identity
            for keyword in keywords
        ):
            return provider

    return None


def _gmail_sync_amount(text):
    """
    Detect a likely final paid/order total from common
    Indian ecommerce and food-delivery email formats.
    """

    if not text:
        return None

    cleaned = re.sub(
        r"\s+",
        " ",
        text
    )

    currency = r"(?:₹|rs\.?|inr)"

    labels = [
        r"grand\s*total",
        r"order\s*total",
        r"amount\s*paid",
        r"total\s*paid",
        r"you\s*paid",
        r"payment\s*amount",
        r"total\s*amount",
        r"final\s*amount",
        r"amount\s*payable",
        r"payable\s*amount",
        r"net\s*amount",
        r"order\s*value",
        r"total\s*value",
        r"bill\s*amount",
        r"invoice\s*total",
        r"paid\s*amount",
        r"total",
    ]

    for label in labels:

        patterns = [
            (
                rf"{label}"
                rf".{{0,70}}?"
                rf"{currency}\s*"
                rf"([\d,]+(?:\.\d{{1,2}})?)"
            ),

            (
                rf"{label}"
                rf".{{0,70}}?"
                rf"([\d,]+(?:\.\d{{1,2}})?)"
                rf"\s*{currency}"
            ),
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                cleaned,
                flags=re.I
            )

            if not match:
                continue

            try:
                amount = float(
                    match.group(1)
                    .replace(",", "")
                )

                if 1 <= amount <= 1000000:
                    return amount

            except (ValueError, TypeError):
                continue

    fallback_patterns = [
        (
            r"(?:paid|payment|charged|debited|payable|total)"
            r".{0,50}?"
            r"(?:₹|rs\.?|inr)\s*"
            r"([\d,]+(?:\.\d{1,2})?)"
        ),

        (
            r"(?:₹|rs\.?|inr)\s*"
            r"([\d,]+(?:\.\d{1,2})?)"
            r".{0,40}?"
            r"(?:paid|payment|charged|total)"
        ),
    ]

    for pattern in fallback_patterns:

        match = re.search(
            pattern,
            cleaned,
            flags=re.I
        )

        if not match:
            continue

        try:
            amount = float(
                match.group(1)
                .replace(",", "")
            )

            if 1 <= amount <= 1000000:
                return amount

        except (ValueError, TypeError):
            continue

    return None


def _gmail_sync_expense_date(date_header):
    from email.utils import parsedate_to_datetime

    if date_header:
        try:
            value = parsedate_to_datetime(
                date_header
            )

            return value.date().isoformat()

        except Exception:
            pass

    return datetime.now().date().isoformat()


def _gmail_sync_category(provider):
    categories = {
        "amazon": "Shopping",
        "flipkart": "Shopping",
        "myntra": "Shopping",

        "swiggy": "Food",
        "zomato": "Food",

        "blinkit": "Groceries",
        "zepto": "Groceries",
    }

    return categories.get(
        provider,
        "Shopping"
    )


def _gmail_sync_expense_columns(cursor):
    """
    Discover the real ExpenseManager expense table columns.
    Works without assuming SQLite-only PRAGMA statements.
    """

    cursor.execute(
        "SELECT * FROM expenses WHERE 1=0"
    )

    return [
        item[0]
        for item in cursor.description
    ]


def _gmail_sync_find_column(
    columns,
    *possibilities
):
    lookup = {
        str(column).lower(): column
        for column in columns
    }

    for possibility in possibilities:
        if possibility.lower() in lookup:
            return lookup[
                possibility.lower()
            ]

    return None


def _gmail_sync_insert_expense(
    cursor,
    columns,
    user_id,
    amount,
    category,
    expense_date,
    description
):
    """
    Insert into the existing ExpenseManager expenses table
    while respecting whichever common field names it uses.
    """

    user_column = _gmail_sync_find_column(
        columns,
        "user_id",
        "userid"
    )

    amount_column = _gmail_sync_find_column(
        columns,
        "amount",
        "expense_amount",
        "cost"
    )

    date_column = _gmail_sync_find_column(
        columns,
        "date",
        "expense_date",
        "spent_on"
    )

    category_column = _gmail_sync_find_column(
        columns,
        "category",
        "expense_category"
    )

    description_column = _gmail_sync_find_column(
        columns,
        "description",
        "note",
        "notes",
        "title",
        "expense_name",
        "name"
    )

    if not user_column:
        raise RuntimeError(
            "expenses table has no user_id column"
        )

    if not amount_column:
        raise RuntimeError(
            "expenses table has no amount column"
        )

    if not date_column:
        raise RuntimeError(
            "expenses table has no date column"
        )

    values = {
        user_column: user_id,
        amount_column: amount,
        date_column: expense_date,
    }

    if category_column:
        values[category_column] = category

    if description_column:
        values[description_column] = (
            description[:240]
        )

    insert_columns = list(
        values.keys()
    )

    placeholders = ", ".join(
        "?"
        for _ in insert_columns
    )

    quoted_columns = ", ".join(
        f'"{column}"'
        for column in insert_columns
    )

    sql = (
        f"INSERT INTO expenses "
        f"({quoted_columns}) "
        f"VALUES ({placeholders})"
    )

    cursor.execute(
        sql,
        tuple(
            values[column]
            for column in insert_columns
        )
    )


@app.route(
    "/connected_apps/gmail/sync",
    methods=["POST"]
)
def gmail_sync_expenses():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    # --------------------------------------------------------
    # Load encrypted refresh token
    # --------------------------------------------------------

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                encrypted_refresh_token,
                scopes
            FROM integration_oauth_tokens
            WHERE user_id=?
              AND provider='gmail'
            """,
            (user_id,)
        )

        token_row = cursor.fetchone()

        if not token_row:
            print(
                "Gmail sync:",
                "No stored OAuth token."
            )

            return redirect(
                "/connected_apps"
                "?gmail_sync_error=auth"
            )

        encrypted_refresh_token = (
            token_row[0]
        )

        stored_scopes = (
            token_row[1]
            if len(token_row) > 1
            else None
        )

        # Deduplication table.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS
            gmail_synced_messages
            (
                user_id INTEGER NOT NULL,
                gmail_message_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                amount REAL,
                synced_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY
                (
                    user_id,
                    gmail_message_id
                )
            )
            """
        )

        conn.commit()

        cursor.execute(
            """
            SELECT gmail_message_id
            FROM gmail_synced_messages
            WHERE user_id=?
            """,
            (user_id,)
        )

        already_synced = {
            row[0]
            for row in cursor.fetchall()
        }

    finally:
        conn.close()

    # --------------------------------------------------------
    # Rebuild Google OAuth credentials
    # --------------------------------------------------------

    try:
        from google.oauth2.credentials import (
            Credentials
        )

        from google.auth.transport.requests import (
            Request as GoogleAuthRequest
        )

        from googleapiclient.discovery import (
            build as google_build
        )

        refresh_token = (
            _gmail_sync_decrypt_token(
                encrypted_refresh_token
            )
        )

        if not refresh_token:
            raise RuntimeError(
                "Stored Gmail refresh token is empty."
            )

        scopes = GMAIL_OAUTH_SCOPES

        if stored_scopes:
            try:
                parsed_scopes = json.loads(
                    stored_scopes
                )

                if isinstance(
                    parsed_scopes,
                    list
                ):
                    scopes = parsed_scopes

            except Exception:
                pass

        client_config = (
            _google_oauth_client_config()
        )

        google_config = (
            client_config.get("web")
            or client_config.get("installed")
        )

        if not google_config:
            raise RuntimeError(
                "Google OAuth client configuration missing."
            )

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=google_config.get(
                "token_uri",
                "https://oauth2.googleapis.com/token"
            ),
            client_id=google_config[
                "client_id"
            ],
            client_secret=google_config[
                "client_secret"
            ],
            scopes=scopes,
        )

        # Verify refresh token immediately.
        credentials.refresh(
            GoogleAuthRequest()
        )

        gmail = google_build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

    except Exception as exc:
        print(
            "Gmail sync authentication error:",
            type(exc).__name__,
            str(exc)[:300]
        )

        return redirect(
            "/connected_apps"
            "?gmail_sync_error=auth"
        )

    # --------------------------------------------------------
    # Search recent purchase emails
    # --------------------------------------------------------

    try:

        # ----------------------------------------------------
        # Search EACH provider separately.
        #
        # A single combined Gmail query allowed providers with
        # many emails (for example Swiggy/Zomato) to dominate
        # the candidate list before Amazon/Flipkart/etc. were
        # ever processed.
        # ----------------------------------------------------

        provider_queries = {

            "amazon": (
                "newer_than:5y "
                "{amazon amazon.in amazon.com} "
                "{order invoice receipt payment paid "
                "purchase purchased shipped shipment delivered}"
            ),

            "flipkart": (
                "newer_than:5y "
                "{flipkart ekart} "
                "{order invoice receipt payment paid "
                "purchase shipped shipment delivered}"
            ),

            "swiggy": (
                "newer_than:5y "
                "{swiggy instamart} "
                "{order receipt payment paid "
                "delivered delivery invoice}"
            ),

            "zomato": (
                "newer_than:5y "
                "zomato "
                "{order receipt payment paid "
                "delivered delivery invoice}"
            ),

            "blinkit": (
                "newer_than:5y "
                "{blinkit grofers} "
                "{order receipt payment paid "
                "delivered delivery invoice}"
            ),

            "zepto": (
                "newer_than:5y "
                "zepto "
                "{order receipt payment paid "
                "delivered delivery invoice}"
            ),

            "myntra": (
                "newer_than:5y "
                "myntra "
                "{order invoice receipt payment paid "
                "purchase shipped shipment delivered}"
            ),
        }


        candidate_map = {}

        gmail_search_stats = {}


        for (
            search_provider,
            provider_query
        ) in provider_queries.items():

            provider_messages = []

            page_token = None


            while True:

                request_args = {
                    "userId": "me",
                    "q": provider_query,
                    "maxResults": 100,
                }

                if page_token:
                    request_args[
                        "pageToken"
                    ] = page_token


                response = (
                    gmail
                    .users()
                    .messages()
                    .list(
                        **request_args
                    )
                    .execute()
                )


                provider_messages.extend(
                    response.get(
                        "messages"
                    )
                    or []
                )


                page_token = response.get(
                    "nextPageToken"
                )


                if (
                    not page_token
                    or len(
                        provider_messages
                    ) >= 300
                ):
                    break


            provider_messages = (
                provider_messages[:300]
            )


            unsynced_provider_messages = [
                item
                for item
                in provider_messages
                if item.get("id")
                and item.get("id")
                    not in already_synced
            ]


            gmail_search_stats[
                search_provider
            ] = {
                "total":
                    len(provider_messages),

                "unsynced":
                    len(
                        unsynced_provider_messages
                    ),
            }


            # Give every platform its own share of the
            # processing batch instead of allowing one
            # provider to consume the entire limit.

            for item in (
                unsynced_provider_messages[:15]
            ):

                message_id = item.get(
                    "id"
                )

                if (
                    message_id
                    and message_id
                    not in candidate_map
                ):
                    candidate_map[
                        message_id
                    ] = item


        messages = list(
            candidate_map.values()
        )


        print(
            "Gmail provider search results:"
        )

        for (
            provider_name,
            stats
        ) in gmail_search_stats.items():

            print(
                f"  {provider_name}:",
                f"total={stats['total']}",
                f"unsynced={stats['unsynced']}"
            )


        print(
            "Gmail search:",
            f"processing={len(messages)}"
        )

    except Exception as exc:
        print(
            "Gmail message search error:",
            type(exc).__name__,
            str(exc)[:300]
        )

        return redirect(
            "/connected_apps"
            "?gmail_sync_error=search"
        )

    # --------------------------------------------------------
    # Parse candidate purchase emails
    # --------------------------------------------------------

    parsed_expenses = []

    provider_stats = {
        "amazon": {"found": 0, "amount": 0},
        "flipkart": {"found": 0, "amount": 0},
        "swiggy": {"found": 0, "amount": 0},
        "zomato": {"found": 0, "amount": 0},
        "blinkit": {"found": 0, "amount": 0},
        "zepto": {"found": 0, "amount": 0},
        "myntra": {"found": 0, "amount": 0},
    }

    for message_number, message_ref in enumerate(
        messages,
        start=1
    ):

        message_id = (
            message_ref.get("id")
        )

        if (
            message_number == 1
            or message_number % 10 == 0
            or message_number == len(messages)
        ):
            print(
                "Gmail sync progress:",
                f"{message_number}/{len(messages)}"
            )

        if not message_id:
            continue

        if message_id in already_synced:
            continue

        try:
            message = (
                gmail
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full",
                    fields="id,snippet,payload"
                )
                .execute()
            )

        except Exception as exc:
            print(
                "Skipping Gmail message:",
                message_id,
                type(exc).__name__
            )
            continue

        headers = _gmail_sync_headers(
            message
        )

        subject = headers.get(
            "subject",
            ""
        )

        sender = headers.get(
            "from",
            ""
        )

        body = _gmail_sync_message_body(
            message.get("payload") or {}
        )

        snippet = (
            message.get("snippet")
            or ""
        )

        searchable_text = (
            subject
            + "\n"
            + snippet
            + "\n"
            + body
        )

        provider = _gmail_sync_provider(
            sender,
            subject,
            searchable_text
        )

        if not provider:
            continue

        if provider in provider_stats:
            provider_stats[provider]["found"] += 1

        # Require purchase-like context.
        lowered = searchable_text.lower()

        if not any(
            keyword in lowered
            for keyword in (
                "order",
                "invoice",
                "receipt",
                "payment",
                "paid",
                "total",
                "purchase",
                "placed",
                "confirmed",
                "confirmation",
                "delivered",
                "delivery",
                "shipment",
                "shipped",
                "charged",
                "debited",
            )
        ):
            continue

        amount = _gmail_sync_amount(
            searchable_text
        )

        if amount is None:
            continue

        if provider in provider_stats:
            provider_stats[provider]["amount"] += 1

        expense_date = (
            _gmail_sync_expense_date(
                headers.get("date")
            )
        )

        category = (
            _gmail_sync_category(
                provider
            )
        )

        provider_name = (
            provider.capitalize()
        )

        clean_subject = re.sub(
            r"\s+",
            " ",
            subject
        ).strip()

        description = (
            f"{provider_name} email sync"
        )

        if clean_subject:
            description += (
                f" • {clean_subject}"
            )

        parsed_expenses.append(
            {
                "message_id": message_id,
                "provider": provider,
                "amount": amount,
                "category": category,
                "date": expense_date,
                "description": description,
            }
        )

    # --------------------------------------------------------
    # Save detected expenses
    # --------------------------------------------------------

    imported = 0

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        expense_columns = (
            _gmail_sync_expense_columns(
                cursor
            )
        )

        for item in parsed_expenses:

            # Double-check dedupe inside transaction.
            cursor.execute(
                """
                SELECT 1
                FROM gmail_synced_messages
                WHERE user_id=?
                  AND gmail_message_id=?
                """,
                (
                    user_id,
                    item["message_id"],
                )
            )

            if cursor.fetchone():
                continue

            _gmail_sync_insert_expense(
                cursor=cursor,
                columns=expense_columns,
                user_id=user_id,
                amount=item["amount"],
                category=item["category"],
                expense_date=item["date"],
                description=item["description"],
            )

            cursor.execute(
                """
                INSERT INTO gmail_synced_messages
                (
                    user_id,
                    gmail_message_id,
                    provider,
                    amount
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    item["message_id"],
                    item["provider"],
                    item["amount"],
                )
            )

            # ------------------------------------------------
            # Record successful Gmail import in Sync Activity
            # ------------------------------------------------

            activity_provider = item["provider"]

            activity_merchant = (
                activity_provider
                .replace("_", " ")
                .title()
            )

            activity_description = (
                item["description"]
            )

            cursor.execute(
                """
                SELECT 1
                FROM integration_sync_activity
                WHERE user_id=?
                  AND provider=?
                  AND amount=?
                  AND transaction_date=?
                  AND description=?
                LIMIT 1
                """,
                (
                    user_id,
                    activity_provider,
                    item["amount"],
                    item["date"],
                    activity_description,
                )
            )

            existing_activity = (
                cursor.fetchone()
            )

            if not existing_activity:

                cursor.execute(
                    """
                    INSERT INTO integration_sync_activity
                    (
                        user_id,
                        provider,
                        merchant,
                        amount,
                        category,
                        description,
                        transaction_date,
                        status,
                        source_type,
                        created_at
                    )
                    VALUES
                    (
                        ?, ?, ?, ?, ?, ?,
                        ?, 'imported',
                        'gmail',
                        CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        user_id,
                        activity_provider,
                        activity_merchant,
                        item["amount"],
                        item["category"],
                        activity_description,
                        item["date"],
                    )
                )

            imported += 1

        cursor.execute(
            """
            UPDATE integration_connections
            SET
                last_sync_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?
              AND provider='gmail'
            """,
            (user_id,)
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        print(
            "Gmail expense import error:",
            type(exc).__name__,
            str(exc)[:400]
        )

        return redirect(
            "/connected_apps"
            "?gmail_sync_error=import"
        )

    finally:
        conn.close()

    scanned = len(messages)

    skipped = max(
        scanned - imported,
        0
    )

    print(
        "Gmail sync completed:",
        f"scanned={scanned}",
        f"parsed={len(parsed_expenses)}",
        f"imported={imported}",
        f"skipped={skipped}",
    )

    print("Gmail provider diagnostics:")

    for provider_name, stats in provider_stats.items():
        print(
            f"  {provider_name}:",
            f"found={stats['found']}",
            f"amount_detected={stats['amount']}"
        )

    return redirect(
        "/connected_apps"
        f"?gmail_sync=1"
        f"&imported={imported}"
        f"&scanned={scanned}"
        f"&skipped={skipped}"
    )


# ============================================================
# GMAIL SYNC ENGINE END
# ============================================================


# ============================================================
# AUTO EXPENSE SYNC ROUTES END
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
