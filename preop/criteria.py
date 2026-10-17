"""
Teaching criteria for the Pre-Op Readiness prototype.

!!! These are ILLUSTRATIVE TEACHING RULES for a class project, NOT clinical
!!! guidelines. Thresholds, validity windows and role assignments were chosen
!!! to be plausible and easy to explain. Do not use for real patient care.

This file is the single source of truth for:
  * which items each procedure requires (REQUIREMENTS)
  * which abnormal values / history items trigger an action (VALUE_RULES)
  * the "order set" of next-step actions each role can recommend (ACTION_CATALOG)

It is used three ways:
  1. the dataset generator uses it to write the answer key,
  2. the rules-only baseline applies it to STRUCTURED fields only,
  3. the LLM prompts include it as the hospital's pre-op criteria document.

Standard library only, so the generator can run anywhere.
"""
from __future__ import annotations

from datetime import date

ROLES = ("nurse", "anesthesia")

# ---------------------------------------------------------------------------
# Lab panels (test names exactly as they appear in lab_results.csv)
# ---------------------------------------------------------------------------
PANELS = {
    "CBC": ["WBC", "Hemoglobin", "Hematocrit", "Platelets"],
    "BMP": ["Sodium", "Potassium", "Chloride", "CO2", "BUN", "Creatinine",
            "Glucose", "Calcium", "eGFR"],
    "Coagulation panel": ["PT", "INR", "PTT"],
    "Liver function tests": ["AST", "ALT", "Alkaline phosphatase", "Total bilirubin"],
    "Albumin": ["Albumin"],
    "HbA1c": ["HbA1c"],
    "POC glucose": ["POC glucose"],
    "Urinalysis": ["UA leukocyte esterase", "UA nitrite", "UA WBC", "UA bacteria"],
    "Urine culture": ["Urine culture"],
    "Pregnancy test": ["Serum hCG"],
}
TEST_TO_PANEL = {t: p for p, tests in PANELS.items() for t in tests}

CARDIAC_DX = {"Atrial fibrillation", "Coronary artery disease",
              "Multivessel coronary artery disease", "Heart failure"}

PROCEDURES = [
    "Laparoscopic Cholecystectomy",
    "Radical Mastectomy",
    "Knee Arthroscopy",
    "Ureteroscopy with Stent Placement",
    "Coronary Artery Bypass Graft",
]

# ---------------------------------------------------------------------------
# Action catalog: the "order set" each role can pick from.
# code -> (role, text)
# ---------------------------------------------------------------------------
ACTION_CATALOG = {
    # --- consents -----------------------------------------------------------
    "OBTAIN_SURGERY_CONSENT": ("nurse", "Contact the surgical team to complete and sign the surgical consent before the patient goes to the OR."),
    "NOTIFY_ANESTHESIA_CONSENT": ("nurse", "Notify anesthesia that the anesthesia consent is not signed."),
    "OBTAIN_ANESTHESIA_CONSENT": ("anesthesia", "Complete the anesthesia consent discussion and signature with the patient."),
    "OBTAIN_BLOOD_CONSENT": ("nurse", "Obtain a signed blood transfusion consent or a signed refusal form."),
    "VERIFY_BLOOD_REFUSAL_FORM": ("nurse", "Patient refuses blood: verify the refusal form is signed and the refusal is flagged for the OR team."),
    "BLOOD_REFUSAL_PLAN": ("anesthesia", "Patient refuses blood products: develop a bloodless management plan with the surgeon (e.g., cell saver, anemia optimization)."),
    "RECONCILE_CONSENT_DOCUMENTATION": ("nurse", "Clinical note and consent record disagree: reconcile which consents are actually signed."),
    # --- documentation ------------------------------------------------------
    "OBTAIN_UPDATED_HP": ("nurse", "Request a current, complete H&P (within 30 days, including heart and lung exam) from the surgical team."),
    "RECONCILE_ALLERGIES": ("nurse", "Allergy list and H&P disagree: reconcile allergies with the patient and update the chart."),
    # --- labs to draw -------------------------------------------------------
    "DRAW_CBC": ("nurse", "Obtain order and draw CBC."),
    "DRAW_BMP": ("nurse", "Obtain order and draw BMP."),
    "DRAW_COAGS": ("nurse", "Obtain order and draw coagulation panel (PT/INR, PTT)."),
    "DRAW_LFT": ("nurse", "Obtain order and draw liver function tests."),
    "DRAW_ALBUMIN": ("nurse", "Obtain order and draw albumin."),
    "DRAW_HBA1C": ("nurse", "Obtain order and draw HbA1c."),
    "DRAW_UA": ("nurse", "Obtain order and collect urinalysis."),
    "DRAW_URINE_CULTURE": ("nurse", "Obtain order and collect urine culture."),
    "DRAW_PREGNANCY_TEST": ("nurse", "Obtain order and draw pregnancy test (serum hCG)."),
    "DRAW_TYPE_AND_SCREEN": ("nurse", "Obtain order and draw a new type and screen (current one missing or expires before surgery)."),
    "REPEAT_BMP": ("nurse", "Obtain order to repeat BMP and notify anesthesia of the result."),
    "POC_GLUCOSE_DAY_OF": ("nurse", "Check point-of-care glucose on arrival day of surgery and notify anesthesia if elevated."),
    # --- tests / imaging / blood --------------------------------------------
    "OBTAIN_EKG": ("nurse", "Obtain order and perform a 12-lead EKG."),
    "OBTAIN_CHEST_XRAY": ("nurse", "Obtain order for a pre-op chest X-ray."),
    "REQUEST_ECHO": ("anesthesia", "Order/request an echocardiogram before surgery."),
    "REQUEST_PFT": ("anesthesia", "Order/request pulmonary function tests before surgery."),
    "ORDER_CROSSMATCH": ("nurse", "Obtain order for crossmatch of 2 units PRBC and confirm with the blood bank."),
    "CONFIRM_BLOOD_PRODUCTS": ("anesthesia", "Confirm crossmatched PRBC (and FFP/platelets per plan) are available before incision."),
    "CONTACT_BLOOD_BANK": ("nurse", "Contact the blood bank about the positive antibody screen; allow extra time for compatible units."),
    "ANTIBODY_BLOOD_BANK": ("anesthesia", "Positive antibody screen: coordinate with blood bank on antibody ID and compatible units; consider delaying if units unavailable."),
    # --- clearances ---------------------------------------------------------
    "REQUEST_CARDIOLOGY_CLEARANCE": ("anesthesia", "Request a cardiology assessment/clearance before surgery."),
    "REQUEST_PULMONARY_CLEARANCE": ("anesthesia", "Request a pulmonary assessment/clearance before surgery."),
    "FOLLOW_UP_CLEARANCE": ("nurse", "Follow up on the pending clearance and make sure the result is in the chart before surgery."),
    # --- abnormal values (anesthesia evaluates, nurse notifies) -------------
    "EVALUATE_ANEMIA": ("anesthesia", "Evaluate anemia: confirm blood availability and consider optimizing or delaying elective surgery."),
    "NOTIFY_LOW_HGB": ("nurse", "Notify surgeon and anesthesia of the low hemoglobin."),
    "EVALUATE_THROMBOCYTOPENIA": ("anesthesia", "Evaluate low platelets: bleeding risk, platelet availability, avoid neuraxial technique if appropriate."),
    "NOTIFY_LOW_PLATELETS": ("nurse", "Notify surgeon and anesthesia of the low platelet count."),
    "EVALUATE_ELEVATED_INR": ("anesthesia", "Evaluate elevated INR: review anticoagulant, plan reversal/hold with surgeon, repeat coags before surgery."),
    "NOTIFY_ELEVATED_INR": ("nurse", "Notify surgeon and anesthesia of the elevated INR."),
    "CORRECT_POTASSIUM": ("anesthesia", "Evaluate and correct potassium before surgery; repeat EKG if indicated."),
    "EVALUATE_SODIUM": ("anesthesia", "Evaluate abnormal sodium before surgery."),
    "RENAL_DOSING_PLAN": ("anesthesia", "Reduced kidney function: adjust renally cleared drugs and avoid nephrotoxins."),
    "NOTIFY_RENAL_FUNCTION": ("nurse", "Notify surgeon and anesthesia of the elevated creatinine."),
    "GLYCEMIC_PLAN": ("anesthesia", "Poor glucose control: create perioperative glucose/insulin plan; consider postponing elective surgery if severe."),
    "REVIEW_LOW_ALBUMIN": ("anesthesia", "Low albumin: note malnutrition/healing risk and discuss optimization with surgeon."),
    "REVIEW_ELEVATED_LFTS": ("anesthesia", "Elevated liver tests: evaluate hepatic function and adjust drug choices."),
    "NOTIFY_ELEVATED_LFTS": ("nurse", "Notify surgeon and anesthesia of the elevated liver tests."),
    "NOTIFY_SURGEON_POSITIVE_CULTURE": ("nurse", "Notify surgeon of positive urinalysis/urine culture so infection is treated before the procedure."),
    "REVIEW_INFECTION_RISK": ("anesthesia", "Active urinary infection: review sepsis risk and whether to proceed."),
    "NOTIFY_POSITIVE_PREGNANCY": ("nurse", "Positive pregnancy test: notify surgeon and anesthesia immediately; do not proceed until reviewed."),
    "REVIEW_POSITIVE_PREGNANCY": ("anesthesia", "Positive pregnancy test: review with surgeon and patient whether to proceed."),
    "EVALUATE_EKG_ABNORMALITY": ("anesthesia", "New EKG abnormality: evaluate and consider cardiology consult before surgery."),
    "NOTIFY_EKG_ABNORMALITY": ("nurse", "Notify anesthesia of the new EKG finding."),
    "REVIEW_LOW_EF": ("anesthesia", "Reduced ejection fraction: plan hemodynamic monitoring/support."),
    "REVIEW_SEVERE_LUNG_DISEASE": ("anesthesia", "Severe obstruction on PFTs: plan for pulmonary risk (bronchodilators, ventilation, post-op care)."),
    "EVALUATE_NEW_SYMPTOMS": ("anesthesia", "New symptoms documented in the H&P: evaluate before surgery and consider postponing."),
    "NOTIFY_NEW_SYMPTOMS": ("nurse", "Notify anesthesia and surgeon of new symptoms reported in the H&P."),
    # --- medications --------------------------------------------------------
    "ANTITHROMBOTIC_PLAN": ("anesthesia", "Blood thinner without a clear hold plan: decide hold/bridge timing with surgeon and prescriber."),
    "VERIFY_ANTITHROMBOTIC_HOLD": ("nurse", "Call patient to verify blood-thinner hold instructions and last dose; document."),
    "METFORMIN_HOLD_INSTRUCTIONS": ("nurse", "Give and document metformin hold instructions for day of surgery."),
    "INSULIN_DOSE_PLAN": ("anesthesia", "Write pre-op insulin dose adjustment orders."),
    "INSULIN_INSTRUCTIONS": ("nurse", "Give and document insulin dose instructions for the night before / morning of surgery."),
    "GLP1_ASPIRATION_REVIEW": ("anesthesia", "GLP-1 agonist: review aspiration risk and hold timing; adjust fasting/airway plan."),
    "VERIFY_GLP1_LAST_DOSE": ("nurse", "Verify date of last GLP-1 agonist dose and document."),
    "SGLT2_HOLD_INSTRUCTIONS": ("nurse", "Give and document SGLT2 inhibitor hold instructions (stop before surgery per protocol)."),
    # --- history / safety ---------------------------------------------------
    "OSA_PRECAUTIONS": ("anesthesia", "Obstructive sleep apnea: plan OSA precautions (airway, opioid-sparing, post-op monitoring)."),
    "BRING_CPAP": ("nurse", "Instruct patient to bring CPAP device on day of surgery."),
    "MH_PRECAUTIONS": ("anesthesia", "Malignant hyperthermia risk: plan trigger-free anesthetic."),
    "NOTIFY_MH_RISK": ("nurse", "Notify OR charge nurse of malignant hyperthermia risk (prepare MH cart / trigger-free machine)."),
    "DIFFICULT_AIRWAY_PLAN": ("anesthesia", "History of difficult airway: prepare difficult airway plan and equipment."),
    "PONV_PROPHYLAXIS": ("anesthesia", "History of post-op nausea/vomiting: plan PONV prophylaxis."),
    "LATEX_PRECAUTIONS": ("nurse", "Latex allergy: notify OR to set up a latex-free room."),
}

# Finding category -> effect on readiness status.
#   critical  -> "Recommend hold"
#   clinical  -> "Needs clinical review"
#   missing   -> "Outstanding items"
#   safety / routine -> no change ("Ready" can still have precautions)
STATUS_ORDER = ["Ready", "Outstanding items", "Needs clinical review", "Recommend hold"]
CATEGORY_TO_STATUS = {"critical": "Recommend hold", "clinical": "Needs clinical review",
                      "missing": "Outstanding items", "safety": "Ready", "routine": "Ready"}

# ---------------------------------------------------------------------------
# Requirements: what must be in the chart, per procedure.
# condition keys are evaluated by CONDITIONS below.
# ---------------------------------------------------------------------------
def _req(rid, procedure, item_type, item, condition, validity_days, actions, desc):
    return dict(requirement_id=rid, procedure=procedure, item_type=item_type, item=item,
                condition=condition, validity_days=validity_days, missing_actions=actions,
                description=desc)

N, A = "nurse", "anesthesia"
CONSENT_SURG = [(N, "OBTAIN_SURGERY_CONSENT")]
CONSENT_ANES = [(A, "OBTAIN_ANESTHESIA_CONSENT"), (N, "NOTIFY_ANESTHESIA_CONSENT")]
LAB_ACTION = {"CBC": "DRAW_CBC", "BMP": "DRAW_BMP", "Coagulation panel": "DRAW_COAGS",
              "Liver function tests": "DRAW_LFT", "Albumin": "DRAW_ALBUMIN", "HbA1c": "DRAW_HBA1C",
              "Urinalysis": "DRAW_UA", "Urine culture": "DRAW_URINE_CULTURE",
              "Pregnancy test": "DRAW_PREGNANCY_TEST"}

REQUIREMENTS = []
_rid = [0]


def _add(procedure, item_type, item, condition, validity, actions, desc):
    _rid[0] += 1
    REQUIREMENTS.append(_req(f"R{_rid[0]:03d}", procedure, item_type, item, condition, validity, actions, desc))


# applies to every procedure
_add("All", "consent", "Surgery consent", "always", None, CONSENT_SURG, "Signed surgical consent")
_add("All", "consent", "Anesthesia consent", "always", None, CONSENT_ANES, "Signed anesthesia consent")
_add("All", "note", "H&P", "always", 30, [(N, "OBTAIN_UPDATED_HP")], "H&P within 30 days of surgery")
_add("All", "lab", "Pregnancy test", "female_18_50", 7, [(N, "DRAW_PREGNANCY_TEST")], "Pregnancy test within 7 days for females age 18-50")
_add("All", "lab", "HbA1c", "diabetes", 90, [(N, "DRAW_HBA1C")], "HbA1c within 90 days for patients with diabetes")
_add("All", "diagnostic", "EKG", "age65_or_cardiac_noncabg", 90, [(N, "OBTAIN_EKG")], "EKG within 90 days if age >= 65 or cardiac history")

_PROC_LABS = {
    "Laparoscopic Cholecystectomy": ["CBC", "BMP", "Liver function tests"],
    "Radical Mastectomy": ["CBC", "BMP"],
    "Knee Arthroscopy": [],
    "Ureteroscopy with Stent Placement": ["CBC", "BMP", "Urinalysis", "Urine culture"],
    "Coronary Artery Bypass Graft": ["CBC", "BMP", "Coagulation panel", "Liver function tests", "Albumin"],
}
for _p, _labs in _PROC_LABS.items():
    for _lab in _labs:
        _add(_p, "lab", _lab, "always", 30, [(N, LAB_ACTION[_lab])], f"{_lab} within 30 days")
_add("Knee Arthroscopy", "lab", "BMP", "knee_bmp", 30, [(N, "DRAW_BMP")], "BMP within 30 days if age >= 65 or HTN/diabetes/CKD")

for _p in ("Radical Mastectomy", "Coronary Artery Bypass Graft"):
    _add(_p, "blood", "Type and screen", "always", None, [(N, "DRAW_TYPE_AND_SCREEN")], "Type and screen valid on surgery date")
    _add(_p, "consent", "Blood consent", "always", None, [(N, "OBTAIN_BLOOD_CONSENT")], "Blood consent or documented refusal")

_C = "Coronary Artery Bypass Graft"
_add(_C, "blood", "Crossmatched PRBC (2 units)", "not_refusing_blood", None,
     [(N, "ORDER_CROSSMATCH"), (A, "CONFIRM_BLOOD_PRODUCTS")], "2 units PRBC crossmatched unless patient refuses blood")
_add(_C, "diagnostic", "EKG", "always", 30, [(N, "OBTAIN_EKG")], "EKG within 30 days")
_add(_C, "diagnostic", "Echocardiogram", "always", 365, [(A, "REQUEST_ECHO")], "Echo within 12 months")
_add(_C, "diagnostic", "Pulmonary function test", "copd", 365, [(A, "REQUEST_PFT")], "PFTs within 12 months if COPD")
_add(_C, "imaging", "Chest X-ray", "always", 30, [(N, "OBTAIN_CHEST_XRAY")], "Chest X-ray within 30 days")
_add(_C, "clearance", "Cardiology assessment", "always", None, [(A, "REQUEST_CARDIOLOGY_CLEARANCE")], "Completed cardiology assessment")
for _p in ("Laparoscopic Cholecystectomy", "Radical Mastectomy", _C):
    _add(_p, "clearance", "Pulmonary assessment", "copd", None, [(A, "REQUEST_PULMONARY_CLEARANCE")], "Completed pulmonary assessment if COPD")


def _has(patient, dx):
    return dx in patient["diagnoses"]


CONDITIONS = {
    "always": lambda c: True,
    "female_18_50": lambda c: c["patient"]["sex"] == "Female" and 18 <= int(c["patient"]["age"]) <= 50,
    "diabetes": lambda c: _has(c["patient"], "Type 2 diabetes mellitus"),
    "copd": lambda c: _has(c["patient"], "COPD"),
    "age65_or_cardiac_noncabg": lambda c: c["case"]["procedure"] != _C and (
        int(c["patient"]["age"]) >= 65 or any(d in c["patient"]["diagnoses"] for d in CARDIAC_DX)),
    "knee_bmp": lambda c: int(c["patient"]["age"]) >= 65 or any(
        _has(c["patient"], d) for d in ("Hypertension", "Type 2 diabetes mellitus", "Chronic kidney disease")),
    "not_refusing_blood": lambda c: not any(
        x["consent_type"] == "Blood consent" and x["status"] == "Refused" for x in c["consents"]),
}

CONDITION_TEXT = {
    "always": "Always", "female_18_50": "Female age 18-50", "diabetes": "Patient has diabetes",
    "copd": "Patient has COPD", "age65_or_cardiac_noncabg": "Age >= 65 or cardiac history (non-cardiac surgery)",
    "knee_bmp": "Age >= 65 or HTN / diabetes / CKD", "not_refusing_blood": "Patient has not refused blood",
}

# ---------------------------------------------------------------------------
# Value / history rules (checked on structured fields)
# ---------------------------------------------------------------------------
VALUE_RULES = [
    # (finding_code, category, plain-language rule, nurse actions, anesthesia actions)
    ("LOW_HEMOGLOBIN", "clinical", "Hemoglobin < 10 g/dL (critical < 7)", ["NOTIFY_LOW_HGB"], ["EVALUATE_ANEMIA"]),
    ("LOW_PLATELETS", "clinical", "Platelets < 100 x10^3/uL", ["NOTIFY_LOW_PLATELETS"], ["EVALUATE_THROMBOCYTOPENIA"]),
    ("ELEVATED_INR", "clinical", "INR > 1.5", ["NOTIFY_ELEVATED_INR"], ["EVALUATE_ELEVATED_INR"]),
    ("ABNORMAL_POTASSIUM", "clinical", "Potassium > 5.5 or < 3.3 mmol/L (critical >= 6.0 or <= 3.0)", ["REPEAT_BMP"], ["CORRECT_POTASSIUM"]),
    ("ABNORMAL_SODIUM", "clinical", "Sodium < 130 or > 150 mmol/L", ["REPEAT_BMP"], ["EVALUATE_SODIUM"]),
    ("ELEVATED_CREATININE", "clinical", "Creatinine > 1.5 mg/dL", ["NOTIFY_RENAL_FUNCTION"], ["RENAL_DOSING_PLAN"]),
    ("HYPERGLYCEMIA", "clinical", "Glucose or POC glucose > 200 mg/dL, or HbA1c > 8.5%", ["POC_GLUCOSE_DAY_OF"], ["GLYCEMIC_PLAN"]),
    ("LOW_ALBUMIN", "clinical", "Albumin < 3.0 g/dL", [], ["REVIEW_LOW_ALBUMIN"]),
    ("ELEVATED_LFTS", "clinical", "AST or ALT > 120 U/L, or total bilirubin > 2.0 mg/dL", ["NOTIFY_ELEVATED_LFTS"], ["REVIEW_ELEVATED_LFTS"]),
    ("URINARY_INFECTION", "clinical", "Urine culture with growth, or UA nitrite positive", ["NOTIFY_SURGEON_POSITIVE_CULTURE"], ["REVIEW_INFECTION_RISK"]),
    ("POSITIVE_PREGNANCY", "critical", "Serum hCG positive", ["NOTIFY_POSITIVE_PREGNANCY"], ["REVIEW_POSITIVE_PREGNANCY"]),
    ("POSITIVE_ANTIBODY_SCREEN", "clinical", "Antibody screen positive", ["CONTACT_BLOOD_BANK"], ["ANTIBODY_BLOOD_BANK"]),
    ("NEW_EKG_ABNORMALITY", "clinical", "EKG compared to prior shows a new finding", ["NOTIFY_EKG_ABNORMALITY"], ["EVALUATE_EKG_ABNORMALITY"]),
    ("LOW_EJECTION_FRACTION", "clinical", "Echo ejection fraction < 35%", [], ["REVIEW_LOW_EF"]),
    ("SEVERE_OBSTRUCTION", "clinical", "PFT FEV1 < 50% predicted", [], ["REVIEW_SEVERE_LUNG_DISEASE"]),
    ("BLOOD_REFUSAL", "clinical", "Blood consent status is Refused", ["VERIFY_BLOOD_REFUSAL_FORM"], ["BLOOD_REFUSAL_PLAN"]),
    ("PENDING_CLEARANCE", "missing", "Required clearance is Pending", ["FOLLOW_UP_CLEARANCE"], []),
    ("ANTITHROMBOTIC_NO_PLAN", "missing", "Anticoagulant/antiplatelet (not aspirin) with no pre-op instruction", ["VERIFY_ANTITHROMBOTIC_HOLD"], ["ANTITHROMBOTIC_PLAN"]),
    ("METFORMIN_NO_INSTRUCTION", "missing", "Metformin with no pre-op instruction", ["METFORMIN_HOLD_INSTRUCTIONS"], []),
    ("INSULIN_NO_INSTRUCTION", "missing", "Insulin with no pre-op instruction", ["INSULIN_INSTRUCTIONS"], ["INSULIN_DOSE_PLAN"]),
    ("SGLT2_NO_INSTRUCTION", "missing", "SGLT2 inhibitor with no pre-op instruction", ["SGLT2_HOLD_INSTRUCTIONS"], []),
    ("GLP1_AGONIST", "clinical", "GLP-1 agonist with no pre-op instruction", ["VERIFY_GLP1_LAST_DOSE"], ["GLP1_ASPIRATION_REVIEW"]),
    ("OBSTRUCTIVE_SLEEP_APNEA", "routine", "Diagnosis of obstructive sleep apnea", ["BRING_CPAP"], ["OSA_PRECAUTIONS"]),
    ("MALIGNANT_HYPERTHERMIA_RISK", "safety", "Personal or family history of malignant hyperthermia", ["NOTIFY_MH_RISK"], ["MH_PRECAUTIONS"]),
    ("DIFFICULT_AIRWAY", "safety", "History of difficult airway", [], ["DIFFICULT_AIRWAY_PLAN"]),
    ("PONV_HISTORY", "routine", "History of post-op nausea and vomiting", [], ["PONV_PROPHYLAXIS"]),
    ("LATEX_ALLERGY", "safety", "Latex allergy", ["LATEX_PRECAUTIONS"], []),
]
VALUE_RULE_MAP = {r[0]: r for r in VALUE_RULES}

# Findings that can only be found by READING THE H&P TEXT (not in structured fields).
NOTE_FINDINGS = [
    ("NOTE_ALLERGY_CONFLICT", "missing", "H&P allergy statement disagrees with allergy list", ["RECONCILE_ALLERGIES"], []),
    ("NOTE_CONSENT_CONFLICT", "missing", "H&P says a consent is signed but consent record says missing", ["RECONCILE_CONSENT_DOCUMENTATION"], []),
    ("NOTE_NEW_SYMPTOMS", "clinical", "H&P documents new cardiac/respiratory symptoms or acute illness", ["NOTIFY_NEW_SYMPTOMS"], ["EVALUATE_NEW_SYMPTOMS"]),
    ("NOTE_MH_FAMILY_HISTORY", "safety", "H&P mentions a family history suggestive of malignant hyperthermia", ["NOTIFY_MH_RISK"], ["MH_PRECAUTIONS"]),
    ("NOTE_EXAM_INCOMPLETE", "missing", "H&P lacks a heart and lung exam", ["OBTAIN_UPDATED_HP"], []),
    ("NOTE_ANTITHROMBOTIC_CONFLICT", "missing", "H&P says patient is still taking a blood thinner that the med list says to hold", ["VERIFY_ANTITHROMBOTIC_HOLD"], ["ANTITHROMBOTIC_PLAN"]),
]
NOTE_FINDING_MAP = {r[0]: r for r in NOTE_FINDINGS}

ANTITHROMBOTICS = {"Warfarin", "Apixaban", "Rivaroxaban", "Clopidogrel"}
INSULINS = {"Insulin glargine", "Insulin lispro"}
GLP1 = {"Semaglutide"}
SGLT2 = {"Empagliflozin"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def d(s):
    return date.fromisoformat(s) if s else None


def days_before(surgery_date, other):
    return (d(surgery_date) - d(other)).days


def latest(rows, key="collection_date"):
    rows = [r for r in rows if r.get(key)]
    return max(rows, key=lambda r: r[key]) if rows else None


def latest_lab(chart, test):
    return latest([r for r in chart["labs"] if r["test_name"] == test])


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def applicable_requirements(chart):
    proc = chart["case"]["procedure"]
    return [r for r in REQUIREMENTS
            if r["procedure"] in ("All", proc) and CONDITIONS[r["condition"]](chart)]


# ---------------------------------------------------------------------------
# Structured evaluation (what a rules engine can see without reading notes)
# ---------------------------------------------------------------------------
def _finding(code, category, detail, nurse, anes, evidence, source="structured"):
    return dict(finding_code=code, category=category, detail=detail,
                actions={"nurse": list(nurse), "anesthesia": list(anes)},
                evidence_ids=list(evidence), source=source)


def _rule_finding(code, detail, evidence, category=None):
    _, cat, _, nurse, anes = VALUE_RULE_MAP[code]
    return _finding(code, category or cat, detail, nurse, anes, evidence)


def check_requirements(chart):
    out = []
    sdate = chart["case"]["surgery_date"]
    for req in applicable_requirements(chart):
        item, kind, valid = req["item"], req["item_type"], req["validity_days"]
        nurse = [c for r, c in req["missing_actions"] if r == "nurse"]
        anes = [c for r, c in req["missing_actions"] if r == "anesthesia"]
        status, evid, detail = "ok", [], ""
        if kind == "lab":
            rows = [r for r in chart["labs"] if TEST_TO_PANEL.get(r["test_name"]) == item]
            last = latest(rows)
            if not last:
                status, detail = "missing", f"{item} not in chart"
            else:
                evid = [r["lab_id"] for r in rows if r["collection_date"] == last["collection_date"]]
                age = days_before(sdate, last["collection_date"])
                if valid is not None and age > valid:
                    status, detail = "outdated", f"{item} drawn {last['collection_date']} ({age} days before surgery; must be within {valid})"
        elif kind == "consent":
            row = next((c for c in chart["consents"] if c["consent_type"] == item), None)
            if row:
                evid = [row["consent_id"]]
            if not row or row["status"] == "Missing":
                status, detail = "missing", f"{item} not signed"
        elif kind == "note":
            notes = [n for n in chart["notes"] if n["note_type"] == "History and Physical"]
            last = latest(notes, "note_date")
            if not last:
                status, detail = "missing", "No H&P in chart"
            else:
                evid = [last["note_id"]]
                age = days_before(sdate, last["note_date"])
                if age > valid:
                    status, detail = "outdated", f"H&P dated {last['note_date']} ({age} days before surgery; must be within {valid})"
        elif kind == "diagnostic":
            last = latest([t for t in chart["diagnostics"] if t["test_type"] == item], "test_date")
            if not last:
                status, detail = "missing", f"No {item} in chart"
            else:
                evid = [last["test_id"]]
                age = days_before(sdate, last["test_date"])
                if age > valid:
                    status, detail = "outdated", f"{item} dated {last['test_date']} ({age} days before surgery; must be within {valid})"
        elif kind == "imaging":
            last = latest([t for t in chart["imaging"] if t["imaging_type"] == item], "imaging_date")
            if not last:
                status, detail = "missing", f"No {item} in chart"
            else:
                evid = [last["imaging_id"]]
                age = days_before(sdate, last["imaging_date"])
                if age > valid:
                    status, detail = "outdated", f"{item} dated {last['imaging_date']} ({age} days before surgery; must be within {valid})"
        elif kind == "blood":
            b = chart["blood"]
            if b:
                evid = [b["blood_record_id"]]
            if item == "Type and screen":
                if not b or not b.get("type_screen_date"):
                    status, detail = "missing", "No type and screen"
                elif d(b["type_screen_expires"]) < d(sdate):
                    status, detail = "outdated", f"Type and screen expires {b['type_screen_expires']}, before surgery {sdate}"
            else:  # crossmatch
                units = int(b["prbc_crossmatched_units"]) if b and b.get("prbc_crossmatched_units") else 0
                if units < 2:
                    status, detail = "missing", f"{units} units PRBC crossmatched (2 required)"
        elif kind == "clearance":
            row = next((c for c in chart["clearances"] if c["clearance_type"] == item), None)
            if row:
                evid = [row["clearance_id"]]
            if row and row["status"] == "Pending":
                out.append(_rule_finding("PENDING_CLEARANCE", f"{item} pending (requested {row['requested_date']})", evid))
                continue
            if not row or row["status"] != "Completed":
                status, detail = "missing", f"{item} not requested/completed"
        if status != "ok":
            code = f"{'MISSING' if status == 'missing' else 'OUTDATED'}:{item}"
            out.append(_finding(code, "missing", detail, nurse, anes, evid))
    return out


def check_values(chart):
    out = []
    lab = lambda t: latest_lab(chart, t)
    p = chart["patient"]

    h = lab("Hemoglobin")
    if h and num(h["result_value"]) is not None and num(h["result_value"]) < 10:
        v = num(h["result_value"])
        out.append(_rule_finding("LOW_HEMOGLOBIN", f"Hemoglobin {v} g/dL", [h["lab_id"]], "critical" if v < 7 else None))
    pl = lab("Platelets")
    if pl and num(pl["result_value"]) is not None and num(pl["result_value"]) < 100:
        out.append(_rule_finding("LOW_PLATELETS", f"Platelets {pl['result_value']}", [pl["lab_id"]]))
    inr = lab("INR")
    if inr and num(inr["result_value"]) is not None and num(inr["result_value"]) > 1.5:
        out.append(_rule_finding("ELEVATED_INR", f"INR {inr['result_value']}", [inr["lab_id"]]))
    k = lab("Potassium")
    if k and num(k["result_value"]) is not None:
        v = num(k["result_value"])
        if v > 5.5 or v < 3.3:
            out.append(_rule_finding("ABNORMAL_POTASSIUM", f"Potassium {v}", [k["lab_id"]],
                                     "critical" if (v >= 6.0 or v <= 3.0) else None))
    na = lab("Sodium")
    if na and num(na["result_value"]) is not None and not (130 <= num(na["result_value"]) <= 150):
        out.append(_rule_finding("ABNORMAL_SODIUM", f"Sodium {na['result_value']}", [na["lab_id"]]))
    cr = lab("Creatinine")
    if cr and num(cr["result_value"]) is not None and num(cr["result_value"]) > 1.5:
        out.append(_rule_finding("ELEVATED_CREATININE", f"Creatinine {cr['result_value']}", [cr["lab_id"]]))
    hyper = []
    for t, lim in (("Glucose", 200), ("POC glucose", 200), ("HbA1c", 8.5)):
        r = lab(t)
        if r and num(r["result_value"]) is not None and num(r["result_value"]) > lim:
            hyper.append(r)
    if hyper:
        out.append(_rule_finding("HYPERGLYCEMIA", "; ".join(f"{r['test_name']} {r['result_value']}" for r in hyper),
                                 [r["lab_id"] for r in hyper]))
    alb = lab("Albumin")
    if alb and num(alb["result_value"]) is not None and num(alb["result_value"]) < 3.0:
        out.append(_rule_finding("LOW_ALBUMIN", f"Albumin {alb['result_value']}", [alb["lab_id"]]))
    lft = [r for r, lim in ((lab("AST"), 120), (lab("ALT"), 120), (lab("Total bilirubin"), 2.0))
           if r and num(r["result_value"]) is not None and num(r["result_value"]) > lim]
    if lft:
        out.append(_rule_finding("ELEVATED_LFTS", "; ".join(f"{r['test_name']} {r['result_value']}" for r in lft),
                                 [r["lab_id"] for r in lft]))
    uc, nit = lab("Urine culture"), lab("UA nitrite")
    uti = [r for r in (uc, nit) if r and r["result_value"] not in ("No growth", "Negative", "")]
    if uti:
        out.append(_rule_finding("URINARY_INFECTION", "; ".join(f"{r['test_name']}: {r['result_value']}" for r in uti),
                                 [r["lab_id"] for r in uti]))
    hcg = lab("Serum hCG")
    if hcg and hcg["result_value"] == "Positive":
        out.append(_rule_finding("POSITIVE_PREGNANCY", "Serum hCG positive", [hcg["lab_id"]]))

    b = chart["blood"]
    if b and b.get("antibody_screen") == "Positive":
        out.append(_rule_finding("POSITIVE_ANTIBODY_SCREEN", "Antibody screen positive", [b["blood_record_id"]]))

    ekg = latest([t for t in chart["diagnostics"] if t["test_type"] == "EKG"], "test_date")
    if ekg and ekg.get("compared_to_prior") == "New finding":
        out.append(_rule_finding("NEW_EKG_ABNORMALITY", f"EKG: {ekg['interpretation']}", [ekg["test_id"]]))
    echo = latest([t for t in chart["diagnostics"] if t["test_type"] == "Echocardiogram"], "test_date")
    if echo and num(echo["result_value"]) is not None and num(echo["result_value"]) < 35:
        out.append(_rule_finding("LOW_EJECTION_FRACTION", f"EF {echo['result_value']}%", [echo["test_id"]]))
    pft = latest([t for t in chart["diagnostics"] if t["test_type"] == "Pulmonary function test"], "test_date")
    if pft and num(pft["result_value"]) is not None and num(pft["result_value"]) < 50:
        out.append(_rule_finding("SEVERE_OBSTRUCTION", f"FEV1 {pft['result_value']}% predicted", [pft["test_id"]]))

    bc = next((c for c in chart["consents"] if c["consent_type"] == "Blood consent"), None)
    if bc and bc["status"] == "Refused":
        out.append(_rule_finding("BLOOD_REFUSAL", "Patient refuses blood products", [bc["consent_id"]]))

    for m in chart["meds"]:
        name, instr = m["medication_name"], (m.get("preop_instruction") or "").strip()
        if instr:
            continue
        if name in ANTITHROMBOTICS:
            out.append(_rule_finding("ANTITHROMBOTIC_NO_PLAN", f"{name} with no pre-op hold instruction", [m["medication_id"]]))
        elif name == "Metformin":
            out.append(_rule_finding("METFORMIN_NO_INSTRUCTION", "Metformin with no pre-op instruction", [m["medication_id"]]))
        elif name in INSULINS:
            out.append(_rule_finding("INSULIN_NO_INSTRUCTION", f"{name} with no pre-op instruction", [m["medication_id"]]))
        elif name in SGLT2:
            out.append(_rule_finding("SGLT2_NO_INSTRUCTION", f"{name} with no pre-op instruction", [m["medication_id"]]))
        elif name in GLP1:
            out.append(_rule_finding("GLP1_AGONIST", f"{name} with no pre-op instruction", [m["medication_id"]]))

    hist = (p.get("anesthesia_complication_history") or "").lower()
    if _has(p, "Obstructive sleep apnea"):
        out.append(_rule_finding("OBSTRUCTIVE_SLEEP_APNEA", "Obstructive sleep apnea", [p["patient_id"]]))
    if "malignant hyperthermia" in hist:
        out.append(_rule_finding("MALIGNANT_HYPERTHERMIA_RISK", p["anesthesia_complication_history"], [p["patient_id"]]))
    if "difficult airway" in hist:
        out.append(_rule_finding("DIFFICULT_AIRWAY", p["anesthesia_complication_history"], [p["patient_id"]]))
    if "nausea" in hist:
        out.append(_rule_finding("PONV_HISTORY", p["anesthesia_complication_history"], [p["patient_id"]]))
    if "latex" in (p.get("allergies") or "").lower():
        out.append(_rule_finding("LATEX_ALLERGY", "Latex allergy", [p["patient_id"]]))
    return out


def evaluate_structured(chart):
    """All findings a rules engine can produce from structured fields."""
    return check_requirements(chart) + check_values(chart)


def note_finding(code, detail, evidence):
    _, cat, _, nurse, anes = NOTE_FINDING_MAP[code]
    return _finding(code, cat, detail, nurse, anes, evidence, source="note")


def status_from_findings(findings):
    best = 0
    for f in findings:
        best = max(best, STATUS_ORDER.index(CATEGORY_TO_STATUS[f["category"]]))
    return STATUS_ORDER[best]


def actions_by_role(findings):
    out = {r: [] for r in ROLES}
    for f in findings:
        for role in ROLES:
            for code in f["actions"][role]:
                if code not in out[role]:
                    out[role].append(code)
    return out


# ---------------------------------------------------------------------------
# Human-readable criteria document (pasted into LLM prompts)
# ---------------------------------------------------------------------------
def criteria_document(procedure=None):
    lines = ["PRE-OP READINESS CRITERIA (synthetic teaching rules, not clinical guidelines)", "",
             "A. REQUIRED ITEMS"]
    for r in REQUIREMENTS:
        if procedure and r["procedure"] not in ("All", procedure):
            continue
        win = f"; valid {r['validity_days']} days before surgery" if r["validity_days"] else ""
        acts = ", ".join(f"{role}:{code}" for role, code in r["missing_actions"])
        lines.append(f"- [{r['procedure']}] {r['item']} ({r['item_type']}) when {CONDITION_TEXT[r['condition']]}{win}. If missing/outdated -> {acts}")
    lines += ["", "B. VALUE AND HISTORY RULES"]
    for code, cat, rule, nurse, anes in VALUE_RULES + NOTE_FINDINGS:
        acts = ", ".join([f"nurse:{c}" for c in nurse] + [f"anesthesia:{c}" for c in anes])
        lines.append(f"- {code} [{cat}]: {rule} -> {acts}")
    lines += ["", "C. STATUS",
              "- Recommend hold: any critical finding (positive pregnancy test, K >= 6.0 or <= 3.0, Hgb < 7).",
              "- Needs clinical review: any clinical finding.",
              "- Outstanding items: only missing/outdated documentation, labs, tests, instructions.",
              "- Ready: none of the above (routine/safety precautions may still apply)."]
    return "\n".join(lines)


def catalog_for_role(role):
    return {c: t for c, (r, t) in ACTION_CATALOG.items() if r == role}
