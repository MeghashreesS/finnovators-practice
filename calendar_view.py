import calendar
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db

bp = Blueprint("calendar_view", __name__)


def _current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return user


@bp.route("/calendar")
def money_calendar():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))

    today = date.today()
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    if month < 1 or month > 12:
        year, month = today.year, today.month

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    conn = get_db()
    rows = conn.execute(
        """
        SELECT l.*, lu.name AS lender_name, bu.name AS borrower_name
        FROM loans l
        JOIN users lu ON l.lender_id = lu.id
        JOIN users bu ON l.borrower_id = bu.id
        WHERE (l.lender_id = ? OR l.borrower_id = ?) AND l.status != 'paid'
        ORDER BY l.due_date
        """,
        (user["id"], user["id"]),
    ).fetchall()
    month_expenses = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM expenses
           WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')""",
        (user["id"],),
    ).fetchone()[0]
    conn.close()

    # Cash you can spend today, above your emergency reserve (estimate)
    base_cash = user["monthly_income"] - month_expenses - user["emergency_reserve"]

    events = {}
    changes = {}
    total_to_pay = 0
    total_to_receive = 0

    for r in rows:
        due = date.fromisoformat(r["due_date"])
        left = r["amount"] - r["amount_repaid"]
        if left <= 0:
            continue
        is_owe = r["borrower_id"] == user["id"]

        # Overdue items count from today onwards in the forecast
        effective = max(due, today)
        changes[effective] = changes.get(effective, 0) + (-left if is_owe else left)

        if due.year == year and due.month == month:
            if is_owe:
                kind, text = "owe", f"Pay {r['lender_name']}"
                total_to_pay += left
            else:
                kind, text = "owed", f"{r['borrower_name']} pays you"
                total_to_receive += left
            events.setdefault(due.day, []).append(
                {"kind": kind, "text": text, "left": left, "overdue": due < today}
            )

    # Running cash forecast
    projected = {}
    running = base_cash
    for d in sorted(changes):
        running += changes[d]
        projected[d] = running
    if today not in projected:
        projected[today] = base_cash

    day_info = {}
    for d, value in projected.items():
        if d.year == year and d.month == month:
            day_info[d.day] = {"cash": value, "danger": value < 0}

    first_danger = None
    for d in sorted(projected):
        if projected[d] < 0:
            first_danger = {"date": d.strftime("%d %b %Y"), "short": -projected[d]}
            break

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    today_day = today.day if (year == today.year and month == today.month) else -1

    return render_template(
        "calendar.html",
        user=user,
        weeks=weeks,
        events=events,
        day_info=day_info,
        first_danger=first_danger,
        base_cash=base_cash,
        year=year,
        month_name=calendar.month_name[month],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today_day=today_day,
        total_to_pay=total_to_pay,
        total_to_receive=total_to_receive,
    )


@bp.route("/repay-plan")
def repay_plan():
    user = _current_user()
    if not user:
        return redirect(url_for("login"))

    today = date.today()
    horizon = 60

    conn = get_db()
    rows = conn.execute(
        """
        SELECT l.*, lu.name AS lender_name, bu.name AS borrower_name
        FROM loans l
        JOIN users lu ON l.lender_id = lu.id
        JOIN users bu ON l.borrower_id = bu.id
        WHERE (l.lender_id = ? OR l.borrower_id = ?) AND l.status != 'paid'
        """,
        (user["id"], user["id"]),
    ).fetchall()
    month_expenses = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) FROM expenses
           WHERE user_id = ? AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')""",
        (user["id"],),
    ).fetchone()[0]
    conn.close()

    base_cash = user["monthly_income"] - month_expenses - user["emergency_reserve"]

    items = []
    for r in rows:
        left = r["amount"] - r["amount_repaid"]
        if left <= 0:
            continue
        items.append(
            {
                "id": r["id"],
                "left": left,
                "due": date.fromisoformat(r["due_date"]),
                "owe": r["borrower_id"] == user["id"],
                "name": r["lender_name"],
            }
        )

    def cash_timeline(skip_id):
        changes = [0] * (horizon + 1)
        for it in items:
            if it["id"] == skip_id:
                continue
            idx = (max(it["due"], today) - today).days
            if idx > horizon:
                continue
            changes[idx] += -it["left"] if it["owe"] else it["left"]
        timeline, running = [], base_cash
        for c in changes:
            running += c
            timeline.append(running)
        return timeline

    plans = []
    for it in items:
        if not it["owe"]:
            continue
        timeline = cash_timeline(it["id"])

        # Lowest cash from each day to the end of the forecast window
        min_from = [0] * (horizon + 1)
        lowest = timeline[horizon]
        for i in range(horizon, -1, -1):
            lowest = min(lowest, timeline[i])
            min_from[i] = lowest

        overdue = it["due"] < today
        last_idx = horizon if overdue else min((it["due"] - today).days, horizon)

        best = None
        for i in range(0, last_idx + 1):
            if min_from[i] - it["left"] >= 0:
                best = today + timedelta(days=i)
                break

        if best is None:
            best_label = None
        elif best == today:
            best_label = "Today"
        else:
            best_label = best.strftime("%d %b %Y")

        plans.append(
            {
                "name": it["name"],
                "left": it["left"],
                "due": it["due"].strftime("%d %b %Y"),
                "overdue": overdue,
                "best": best_label,
                "safe_now": max(0, min(it["left"], min_from[0])),
            }
        )

    return render_template("repay_plan.html", user=user, plans=plans)