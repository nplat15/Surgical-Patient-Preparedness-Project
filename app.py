"""
Mock EHR "Pre-Op Readiness" board: patient chart and OR schedule.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...        (or OPENAI_API_KEY + PREOP_LLM_PROVIDER=openai + PREOP_LLM_MODEL=...)
    streamlit run app.py

Without an API key the app still runs using the rules-only engine.
Fully synthetic patients. Teaching rules, not clinical guidelines.
"""
from __future__ import annotations

import calendar
import csv
import hmac
import os
import re
import threading
from datetime import date, datetime
from html import escape as esc

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from preop import criteria as C
from preop import data as D
from preop import schedule as S
from preop import workflow as W
from preop.classroom import Roster
from preop.llm import LLM, default_provider
from preop.pipeline import action_text, rules_next_steps, rules_summary, run_case

st.set_page_config(page_title="Pre-Op Readiness", page_icon="🩺", layout="wide", initial_sidebar_state="collapsed")

# Streamlit Community Cloud exposes configured credentials through st.secrets,
# while the LLM client reads environment variables. st.secrets loads lazily, so a missing
# secrets.toml (a local run) raises on first lookup, not on access.
try:
    for setting in ("PREOP_LLM_PROVIDER", "PREOP_LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PREOP_TEAM_CODE"):
        if not os.environ.get(setting) and setting in st.secrets:
            os.environ[setting] = str(st.secrets[setting])
except StreamlitSecretNotFoundError:
    pass

ROLE_LABEL = {"nurse": "Pre-op nurse", "anesthesia": "Anesthesiologist"}
EKG_DISPOSITION_LABELS = {
    "proceed": "Proceed as scheduled",
    "move_later": "Move later today",
    "reschedule": "Reschedule",
    "clinical_hold": "Clinical hold",
}
STATUS_CLS = {"Ready": "ready", "Outstanding items": "later", "Needs clinical review": "resched", "Recommend hold": "hold"}
KEY_TESTS = {
    "nurse": ["Hemoglobin", "Potassium", "Glucose", "POC glucose", "INR", "Serum hCG", "UA nitrite", "Urine culture"],
    "anesthesia": ["Hemoglobin", "Hematocrit", "Platelets", "PT", "INR", "PTT", "Sodium", "Potassium", "Creatinine",
                   "eGFR", "Glucose", "POC glucose", "HbA1c", "Albumin", "AST", "ALT", "Total bilirubin"],
}
ICON = {"ready": "🟢", "open": "⚪", "later": "🟠", "resched": "🔴", "hold": "🟣"}
CK = {"ok": ("✓", "Complete"), "missing": ("✗", "Missing"), "outdated": ("!", "Expired"),
      "pending": ("…", "Pending"), "refused": ("✗", "Refused")}
DECLINE_REASONS = ["Already done elsewhere", "Not indicated for this patient", "Patient declined", "Covered by another order", "Other"]
DECISIONS = os.path.join(D.ROOT, "results", "decisions.csv")

# Status colors from the demo page; the dark set matches the dark theme in .streamlit/config.toml.
st.markdown("""<style>
:root{--ok:#1d7a4e;--warn:#a8650a;--bad:#b83a2f;--hold:#6d2f8f;--ok-bg:#e3f2ea;--warn-bg:#fbf0dc;--bad-bg:#f9e4e1;--hold-bg:#f0e5f6;
  --accent:#0d6b73;--muted:#5b6d72;--line:#d6e0e1;--soft:#e8eff0}
@media (prefers-color-scheme: dark){:root{--ok:#5cc28e;--warn:#e3a649;--bad:#ef7a6e;--hold:#c08ae0;--ok-bg:#183126;--warn-bg:#352a15;
  --bad-bg:#3a1f1c;--hold-bg:#2d1f37;--accent:#4fb3bb;--muted:#93a6ab;--line:#2a3a3e;--soft:#1d2b2f}}
.s-ready{--c:var(--ok);--cb:var(--ok-bg)} .s-open{--c:var(--muted);--cb:var(--soft)} .s-later{--c:var(--warn);--cb:var(--warn-bg)}
.s-resched{--c:var(--bad);--cb:var(--bad-bg)} .s-hold{--c:var(--hold);--cb:var(--hold-bg)}
.banner{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-bottom:8px;line-height:1.6}
.banner .nm{font-size:1.3em;font-weight:700;margin-right:10px} .banner .mt{color:var(--muted);font-size:.92em}
.allergy{color:var(--bad);font-weight:600}
.sugg{margin-top:6px;padding:6px 10px;border-radius:6px;background:var(--cb);border-left:4px solid var(--c)}
.sugg .lb{color:var(--c);font-size:.75em;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-right:8px}
.card{padding:16px 20px;border-radius:10px;background:var(--cb);border:1px solid var(--c);margin-bottom:10px}
.card .ti{font-size:1.6em;font-weight:700;color:var(--c);line-height:1.2}
.card .sub{margin-top:2px} .card .fx{margin-top:6px;font-size:.9em;color:var(--muted)}
.card ul{margin:6px 0;padding-left:0;list-style:none} .card li{margin:2px 0}
.lead{font-size:.85em;color:var(--muted);margin-left:6px} .lead.days{color:var(--bad);font-weight:600}
.bar{padding:8px 14px;border-radius:6px;font-weight:600;background:var(--cb);color:var(--c);margin-bottom:10px}
.bar span{font-weight:400;color:inherit;opacity:.9}
.ck-ok{color:var(--ok)} .ck-missing,.ck-refused{color:var(--bad)} .ck-outdated,.ck-pending{color:var(--warn)}
table.ck{border-collapse:collapse;width:100%;font-size:.9em} table.ck td,table.ck th{text-align:left;padding:5px 8px;border-bottom:1px solid var(--soft);vertical-align:top}
table.ck th{font-size:.75em;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.legend span{margin-right:14px;font-size:.88em;white-space:nowrap} .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;background:var(--c)}
.og-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
.og{display:grid;min-width:max-content;--q:13px}
.og .hd{font-size:.72em;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding:8px;background:var(--soft);grid-row:1}
.og .tm{font-family:monospace;font-size:.7em;color:var(--muted);padding:2px 6px 0;border-top:1px solid var(--line);grid-column:1}
.og .lane{border-left:1px solid var(--soft);background:repeating-linear-gradient(to bottom,var(--line) 0 1px,transparent 1px calc(var(--q)*4))}
.blk{display:flex;flex-direction:column;margin:1px 3px;overflow:hidden;border-left:4px solid var(--c);background:var(--cb);border-radius:6px;padding:4px 6px;font-size:.72em;line-height:1.25;z-index:1}
.blk .st{font-size:.85em;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--c)}
.blk .tt{font-family:monospace} .blk .pl{color:var(--muted)} .blk .mv{font-style:italic}
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;text-align:center;font-size:.85em}
.cal .w{font-size:.75em;font-weight:600;color:var(--muted)}
.cal .d{position:relative;border-radius:6px;padding:4px 0;line-height:1.1}
.cal .d.has{border:1px solid var(--line);font-weight:600} .cal .d.sel{background:var(--accent);color:#fff;border-color:var(--accent)}
.cal .d small{display:block;font-size:.72em;font-weight:400;opacity:.75} .cal .d.off{opacity:.45}
.cal .d i{position:absolute;top:3px;right:3px;width:6px;height:6px;border-radius:50%;background:var(--c)}
.sg{border-left:4px solid var(--c);padding:2px 0 2px 10px;margin:8px 0;font-size:.92em}
.src{color:var(--muted);font-size:.85em}
.st-key-plist [data-testid="stVerticalBlock"]{gap:3px}
.st-key-plist button{justify-content:flex-start;padding:6px 10px;min-height:0}
.st-key-plist button p{text-align:left;font-size:.86em;line-height:1.35}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def shared():
    """One per server, shared by every browser session: the class roster, a lock for the decisions log,
    and a cap on AI reviews running at once (the rest wait their turn)."""
    return Roster(), threading.Lock(), threading.Semaphore(4)


ROSTER, DECISIONS_LOCK, AI_SLOTS = shared()
ss = st.session_state


def completed_actions(sid):
    """Actions with all checkboxes and required session inputs completed."""
    completed = set()
    chart = D.build_chart(sid)
    medication_doses = ss.get(f"med-dose|{sid}", {})
    chart = W.apply_completed_actions(
        chart, set(), day_of_values=ss.get(f"dayof|{sid}", {}),
        ekg_machine_reading=ss.get(f"session_ekg|{sid}", {}).get("reading"),
        ekg_nurse_note=ss.get(f"session_ekg|{sid}", {}).get("note"),
        medication_doses=medication_doses, track_medication_doses=True,
    )
    for code in C.ACTION_FOLLOW_UP:
        role = C.ACTION_CATALOG[code][0]
        if (ss.get(f"completed|{sid}|{role}|{code}")
                or action_is_complete(sid, role, code, chart)):
            completed.add((role, code))
    return completed


def medication_ids_for_action(chart, code):
    if code != "VERIFY_MEDICATION_LAST_DOSE":
        return []
    return [
        row["medication_id"] for row in chart["meds"]
        if (row.get("preop_instruction") or "").strip()
        and any(word in row["preop_instruction"].lower() for word in ("hold", "stop"))
    ]


def action_tasks_for(sid, role, code, chart=None):
    tasks, closes = C.ACTION_FOLLOW_UP.get(code, ([], ""))
    if code in {"NOTIFY_EKG_ABNORMALITY", "REVIEW_COMPUTERIZED_EKG"}:
        reading = ss.get(f"session_ekg|{sid}", {}).get("reading")
        if reading in C.COMPUTERIZED_EKG_GUIDANCE:
            if code == "NOTIFY_EKG_ABNORMALITY":
                tasks = [
                    C.COMPUTERIZED_EKG_GUIDANCE[reading][0],
                    "Notify anesthesia of this reading and document the handoff",
                ]
            else:
                tasks = C.computerized_ekg_review_tasks(reading)
    return tasks, closes


def action_inputs_ready(sid, code, chart=None):
    if code in C.ACTION_CATALOG and code in C.ACTION_FOLLOW_UP:
        tests = W.DAY_OF_LAB_ACTIONS.get(code, ())
        if tests and any(test not in ss.get(f"dayof|{sid}", {}) for test in tests):
            return False
        if code in {"OBTAIN_EKG", "NOTIFY_EKG_ABNORMALITY", "REVIEW_COMPUTERIZED_EKG"}:
            if (not ss.get(f"session_ekg|{sid}", {}).get("reading")
                    or ss.get(f"session_ekg_pending|{sid}")):
                return False
        if code == "VERIFY_MEDICATION_LAST_DOSE":
            chart = chart or D.build_chart(sid)
            saved = ss.get(f"med-dose|{sid}", {})
            med_ids = medication_ids_for_action(chart, code)
            if not med_ids or any(
                med_id not in saved or saved[med_id].get("within_hold_period") not in (True, False)
                for med_id in med_ids
            ):
                return False
    return True


def action_is_complete(sid, role, code, chart=None):
    decision = f"dec|{sid}|{role}|{code}"
    if ss.get(decision) != "Accept":
        return False
    if code == "OBTAIN_ANESTHESIA_CONSENT":
        return ss.get(f"consent_status|{sid}") in ("signed", "refused")
    if code == "BRING_CPAP":
        return ss.get(f"cpap_status|{sid}") in ("brought", "not_brought")
    tasks, _ = action_tasks_for(sid, role, code, chart)
    checkboxes_done = all(
        ss.get(f"todo|{sid}|{role}|{code}|{index}")
        for index in range(len(tasks))
    )
    return checkboxes_done and action_inputs_ready(sid, code, chart)


def mark_action_complete(sid, role, code):
    decision = f"dec|{sid}|{role}|{code}"
    completed_key = f"completed|{sid}|{role}|{code}"
    if action_is_complete(sid, role, code):
        ss[completed_key] = True
    else:
        ss.pop(completed_key, None)


def mark_cpap_status(sid):
    status = ss.get(f"cpap|{sid}")
    ss[f"cpap_status|{sid}"] = status
    completed_key = f"completed|{sid}|nurse|BRING_CPAP"
    if status in ("brought", "not_brought"):
        ss[completed_key] = True
    else:
        ss.pop(f"cpap_status|{sid}", None)
        ss.pop(completed_key, None)


def mark_consent_answer(sid):
    answer = ss.get(f"consent-answer|{sid}")
    outcome_key = f"consent-outcome-value|{sid}"
    if answer in ("yes", "no"):
        ss[f"consent-answer-value|{sid}"] = answer
    status_key = f"consent_status|{sid}"
    if answer == "yes":
        ss.pop(outcome_key, None)
        ss[status_key] = "signed"
    elif answer == "no" and ss.get(outcome_key) == "refused":
        ss[status_key] = "refused"
    else:
        ss.pop(status_key, None)


def mark_consent_outcome(sid):
    ss[f"consent-outcome-value|{sid}"] = ss.get(f"consent-outcome|{sid}", "")
    mark_consent_answer(sid)


def reset_action_checkboxes(sid, role, code):
    prefix = f"todo|{sid}|{role}|{code}|"
    for key in list(ss.keys()):
        if key.startswith(prefix):
            ss.pop(key, None)
    ss.pop(f"completed|{sid}|{role}|{code}", None)


def save_ekg_disposition(sid):
    disposition = ss.get(f"ekg-disposition|{sid}")
    if disposition in EKG_DISPOSITION_LABELS:
        ss[f"ekg-disposition-value|{sid}"] = disposition


def append_change_history(sid, field, old_value, new_value):
    if old_value == new_value:
        return
    history_key = f"history|{sid}|{field}"
    history = list(ss.get(history_key, []))
    user = globals().get("USER") or {}
    history.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": user.get("name", "Student"),
        "role": ss.get("role", "nurse"),
        "old_value": old_value,
        "new_value": new_value,
    })
    ss[history_key] = history


def open_session_edit(sid, field):
    ss[f"edit|{sid}|{field}"] = True


def record_ekg_form(sid, reading, note):
    old_entry = ss.get(f"session_ekg|{sid}", {})
    new_entry = {"reading": reading, "note": note.strip()} if reading else {}
    if old_entry:
        append_change_history(sid, "ekg", old_entry, new_entry)
    changed_existing = bool(old_entry and old_entry != new_entry)
    if reading:
        ss[f"session_ekg|{sid}"] = new_entry
        ss.pop(f"edit|{sid}|ekg", None)
        ss.pop(f"session_ekg_pending|{sid}", None)
        if changed_existing:
            ss.pop(f"ekg-disposition-value|{sid}", None)
            ss.pop(f"ekg-disposition|{sid}", None)
            for code in ("OBTAIN_EKG", "NOTIFY_EKG_ABNORMALITY", "REVIEW_COMPUTERIZED_EKG"):
                role = C.ACTION_CATALOG[code][0]
                reset_action_checkboxes(sid, role, code)
        mark_action_complete(sid, "nurse", "OBTAIN_EKG")
    else:
        if old_entry:
            ss.pop(f"ekg-disposition-value|{sid}", None)
            ss.pop(f"ekg-disposition|{sid}", None)
            for code in ("OBTAIN_EKG", "NOTIFY_EKG_ABNORMALITY", "REVIEW_COMPUTERIZED_EKG"):
                role = C.ACTION_CATALOG[code][0]
                reset_action_checkboxes(sid, role, code)
        ss.pop(f"session_ekg|{sid}", None)
        ss.pop(f"edit|{sid}|ekg", None)


def save_day_of_value(sid, test, value, unit):
    values = dict(ss.get(f"dayof|{sid}", {}))
    old_entry = values.get(test)
    new_entry = dict(value=value, unit=unit)
    if old_entry and old_entry != new_entry:
        append_change_history(sid, f"lab:{test}", old_entry, new_entry)
        for code, tests in W.DAY_OF_LAB_ACTIONS.items():
            if test in tests:
                reset_action_checkboxes(sid, "nurse", code)
    values[test] = new_entry
    ss[f"dayof|{sid}"] = values
    ss.pop(f"edit|{sid}|lab:{test}", None)
    pending = dict(ss.get(f"dayof_pending|{sid}", {}))
    pending.pop(test, None)
    ss[f"dayof_pending|{sid}"] = pending
    for code, tests in W.DAY_OF_LAB_ACTIONS.items():
        if test in tests:
            mark_action_complete(sid, "nurse", code)


def mark_lab_pending(sid, test):
    pending = dict(ss.get(f"dayof_pending|{sid}", {}))
    pending[test] = True
    ss[f"dayof_pending|{sid}"] = pending


def medication_dose_form(sid, medication, surgery_date):
    med_id = medication["medication_id"]
    saved = ss.get(f"med-dose|{sid}", {}).get(med_id, {})
    instruction = medication.get("preop_instruction") or "No hold instruction documented"
    surgery_day = date.fromisoformat(surgery_date)
    dose_match = re.match(r"\s*(\d+(?:\.\d+)?)\s*(.*)", medication.get("dose", ""))
    default_amount = float(dose_match.group(1)) if dose_match else 0.0
    default_unit = dose_match.group(2).strip() if dose_match else "dose"
    if saved and not ss.get(f"edit|{sid}|medication:{med_id}"):
        st.caption(f"Recorded last dose: {saved['amount']:g} {saved['unit']} · {saved['date']}")
        st.button(
            f"Make edit to {medication['medication_name']} last dose",
            key=f"edit-medication|{sid}|{med_id}",
            on_click=open_session_edit,
            args=(sid, f"medication:{med_id}"),
        )
        history = ss.get(f"history|{sid}|medication:{med_id}", [])
        if history:
            with st.popover(f"🕘 Change history · {medication['medication_name']}"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")
        return
    with st.form(f"med-dose-form|{sid}|{med_id}"):
        st.caption(f"Instruction: {instruction}")
        amount_col, unit_col = st.columns([1, 1])
        amount = amount_col.number_input(
            "Last dose amount",
            min_value=0.0,
            value=float(saved["amount"]) if saved else default_amount,
            step=0.5,
            key=f"med-dose-amount|{sid}|{med_id}",
        )
        unit = unit_col.text_input(
            "Dose unit",
            value=saved.get("unit", default_unit),
            key=f"med-dose-unit|{sid}|{med_id}",
        )
        taken_date = st.date_input(
            "Date of last dose",
            value=date.fromisoformat(saved["date"]) if saved else min(date.today(), surgery_day),
            key=f"med-dose-date|{sid}|{med_id}",
        )
        within_options = ["yes", "no"]
        saved_within = ("yes" if saved["within_hold_period"] else "no") if saved else None
        within = st.radio(
            "Was it taken within the documented hold period?",
            within_options,
            index=within_options.index(saved_within) if saved_within else None,
            format_func=lambda value: {
                "yes": "Yes — notify anesthesia",
                "no": "No — followed the hold timing",
            }[value],
            key=f"med-dose-within|{sid}|{med_id}",
        )
        submitted = st.form_submit_button("Record last dose")
    if submitted:
        if amount <= 0 or not unit.strip():
            st.error("Enter a positive dose amount and its unit.")
        elif not within:
            st.error("Choose whether the dose was taken within the documented hold period.")
        elif taken_date > surgery_day:
            st.error("The last-dose date cannot be after the scheduled surgery date.")
        else:
            values = dict(ss.get(f"med-dose|{sid}", {}))
            entry = {
                "medication_name": medication["medication_name"],
                "amount": amount,
                "unit": unit.strip(),
                "date": taken_date.isoformat(),
                "within_hold_period": within == "yes",
            }
            old_entry = values.get(med_id)
            if old_entry and old_entry != entry:
                append_change_history(sid, f"medication:{med_id}", old_entry, entry)
                reset_action_checkboxes(sid, "nurse", "VERIFY_MEDICATION_LAST_DOSE")
            values[med_id] = entry
            ss[f"med-dose|{sid}"] = values
            ss.pop(f"edit|{sid}|medication:{med_id}", None)
            mark_action_complete(sid, "nurse", "VERIFY_MEDICATION_LAST_DOSE")
            st.rerun()
    if saved:
        history = ss.get(f"history|{sid}|medication:{med_id}", [])
        if history:
            with st.popover(f"🕘 Change history · {medication['medication_name']}"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")


def select_chart_tab(tab_name):
    ss["chart-section"] = tab_name


def day_of_value_form(sid, test):
    """Record a day-of result without changing the source dataset."""
    panel, default_unit, unit_factors = W.DAY_OF_TESTS[test]
    saved = ss.get(f"dayof|{sid}", {}).get(test)
    latest = C.latest_lab(D.build_chart(sid), test)
    if latest:
        st.caption(f"{panel} · Most recent chart value: {latest['result_value']} {latest['unit']} · {latest['collection_date']}")
    else:
        st.caption(panel)
    if saved and not ss.get(f"edit|{sid}|lab:{test}"):
        line, edit_col, history_col = st.columns([3, 1, 1])
        line.caption(f"Recorded day-of value: {saved['value']:g} {saved['unit']}")
        edit_col.button(
            "Make edit",
            key=f"edit-lab|{sid}|{test}",
            on_click=open_session_edit,
            args=(sid, f"lab:{test}"),
        )
        history = ss.get(f"history|{sid}|lab:{test}", [])
        if history:
            with history_col.popover("🕘 Change history"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")
        return
    form_key = f"dayof-form|{sid}|{test}"
    with st.form(form_key):
        value_col, unit_col = st.columns([1, 1])
        value = value_col.number_input(
            f"{test} day-of value",
            value=float(saved["value"]) if saved else None,
            step=0.1,
            key=f"dayof-value|{sid}|{test}",
        )
        units = list(unit_factors)
        unit = unit_col.selectbox(
            "Unit",
            units,
            index=units.index(saved["unit"]) if saved else units.index(default_unit),
            key=f"dayof-unit|{sid}|{test}",
        )
        if st.form_submit_button(f"Record {test}"):
            if value is None:
                st.error(f"Enter a day-of value for {test} before recording it.")
            else:
                save_day_of_value(sid, test, value, unit)
                st.rerun()
    if saved:
        history = ss.get(f"history|{sid}|lab:{test}", [])
        if history:
            with st.popover("🕘 Change history"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")
    elif ss.get(f"dayof_pending|{sid}", {}).get(test):
        st.warning("Lab team has drawn this test; result pending. The to-do stays open until the result is entered.")
    if not saved:
        st.button(
            f"Lab team has drawn {test}; result pending",
            key=f"lab-pending|{sid}|{test}",
            on_click=mark_lab_pending,
            args=(sid, test),
            disabled=bool(ss.get(f"dayof_pending|{sid}", {}).get(test)),
        )


def session_ekg_form(sid):
    """Record a session-only, machine-generated reading and an optional nurse note."""
    saved = ss.get(f"session_ekg|{sid}", {})
    if saved and not ss.get(f"edit|{sid}|ekg"):
        entry_col, edit_col, history_col = st.columns([3, 1, 1])
        entry_col.caption(f"EKG · Computerized reading: {saved['reading']}")
        edit_col.button(
            "Make edit",
            key=f"edit-ekg|{sid}",
            on_click=open_session_edit,
            args=(sid, "ekg"),
        )
        history = ss.get(f"history|{sid}|ekg", [])
        if history:
            with history_col.popover("🕘 Change history"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")
        return
    options = [""] + list(C.COMPUTERIZED_EKG_GUIDANCE)
    with st.form(f"ekg-form|{sid}"):
        reading = st.selectbox(
            "Computerized reading from the EKG machine (not a clinician interpretation)",
            options,
            index=options.index(saved.get("reading", "")),
            format_func=lambda value: value or "Select a machine reading…",
            key=f"ekg-reading|{sid}",
        )
        note = st.text_area(
            "Optional pre-op nurse notation for anesthesia",
            value=saved.get("note", ""),
            max_chars=500,
            key=f"ekg-note|{sid}",
        )
        submitted = st.form_submit_button("Record EKG reading")
    if submitted:
        if reading:
            record_ekg_form(sid, reading, note)
            st.success("Machine reading recorded for this session.")
            st.rerun()
        if saved:
            record_ekg_form(sid, "", "")
            st.info("Session EKG reading cleared.")
            st.rerun()
        st.error("Choose a computerized machine reading before recording.")
    if saved:
        history = ss.get(f"history|{sid}|ekg", [])
        if history:
            with st.popover("🕘 Change history"):
                for change in history:
                    st.write(f"{change['timestamp']} · {change['user']} ({change['role']})")
                    st.write(f"{change['old_value']} → {change['new_value']}")
    if ss.get(f"session_ekg_pending|{sid}") and not saved:
        st.warning("EKG performed; machine reading pending. The to-do stays open until the reading is entered.")
    st.button(
        "EKG performed; machine reading pending",
        key=f"ekg-pending|{sid}",
        on_click=lambda: ss.__setitem__(f"session_ekg_pending|{sid}", True),
        disabled=bool(saved) or bool(ss.get(f"session_ekg_pending|{sid}")),
    )


def sign_in():
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown("### 🩺 Pre-Op Readiness Board")
        st.write("Enter your first name or a nickname to get your own example patient. "
                 "Anything you change only shows on your screen.")
        with st.form("join"):
            name = st.text_input("Your name", max_chars=40, placeholder="e.g. Sam")
            if st.form_submit_button("Get my patient", type="primary", width="stretch"):
                st.query_params["u"] = ROSTER.join(name.strip() or "Guest")  # in the URL so a refresh keeps the patient
                st.rerun()
        st.caption("Fictional patients · teaching rules, not clinical guidelines · not for patient care")


def start_clean():
    """Forget this tab's student work, but keep a project team unlock."""
    team = ss.get("team")
    ss.clear()
    if team:
        ss.team = True


def sign_out():
    st.query_params.clear()
    start_clean()


def reset_demo(archive):
    ROSTER.reset()
    if archive and os.path.exists(DECISIONS):
        with DECISIONS_LOCK:
            os.replace(DECISIONS, DECISIONS.replace(".csv", f"_{datetime.now():%Y%m%d_%H%M%S}.csv"))
    ss.reset_done = f"Reset at {datetime.now():%H:%M}. Open screens go back to sign-in within about 10 seconds."


def team_panel():
    """Sidebar controls for the project team, unlocked with PREOP_TEAM_CODE."""
    with st.sidebar:
        st.markdown("**Project team**")
        code = os.environ.get("PREOP_TEAM_CODE", "")
        if not code:
            st.caption("Add PREOP_TEAM_CODE to the app's secrets to turn on the team controls.")
            return
        if not ss.get("team"):
            entered = st.text_input("Team passcode", type="password")
            if entered and hmac.compare_digest(entered, code):
                ss.team = True
                st.rerun()
            elif entered:
                st.caption("Wrong passcode.")
            return
        st.caption(f"{len(ROSTER)} signed in")
        sure = st.checkbox("Sign everyone out and clear their changes")
        archive = st.checkbox("Also set aside saved decisions", help="Renames results/decisions.csv with today's date and time.")
        st.button("Reset demo for everyone", type="primary", disabled=not sure, on_click=reset_demo, args=(archive,), width="stretch")
        if ss.get("reset_done"):
            st.success(ss.reset_done)


@st.fragment(run_every=10)
def watch_for_reset():
    """Sends this screen back to sign-in soon after the team resets the demo, instead of waiting for a click."""
    if ROSTER.get(TOKEN) is None:
        st.rerun()


team_panel()

# Who is this? The token in the URL names the student and their assigned case.
TOKEN = st.query_params.get("u", "")
USER = ROSTER.get(TOKEN)
if USER is None:
    sign_in()
    st.stop()
if ss.get("me") != TOKEN:  # new student in this browser tab: start clean
    start_clean()
    ss.me = TOKEN
ME = USER["sid"]
watch_for_reset()

ss.setdefault("moves", {})  # demo schedule changes for this browser session: sid -> (date, time, room, kind)
MOVES = tuple(sorted((sid, *mv) for sid, mv in ss.moves.items()))
BOARD = {x["id"]: x for x in S.cases(MOVES)}


def with_session_work(case):
    """A board case with this browser session's completed work applied to its checklist, rules and state."""
    case_id = case["id"]
    completed = completed_actions(case_id)
    day_of_values = ss.get(f"dayof|{case_id}", {})
    consent_status = ss.get(f"consent_status|{case_id}")
    ekg = ss.get(f"session_ekg|{case_id}", {})
    chart_with_work = W.apply_completed_actions(
        D.build_chart(case_id), completed, ss.get(f"cpap_status|{case_id}"), day_of_values,
        consent_status, ekg.get("reading"), ekg.get("note"),
        ss.get(f"med-dose|{case_id}", {}), track_medication_doses=True)
    ekg_disposition = ss.get(f"ekg-disposition-value|{case_id}")
    if ekg_disposition:
        chart_with_work["session_ekg_anesthesia_disposition"] = ekg_disposition
    case = dict(case)
    case["reqs"] = [S.checklist_row(req, chart_with_work)
                    for req in C.applicable_requirements(chart_with_work)]
    case["rules"] = {}
    for role in C.ROLES:
        result = rules_next_steps(chart_with_work, role)
        case["rules"][role] = dict(
            status=result["status"],
            actions=[
                dict(code=a["code"], reason=a["reason"], evidence_ids=a["evidence_ids"],
                     priority=a["priority"])
                for a in result["actions"]
                if (role, a["code"]) not in completed
            ],
        )
    case["state"] = S.sched_state(case)
    case["state"] = {
        "move_later": "later",
        "reschedule": "resched",
        "clinical_hold": "hold",
    }.get(ekg_disposition, case["state"])
    return {k: case[k] for k in ("reqs", "rules", "state")}


@st.cache_resource
def untouched_readiness():
    """case id -> checklist, rules and state for a case no one has worked on in their session. These are the same
    for every student, so they are worked out once per server and shared, not redone for all 100 cases on every
    click in every session (that made the app stall when a class signed in at once). Never modify the values.
    The lock lets one session fill it in while the others wait, instead of all of them doing the same work."""
    return {}, threading.Lock()


# A case this session has changed has its id in a session key (dec|S012|..., dayof|S012, ...): only those are
# recomputed on each rerun.
UNTOUCHED, UNTOUCHED_LOCK = untouched_readiness()
touched = {part for key in ss.keys() if isinstance(key, str) for part in key.split("|")}
if any(i not in UNTOUCHED and i not in touched for i in BOARD):
    with UNTOUCHED_LOCK:
        for case_id, case in BOARD.items():
            if case_id not in UNTOUCHED and case_id not in touched:
                UNTOUCHED[case_id] = with_session_work(case)
for case_id, case in list(BOARD.items()):
    work = with_session_work(case) if case_id in touched else UNTOUCHED[case_id]
    BOARD[case_id] = dict(case, **work)
DAYS =sorted({x["case"]["surgery_date"] for x in BOARD.values()})
ss.setdefault("sid", ME)
ss.setdefault("view", "Patient chart")
ss.setdefault("role", "nurse")
ss.setdefault("day", BOARD[ss.sid]["case"]["surgery_date"])
ss.setdefault("results", {})
ss.setdefault("dec_time", {})


def open_chart(sid):
    """Callback: jump from the schedule to a patient's chart."""
    ss.sid, ss.view = sid, "Patient chart"


def open_day(day):
    ss.day = day


def pick(sid):
    ss.sid = sid


def apply_move(sid, to, also=()):
    """Apply one move, plus any that go with it (the cases a latex-allergy case goes ahead of)."""
    for i, t in [(sid, to), *also]:
        ss.moves[i] = (t["date"], t["time"], t["room"], t["kind"])


def apply_all(items):
    for g in items:
        if g["to"]:
            apply_move(g["x"]["id"], g["to"], g.get("also", ()))


def undo_move(sid):
    ss.moves.pop(sid, None)


def moved_text(x):
    """'Rescheduled from Mon Oct 19, 07:30 in Cardiac 1' and the like, or ''."""
    m = x.get("moved")
    if not m:
        return ""
    if m["kind"] == "hold":
        return f"Taken off the schedule (was {S.fmt_day(m['date'])}, {m['time']})"
    verb = {"resched": "Rescheduled", "later": "Moved later", "up": "Moved up"}[m["kind"]]
    src = f"{S.fmt_day(m['date'])}, {m['time']}" if m["date"] != x["case"]["surgery_date"] else m["time"]
    room = f" in {S.short_room(m['room'])}" if m["room"] != x["case"]["surgery_location"] else ""
    return f"{verb} from {src}{room}"


def keep(k, fallback):
    """Segmented controls can be clicked off; keep the last choice instead of None."""
    if ss.get(k) is None:
        ss[k] = ss.get(f"_{k}", fallback)
    ss[f"_{k}"] = ss[k]


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def table(rows, cols=None, hl=(), bad=()):
    """A plain HTML table; values of the `hl` columns that are in `bad` are shown in red. Used instead of
    st.dataframe, which makes each browser download a large extra script the first time it shows a table. Under
    classroom load that download timed out ("TypeError: Failed to fetch dynamically imported module")."""
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    cell = lambda r, c: ("<td style='color:#d0473b;font-weight:600'>" if c in hl and r.get(c) in bad else "<td>") + \
        esc("" if r.get(c) is None else str(r.get(c))) + "</td>"
    html("<div style='overflow-x:auto'><table class='ck'><tr>"
         + "".join(f"<th>{esc(c.replace('_', ' '))}</th>" for c in cols) + "</tr>"
         + "".join("<tr>" + "".join(cell(r, c) for c in cols) + "</tr>" for r in rows) + "</table></div>")


# ---------------------------------------------------------------------------
# Header: title and view switch, as on the demo page
# ---------------------------------------------------------------------------
top = st.columns([3, 2], vertical_alignment="center")
top[0].markdown("### 🩺 Pre-Op Readiness Board")
view = top[1].segmented_control("View", ["Patient chart", "OR schedule"], key="view", label_visibility="collapsed",
                                on_change=keep, args=("view", "Patient chart"))
mine = BOARD[ME]
me = st.columns([5, 1.3, 0.8], vertical_alignment="center")
me[0].markdown(f"👤 <b>{esc(USER['name'])}</b> · Your patient: <b>⭐ {esc(mine['patient']['name'])}</b> · "
               f"{esc(D.procedure_label(mine['case']))} · {S.fmt_day(mine['case']['surgery_date'])} {mine['case']['surgery_time']}",
               unsafe_allow_html=True)
me[1].button("Open my patient", on_click=open_chart, args=(ME,), width="stretch",
             disabled=ss.sid == ME and view == "Patient chart")
me[2].button("Sign out", on_click=sign_out, width="stretch")
with st.expander("What to try (about 3 minutes)", expanded=ss.sid == ME and not ss.moves):
    st.markdown(
        "1. Read the card at the top of your patient's **Pre-Op Readiness** tab: is the patient ready for surgery?\n"
        "2. Switch between **Pre-op nurse** and **Anesthesiologist**. What does each one need to do?\n"
        "3. **Accept** or **Decline** each next step. Accepted steps add tasks to your to-do list.\n"
        "4. If a new time is suggested, apply it, then open the **OR schedule** to see the change.\n\n"
        "Your changes only show on your screen. Classmates each have their own copy of the board.")
st.caption("Fictional patients · teaching rules, not clinical guidelines · not for patient care")
provider = default_provider()


# ---------------------------------------------------------------------------
# OR schedule
# ---------------------------------------------------------------------------
def month_calendar(day):
    y, m = int(day[:4]), int(day[5:7])
    by_day = {}
    for x in BOARD.values():
        if not x.get("off"):
            by_day.setdefault(x["case"]["surgery_date"], []).append(x["state"])
    cells = [f"<span class='w'>{w}</span>" for w in "MTWTFSS"]
    cells += ["<span></span>"] * calendar.monthrange(y, m)[0]
    for i in range(1, calendar.monthrange(y, m)[1] + 1):
        d = f"{y:04d}-{m:02d}-{i:02d}"
        sts = by_day.get(d)
        if not sts:
            cells.append(f"<span class='d off'>{i}</span>")
            continue
        flag = "s-resched" if {"resched", "hold"} & set(sts) else "s-later" if "later" in sts else ""
        cells.append(f"<span class='d has {'sel' if d == day else ''}'>{i}<small>{len(sts)}</small>"
                     f"{f'<i class={flag}></i>' if flag else ''}</span>")
    return (f"<b>{calendar.month_name[m]} {y}</b><div class='cal'>{''.join(cells)}</div>"
            "<div class='src' style='margin-top:6px'><span class='s-resched'>●</span> reschedule or hold "
            "<span class='s-later'>●</span> move later · number = cases</div>")


def timeline(cases, sugg):
    """Room-by-room grid, one row per 15 minutes from 07:00 to 18:00."""
    rooms = sorted({x["case"]["surgery_location"] for x in cases})
    g0, g1, step = S.to_min("07:00"), S.to_min("18:00"), 15
    nrows = (g1 - g0) // step
    row = lambda m: 2 + (m - g0) // step
    overlaps = lambda x: any(y is not x and y["case"]["surgery_location"] == x["case"]["surgery_location"]
                             and S.start(y) < S.end(x) and S.start(x) < S.end(y) for y in cases)
    parts = ["<div class='hd'></div>"] + [f"<div class='hd' style='grid-column:{i + 2}'>{esc(S.short_room(r))}</div>" for i, r in enumerate(rooms)]
    parts += [f"<div class='tm' style='grid-row:{row(m)} / span 4'>{S.hhmm(m)}</div>" for m in range(g0, g1, 60)]
    parts += [f"<div class='lane' style='grid-column:{i + 2};grid-row:2 / span {nrows}'></div>" for i in range(len(rooms))]
    for x in cases:
        stt, g = x["state"], sugg.get(x["id"])
        tip = f"{x['patient']['name']} · {D.procedure_label(x['case'])} · {S.span(S.start(x), S.dur(x))} ({S.dur_label(S.dur(x))}) · {S.SCHED[stt]}"
        parts.append(
            f"<div class='blk s-{stt}' title='{esc(tip, quote=True)}' style='grid-column:{rooms.index(x['case']['surgery_location']) + 2};"
            f"grid-row:{row(S.start(x))} / span {S.dur(x) // step}'><span class='tt'>{S.span(S.start(x), S.dur(x))}</span>"
            f"<span class='st'>{S.SCHED[stt]}{' · overlap' if overlaps(x) else ''}</span><b>{esc(x['patient']['name'])}</b>"
            f"<span class='pl'>{esc(D.procedure_label(x['case']))}</span>"
            + (f"<span class='mv'>Suggested: {esc(g['tag'].lower())}</span>" if g else "")
            + (f"<span class='mv'>↪ {esc(moved_text(x))}</span>" if x.get("moved") else "") + "</div>")
    return (f"<div class='og-wrap'><div class='og' style='grid-template-columns:52px repeat({len(rooms)}, minmax(118px, 1fr));"
            f"grid-template-rows:auto repeat({nrows}, var(--q))'>{''.join(parts)}</div></div>")


def schedule_view():
    if ss.day not in DAYS:
        ss.day = DAYS[0]
    di = DAYS.index(ss.day)
    cases = [x for x in BOARD.values() if x["case"]["surgery_date"] == ss.day and not x.get("off")]
    items = S.day_suggestions(ss.day, MOVES)
    sugg = {g["x"]["id"]: g for g in items}

    nav = st.columns([0.6, 5, 0.6, 3], vertical_alignment="center")
    nav[0].button("‹", disabled=di == 0, on_click=open_day, args=(DAYS[di - 1],), help="Previous surgery day")
    nav[1].subheader(f"{S.fmt_day(ss.day, long=True)} · {len(cases)} cases")
    nav[2].button("›", disabled=di == len(DAYS) - 1, on_click=open_day, args=(DAYS[min(di + 1, len(DAYS) - 1)],), help="Next surgery day")

    def day_label(d):
        sts = [x["state"] for x in BOARD.values() if x["case"]["surgery_date"] == d and not x.get("off")]
        flag = " 🔴" if {"resched", "hold"} & set(sts) else " 🟠" if "later" in sts else ""
        return f"{S.fmt_day(d)} · {len(sts)} cases{flag}"
    nav[3].selectbox("Go to day", DAYS, key="day", format_func=day_label, label_visibility="collapsed")

    counts = [(s, sum(x["state"] == s for x in cases)) for s in S.SCHED]
    html("<div class='legend'>" + "".join(f"<span class='s-{s}'><i></i>{S.SCHED[s]} {n}</span>" for s, n in counts if n) + "</div>")

    main, side = st.columns([3, 1.1])
    with main:
        html(timeline(cases, sugg))
        st.caption("Hover a block for details. Open any patient below.")
        order = sorted(cases, key=lambda x: (x["case"]["surgery_location"], S.start(x)))
        for i, x in enumerate(order):
            if i % 4 == 0:
                cols = st.columns(4)
            cols[i % 4].button(f"{ICON[x['state']]} {x['case']['surgery_time']} {'⭐ ' * (x['id'] == ME)}{x['patient']['name']}", key=f"go_{x['id']}",
                               on_click=open_chart, args=(x["id"],), width="stretch")
    with side:
        with st.container(border=True):
            html(month_calendar(ss.day))
        with st.container(border=True):
            st.markdown("**Suggested adjustments**")
            st.caption(f"{S.fmt_day(ss.day)} · based on readiness")
            if not items:
                st.write("No adjustments needed. Every case can go as scheduled.")
            elif sum(bool(g["to"]) for g in items) > 1:
                st.button(f"Apply all {sum(bool(g['to']) for g in items)} suggestions", type="primary", width="stretch",
                          on_click=apply_all, args=(items,))
            for g in items:
                x = g["x"]
                html(f"<div class='sg s-{x['state']}'><b>{esc(x['patient']['name'])}</b> "
                     f"<span class='src'>{S.span(S.start(x), S.dur(x))} · {esc(S.short_room(x['case']['surgery_location']))}</span>"
                     f"<div><b>{esc(g['text'])}</b></div><div class='src'>{esc(g['reason'])}</div></div>")
                b = st.columns(2)
                if g["to"]:
                    b[0].button("Take off schedule" if g["to"]["kind"] == "hold" else g["tag"], key=f"ap_{x['id']}",
                                on_click=apply_move, args=(x["id"], g["to"], g.get("also", ())), width="stretch")
                b[1].button("Open chart", key=f"sg_{x['id']}", on_click=open_chart, args=(x["id"],), width="stretch")
            st.caption("Suggestions only. Confirm with the surgeons, anesthesia and the patients before changing the schedule.")
        done = [x for x in BOARD.values() if x.get("moved") and ss.day in (x["case"]["surgery_date"], x["moved"]["date"])]
        if done:
            with st.container(border=True):
                st.markdown("**Changes made**")
                for x in sorted(done, key=S.start):
                    r = st.columns([3, 1], vertical_alignment="center")
                    r[0].markdown(f"**{x['patient']['name']}** · {S.fmt_day(x['case']['surgery_date'])} {x['case']['surgery_time']}  \n"
                                  f"<span class='src'>{esc(moved_text(x))}</span>", unsafe_allow_html=True)
                    r[1].button("Undo", key=f"un_{x['id']}", on_click=undo_move, args=(x["id"],))
        if ss.moves:
            st.button(f"Reset all schedule changes ({len(ss.moves)})", on_click=ss.moves.clear)


if view == "OR schedule":
    schedule_view()
    st.stop()

# ---------------------------------------------------------------------------
# Patient chart: scrolling patient list on the left, chart on the right
# ---------------------------------------------------------------------------
rail, main = st.columns([1, 3.2], gap="medium")
with rail:
    with st.container(border=True):
        pf = st.selectbox("Procedure", [""] + list(C.PROCEDURES), format_func=lambda s: s or "All procedures")
        sf = st.selectbox("Readiness", [""] + list(S.SCHED), format_func=lambda s: S.SCHED.get(s, "Any status"))
        rows = sorted((x for x in BOARD.values() if (not pf or x["case"]["procedure"] == pf) and (not sf or x["state"] == sf)),
                      key=lambda x: (x["case"]["surgery_date"], x["case"]["surgery_time"]))
        st.caption(f"{len(rows)} cases")
        with st.container(height=720, border=False, key="plist"):
            for x in rows:
                tag = f"{S.open_count(x)} open" if x["state"] == "open" else S.SCHED[x["state"]]
                tag += " · off schedule" if x.get("off") else " · ↪ moved" if x.get("moved") else ""
                st.button(f"{ICON[x['state']]} {'⭐ ' * (x['id'] == ME)}**{x['patient']['name']}** ·{x['case']['surgery_date'][5:]} {x['case']['surgery_time']} · "
                          f"{D.procedure_label(x['case'])} · {tag}", key=f"pt_{x['id']}", on_click=pick, args=(x["id"],),
                          type="primary" if x["id"] == ss.sid else "secondary", width="stretch")
            if not rows:
                st.caption("No cases match.")
        st.caption("⭐ your patient · 🟢 Ready · ⚪ items outstanding · 🟠 move later · 🔴 reschedule · 🟣 clinical hold")

with main:
    sid = ss.sid
    x = BOARD[sid]
    completed = completed_actions(sid)
    consent_status = ss.get(f"consent_status|{sid}")
    ekg = ss.get(f"session_ekg|{sid}", {})
    chart = W.apply_completed_actions(
        D.build_chart(sid), completed, ss.get(f"cpap_status|{sid}"), ss.get(f"dayof|{sid}", {}),
        consent_status, ekg.get("reading"), ekg.get("note"),
        ss.get(f"med-dose|{sid}", {}), track_medication_doses=True)
    ekg_disposition = ss.get(f"ekg-disposition-value|{sid}")
    if ekg_disposition:
        chart["session_ekg_anesthesia_disposition"] = ekg_disposition
    c = dict(chart["case"], **{k: x["case"][k] for k in ("surgery_date", "surgery_time", "surgery_location")})  # after any move
    p = chart["patient"]
    proc = D.procedure_label(c)
    when = f"{c['surgery_date']} {S.span(S.start(x), S.dur(x))}"

    sg = S.suggested_time(x, MOVES)
    suggestion_html = (
        f'<div class="sugg s-{sg["cls"]}"><span class="lb">Suggested new time</span>'
        f'<b>{S.fmt_day(sg["date"])} · {sg["time"]} · {esc(sg["room"])}</b>'
        f'<span class="src"> {esc(sg["why"])}</span></div>'
        if sg else ""
    )
    schedule_change_html = (
        f'<div class="sugg s-{x["state"]}"><span class="lb">Schedule changed</span>'
        f'<b>{esc(moved_text(x))}</b></div>'
        if x.get("moved") else ""
    )
    banner_html = (
        f'<div class="banner"><span class="nm">{esc(p["name"])}</span>{esc(p["age"])} y/o '
        f'{esc(p["sex"])} · MRN {esc(p["mrn"])} · BMI {esc(p["bmi"])} · '
        f'<span class="{"" if p["allergies"].startswith("No known") else "allergy"}">'
        f'Allergies: {esc(p["allergies"])}</span><br>'
        f'<span class="mt"><b>{esc(proc)}</b> · {when} ({S.dur_label(S.dur(x))}) · '
        f'{esc(c["surgery_location"])} · {esc(c["surgeon"])} · '
        f'Anesthesia: {esc(c["planned_anesthesia"])} · Post-op: '
        f'{esc(c["postoperative_location"])}</span>{suggestion_html}{schedule_change_html}</div>'
    )
    html(banner_html)
    act = st.columns([1.6, 1.6, 3])
    if sg:
        act[0].button(f"Reschedule to {S.fmt_day(sg['date'])}, {sg['to']['time']}" if sg["cls"] == "resched"
                      else f"Make first case ({sg['to']['time']})" if sg.get("first") else f"Move to {sg['to']['time']} today",
                      key="sg_apply", type="primary", on_click=apply_move, args=(sid, sg["to"], sg.get("also", ())), width="stretch")
    elif x["state"] == "hold" and not x.get("moved"):
        act[0].button("Take off schedule (hold)", key="sg_hold", on_click=apply_move,
                      args=(sid, dict(date=None, time=None, room=None, kind="hold")), width="stretch")
    if x.get("moved"):
        act[0].button("Undo schedule change", key="sg_undo", on_click=undo_move, args=(sid,), width="stretch")
    if sg or x.get("moved"):
        act[1].button("See it on the OR schedule", key="sg_sched", width="stretch",
                      on_click=lambda: ss.update(view="OR schedule", day=x["case"]["surgery_date"]))

    ctl = st.columns([2, 1.3], vertical_alignment="center")
    role = ctl[0].segmented_control("Role", list(ROLE_LABEL), format_func=ROLE_LABEL.get, key="role",
                                    label_visibility="collapsed", on_change=keep, args=("role", "nurse"))
    ai = ctl[1].toggle("AI review (LLM)", value=provider != "mock", key="ai")
    engine = "llm" if ai else "rules"
    if ai and provider == "mock":
        ctl[1].caption("No API key found. Showing the rules-only check.")

    chart_sections = ["Pre-Op Readiness", "Labs", "Medications", "Tests & Imaging", "Consents & Blood", "H&P"]
    ss.setdefault("chart-section", chart_sections[0])
    nav_columns = st.columns([1.5, 0.6, 1, 1.35, 1.4, 0.5], gap="small")
    for column, section in zip(nav_columns, chart_sections):
        column.button(
            section,
            key=f"chart-nav|{sid}|{section}",
            type="primary" if ss["chart-section"] == section else "secondary",
            width="stretch",
            on_click=select_chart_tab,
            args=(section,),
        )


    def top_card(status, n, headline):
        """Ready card, reschedule card, or a plain status bar, as on the demo page."""
        open_items = S.open_reqs(x)
        done = len(x["reqs"]) - len(open_items)
        if ekg_disposition in {"move_later", "reschedule", "clinical_hold"}:
            slow = [r for r in open_items if S.takes_days(r)]
            card_class = {
                "move_later": "later",
                "reschedule": "resched",
                "clinical_hold": "hold",
            }[ekg_disposition]
            pending_outside_html = ""
            if slow:
                pending_items = "".join(
                    f"<li><b>{esc(r['item'])}</b>"
                    f"<span class='lead days'>Pending outside completion</span></li>"
                    for r in slow
                )
                pending_outside_html = (
                    "<div class='sugg s-resched'>"
                    "<span class='lb'>Rescheduling reminder</span>"
                    "<b>Rescheduling may still be needed while outside work is pending:</b>"
                    f"<ul>{pending_items}</ul>"
                    "<span class='src'>This reminder remains alongside the anesthesia disposition. "
                    "Reassess surgical timing after these items are completed.</span></div>"
                )
            return (
                f"<div class='card s-{card_class}'><div class='ti'>"
                f"Anesthesia disposition: {esc(EKG_DISPOSITION_LABELS[ekg_disposition])}</div>"
                f"<div class='sub'>Recorded for this session after review of the computerized EKG reading.</div>"
                f"<div class='fx'><b>{esc(proc)}</b> · Current surgery: {when} · "
                f"{esc(c['surgery_location'])}</div>"
                f"{pending_outside_html}"
                f"<div class='src'>This disposition does not itself change the OR schedule. "
                f"Confirm timing with the care team.</div></div>"
            )
        if not n and status == "Ready":
            return (f"<div class='card s-ready'><div class='ti'>✓ Ready for surgery</div>"
                    f"<div class='sub'>Nothing outstanding for the {ROLE_LABEL[role].lower()}</div>"
                    f"<div class='fx'><b>{esc(proc)}</b> · Surgery: {when} · {esc(c['surgery_location'])} · "
                    f"Checklist {done} of {len(x['reqs'])} complete</div></div>")
        if (x["state"] in ("resched", "later", "hold") and open_items) or status == "Recommend hold":
            slow = [r for r in open_items if S.takes_days(r)]
            hold = status == "Recommend hold"
            hard = x["state"] == "resched"
            note = ("A clinical finding recommends holding this case. Review with the surgeon and anesthesia before choosing a new date."
                    if hold and not slow else
                    f"{' and '.join(r['item'] for r in slow)} {'is' if len(slow) == 1 else 'are'} unlikely to be ready in time. Talk with the surgeon about a new date."
                    if slow else
                    "Latex allergy: the patient has to be the first case of the day, so there is no time to wait for results. "
                    "Choose a day when they can go first." if hard else
                    "Everything can be done on the day. A later slot gives time for results before the patient goes to the OR.")
            items = "".join(f"<li><span class='ck-{r['status']}'>{CK[r['status']][1]}</span> <b>{esc(r['item'])}</b>"
                            f"<span class='lead {'days' if S.takes_days(r) else ''}'>{S.lead_label(r)}</span></li>"
                            for r in open_items)
            title = ({"resched": "Rescheduled", "later": "Moved later today", "up": "Moved up", "hold": "Off the schedule"}[x["moved"]["kind"]]
                     if x.get("moved") else "Clinical hold — team review required" if hold else
                     "Consider rescheduling" if hard else "Consider moving later today")
            k = len(open_items)
            card_class = "hold" if hold else "resched" if hard else "later"
            schedule_text = (
                f"Suggested new time: {S.fmt_day(sg['date'])} · {sg['time']} · {esc(sg['room'])}"
                if hard and sg else f"Surgery: {when} · {esc(c['surgery_location'])}"
            )
            external_work_note = (
                f"Nothing outstanding for the {ROLE_LABEL[role].lower()}; "
                f"{' and '.join(r['item'] for r in slow)} still requires outside completion."
                if not n and slow else note
            )
            return (f"<div class='card s-{card_class}'><div class='ti'>{title}</div>"
                    f"<div class='sub'>{k} pre-op item{'s' * (k != 1)} {'is' if k == 1 else 'are'} not ready for {esc(proc)} at {c['surgery_date']} {c['surgery_time']} · {esc(status)}</div>"
                    f"<div class='fx'><b>{schedule_text}</b></div>"
                    f"<ul>{items}</ul><div class='src'>{esc(external_work_note)}</div></div>")
        return (f"<div class='bar s-{STATUS_CLS.get(status, 'open')}'>{esc(status)} "
                f"<span>· {esc(headline)} · Surgery: {when} · {esc(c['surgery_location'])}</span></div>")


    def checklist_html():
        done = sum(r["status"] == "ok" for r in x["reqs"])
        rows = "".join(f"<tr><td class='ck-{r['status']}'><b>{CK[r['status']][0]} {CK[r['status']][1]}</b></td><td><b>{esc(r['item'])}</b></td>"
                       f"<td>{esc(r['note'])}</td><td class='src'>{esc(r['why'])}</td></tr>" for r in x["reqs"])
        return (f"<b>Pre-op checklist</b> <span class='src'>· {done} of {len(x['reqs'])} complete</span>"
                f"<table class='ck'><tr><th>Status</th><th>Item</th><th>On file</th><th>Needed because</th></tr>{rows}</table>")

    def show_session_work(item_types):
        items = [row["item"] for row in chart.get("session_completed_items", [])
                 if row["type"] in item_types]
        if items:
            st.caption("Completed in this session (not saved to the source dataset): " + ", ".join(items))


    def stamp(dk):
        ss.dec_time[dk] = datetime.now().strftime("%b %d %H:%M")


    if ss["chart-section"] == "Pre-Op Readiness":
        key = (sid, role, engine)
        if key not in ss.results and not (engine == "llm" and provider != "mock"):
            ss.results[key] = run_case(sid, role=role, engine=engine)
        res = ss.results.get(key)
        if engine == "llm" and provider != "mock":
            if st.button("Run the AI review again" if res else f"Run AI readiness review for the {ROLE_LABEL[role].lower()}", type="primary"):
                with st.spinner("Reading the chart (Modules 2-4). This can take a minute when many people run reviews at once…"):
                    try:
                        with AI_SLOTS:
                            ss.results[key] = res = run_case(sid, role=role, engine="llm", llm=LLM(), use_cache=res is None)
                    except Exception as e:  # rate limit or network error after retries: keep the page usable
                        st.error(f"The AI review did not finish ({type(e).__name__}). Try again in a minute.")
        if engine == "rules" or provider == "mock":
            steps = rules_next_steps(chart, role)
            res = dict(engine="rules" if engine == "rules" else "mock (no API key: rules output shown)",
                       summary=rules_summary(chart, role, steps), next_steps=steps)
        elif res is None:
            steps = rules_next_steps(chart, role)
            res = dict(engine="rules", summary=rules_summary(chart, role, steps), next_steps=steps)
            st.caption("Showing the rules-only check until the AI review is run.")
        res = dict(res)
        steps = dict(res["next_steps"])
        session_findings = []
        session_ids = set()
        if role == "anesthesia":
            session_ids.update(row["lab_id"] for row in chart.get("session_day_of_labs", []))
        session_ids.update(row["test_id"] for row in chart.get("session_machine_ekgs", []))
        held_med_ids = medication_ids_for_action(chart, "VERIFY_MEDICATION_LAST_DOSE")
        session_ids.update(held_med_ids)
        if session_ids or consent_status in ("signed", "refused"):
            rule_steps = rules_next_steps(chart, role)
            session_findings = [
                finding for finding in rule_steps.get("findings", [])
                if (
                    session_ids.intersection(finding["evidence_ids"])
                    and (role == "nurse" or finding.get("finding_code") != "MEDICATION_LAST_DOSE")
                ) or (
                    role == "anesthesia"
                    and finding.get("finding_code") == "ANESTHESIA_CONSENT_REFUSED"
                )
            ]
            existing_findings = {finding.get("finding_code") for finding in steps.get("findings", [])}
            base_findings = [
                finding for finding in steps.get("findings", [])
                if not (consent_status == "signed"
                        and finding.get("finding_code") == "MISSING:Anesthesia consent")
            ]
            steps["findings"] = [
                *base_findings,
                *(finding for finding in session_findings
                  if finding.get("finding_code") not in existing_findings),
            ]
            existing_actions = {action["code"] for action in steps.get("actions", [])}
            base_actions = [
                action for action in steps.get("actions", [])
                if not (consent_status == "signed"
                        and action["code"] in {"OBTAIN_ANESTHESIA_CONSENT", "NOTIFY_ANESTHESIA_CONSENT"})
            ]
            steps["actions"] = [
                *base_actions,
                *(action for action in rule_steps["actions"]
                  if action["code"] not in existing_actions
                  and (session_ids.intersection(action["evidence_ids"])
                       or (role == "anesthesia" and consent_status == "refused"
                           and action["code"] == "RESCHEDULE_AFTER_CONSENT_REFUSAL"))),
            ]
            if steps.get("findings"):
                steps["status"] = max(
                    [steps.get("status", "Ready"),
                     C.status_from_findings(steps["findings"])],
                    key=C.STATUS_ORDER.index,
                )
            elif consent_status == "signed" and steps.get("status") == "Outstanding items":
                steps["status"] = rule_steps["status"]
        if role == "anesthesia" and ss.get(f"cpap_status|{sid}") == "not_brought":
            rule_steps = rules_next_steps(chart, role)
            cpap_findings = [f for f in rule_steps.get("findings", [])
                             if f["finding_code"] == "CPAP_NOT_BROUGHT"]
            steps["findings"] = [*steps.get("findings", []), *cpap_findings]
            session_findings.extend(cpap_findings)
            known_codes = {a["code"] for a in steps["actions"]}
            steps["actions"] = [*steps["actions"],
                                *(a for a in rule_steps["actions"]
                                  if a["code"] == "CPAP_NOT_BROUGHT" and a["code"] not in known_codes)]
        completed_for_role = {code for completed_role, code in completed if completed_role == role}
        steps["actions"] = [a for a in steps["actions"] if a["code"] not in completed_for_role]
        existing_codes = {action["code"] for action in steps["actions"]}
        for code, (action_role, text) in C.ACTION_CATALOG.items():
            if (action_role == role and ss.get(f"dec|{sid}|{role}|{code}") == "Accept"
                    and code not in completed_for_role and code not in existing_codes):
                evidence = []
                if code == "OBTAIN_EKG":
                    evidence = [row["test_id"] for row in chart.get("session_machine_ekgs", [])]
                elif code in {"NOTIFY_EKG_ABNORMALITY", "REVIEW_COMPUTERIZED_EKG"}:
                    evidence = [row["test_id"] for row in chart.get("session_machine_ekgs", [])]
                elif code == "VERIFY_MEDICATION_LAST_DOSE":
                    evidence = held_med_ids
                steps["actions"].append(dict(
                    code=code, reason=text, evidence_ids=evidence, priority="medium",
                ))
        res["next_steps"] = steps
        summ = res["summary"]
        n = len(steps["actions"])
        html(top_card(steps["status"], n, summ.get("headline") or f"{n} item{'s' * (n != 1)} to address before surgery."))
        st.caption(f"{ROLE_LABEL[role]} view · engine: {res['engine']} · {steps.get('status_reason', '')}")
        if role == "anesthesia" and chart.get("session_machine_ekgs"):
            review_completed = ("anesthesia", "REVIEW_COMPUTERIZED_EKG") in completed
            if review_completed:
                saved_disposition = ss.get(f"ekg-disposition-value|{sid}")
                options = ["proceed", "move_later", "reschedule", "clinical_hold"]
                st.selectbox(
                    "Anesthesia disposition after EKG review",
                    options,
                    index=options.index(saved_disposition) if saved_disposition else None,
                    format_func=EKG_DISPOSITION_LABELS.get,
                    key=f"ekg-disposition|{sid}",
                    on_change=save_ekg_disposition,
                    args=(sid,),
                    placeholder="Select a disposition…",
                    help="This prototype records the anesthesiologist's choice; it does not interpret the machine reading or change the OR schedule.",
                )
            else:
                st.caption("Complete the anesthesia EKG review to-do before recording a disposition.")
        for finding in session_findings:
            if finding.get("finding_code") == "COMPUTERIZED_EKG_REVIEW":
                reading = next(
                    (row["machine_reading"] for row in chart.get("session_machine_ekgs", [])
                     if row["test_id"] in finding["evidence_ids"]),
                    "available",
                )
                st.info(f"New EKG reading: {reading}")
                st.button(
                    "View details in Tests & Imaging",
                    key=f"view-ekg|{sid}",
                    on_click=select_chart_tab,
                    args=("Tests & Imaging",),
                )
            elif finding.get("finding_code") == "MEDICATION_DOSE_WITHIN_HOLD":
                medication_ids = set(finding["evidence_ids"])
                for dose in chart.get("session_medication_doses", []):
                    if dose["medication_id"] in medication_ids:
                        st.info(f"{dose['medication_name']} taken within hold period.")
            else:
                st.warning(f"Rule finding: {finding['detail']}")

        dkey = lambda code: f"dec|{sid}|{role}|{code}"
        left, right = st.columns([1, 1.15])
        with left:
            accepted = [a for a in steps["actions"] if ss.get(dkey(a["code"])) == "Accept"]
            if n or completed_for_role:
                with st.container(border=True):
                    task_count = done = 0
                    for action in accepted:
                        code = action["code"]
                        if code == "BRING_CPAP":
                            task_count += 1
                            done += ss.get(f"cpap_status|{sid}") in ("brought", "not_brought")
                        elif code == "OBTAIN_ANESTHESIA_CONSENT":
                            task_count += 2
                            done += 2 if ss.get(f"consent_status|{sid}") in ("signed", "refused") else 0
                        else:
                            tasks, _ = action_tasks_for(sid, role, code, chart)
                            task_count += len(tasks)
                            done += sum(bool(ss.get(f"todo|{sid}|{role}|{code}|{i}"))
                                        for i in range(len(tasks)))
                    st.markdown(f"**To-do · {ROLE_LABEL[role]}**" + (f" <span class='src'>· {done} of {task_count} done</span>" if task_count else ""),
                                unsafe_allow_html=True)
                    if completed_for_role:
                        st.markdown("**Completed in this session**")
                        for code in sorted(completed_for_role):
                            st.markdown(f"- ✓ {esc(action_text(code))}")
                    if not accepted:
                        st.caption("Accept a next step to add its tasks here.")
                    for a in accepted:
                        todo_steps, closes = action_tasks_for(sid, role, a["code"], chart)
                        st.markdown(f"<span class='src'><b>{esc(action_text(a['code']))}</b></span>", unsafe_allow_html=True)
                        if a["code"] == "BRING_CPAP":
                            st.radio("Did the patient bring their CPAP machine, mask and settings?",
                                     ["brought", "not_brought"], index=None,
                                     format_func=lambda value: {
                                         "brought": "Yes — patient brought CPAP",
                                         "not_brought": "No — patient did not bring CPAP",
                                     }[value],
                                     key=f"cpap|{sid}", on_change=mark_cpap_status, args=(sid,))
                            cpap_status = ss.get(f"cpap_status|{sid}")
                            if cpap_status == "brought":
                                st.caption("Recorded: patient brought CPAP.")
                            elif cpap_status == "not_brought":
                                st.caption("Recorded: patient did not bring CPAP. Anesthesia will see a rule finding.")
                        elif a["code"] == "OBTAIN_ANESTHESIA_CONSENT":
                            st.markdown("**Did the patient sign the anesthesia consent?**")
                            saved_answer = ss.get(f"consent-answer-value|{sid}")
                            st.radio(
                                "Consent response",
                                ["yes", "no"],
                                index=["yes", "no"].index(saved_answer) if saved_answer else None,
                                format_func=lambda value: {
                                    "yes": "Yes — signed",
                                    "no": "No — not signed",
                                }[value],
                                key=f"consent-answer|{sid}",
                                on_change=mark_consent_answer,
                                args=(sid,),
                                label_visibility="collapsed",
                            )
                            if ss.get(f"consent-answer|{sid}") == "no":
                                saved_outcome = ss.get(f"consent-outcome-value|{sid}", "")
                                outcomes = ["", "pending", "refused"]
                                st.selectbox(
                                    "If not signed",
                                    outcomes,
                                    index=outcomes.index(saved_outcome),
                                    format_func=lambda value: {
                                        "": "Choose whether consent is pending or refused…",
                                        "pending": "Still discussing / not yet signed",
                                        "refused": "Patient refuses to sign",
                                    }[value],
                                    key=f"consent-outcome|{sid}",
                                    on_change=mark_consent_outcome,
                                    args=(sid,),
                                )
                            consent_status = ss.get(f"consent_status|{sid}")
                            if consent_status == "signed":
                                st.caption("Signed consent is reflected in the chart and pre-op checklist for this session.")
                            elif consent_status == "refused":
                                st.warning("Patient refusal is documented for this session. The case is on clinical hold pending team review.")
                            else:
                                st.caption("Pending or unanswered consent remains missing; it is not treated as signed.")
                        elif role == "nurse" and a["code"] == "OBTAIN_EKG":
                            for i, task in enumerate(todo_steps):
                                st.checkbox(task, key=f"todo|{sid}|{role}|{a['code']}|{i}",
                                            on_change=mark_action_complete, args=(sid, role, a["code"]))
                            session_ekg_form(sid)
                        elif a["code"] == "VERIFY_MEDICATION_LAST_DOSE":
                            for i, task in enumerate(todo_steps):
                                st.checkbox(task, key=f"todo|{sid}|{role}|{a['code']}|{i}",
                                            on_change=mark_action_complete, args=(sid, role, a["code"]))
                            for med_id in medication_ids_for_action(chart, a["code"]):
                                medication = next(row for row in chart["meds"] if row["medication_id"] == med_id)
                                medication_dose_form(sid, medication, c["surgery_date"])
                        else:
                            for i, s in enumerate(todo_steps):
                                st.checkbox(s, key=f"todo|{sid}|{role}|{a['code']}|{i}",
                                            on_change=mark_action_complete, args=(sid, role, a["code"]))
                        if a["code"] not in {"BRING_CPAP", "OBTAIN_ANESTHESIA_CONSENT"}:
                            checks_done = all(
                                ss.get(f"todo|{sid}|{role}|{a['code']}|{i}")
                                for i in range(len(todo_steps))
                            )
                            if checks_done and not action_inputs_ready(sid, a["code"], chart):
                                st.caption("Tasks checked · waiting for the required result or information.")
                            elif checks_done:
                                st.caption(f"Tasks done · waiting for the chart: {closes}")
                    if role == "nurse":
                        day_of_tests = dict.fromkeys(
                            test for action in accepted
                            for test in W.DAY_OF_LAB_ACTIONS.get(action["code"], ())
                        )
                        if day_of_tests:
                            st.markdown("**Day-of lab values**")
                            st.caption("Values are session-only. Existing teaching-rule thresholds flag results for anesthesia review.")
                            for test in day_of_tests:
                                day_of_value_form(sid, test)
            with st.container(border=True):
                for sec in summ.get("sections", []):
                    st.markdown(f"**{sec['title']}**")
                    for b in sec.get("bullets", []):
                        st.markdown(f"- {b}")
                st.markdown("**Key values**")
                rows = []
                for t in KEY_TESTS[role]:
                    lab = C.latest_lab(chart, t)
                    if lab:
                        rows.append(dict(Test=t, Value=f"{lab['result_value']} {'' if lab['unit'] == 'text' else lab['unit']}",
                                         Flag=lab["flag"], Date=lab["collection_date"],
                                         Prior=(f"{lab['prior_value']} {lab['prior_unit']} · {lab['prior_date']}"
                                                if lab.get("session_day_of") and lab.get("prior_value") else ""),
                                         ID=lab["lab_id"]))
                for d in chart["diagnostics"]:
                    if role == "anesthesia" or d["test_type"] == "EKG":
                        rows.append(dict(Test=d["test_type"], Value=(f"{d['result_value']} {d['result_unit']}".strip() or d["interpretation"]),
                                         Flag="New" if d["compared_to_prior"] == "New finding" else "", Date=d["test_date"], ID=d["test_id"]))
                if rows:
                    table(rows, hl=("Flag",), bad=("H", "L", "Critical", "Abnormal", "New"))
                else:
                    st.caption("No values in chart.")

        with right:
            st.markdown(f"**Next steps · {ROLE_LABEL[role]}**")
            if not n:
                st.success("Nothing outstanding.")
            for a in steps["actions"]:
                dk = dkey(a["code"])
                badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(a.get("priority"), "⚪")
                with st.container(border=True):
                    st.markdown(f"{badge} **{action_text(a['code'])}**")
                    st.caption(f"{a.get('reason', '')} · Evidence: {', '.join(a.get('evidence_ids', [])) or '-'}")
                    dec = st.radio("Decision", ["Pending", "Accept", "Decline"], horizontal=True, key=dk,
                                   label_visibility="collapsed", on_change=stamp, args=(dk,))
                    t = f" · {ss.dec_time[dk]}" if dk in ss.dec_time else ""
                    if dec == "Accept":
                        st.markdown(f"<span class='s-later' style='color:var(--c);font-weight:600'>Accepted{t} · still open · tasks added to your to-do list</span>"
                                    f"<br><span class='src'><b>Closes when:</b> {esc(C.ACTION_FOLLOW_UP.get(a['code'], ([], ''))[1])}</span>",
                                    unsafe_allow_html=True)
                    elif dec == "Decline":
                        st.caption(f"Declined{t}")
                        st.selectbox("Reason", [""] + DECLINE_REASONS, key=f"why|{dk}", format_func=lambda r: r or "Choose a reason…")
            if steps.get("other_considerations"):
                st.markdown("**Other considerations**")
                for o in steps["other_considerations"]:
                    st.markdown(f"- {o}")
            if n and st.button("Save decisions"):
                os.makedirs(os.path.dirname(DECISIONS), exist_ok=True)
                with DECISIONS_LOCK:  # one writer at a time so rows from different users don't interleave
                    new = not os.path.exists(DECISIONS)
                    with open(DECISIONS, "a", newline="") as f:
                        w = csv.writer(f)
                        if new:
                            w.writerow(["timestamp", "user", "surgery_id", "role", "engine", "action_code", "decision", "decline_reason"])
                        for a in steps["actions"]:
                            dk = dkey(a["code"])
                            w.writerow([datetime.now().isoformat(timespec="seconds"), USER["name"], sid, role, res["engine"], a["code"],
                                        ss.get(dk, "Pending"), ss.get(f"why|{dk}", "")])
                st.success(f"Decisions saved to {os.path.relpath(DECISIONS, D.ROOT)}.")

        with st.container(border=True):
            html(checklist_html())
        if res.get("qa"):
            with st.expander("Module 2 answers (question answering, with evidence)"):
                for a in res["qa"].get("answers", []):
                    st.markdown(f"**{a.get('question_id')}** {a.get('answer')}  \n`{', '.join(a.get('evidence_ids', []))}`")
        st.caption("Every suggestion needs human review.")

    # ---------------------------------------------------------------------------
    # Chart tabs
    # ---------------------------------------------------------------------------
    def show(rows, cols, hl=None, title=None):
        if title:
            st.markdown(f"**{title}**")
        if not rows:
            st.caption("None in chart.")
            return
        table(rows, cols, hl or (), {"H", "L", "Critical", "Abnormal", "Missing", "Refused", "Pending", "Positive", "New finding"})


    if ss["chart-section"] == "Labs":
        show(sorted(chart["labs"], key=lambda r: (r["panel"], r["test_name"])),
             ["panel", "test_name", "result_value", "unit", "reference_low", "reference_high", "flag", "collection_date", "lab_id"], ["flag"])
        show_session_work({"lab"})
        editable_tests = sorted(set(
            test for code in C.ACTION_FOLLOW_UP
            for test in W.DAY_OF_LAB_ACTIONS.get(code, ())
            if test in ss.get(f"dayof|{sid}", {})
        ))
        if role == "nurse" and editable_tests:
            st.markdown("**Edit session day-of results**")
            for test in editable_tests:
                day_of_value_form(sid, test)
    if ss["chart-section"] == "Medications":
        show([dict(m, preop_instruction=m["preop_instruction"] or "⚠ none documented") for m in chart["meds"]],
             ["medication_name", "dose", "route", "frequency", "preop_instruction", "medication_id"])
        if role == "nurse":
            held_med_ids = medication_ids_for_action(chart, "VERIFY_MEDICATION_LAST_DOSE")
            saved_med_ids = set(ss.get(f"med-dose|{sid}", {}))
            edit_ids = sorted(saved_med_ids.intersection(held_med_ids))
            if edit_ids:
                st.markdown("**Edit session last-dose entries**")
                for med_id in edit_ids:
                    medication = next(row for row in chart["meds"] if row["medication_id"] == med_id)
                    medication_dose_form(sid, medication, c["surgery_date"])
    if ss["chart-section"] == "Tests & Imaging":
        show(chart["diagnostics"], ["test_type", "test_date", "result_value", "result_unit", "interpretation", "compared_to_prior", "test_id"],
             ["compared_to_prior"], title="Diagnostic tests")
        if role == "nurse":
            session_ekg_form(sid)
        show(chart["imaging"], ["imaging_type", "imaging_date", "report", "imaging_id"], title="Imaging")
        show(chart["clearances"], ["clearance_type", "status", "requested_date", "completed_date", "assessment_note", "clearance_id"], ["status"],
             title="Clearances")
        show_session_work({"diagnostic", "imaging", "clearance"})
    if ss["chart-section"] == "Consents & Blood":
        show(chart["consents"], ["consent_type", "status", "signed_date", "consent_id"], ["status"], title="Consents")
        show_session_work({"consent", "blood"})
        if chart["blood"]:
            show([chart["blood"]], ["abo_rh", "antibody_screen", "type_screen_date", "type_screen_expires", "prbc_crossmatched_units",
                                    "ffp_units_available", "platelet_units_available"], ["antibody_screen"], title="Blood bank")
        else:
            st.caption("No blood bank record (not required for this procedure).")
    if ss["chart-section"] == "H&P":
        if chart["notes"]:
            for note in chart["notes"]:
                st.text(note["note_text"])
        else:
            st.warning("No H&P in chart.")
        show_session_work({"note"})
        st.caption(f"Anesthesia history: {p['anesthesia_complication_history']}")
