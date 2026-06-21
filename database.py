import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "expenses.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ================= USERS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    upi_id TEXT
)
""")

# ================= EXPENSES =================
# NOTE: column order below matches the REAL physical order confirmed via
# `sqlite3 expenses.db "PRAGMA table_info(expenses);"` on the live database:
#   id, amount, category, description, date, user_id
# user_id is listed last because it was added later via ALTER TABLE on an
# existing database -- SQLite always appends ALTER TABLE ADD COLUMN at the
# end, regardless of where it's written in CREATE TABLE. Writing it in this
# position here keeps this file honest about what's actually on disk, and
# keeps the safety check below a no-op for databases that already match.

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date TEXT NOT NULL,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= INCOME =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= GROUPS =================
# user_id here is the OWNER/creator of the group (kept for backwards
# compatibility with existing code/queries). Actual access control for
# "who can view/use this group" is handled by group_members below, so
# that more than one real user account can use a group.

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= GROUP MEMBERS (real user accounts) =================
# This is the access-control table: it links a real, logged-in user
# account to a group. A user can only see/use a group if a row exists
# here for (group_id, user_id). This is separate from the `members`
# table below, which is just the list of names used to split bills and
# does not by itself grant any login access.

cursor.execute("""
CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(group_id) REFERENCES groups_table(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    UNIQUE(group_id, user_id)
)
""")

# ================= MEMBERS =================
# Free-text split participants shown in "Add Shared Expense" / breakdown.
# user_id is OPTIONAL: it links a split participant to a real account
# once that person has been invited via group_members. If user_id is
# NULL, the member is just a name with no login access (e.g. a person
# being tracked for splitting purposes who doesn't use the app).

cursor.execute("""
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    member_name TEXT NOT NULL,
    user_id INTEGER,
    FOREIGN KEY(group_id) REFERENCES groups_table(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= SHARED EXPENSES =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS shared_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    description TEXT,
    amount REAL,
    paid_by TEXT,
    split_members TEXT
)
""")

# ================= SETTLEMENTS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    payer TEXT,
    receiver TEXT,
    amount REAL,
    settlement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ================= BILLS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    due_date TEXT NOT NULL,
    recurrence TEXT NOT NULL DEFAULT 'none',
    status TEXT NOT NULL DEFAULT 'pending',
    last_generated_date TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= PASSWORD RESETS =================
# Single-use, time-limited tokens for the "Forgot Password" email flow.
# A row is created when the user requests a reset; it's marked used=1
# the moment it's successfully redeemed so the same link can't be used
# twice, and expires_at enforces a time window even if it's never used.

cursor.execute("""
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

conn.commit()

# =====================================================
# SAFETY CHECK (does NOT modify data): add user_id to any
# expenses/income/groups_table/members that predate these columns,
# for installs that started from an even older schema version
# where these columns didn't exist anywhere yet. This only ADDS the
# column if missing -- it never reorders or rewrites existing
# rows, since reordering is unnecessary as long as every query
# in app.py reads columns by name (SELECT user_id, amount, ...)
# or unpacks SELECT * using the indices that match THIS file's
# column order above.
# =====================================================

def _column_exists(table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


for table in ("expenses", "income", "groups_table"):
    if not _column_exists(table, "user_id"):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")

if not _column_exists("members", "user_id"):
    cursor.execute("ALTER TABLE members ADD COLUMN user_id INTEGER")

if not _column_exists("users", "upi_id"):
    cursor.execute("ALTER TABLE users ADD COLUMN upi_id TEXT")

if not _column_exists("shared_expenses", "split_members"):
    cursor.execute("ALTER TABLE shared_expenses ADD COLUMN split_members TEXT")

conn.commit()

# =====================================================
# BACKFILL: make sure every existing group has its owner
# present in group_members with role='owner'. Without this,
# groups created before this feature existed would have NO
# row in group_members, which would lock the owner out under
# the new access-control checks.
# =====================================================

cursor.execute("SELECT id, user_id FROM groups_table WHERE user_id IS NOT NULL")
for group_id, owner_id in cursor.fetchall():
    cursor.execute(
        """
        INSERT OR IGNORE INTO group_members (group_id, user_id, role)
        VALUES (?, ?, 'owner')
        """,
        (group_id, owner_id)
    )

conn.commit()
conn.close()

print("Database created successfully")