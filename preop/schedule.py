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


def done_in_preop(r):
    """Quick items finished in pre-op holding before the case (signing a consent, the surgeon's H&P or its update,
    a 12-lead EKG). They never move a case. Labs, imaging and blood bank work are done on the day but wait on results."""
    return r["type"] in ("consent", "note") or r["item"] == "EKG"


def lead_label(r):
    return "Usually needs days" if takes_days(r) else "Can be done in pre-op" if done_in_preop(r) else "Needs results today"


def open_reqs(x):
    return [r for r in x["reqs"] if r["status"] != "ok"]


def slow_reqs(x):
    return [r for r in open_reqs(x) if not done_in_preop(r)]


def latex(x):
    """Latex allergy: first case of the day in the room, before any latex has been used in it."""
    return "latex" in (x["patient"].get("allergies") or "").lower()


def is_hold(x):
    return any(x["rules"][r]["status"] == "Recommend hold" for r in C.ROLES)


def is_clear(x, role):
    return not x["rules"][role]["actions"] and x["rules"][role]["status"] == "Ready"


def sched_state(x):
    """Quick pre-op items don't count. Anything that takes days means a new date. Two or more items waiting on
    results, or one lab, mean a later slot today. A latex allergy has to stay the first case: one lab is drawn on
    arrival, more than that means a new date."""
    slow = slow_reqs(x)
    if any(takes_days(r) for r in slow) or (is_hold(x) and slow):
        return "resched"
    if is_hold(x):
        return "hold"
    if len(slow) >= 2:
        return "resched" if latex(x) else "later"
    if any(r["type"] == "lab" for r in slow) and not latex(x):
        return "later"
    return "ready" if all(is_clear(x, r) for r in C.ROLES) else "open"


def wait_min(x):
    """How much later a 'later' case moves: about an hour for one lab's results, two hours for more."""
    return 60 if len(slow_reqs(x)) == 1 else 120


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


@lru_cache(maxsize=64)
def cases(moves=()):
    """board() with schedule changes applied (the app's demo moves).

    moves: sorted tuple of (id, date, time, room, kind). kind is resched / later / up, or hold to take the
    case off the schedule. A moved case keeps its readiness state and is not suggested again.
    """
    if not moves:
        return board()
    m = {mv[0]: mv for mv in moves}
    out = []
    for x in board():
        if x["id"] in m:
            _, d, t, room, kind = m[x["id"]]
            k = x["case"]
            x = dict(x, case=dict(k, surgery_date=d or k["surgery_date"], surgery_time=t or k["surgery_time"],
                                  surgery_location=room or k["surgery_location"]),
                     moved=dict(kind=kind, date=k["surgery_date"], time=k["surgery_time"], room=k["surgery_location"]),
                     off=kind == "hold")
        out.append(x)
    return out


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


def results_for(x):
    """'CBC results' or 'HbA1c and Chest X-ray results': what a 'later' case is waiting on."""
    return f"{' and '.join(r['item'] for r in slow_reqs(x))} results"


def why_not(x):
    o = open_reqs(x)
    return ", ".join(r["item"] for r in o) if o else "clinical finding needs review"


# ---------------------------------------------------------------------------
# Suggested new dates and same-day moves
# ---------------------------------------------------------------------------
def lead_days(x):
    """About a week for an outside assessment or clinical review, 5 days for PFTs or an echo."""
    return max([7 if is_hold(x) else 0] + [7 if r["type"] == "clearance" else 5 if takes_days(r) else 1 for r in open_reqs(x)])


@lru_cache(maxsize=64)
def resched_plan(moves=()):
    cs = [x for x in cases(moves) if not x.get("off")]
    busy, plan, first = {}, {}, {}  # first: (day, room) -> end of a latex case that has to stay first
    for x in cs:
        busy.setdefault((x["case"]["surgery_date"], x["case"]["surgery_location"]), []).append((start(x), end(x)))
        if latex(x):
            first[(x["case"]["surgery_date"], x["case"]["surgery_location"])] = end(x)
    all_rooms = sorted({x["case"]["surgery_location"] for x in cs})
    todo = sorted((x for x in cs if x["state"] == "resched" and not x.get("moved")),
                  key=lambda x: (x["case"]["surgery_date"], x["case"]["surgery_time"]))
    for x in todo:
        k, d = x["case"], dur(x)
        rooms = [k["surgery_location"]] + [r for r in all_rooms if r != k["surgery_location"] and service(r) == service(k["surgery_location"])]
        day = weekday(add_days(k["surgery_date"], lead_days(x)))
        for _ in range(40):
            for room in rooms:
                b = busy.setdefault((day, room), [])
                if latex(x):  # only a day when the room's first slot is free
                    st = DAY_START if (day, room) not in first and fits(b, DAY_START, d) else None
                else:
                    frm = first.get((day, room), DAY_START)
                    st = start(x) if start(x) >= frm and fits(b, start(x), d) else first_fit(b, d, frm)
                if st is not None:
                    plan[x["id"]] = dict(date=day, room=room, start=st, dur=d, lead=lead_days(x))
                    b.append((st, st + d))
                    if latex(x):
                        first[(day, room)] = st + d
                    break
            if x["id"] in plan:
                break
            day = weekday(add_days(day, 1))
    return plan


def propose_day(day, moves=(), pull=True):
    """Room by room: holds and reschedules come off, a latex-allergy case moves to the room's first slot and the
    cases before it follow it, cases after a freed block move up into it, and cases that need same-day work move
    to the first time that still fits after their results are back (wait_min). Cases already moved stay where they were put.
    pull=False leaves holds and reschedules where they are (the latex move on its own, for the patient chart)."""
    cs = [x for x in cases(moves) if x["case"]["surgery_date"] == day and not x.get("off")]
    placed, off, rooms = [], [], {}
    for x in cs:
        rooms.setdefault(x["case"]["surgery_location"], []).append(x)
    for room, g in rooms.items():
        keep = []
        for x in g:
            (off if pull and x["state"] in ("resched", "hold") and not x.get("moved") else keep).append(x)
        fixed = [(start(x), end(x)) for x in keep if x.get("moved")]
        placed += [dict(x=x, room=room, start=start(x)) for x in keep if x.get("moved")]
        freed_from = min((start(y) for y in off if y["case"]["surgery_location"] == room), default=float("inf"))
        room_start = min(start(y) for y in g)
        cur = None
        for x in sorted((x for x in keep if x["state"] != "later" and not x.get("moved")), key=lambda x: (not latex(x), start(x))):
            earliest = room_start if latex(x) else min(start(x), freed_from) if start(x) > freed_from else start(x)
            st = earliest if cur is None else max(earliest, cur + TURNOVER)
            if fixed and not fits(fixed, st, dur(x)):
                st = first_fit(fixed, dur(x), st)
                st = start(x) if st is None else st
            placed.append(dict(x=x, room=room, start=int(st)))
            cur = st + dur(x)
        for x in sorted((x for x in keep if x["state"] == "later" and not x.get("moved")), key=start):
            busy = [(p["start"], p["start"] + dur(p["x"])) for p in placed if p["room"] == room]
            st = first_fit(busy, dur(x), start(x) + wait_min(x))
            placed.append(dict(x=x, room=room, start=start(x) if st is None else st, stuck=st is None))
    return placed, off


def bumped_by_latex(placed, p):
    """Moves for the cases a latex case p goes ahead of in its room: (id, move) pairs to apply along with it."""
    return [(q["x"]["id"], dict(date=q["x"]["case"]["surgery_date"], time=hhmm(q["start"]), room=q["room"], kind="later"))
            for q in placed if q["room"] == p["room"] and q["x"] is not p["x"] and not q["x"].get("moved")
            and start(q["x"]) < start(p["x"]) and q["start"] > start(q["x"])]


def suggested_time(x, moves=()):
    """Suggested new time for the patient header, or None. `to` is what the app applies as a move,
    `also` any moves of other cases that go with it."""
    st, k = x["state"], x["case"]
    if x.get("moved"):
        return None
    if latex(x) and st not in ("resched", "hold"):
        placed = propose_day(k["surgery_date"], moves, pull=False)[0]
        p = next((p for p in placed if p["x"]["id"] == x["id"]), None)
        if p and p["start"] < start(x):
            also = bumped_by_latex(placed, p)
            return dict(cls="later", date=k["surgery_date"], time=span(p["start"], dur(x)), room=p["room"], first=True,
                        why="latex allergy: first case in the room, before any latex is used that day"
                            + (f" · {len(also)} case{'s' * (len(also) != 1)} before it move{'s' * (len(also) == 1)} later" if also else ""),
                        to=dict(date=k["surgery_date"], time=hhmm(p["start"]), room=p["room"], kind="up"), also=also)
    if st == "resched":
        s = resched_plan(moves).get(x["id"])
        if s:
            lead = "about a week" if s["lead"] >= 7 else "a day" if s["lead"] == 1 else f"about {s['lead']} days"
            return dict(cls="resched", date=s["date"], time=span(s["start"], s["dur"]), room=s["room"],
                        why=f"allows {lead} to finish outstanding items",
                        to=dict(date=s["date"], time=hhmm(s["start"]), room=s["room"], kind="resched"))
    if st == "later":
        p = next((p for p in propose_day(k["surgery_date"], moves)[0] if p["x"]["id"] == x["id"]), None)
        if p and p["start"] > start(x):
            return dict(cls="later", date=k["surgery_date"], time=span(p["start"], dur(x)), room=p["room"],
                        why=f"time for {results_for(x)}, first time later today that fits the case",
                        to=dict(date=k["surgery_date"], time=hhmm(p["start"]), room=p["room"], kind="later"))
    return None


def day_suggestions(day, moves=()):
    """Suggested adjustments for one day. Only listed; the timeline shows the real schedule.
    `to` is the move the app applies (None when there is nothing to apply)."""
    placed, off = propose_day(day, moves)
    sug = {}
    for x in off:
        plan = resched_plan(moves).get(x["id"])
        if x["state"] == "hold":
            sug[x["id"]] = dict(x=x, tag="Hold", text="Hold for clinical review", reason=why_not(x),
                                to=dict(date=None, time=None, room=None, kind="hold"))
        else:
            text = (f"Reschedule to {fmt_day(plan['date'])}, {span(plan['start'], plan['dur'])} in {short_room(plan['room'])}"
                    if plan else "Reschedule")
            sug[x["id"]] = dict(x=x, tag="Reschedule", text=text, reason=f"not ready: {why_not(x)}",
                                to=plan and dict(date=plan["date"], time=hhmm(plan["start"]), room=plan["room"], kind="resched"))
    for p in placed:
        x = p["x"]
        if p.get("stuck"):
            sug[x["id"]] = dict(x=x, tag="Reschedule", text=f"No later time today fits a {dur_label(dur(x))} case; consider rescheduling",
                                reason=f"not ready: {why_not(x)}", to=None)
        elif p["start"] != start(x):
            up = p["start"] < start(x)
            to = dict(date=day, time=hhmm(p["start"]), room=p["room"], kind="up" if up else "later")
            if latex(x) and up:
                sug[x["id"]] = dict(x=x, tag="Make first case", text=f"First case: {x['case']['surgery_time']} → {span(p['start'], dur(x))}",
                                    reason="latex allergy: first case in the room, before any latex is used that day",
                                    to=to, also=bumped_by_latex(placed, p))
                continue
            freed = next((y for y in off if y["case"]["surgery_location"] == p["room"] and start(y) <= p["start"] < end(y)), None)
            ahead = next((q["x"] for q in placed if q["room"] == p["room"] and latex(q["x"]) and q["start"] < start(q["x"])
                          and start(x) < start(q["x"]) and not up), None)
            reason = (f"time for {results_for(x)}" if x["state"] == "later"
                      else f"makes room for {ahead['patient']['name']} (latex allergy) as the first case" if ahead
                      else f"uses time freed by {freed['patient']['name']}" if freed else "follows the case before it")
            sug[x["id"]] = dict(x=x, tag="Move up" if up else "Move later",
                                text=f"Move {'up' if up else 'later'}: {x['case']['surgery_time']} → {span(p['start'], dur(x))}",
                                reason=reason, to=to)
    return sorted(sug.values(), key=lambda g: start(g["x"]))
