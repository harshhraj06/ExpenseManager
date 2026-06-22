import os
import db_compat as sqlite3

# DATABASE_URL is provided automatically by Render once a PostgreSQL
# database is created and linked to this web service (Render injects it
# as an environment variable). This is what replaces the old local
# expenses.db file -- Postgres data lives in Render's managed database
# service, completely independent of the web service's own filesystem,
# so it survives every redeploy/restart instead of being wiped.
#
# For local development, set DATABASE_URL in your own environment to
# point at a local or remote Postgres instance, e.g.:
#   export DATABASE_URL="postgresql://user:password@localhost:5432/expenses"
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. On Render: create a free PostgreSQL "
        "database (New -> PostgreSQL), then add its Internal Database "
        "URL as the DATABASE_URL environment variable on this web "
        "service. Locally: export DATABASE_URL pointing at your own "
        "Postgres instance before running the app."
    )

conn = sqlite3.connect(DATABASE_URL)
cursor = conn.cursor()

# ================= USERS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    upi_id TEXT
)
""")

# ================= EXPENSES =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
)
""")

# ================= INCOME =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    id SERIAL PRIMARY KEY,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
)
""")

# ================= GROUPS =================
# user_id here is the OWNER/creator of the group (kept for backwards
# compatibility with existing code/queries). Actual access control for
# "who can view/use this group" is handled by group_members below, so
# that more than one real user account can use a group.

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups_table (
    id SERIAL PRIMARY KEY,
    group_name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
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
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups_table(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL DEFAULT 'member',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups_table(id),
    member_name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
)
""")

# ================= SHARED EXPENSES =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS shared_expenses (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    due_date TEXT NOT NULL,
    recurrence TEXT NOT NULL DEFAULT 'none',
    status TEXT NOT NULL DEFAULT 'pending',
    last_generated_date TEXT
)
""")

# ================= NOTIFICATIONS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    due_date TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ================= PASSWORD RESETS =================
# Single-use, time-limited tokens for the "Forgot Password" email flow.
# A row is created when the user requests a reset; it's marked used=1
# the moment it's successfully redeemed so the same link can't be used
# twice, and expires_at enforces a time window even if it's never used.

cursor.execute("""
CREATE TABLE IF NOT EXISTS password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_chats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# =====================================================
# SAFETY CHECK (does NOT modify data): add columns that
# might be missing if this database was upgraded from an
# earlier version of this schema. This only ADDS a column
# if missing -- it never reorders or rewrites existing rows.
# Uses Postgres's information_schema instead of sqlite's
# PRAGMA table_info, and ADD COLUMN IF NOT EXISTS, which
# Postgres supports natively (so no separate existence
# check is even required, but we keep one for clarity and
# to match the original structure of this file).
# =====================================================


def _column_exists(table, column):
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = ? AND column_name = ?
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


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