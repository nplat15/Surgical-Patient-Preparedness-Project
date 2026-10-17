"""
Mock EHR "Pre-Op Readiness" tab.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...        (or OPENAI_API_KEY + PREOP_LLM_PROVIDER=openai + PREOP_LLM_MODEL=...)
    streamlit run app.py

Without an API key the app still runs using the rules-only engine.
Fully synthetic patients. Teaching rules, not clinical guidelines.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from preop import criteria as C
from preop import data as D
from preop.llm import LLM, default_provider
from preop.pipeline import action_text, run_case

st.set_page_config(page_title="Pre-Op Readiness", page_icon="🩺", layout="wide")

STATUS_COLOR = {"Ready": "#1f7a4d", "Outstanding items": "#b26a00", "Needs clinical review": "#c0392b",
                "Recommend hold": "#7b1fa2"}
KEY_TESTS = {
    "nurse": ["Hemoglobin", "Potassium", "Glucose", "POC glucose", "INR", "Serum hCG", "UA nitrite", "Urine culture"],
    "anesthesia": ["Hemoglobin", "Hematocrit", "Platelets", "PT", "INR", "PTT", "Sodium", "Potassium", "Creatinine",
                   "eGFR", "Glucose", "POC glucose", "HbA1c", "Albumin", "AST", "ALT", "Total bilirubin"],
}
DECISIONS = os.path.join(D.ROOT, "results", "decisions.csv")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🩺 Pre-Op Readiness")
role = st.sidebar.radio("I am the…", ["nurse", "anesthesia"],
                        format_func=lambda r: "Pre-op nurse" if r == "nurse" else "Anesthesiologist")
provider = default_provider()
engines = ["AI (LLM)", "Rules only"] if provider != "mock" else ["Rules only", "AI (LLM)"]
engine_label = st.sidebar.selectbox("Engine", engines)
engine = "llm" if engine_label.startswith("AI") else "rules"
if engine == "llm" and provider == "mock":
    st.sidebar.warning("No API key found. AI mode will show the rules-only output.")
split = st.sidebar.selectbox("Cases", ["all", "dev", "test"])
cases = D.list_cases(split=None if split == "all" else split)
proc_filter = st.sidebar.multiselect("Procedure", C.PROCEDURES)
if proc_filter:
    cases = [c for c in cases if c["procedure"] in proc_filter]
labels = {c["surgery_id"]: f"{c['surgery_date'][5:]} {c['surgery_time']} · {c['name']} · {c['procedure']}" for c in cases}
default_idx = next((i for i, c in enumerate(cases) if c["surgery_id"] == "S082"), 0)
sid = st.sidebar.selectbox("Patient (OR schedule)", list(labels), index=default_idx, format_func=labels.get)
st.sidebar.caption("Synthetic data · teaching rules, not clinical guidelines")

chart = D.build_chart(sid)
c, p = chart["case"], chart["patient"]

# ---------------------------------------------------------------------------
# Patient header (like an EHR banner)
# ---------------------------------------------------------------------------
allergy_color = "#c0392b" if not p["allergies"].startswith("No known") else "inherit"
st.markdown(
    f"""<div style="border:1px solid #ccc;border-radius:8px;padding:10px 14px;margin-bottom:8px">
    <b style="font-size:1.25em">{p['name']}</b> &nbsp; {p['age']} y/o {p['sex']} &nbsp;·&nbsp; MRN {p['mrn']} &nbsp;·&nbsp;
    BMI {p['bmi']} &nbsp;·&nbsp; <span style="color:{allergy_color}"><b>Allergies:</b> {p['allergies']}</span><br>
    <b>{c['procedure']}</b> · {c['surgery_date']} {c['surgery_time']} · {c['surgery_location']} · {c['surgeon']} ·
    Anesthesia: {c['planned_anesthesia']} · Post-op: {c['postoperative_location']}</div>""",
    unsafe_allow_html=True)

tabs = st.tabs(["Pre-Op Readiness", "Labs", "Medications", "Tests & Imaging", "Consents & Blood", "H&P"])

# ---------------------------------------------------------------------------
# Readiness tab (Modules 1-4)
# ---------------------------------------------------------------------------
with tabs[0]:
    key = (sid, role, engine)
    if "results" not in st.session_state:
        st.session_state.results = {}
    if key not in st.session_state.results:
        if engine == "llm" and provider != "mock":
            if st.button(f"Run AI readiness review for {p['name']}", type="primary"):
                with st.spinner("Reading the chart (Modules 2-4)…"):
                    st.session_state.results[key] = run_case(sid, role=role, engine="llm", llm=LLM())
        else:
            st.session_state.results[key] = run_case(sid, role=role, engine=engine)
    res = st.session_state.results.get(key)
    if res:
        steps, summ = res["next_steps"], res["summary"]
        color = STATUS_COLOR.get(steps["status"], "#555")
        st.markdown(f"<div style='background:{color};color:white;padding:8px 14px;border-radius:6px;font-weight:600'>"
                    f"{steps['status']} — {summ.get('headline', '')}</div>", unsafe_allow_html=True)
        st.caption(f"View: {'Pre-op nurse' if role == 'nurse' else 'Anesthesiologist'} · engine: {res['engine']} · "
                   f"{steps.get('status_reason', '')}")

        left, right = st.columns([1, 1.15])
        with left:
            st.subheader("Summary")
            for sec in summ.get("sections", []):
                st.markdown(f"**{sec['title']}**")
                for b in sec.get("bullets", []):
                    st.markdown(f"- {b}")
            st.subheader("Key values for this role")
            rows = []
            for t in KEY_TESTS[role]:
                lab = C.latest_lab(chart, t)
                if lab:
                    rows.append(dict(Test=t, Value=f"{lab['result_value']} {'' if lab['unit'] == 'text' else lab['unit']}",
                                     Flag=lab["flag"], Date=lab["collection_date"], ID=lab["lab_id"]))
            for d in chart["diagnostics"]:
                if role == "anesthesia" or d["test_type"] == "EKG":
                    rows.append(dict(Test=d["test_type"], Value=(f"{d['result_value']} {d['result_unit']}".strip() or d["interpretation"]),
                                     Flag="New" if d["compared_to_prior"] == "New finding" else "", Date=d["test_date"], ID=d["test_id"]))
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df.style.map(lambda v: "color:#c0392b;font-weight:600" if v in ("H", "L", "Critical", "Abnormal", "New") else "",
                                          subset=["Flag"]), hide_index=True, use_container_width=True)
            else:
                st.info("No lab values in chart.")

        with right:
            st.subheader(f"Next steps — {'Pre-op nurse' if role == 'nurse' else 'Anesthesiologist'}")
            if not steps["actions"]:
                st.success("No actions recommended for this role.")
            decisions = {}
            for i, a in enumerate(steps["actions"]):
                badge = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(a.get("priority"), "⚪")
                with st.container(border=True):
                    st.markdown(f"{badge} **{action_text(a['code'])}**")
                    st.caption(f"Why: {a.get('reason', '')} · Evidence: {', '.join(a.get('evidence_ids', [])) or '-'} · `{a['code']}`")
                    decisions[a["code"]] = st.radio("Decision", ["Pending", "Accept", "Decline"], horizontal=True,
                                                    key=f"dec_{sid}_{role}_{engine}_{i}", label_visibility="collapsed")
            if steps.get("other_considerations"):
                st.markdown("**Other considerations**")
                for o in steps["other_considerations"]:
                    st.markdown(f"- {o}")
            if steps["actions"] and st.button("Save decisions"):
                os.makedirs(os.path.dirname(DECISIONS), exist_ok=True)
                new = not os.path.exists(DECISIONS)
                with open(DECISIONS, "a", newline="") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(["timestamp", "surgery_id", "role", "engine", "action_code", "decision"])
                    for code, dec in decisions.items():
                        w.writerow([datetime.now().isoformat(timespec="seconds"), sid, role, res["engine"], code, dec])
                st.success("Decisions saved.")

        if res.get("qa"):
            with st.expander("Module 2 answers (question answering, with evidence)"):
                for a in res["qa"].get("answers", []):
                    st.markdown(f"**{a.get('question_id')}** {a.get('answer')}  \n`{', '.join(a.get('evidence_ids', []))}`")
        with st.expander("Module 1: scheduled surgery and requirements that apply"):
            st.dataframe(pd.DataFrame(res["module1"]["requirements"]), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Chart tabs
# ---------------------------------------------------------------------------
def show(rows, cols, hl=None):
    if not rows:
        st.info("None in chart.")
        return
    df = pd.DataFrame(rows)[cols]
    if hl:
        bad = {"H", "L", "Critical", "Abnormal", "Missing", "Refused", "Pending", "Positive", "New finding"}
        df = df.style.map(lambda v: "color:#c0392b;font-weight:600" if v in bad else "", subset=hl)
    st.dataframe(df, hide_index=True, use_container_width=True)


with tabs[1]:
    show(sorted(chart["labs"], key=lambda x: (x["panel"], x["test_name"])),
         ["panel", "test_name", "result_value", "unit", "reference_low", "reference_high", "flag", "collection_date", "lab_id"], ["flag"])
with tabs[2]:
    show(chart["meds"], ["medication_name", "dose", "route", "frequency", "preop_instruction", "medication_id"])
with tabs[3]:
    show(chart["diagnostics"], ["test_type", "test_date", "result_value", "result_unit", "interpretation", "compared_to_prior", "test_id"],
         ["compared_to_prior"])
    show(chart["imaging"], ["imaging_type", "imaging_date", "report", "imaging_id"])
    show(chart["clearances"], ["clearance_type", "status", "requested_date", "completed_date", "assessment_note", "clearance_id"], ["status"])
with tabs[4]:
    show(chart["consents"], ["consent_type", "status", "signed_date", "consent_id"], ["status"])
    if chart["blood"]:
        b = chart["blood"]
        show([b], ["abo_rh", "antibody_screen", "type_screen_date", "type_screen_expires", "prbc_crossmatched_units",
                   "ffp_units_available", "platelet_units_available"], ["antibody_screen"])
with tabs[5]:
    if chart["notes"]:
        for n in chart["notes"]:
            st.text(n["note_text"])
    else:
        st.warning("No H&P in chart.")
    st.caption(f"Anesthesia history: {p['anesthesia_complication_history']}")
