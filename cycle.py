"""Budget-cycle logic: turns a government's fiscal-year start month into
call windows for any given month.

Model (k = months since the fiscal year started, 0-11):
    k 0-2   New fiscal year   - money just released; follow up only where they budgeted us
    k 3-6   CALL NOW          - departments drafting next year's budget requests
    k 7-8   Last call         - budget under review; still possible to get added
    k 9     Budget locked     - council adopting next budget; don't cold call
    k 10-11 Year-end spend    - leftover funds; pitch small purchases / Pay As You Spray

The ranges are defaults and can be changed in the app sidebar.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

MONTHS = list(calendar.month_name)[1:]


@dataclass(frozen=True)
class Phase:
    key: str
    label: str
    action: str
    color: tuple[int, int, int]
    priority: int  # 1 = call first


PHASES = {
    "call_now": Phase("call_now", "🟢 Call now", "Budget requests being drafted. Get the robot into next year's request.", (8, 52, 0), 1),
    "last_call": Phase("last_call", "🟢 Last call", "Budget under review. Push for it to be added before adoption.", (76, 140, 43), 2),
    "year_end": Phase("year_end", "🟡 Year-end spend", "Use-it-or-lose-it money. Pitch Pay As You Spray or small purchases.", (214, 158, 46), 3),
    "new_fy": Phase("new_fy", "🔵 New fiscal year", "Money just released. Follow up only if they budgeted for us.", (59, 110, 201), 4),
    "locked": Phase("locked", "🔴 Budget locked", "Council is adopting next year's budget. Don't cold call.", (190, 50, 40), 5),
}

DEFAULT_WINDOWS = {  # phase -> (first k, last k), inclusive
    "new_fy": (0, 2),
    "call_now": (3, 6),
    "last_call": (7, 8),
    "locked": (9, 9),
    "year_end": (10, 11),
}


def months_since_start(fy_start_month: int, month: int) -> int:
    return (month - fy_start_month) % 12


def phase_for(fy_start_month: int, month: int, windows: dict = DEFAULT_WINDOWS) -> Phase:
    k = months_since_start(fy_start_month, month)
    for key, (a, b) in windows.items():
        if a <= k <= b:
            return PHASES[key]
    return PHASES["locked"]


def best_window(fy_start_month: int, windows: dict = DEFAULT_WINDOWS) -> tuple[int, int]:
    """Calendar months (1-12) when the 'call now' window opens and closes."""
    a, b = windows["call_now"]
    return ((fy_start_month - 1 + a) % 12) + 1, ((fy_start_month - 1 + b) % 12) + 1


def next_call_now(fy_start_month: int, today: date, windows: dict = DEFAULT_WINDOWS) -> date:
    """First day of the next (or current) 'call now' window."""
    start, _ = best_window(fy_start_month, windows)
    if phase_for(fy_start_month, today.month, windows).key == "call_now":
        return today
    y = today.year if start > today.month else today.year + 1
    return date(y, start, 1)


def window_text(fy_start_month: int, windows: dict = DEFAULT_WINDOWS) -> str:
    a, b = best_window(fy_start_month, windows)
    return f"{MONTHS[a-1][:3]}–{MONTHS[b-1][:3]}"


if __name__ == "__main__":
    # Sanity checks: July-1 fiscal year (Atlanta, most school districts)
    assert phase_for(7, 7).key == "new_fy"
    assert phase_for(7, 10).key == "call_now"   # Oct
    assert phase_for(7, 1).key == "call_now"    # Jan
    assert phase_for(7, 3).key == "last_call"   # Mar
    assert phase_for(7, 4).key == "locked"      # Apr
    assert phase_for(7, 6).key == "year_end"    # Jun
    assert window_text(7) == "Oct–Jan"
    # October-1 fiscal year (many Texas/Florida cities)
    assert window_text(10) == "Jan–Apr"
    # January-1 fiscal year (calendar-year cities/counties)
    assert window_text(1) == "Apr–Jul"
    assert next_call_now(1, date(2026, 10, 20)) == date(2027, 4, 1)
    print("cycle.py OK")
