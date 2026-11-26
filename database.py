import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "finnovators.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        monthly_income REAL DEFAULT 0,
        emergency_reserve REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        category TEXT,
        date TEXT,
        is_essential INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lender_id INTEGER NOT NULL,
        borrower_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        amount_repaid REAL DEFAULT 0,
        due_date TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lender_id) REFERENCES users(id),
        FOREIGN KEY (borrower_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS repayments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        confirmed INTEGER DEFAULT 0,
        FOREIGN KEY (loan_id) REFERENCES loans(id)
    );
    """)

    # Add sample data only if the database is empty
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        pw = generate_password_hash("1234")
        users = [
            ("Aarav", "aarav@example.com", pw, 20000, 3000),
            ("Priya", "priya@example.com", pw, 15000, 2000),
            ("Rahul", "rahul@example.com", pw, 8000, 1000),
            ("Sneha", "sneha@example.com", pw, 10000, 1500),
        ]
        cur.executemany(
            "INSERT INTO users (name, email, password_hash, monthly_income, emergency_reserve) VALUES (?, ?, ?, ?, ?)",
            users,
        )

        expenses = [
            (1, 5000, "Rent", "2026-11-01", 1),
            (1, 2000, "Food", "2026-11-05", 1),
            (1, 800, "Movies", "2026-11-10", 0),
            (3, 3000, "Hostel fees", "2026-11-01", 1),
            (3, 1200, "Food", "2026-11-06", 1),
        ]
        cur.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, is_essential) VALUES (?, ?, ?, ?, ?)",
            expenses,
        )

        # Sample loan: Aarav lent Rahul 500, Rahul repaid 200 (confirmed)
        cur.execute(
            "INSERT INTO loans (lender_id, borrower_id, amount, amount_repaid, due_date, status) VALUES (1, 3, 500, 200, '2026-12-05', 'partly_paid')"
        )
        cur.execute(
            "INSERT INTO repayments (loan_id, amount, confirmed) VALUES (1, 200, 1)"
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database ready")