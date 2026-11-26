from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session
from database import get_db, init_db
from affordability import calculate_affordability, check_repayment

app = Flask(__name__)
app.secret_key = "finnovators-dev-key"

init_db()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return user


def get_affordability(user):
    conn = get_db()
    total_expenses = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM expenses
           WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')""",
        (user["id"],),
    ).fetchone()[0]
    owed = conn.execute(
        "SELECT COALESCE(SUM(amount - amount_repaid), 0) FROM loans WHERE borrower_id = ? AND status != 'paid'",
        (user["id"],),
    ).fetchone()[0]
    owed_to_me = conn.execute(
        "SELECT COALESCE(SUM(amount - amount_repaid), 0) FROM loans WHERE lender_id = ? AND status != 'paid'",
        (user["id"],),
    ).fetchone()[0]
    conn.close()
    return calculate_affordability(
        user["monthly_income"], user["emergency_reserve"], total_expenses, owed, owed_to_me
    )


@app.route("/")
def home():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()
    if request.method == "POST":
        session["user_id"] = int(request.form["user_id"])
        conn.close()
        return redirect(url_for("dashboard"))
    users = conn.execute("SELECT id, name FROM users").fetchall()
    conn.close()
    return render_template("login.html", users=users)


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user, a=get_affordability(user))


@app.route("/recommendation", methods=["GET", "POST"])
def recommendation():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    a = get_affordability(user)
    verdict = None
    if request.method == "POST":
        amount = float(request.form["amount"])
        ok, message = check_repayment(amount, a["cash_left"])
        verdict = {"ok": ok, "message": message, "amount": amount}
    return render_template("recommendation.html", user=user, a=a, verdict=verdict)


@app.route("/expenses")
def expenses():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    a = get_affordability(user)
    return render_template(
        "expenses.html",
        user=user,
        expenses=rows,
        month_total=a["total_expenses"],
        today=date.today().isoformat(),
    )


@app.route("/expenses/add", methods=["POST"])
def add_expense():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    amount = float(request.form["amount"])
    category = request.form["category"]
    exp_date = request.form["date"]
    is_essential = 1 if request.form.get("is_essential") else 0

    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, is_essential) VALUES (?, ?, ?, ?, ?)",
        (user["id"], amount, category, exp_date, is_essential),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expenses"))


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
def delete_expense(expense_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user["id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expenses"))


@app.route("/profile/update", methods=["POST"])
def update_profile():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    income = float(request.form["monthly_income"])
    reserve = float(request.form["emergency_reserve"])
    conn = get_db()
    conn.execute(
        "UPDATE users SET monthly_income = ?, emergency_reserve = ? WHERE id = ?",
        (income, reserve, user["id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expenses"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/loans")
def loans():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT l.*, lu.name AS lender_name, bu.name AS borrower_name
        FROM loans l
        JOIN users lu ON l.lender_id = lu.id
        JOIN users bu ON l.borrower_id = bu.id
        WHERE l.lender_id = ? OR l.borrower_id = ?
        ORDER BY l.created_at DESC
    """, (user["id"], user["id"])).fetchall()
    friends = conn.execute(
        "SELECT id, name FROM users WHERE id != ?", (user["id"],)
    ).fetchall()

    pending_rows = conn.execute("""
        SELECT r.* FROM repayments r
        JOIN loans l ON r.loan_id = l.id
        WHERE r.confirmed = 0 AND (l.lender_id = ? OR l.borrower_id = ?)
    """, (user["id"], user["id"])).fetchall()
    conn.close()

    pending = {}
    for p in pending_rows:
        pending.setdefault(p["loan_id"], []).append(p)

    return render_template(
        "loans.html", user=user, loans=rows, friends=friends, pending=pending
    )


@app.route("/loans/add", methods=["POST"])
def add_loan():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    friend_id = int(request.form["friend_id"])
    kind = request.form["kind"]
    amount = float(request.form["amount"])
    due_date = request.form["due_date"]

    if kind == "lend":
        lender, borrower = user["id"], friend_id
    else:
        lender, borrower = friend_id, user["id"]

    conn = get_db()
    conn.execute(
        "INSERT INTO loans (lender_id, borrower_id, amount, due_date, status) VALUES (?, ?, ?, ?, 'active')",
        (lender, borrower, amount, due_date),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("loans"))


@app.route("/loans/<int:loan_id>/repay", methods=["POST"])
def repay(loan_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    amount = float(request.form["amount"])

    conn = get_db()
    loan = conn.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()

    if loan and loan["borrower_id"] == user["id"]:
        pending_total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE loan_id = ? AND confirmed = 0",
            (loan_id,),
        ).fetchone()[0]
        remaining = loan["amount"] - loan["amount_repaid"] - pending_total
        if 0 < amount <= remaining:
            conn.execute(
                "INSERT INTO repayments (loan_id, amount, confirmed) VALUES (?, ?, 0)",
                (loan_id, amount),
            )
            conn.commit()
    conn.close()
    return redirect(url_for("loans"))


@app.route("/repayments/<int:repayment_id>/confirm", methods=["POST"])
def confirm_repayment(repayment_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    rep = conn.execute(
        "SELECT * FROM repayments WHERE id = ?", (repayment_id,)
    ).fetchone()

    if rep and rep["confirmed"] == 0:
        loan = conn.execute(
            "SELECT * FROM loans WHERE id = ?", (rep["loan_id"],)
        ).fetchone()
        if loan and loan["lender_id"] == user["id"]:
            new_repaid = loan["amount_repaid"] + rep["amount"]
            status = "paid" if new_repaid >= loan["amount"] else "partly_paid"
            conn.execute(
                "UPDATE repayments SET confirmed = 1 WHERE id = ?", (repayment_id,)
            )
            conn.execute(
                "UPDATE loans SET amount_repaid = ?, status = ? WHERE id = ?",
                (new_repaid, status, loan["id"]),
            )
            conn.commit()
    conn.close()
    return redirect(url_for("loans"))


if __name__ == "__main__":
    app.run(debug=True)