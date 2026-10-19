"""
OR schedule view: one readiness state per case, the pre-op checklist, and suggested schedule changes.

Shared by the Streamlit app (app.py) and the demo page builder (demo/build_demo_data.py).
Rules-only, no AI. Lead times and the 07:30-17:30 day are teaching assumptions, not hospital policy.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from . import criteria as C
from . import data as D
from .pipeline import rules_next_steps

# ---------------------------------------------------------------------------
# Pre-op checklist rows
# ---------------------------------------------------------------------------
WHY = {"always": "All surgical patients", "female_18_50": "Female, age 18-50", "diabetes": "Diabetic", "copd": "COPD",
       "not_refusing_blood": "Blood may be needed",
       "age65_or_cardiac_noncabg": "Age 65+ or cardiac history", "knee_bmp": "Age 65+ or HTN / diabetes / CKD"}


def why(r, ch):
    if r["condition"] == "always" and r["procedure"] != "All":
        return f"Standard for {ch['case']['procedure']}"
    return WHY.get(r["condition"], C.CONDITION_TEXT[r["condition"]])


def checklist_row(r, ch):
    s = C.requirement_status(ch, r)
    st, on, valid = s["status"], s["on_file"], r["validity_days"]
    if st == "ok":
        note = on
    elif st == "outdated":
        note = f"{on} · expires before surgery" if r["item"] == "Type and screen" else f"{on} · older than {valid} days"
    elif st == "pending":
        note = on
    elif r["item_type"] == "blood" and on:
        note = f"{on} (2 needed)"
    else:
        note = "Not signed" if r["item_type"] == "consent" else "Not in chart"
    return dict(item=r["item"], type=r["item_type"], status=st, note=note, why=why(r, ch))


# ---------------------------------------------------------------------------
# One readiness state per case (both roles)
# ---------------------------------------------------------------------------
SCHED = {"ready": "Ready", "open": "Items outstanding", "later": "Move later", "resched": "Reschedule", "hold": "Clinical hold"}


def takes_days(r):
    """Items that usually take days to arrange (appointments, outside testing) vs. ones done on the day."""
    return r["type"] == "clearance" or (r["type"] == "diagnostic" and r["item"] != "EKG")


def open_reqs(x):
    return [r for r in x["reqs"] if r["status"] != "ok"]


def is_hold(x):
    return any(x["rules"][r]["status"] == "Recommend hold" for r in C.ROLES)


def is_clear(x, role):
    return not x["rules"][role]["actions"] and x["rules"][role]["status"] == "Ready"


def sched_state(x):
    o = open_reqs(x)
    if len(o) >= 2 and (is_hold(x) or any(takes_days(r) for r in o)):
        return "resched"
    if is_hold(x):
        return "hold"
    if len(o) >= 2:
        return "later"
    return "ready" if all(is_clear(x, r) for r in C.ROLES) else "open"


def open_count(x):
    """Distinct next steps across both roles."""
    return len({a["code"] for r in C.ROLES for a in x["rules"][r]["actions"]})


@lru_cache(maxsize=1)
def board():
    """Every case with its checklist, rules output for both roles, and schedule state."""
    out = []
    for c in D.list_cases():
        ch = D.build_chart(c["surgery_id"])
        rules = {}
        for role in C.ROLES:
            s = rules_next_steps(ch, role)
            rules[role] = dict(status=s["status"], actions=[dict(code=a["code"], reason=a["reason"],
                               evidence_ids=a["evidence_ids"], priority=a["priority"]) for a in s["actions"]])
        x = dict(id=c["surgery_id"], split=c["split"], case=ch["case"], patient=ch["patient"],
                 reqs=[checklist_row(r, ch) for r in C.applicable_requirements(ch)], rules=rules)
        x["state"] = sched_state(x)
        out.append(x)
    return out


def by_id():
    return {x["id"]: x for x in board()}


# ---------------------------------------------------------------------------
# Times are minutes after midnight. Each case has a start (surgery_time) and a length (duration_min).
# ---------------------------------------------------------------------------
def to_min(t):
    return int(t[:2]) * 60 + int(t[3:5])


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


DAY_START, DAY_END, TURNOVER = to_min("07:30"), to_min("17:30"), 30


def dur(x):
    return int(x["case"]["duration_min"])


def start(x):
    return to_min(x["case"]["surgery_time"])


def end(x):
    return start(x) + dur(x)


def span(st, d):
    return f"{hhmm(st)}–{hhmm(st + d)}"


def dur_label(m):
    return " ".join(p for p in (f"{m // 60} h" if m // 60 else "", f"{m % 60} min" if m % 60 else "") if p)


def fits(busy, st, d):
    """Ends by DAY_END and keeps TURNOVER minutes from every busy [start, end] in the room."""
    return st >= DAY_START and st + d <= DAY_END and all(st + d + TURNOVER <= a or st >= b + TURNOVER for a, b in busy)


def first_fit(busy, d, frm):
    st = max(frm, DAY_START)
    while st + d <= DAY_END:
        if fits(busy, st, d):
            return st
        st += 15
    return None


def service(loc):
    parts = loc.rsplit(" OR ", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else loc


def short_room(r):
    return r.replace(" OR ", " ")


def add_days(d, n):
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def weekday(d):
    while date.fromisoformat(d).weekday() >= 5:
        d = add_days(d, 1)
    return d


def fmt_day(d, long=False):
    x = date.fromisoformat(d)
    return f"{x:%A}, {x:%B} {x.day}" if long else f"{x:%a} {x:%b} {x.day}"


def why_not(x):
    o = open_reqs(x)
    return ", ".join(r["item"] for r in o) if o else "clinical finding needs review"


# ---------------------------------------------------------------------------
# Suggested new dates and same-day moves
# ---------------------------------------------------------------------------
def lead_days(x):
    """About a week for an outside assessment or clinical review, 5 days for PFTs or an echo."""
    return max([7 if is_hold(x) else 0] + [7 if r["type"] == "clearance" else 5 if takes_days(r) else 1 for r in open_reqs(x)])


@lru_cache(maxsize=1)
def resched_plan():
    cases = board()
    busy, plan = {}, {}
    for x in cases:
        busy.setdefault((x["case"]["surgery_date"], x["case"]["surgery_location"]), []).append((start(x), end(x)))
    all_rooms = sorted({x["case"]["surgery_location"] for x in cases})
    todo = sorted((x for x in cases if x["state"] == "resched"), key=lambda x: (x["case"]["surgery_date"], x["case"]["surgery_time"]))
    for x in todo:
        k, d = x["case"], dur(x)
        rooms = [k["surgery_location"]] + [r for r in all_rooms if r != k["surgery_location"] and service(r) == service(k["surgery_location"])]
        day = weekday(add_days(k["surgery_date"], lead_days(x)))
        for _ in range(40):
            for room in rooms:
                b = busy.setdefault((day, room), [])
                st = start(x) if fits(b, start(x), d) else first_fit(b, d, DAY_START)
                if st is not None:
                    plan[x["id"]] = dict(date=day, room=room, start=st, dur=d, lead=lead_days(x))
                    b.append((st, st + d))
                    break
            if x["id"] in plan:
                break
            day = weekday(add_days(day, 1))
    return plan


def propose_day(day):
    """Room by room: holds and reschedules come off, cases after a freed block move up into it,
    and cases that need same-day work move to the first time at least 2 hours later that still fits."""
    cases = [x for x in board() if x["case"]["surgery_date"] == day]
    placed, off, rooms = [], [], {}
    for x in cases:
        rooms.setdefault(x["case"]["surgery_location"], []).append(x)
    for room, g in rooms.items():
        keep = []
        for x in g:
            (off if x["state"] in ("resched", "hold") else keep).append(x)
        freed_from = min((start(y) for y in off if y["case"]["surgery_location"] == room), default=float("inf"))
        cur = None
        for x in sorted((x for x in keep if x["state"] != "later"), key=start):
            earliest = min(start(x), freed_from) if start(x) > freed_from else start(x)
            st = earliest if cur is None else max(earliest, cur + TURNOVER)
            placed.append(dict(x=x, room=room, start=int(st)))
            cur = st + dur(x)
        for x in sorted((x for x in keep if x["state"] == "later"), key=start):
            busy = [(p["start"], p["start"] + dur(p["x"])) for p in placed if p["room"] == room]
            st = first_fit(busy, dur(x), start(x) + 120)
            placed.append(dict(x=x, room=room, start=start(x) if st is None else st, stuck=st is None))
    return placed, off


def suggested_time(x):
    """Suggested new time for the patient header, or None."""
    st, k = x["state"], x["case"]
    if st == "resched":
        s = resched_plan().get(x["id"])
        if s:
            lead = "about a week" if s["lead"] >= 7 else f"about {s['lead']} days"
            return dict(cls="resched", date=s["date"], time=span(s["start"], s["dur"]), room=s["room"],
                        why=f"allows {lead} to finish outstanding items")
    if st == "later":
        p = next((p for p in propose_day(k["surgery_date"])[0] if p["x"]["id"] == x["id"]), None)
        if p and p["start"] > start(x):
            return dict(cls="later", date=k["surgery_date"], time=span(p["start"], dur(x)), room=p["room"],
                        why="first time later today that fits the case")
    return None


def day_suggestions(day):
    """Suggested adjustments for one day. Only listed; the timeline shows the real schedule."""
    placed, off = propose_day(day)
    sug = {}
    for x in off:
        plan = resched_plan().get(x["id"])
        if x["state"] == "hold":
            sug[x["id"]] = dict(x=x, tag="Hold", text="Hold for clinical review", reason=why_not(x))
        else:
            text = (f"Reschedule to {fmt_day(plan['date'])}, {span(plan['start'], plan['dur'])} in {short_room(plan['room'])}"
                    if plan else "Reschedule")
            sug[x["id"]] = dict(x=x, tag="Reschedule", text=text, reason=f"not ready: {why_not(x)}")
    for p in placed:
        x = p["x"]
        if p.get("stuck"):
            sug[x["id"]] = dict(x=x, tag="Reschedule", text=f"No later time today fits a {dur_label(dur(x))} case; consider rescheduling",
                                reason=f"not ready: {why_not(x)}")
        elif p["start"] != start(x):
            up = p["start"] < start(x)
            freed = next((y for y in off if y["case"]["surgery_location"] == p["room"] and start(y) <= p["start"] < end(y)), None)
            reason = (f"time to finish {why_not(x)}" if x["state"] == "later"
                      else f"uses time freed by {freed['patient']['name']}" if freed else "follows the case before it")
            sug[x["id"]] = dict(x=x, tag="Move up" if up else "Move later",
                                text=f"Move {'up' if up else 'later'}: {x['case']['surgery_time']} → {span(p['start'], dur(x))}",
                                reason=reason)
    return sorted(sug.values(), key=lambda g: start(g["x"]))
