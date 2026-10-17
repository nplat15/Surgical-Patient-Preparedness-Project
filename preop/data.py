"""
Data access + Module 1 (Surgery Identification).

Module 1 is NOT AI: it is a database-style lookup. Given a surgery_id it returns
the scheduled case and the requirements that apply to it.

The answer key folder is never read here, so nothing in this module can leak
expected answers into the AI's input.
"""
from __future__ import annotations

import csv
import json
import os
from functools import lru_cache

from . import criteria as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "surgical_patient_dataset_v2")

FILES = ["patients", "surgical_cases", "medications", "lab_results", "diagnostic_tests", "imaging",
         "clearances", "consents", "blood_products", "clinical_notes", "past_surgeries"]


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=4)
def load(data_dir=DEFAULT_DATA):
    return {name: _read(os.path.join(data_dir, f"{name}.csv")) for name in FILES}


def procedure_label(case):
    """Procedure with its side, e.g. 'Left Knee Arthroscopy' (side is blank for midline procedures)."""
    side = case.get("laterality") or ""
    return f"{side} {case['procedure']}".strip()


def list_cases(data_dir=DEFAULT_DATA, split=None):
    db = load(data_dir)
    pts = {p["patient_id"]: p for p in db["patients"]}
    out = []
    for c in db["surgical_cases"]:
        if split and c.get("split") != split:
            continue
        p = pts[c["patient_id"]]
        out.append(dict(c, name=p["name"], age=p["age"], sex=p["sex"], mrn=p["mrn"]))
    return sorted(out, key=lambda c: (c["surgery_date"], c["surgery_time"]))


# ---------------------------------------------------------------------------
# Module 1: Surgery Identification (rule-based lookup, no AI)
# ---------------------------------------------------------------------------
def module1_identify_surgery(surgery_id, data_dir=DEFAULT_DATA):
    """Return the scheduled surgery and the requirements that apply to this patient."""
    chart = build_chart(surgery_id, data_dir)
    reqs = C.applicable_requirements(chart)
    return dict(
        scheduled=True,
        case=chart["case"],
        patient={k: chart["patient"][k] for k in ("patient_id", "name", "mrn", "age", "sex")},
        requirements=[dict(item=r["item"], item_type=r["item_type"], validity_days=r["validity_days"],
                           condition=C.CONDITION_TEXT[r["condition"]]) for r in reqs],
    )


def build_chart(surgery_id, data_dir=DEFAULT_DATA):
    """Gather every record for one surgical case into a single dict (the 'chart')."""
    db = load(data_dir)
    case = next((c for c in db["surgical_cases"] if c["surgery_id"] == surgery_id), None)
    if case is None:
        raise KeyError(f"No scheduled surgery {surgery_id}")
    case = {k: v for k, v in case.items() if k != "split"}  # split is bookkeeping, not chart data
    pid = case["patient_id"]
    patient = dict(next(p for p in db["patients"] if p["patient_id"] == pid))
    patient["diagnoses"] = [d.strip() for d in patient["diagnoses"].split(";") if d.strip()]
    by_case = lambda name: [r for r in db[name] if r.get("surgery_id") == surgery_id]
    blood = by_case("blood_products")
    return dict(
        case=case, patient=patient,
        meds=[m for m in db["medications"] if m["patient_id"] == pid],
        labs=by_case("lab_results"), diagnostics=by_case("diagnostic_tests"), imaging=by_case("imaging"),
        clearances=by_case("clearances"), consents=by_case("consents"), blood=blood[0] if blood else None,
        notes=by_case("clinical_notes"), past_surgeries=[s for s in db["past_surgeries"] if s["patient_id"] == pid],
    )


def chart_to_packet(chart):
    """Turn the chart into compact text for the LLM. Every line keeps its record ID so answers can cite it."""
    c, p = chart["case"], chart["patient"]
    L = [f"SCHEDULED SURGERY [{c['surgery_id']}]: {procedure_label(c)} on {c['surgery_date']} {c['surgery_time']}, "
         f"{c['surgery_location']}, surgeon {c['surgeon']}, planned anesthesia {c['planned_anesthesia']}, "
         f"post-op {c['postoperative_location']}",
         f"PATIENT [{p['patient_id']}]: {p['name']}, {p['age']} y/o {p['sex']}, BMI {p['bmi']}, smoking {p['smoking_status']}",
         f"  Diagnoses: {'; '.join(p['diagnoses'])}",
         f"  Allergies (allergy list): {p['allergies']}",
         f"  Anesthesia complication history: {p['anesthesia_complication_history']}",
         "", "MEDICATIONS (with documented pre-op instruction; blank = none documented)"]
    for m in chart["meds"]:
        L.append(f"  [{m['medication_id']}] {m['medication_name']} {m['dose']} {m['route']} {m['frequency']} | "
                 f"pre-op instruction: {m['preop_instruction'] or '(none documented)'}")
    L += ["", "LAB RESULTS (value, unit, reference range, flag, collected)"]
    for lab in sorted(chart["labs"], key=lambda x: (x["panel"], x["test_name"])):
        rng = f"{lab['reference_low']}-{lab['reference_high']}" if (lab["reference_low"] or lab["reference_high"]) else ""
        L.append(f"  [{lab['lab_id']}] {lab['panel']} / {lab['test_name']}: {lab['result_value']} {lab['unit'] if lab['unit'] != 'text' else ''}"
                 f" (ref {rng or 'n/a'}) {('FLAG ' + lab['flag']) if lab['flag'] else ''} collected {lab['collection_date']}")
    if not chart["labs"]:
        L.append("  (no labs in chart)")
    L += ["", "DIAGNOSTIC TESTS"]
    for t in chart["diagnostics"]:
        L.append(f"  [{t['test_id']}] {t['test_type']} {t['test_date']}: {t['interpretation']} "
                 f"(compared to prior: {t['compared_to_prior']})")
    if not chart["diagnostics"]:
        L.append("  (none in chart)")
    L += ["", "IMAGING"] + [f"  [{i['imaging_id']}] {i['imaging_type']} {i['imaging_date']}: {i['report']}" for i in chart["imaging"]]
    L += ["", "CLEARANCES"]
    for cl in chart["clearances"]:
        L.append(f"  [{cl['clearance_id']}] {cl['clearance_type']}: {cl['status']} (requested {cl['requested_date']}, "
                 f"completed {cl['completed_date'] or '-'}) {cl['assessment_note']}")
    if not chart["clearances"]:
        L.append("  (none in chart)")
    L += ["", "CONSENTS"] + [f"  [{x['consent_id']}] {x['consent_type']}: {x['status']} {x['signed_date']}" for x in chart["consents"]]
    b = chart["blood"]
    L += ["", "BLOOD BANK"]
    if b:
        L.append(f"  [{b['blood_record_id']}] {b['abo_rh']}, antibody screen {b['antibody_screen']}, type & screen drawn "
                 f"{b['type_screen_date']} expires {b['type_screen_expires']}, PRBC crossmatched {b['prbc_crossmatched_units']} units, "
                 f"FFP {b['ffp_units_available']}, platelets {b['platelet_units_available']}")
    else:
        L.append("  (no blood bank record)")
    L += ["", "PAST SURGERIES"] + ([f"  {s['prior_procedure']} ({s['procedure_year']}), anesthesia issue: {s['prior_anesthesia_issue']}"
                                     for s in chart["past_surgeries"]] or ["  (none)"])
    L += ["", "CLINICAL NOTES"]
    for n in chart["notes"]:
        L.append(f"--- [{n['note_id']}] {n['note_type']} {n['note_date']} ---\n{n['note_text']}")
    if not chart["notes"]:
        L.append("  (no H&P or other notes in chart)")
    return "\n".join(L)


def dumps(x):
    return json.dumps(x, indent=2, default=str)
