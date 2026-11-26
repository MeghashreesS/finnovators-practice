def calculate_affordability(income, reserve, total_expenses, owed, owed_to_me):
    """Simple rule-based estimate. Results are estimates only."""
    cash_left = income - total_expenses - reserve
    safe_to_repay = min(owed, max(0, cash_left))
    safe_to_spend = max(0, cash_left - owed)
    return {
        "income": income,
        "reserve": reserve,
        "total_expenses": total_expenses,
        "owed": owed,
        "owed_to_me": owed_to_me,
        "cash_left": cash_left,
        "safe_to_repay": safe_to_repay,
        "safe_to_spend": safe_to_spend,
    }


def check_repayment(amount, cash_left):
    """Can the user repay this amount without dipping into their reserve?"""
    if amount <= cash_left:
        left_after = cash_left - amount
        return True, f"Safe to repay. You would still have about ₹{left_after:.0f} left after your expenses and reserve."
    short = amount - max(0, cash_left)
    return False, f"Not recommended right now. This is about ₹{short:.0f} more than you can safely spare without touching your emergency reserve."