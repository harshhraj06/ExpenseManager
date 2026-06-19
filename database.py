import sqlite3

conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

# Expenses
cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date TEXT NOT NULL
)
""")

# Income
cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    date TEXT NOT NULL
)
""")

# Groups
cursor.execute("""
CREATE TABLE IF NOT EXISTS groups_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL
)
""")

# Members
cursor.execute("""
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    member_name TEXT NOT NULL
)
""")

# Shared Expenses
cursor.execute("""
CREATE TABLE IF NOT EXISTS shared_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    description TEXT,
    amount REAL,
    paid_by TEXT
)
""")

# Settlements
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
import sqlite3

conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

conn.commit()
conn.close()


print("Database updated successfully!")