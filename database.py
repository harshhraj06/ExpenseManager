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

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= INCOME =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    date TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# ================= GROUPS =================

cursor.execute("""
CREATE TABLE IF NOT EXISTS groups_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    group_name TEXT NOT NULL,
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

# =====================================================
# MIGRATION: add user_id to tables created before this
# column existed in expenses / income / groups_table.
# Without this, older databases (created by an earlier
# version of this script) crash every query that filters
# by user_id with "no such column: user_id".
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