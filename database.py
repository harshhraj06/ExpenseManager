import sqlite3

conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

# ================= USERS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= MEMBERS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    member_name TEXT NOT NULL
)
""")

# ================= SHARED EXPENSES =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS shared_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    description TEXT,
    amount REAL,
    paid_by TEXT
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

conn.commit()

# =====================================================
# SAFETY CHECK (does NOT modify data): add user_id to any
# expenses/income/groups_table that predates this column,
# for installs that started from an even older schema version
# where user_id didn't exist anywhere yet. This only ADDS the
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

conn.commit()
conn.close()

print("Database created successfully")