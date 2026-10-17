"""
Generate the v2 synthetic Pre-Op Readiness dataset.

100 fictional patients, 20 per procedure. Every value is invented.
Labs have realistic values and reference ranges; some cases have injected
problems (abnormal values, missing items, note-only findings) and the answer key
lists the expected next steps for the NURSE and the ANESTHESIOLOGIST.

Run from the repo root:   python surgical_patient_dataset_v2/generate_v2.py
Uses only the Python standard library and a fixed seed (same output every run).

NOT clinical data and NOT clinical guidelines. See preop/criteria.py.
"""
from __future__ import annotations

import csv
import math
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from preop import criteria as C  # noqa: E402

OUT = HERE
SEED = 20261017
R = random.Random(SEED)

# ---------------------------------------------------------------------------
# Static content
# ---------------------------------------------------------------------------
FIRST_F = ["Linda", "Maria", "Denise", "Karen", "Angela", "Tamika", "Rosa", "Heather", "Joan", "Priya",
           "Brenda", "Monica", "Sharon", "Keisha", "Lauren", "Gloria", "Yvonne", "Carmen", "Diane", "Erin"]
FIRST_M = ["Harold", "James", "Robert", "Luis", "Marcus", "Dennis", "Thomas", "Andre", "Michael", "Raj",
           "Gerald", "Kevin", "Victor", "Darnell", "Steven", "Frank", "Omar", "Wayne", "Paul", "Curtis"]
LAST = ["Whitfield", "Okafor", "Brennan", "Delgado", "Nguyen", "Hollis", "Pruitt", "Castillo", "Mercer",
        "Abernathy", "Lindqvist", "Batiste", "Fairchild", "Kowalski", "Rhodes", "Sandoval", "Tanaka",
        "Underwood", "Vasquez", "Wexler", "Yarbrough", "Zamora", "Ingram", "Gallagher", "Haddad"]

PROC = {
    "Laparoscopic Cholecystectomy": dict(loc="General OR", postop="PACU", surgeon="Dr. Synth Alvarez (General Surgery)",
                                        indication="Symptomatic cholelithiasis", ages=(22, 82), anes="General"),
    "Radical Mastectomy": dict(loc="Oncology OR", postop="Surgical ward", surgeon="Dr. Synth Morrow (Surgical Oncology)",
                               indication="Breast malignancy", ages=(32, 80), anes="General"),
    "Knee Arthroscopy": dict(loc="Ambulatory OR", postop="PACU", surgeon="Dr. Synth Patel (Orthopedics)",
                             indication="Meniscal tear", ages=(20, 76), anes="General or spinal"),
    "Ureteroscopy with Stent Placement": dict(loc="Urology OR", postop="PACU", surgeon="Dr. Synth Greene (Urology)",
                                              indication="Ureteral calculus", ages=(24, 80), anes="General"),
    "Coronary Artery Bypass Graft": dict(loc="Cardiac OR", postop="Cardiac ICU", surgeon="Dr. Synth Okonkwo (Cardiothoracic)",
                                         indication="Multivessel coronary artery disease", ages=(52, 84), anes="General"),
}
SIDED = {"Radical Mastectomy", "Knee Arthroscopy", "Ureteroscopy with Stent Placement"}


def side_for(sid, proc):
    """Left/Right for one-sided procedures. Own RNG so the rest of the dataset is unchanged."""
    return random.Random(f"{SEED}-{sid}-side").choice(["Left", "Right"]) if proc in SIDED else ""


IMAGING = {
    "Laparoscopic Cholecystectomy": ("RUQ ultrasound", "Multiple gallstones; no gallbladder wall thickening or ductal dilation."),
    "Radical Mastectomy": ("Breast MRI", "2.8 cm enhancing mass, {side} breast, upper outer quadrant; biopsy-proven invasive ductal carcinoma."),
    "Knee Arthroscopy": ("Knee MRI", "{Side} knee: complex tear of the posterior horn of the medial meniscus; no fracture."),
    "Ureteroscopy with Stent Placement": ("CT abdomen/pelvis", "6 mm {side} proximal ureteral calculus with mild {side} hydronephrosis."),
    "Coronary Artery Bypass Graft": ("Cardiac catheterization", "Three-vessel coronary artery disease: LAD 90%, circumflex 80%, RCA 75% stenosis."),
}
OTHER_DX = ["Hypertension", "Type 2 diabetes mellitus", "Hyperlipidemia", "Asthma", "Obstructive sleep apnea",
            "Chronic kidney disease", "Atrial fibrillation", "Hypothyroidism", "Gastroesophageal reflux disease", "COPD",
            "Obesity"]

# dx -> list of (name, dose, route, frequency, preop_instruction)
MEDS = {
    "Hypertension": [("Lisinopril", "10 mg", "PO", "Daily", "Hold morning of surgery")],
    "Type 2 diabetes mellitus": [("Metformin", "1000 mg", "PO", "BID", "Hold morning of surgery")],
    "Hyperlipidemia": [("Atorvastatin", "40 mg", "PO", "Nightly", "Continue")],
    "Asthma": [("Albuterol inhaler", "90 mcg 2 puffs", "INH", "Q4H PRN", "Bring inhaler day of surgery")],
    "Atrial fibrillation": [("Apixaban", "5 mg", "PO", "BID", "Hold 2 days before surgery per surgeon"),
                            ("Metoprolol succinate", "50 mg", "PO", "Daily", "Take morning of surgery with sip of water")],
    "Hypothyroidism": [("Levothyroxine", "75 mcg", "PO", "Daily", "Take morning of surgery")],
    "Gastroesophageal reflux disease": [("Omeprazole", "20 mg", "PO", "Daily", "Take morning of surgery")],
    "COPD": [("Tiotropium", "18 mcg", "INH", "Daily", "Take morning of surgery"),
             ("Albuterol inhaler", "90 mcg 2 puffs", "INH", "Q4H PRN", "Bring inhaler day of surgery")],
    "Anemia": [("Ferrous sulfate", "325 mg", "PO", "Daily", "Hold morning of surgery")],
    "Multivessel coronary artery disease": [("Aspirin", "81 mg", "PO", "Daily", "Continue through surgery"),
                                            ("Metoprolol succinate", "50 mg", "PO", "Daily", "Take morning of surgery with sip of water"),
                                            ("Atorvastatin", "80 mg", "PO", "Nightly", "Continue"),
                                            ("Nitroglycerin", "0.4 mg", "SL", "PRN chest pain", "Bring to hospital")],
}

ALLERGIES = ["No known drug allergies"] * 6 + ["Penicillin (hives)", "Sulfonamides (rash)", "Codeine (nausea)", "Latex (contact dermatitis)"]

# injection pools
COMMON = ["missing_surgery_consent", "missing_anesthesia_consent", "consent_conflict", "hp_outdated", "hp_missing",
          "note_exam_missing", "note_allergy_conflict", "note_new_symptoms", "note_mh_family", "mh_history",
          "difficult_airway", "antithrombotic_no_plan", "med_instruction_missing", "note_antithrombotic_conflict",
          "positive_hcg", "missing_hcg", "missing_hba1c", "missing_ekg", "outdated_ekg", "new_ekg_abn", "glp1"]
POOLS = {
    "Laparoscopic Cholecystectomy": COMMON + ["missing_lab", "outdated_lab", "low_hgb", "high_k", "low_na", "high_cr",
                                              "high_glucose", "high_lft", "missing_pulm_clearance", "elevated_inr"],
    "Radical Mastectomy": COMMON + ["missing_lab", "outdated_lab", "low_hgb", "low_plt", "high_k", "high_glucose",
                                    "expired_ts", "antibody_pos", "missing_blood_consent", "blood_refusal", "missing_pulm_clearance"],
    "Knee Arthroscopy": COMMON + ["missing_knee_bmp", "high_k", "high_glucose"],
    "Ureteroscopy with Stent Placement": COMMON + ["missing_lab", "outdated_lab", "positive_ua", "high_cr", "low_k", "low_hgb", "high_glucose"],
    "Coronary Artery Bypass Graft": [x for x in COMMON if x not in ("positive_hcg", "missing_hcg", "new_ekg_abn")] + [
        "missing_lab", "outdated_lab", "low_hgb", "low_plt", "high_k", "low_k", "high_cr", "high_glucose", "elevated_inr",
        "low_albumin", "high_lft", "expired_ts", "antibody_pos", "no_crossmatch", "missing_blood_consent", "blood_refusal",
        "low_ef", "missing_echo", "low_fev1", "missing_pft", "missing_cxr", "missing_cardiology", "pending_cardiology",
        "missing_pulm_clearance"],
}
EXCLUSIVE = [
    {"hp_missing", "hp_outdated", "note_exam_missing", "note_allergy_conflict", "note_new_symptoms", "note_mh_family",
     "consent_conflict", "note_antithrombotic_conflict"},
    {"blood_refusal", "no_crossmatch", "missing_blood_consent"},
    {"high_k", "low_k"},
    {"missing_lab", "outdated_lab"},
    {"positive_hcg", "missing_hcg"},
    {"missing_ekg", "outdated_ekg", "new_ekg_abn"},
    {"missing_cardiology", "pending_cardiology"},
    {"missing_pft", "low_fev1"},
    {"missing_echo", "low_ef"},
    {"mh_history", "note_mh_family", "difficult_airway"},
    {"antithrombotic_no_plan", "note_antithrombotic_conflict"},
    {"missing_anesthesia_consent", "consent_conflict"},
]
SHOWCASE = ["high_k", "elevated_inr", "antithrombotic_no_plan", "low_hgb", "high_glucose", "no_crossmatch", "note_new_symptoms"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def rnd(lo, hi, dp=1):
    v = R.uniform(lo, hi)
    return round(v, dp) if dp else int(round(v))


def egfr(cr, age, female):
    k, a = (0.7, -0.241) if female else (0.9, -0.302)
    v = 142 * min(cr / k, 1) ** a * max(cr / k, 1) ** -1.200 * 0.9938 ** age * (1.012 if female else 1)
    return int(round(v))


class Ids:
    def __init__(self):
        self.n = {}

    def __call__(self, prefix, width=4):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]:0{width}d}"


ID = Ids()


def eligible(inj, p, proc, chosen):
    female = p["sex"] == "Female"
    age = p["age"]
    dx = p["dx"]
    for group in EXCLUSIVE:
        if inj in group and group & set(chosen):
            return False
    if inj in ("positive_hcg", "missing_hcg"):
        return female and 18 <= age <= 50
    if inj in ("missing_ekg", "outdated_ekg", "new_ekg_abn"):
        return proc == "Coronary Artery Bypass Graft" or age >= 65 or bool(set(dx) & C.CARDIAC_DX)
    if inj == "missing_knee_bmp":
        return age >= 65 or bool({"Hypertension", "Type 2 diabetes mellitus", "Chronic kidney disease"} & set(dx))
    if inj in ("high_k",) and proc == "Knee Arthroscopy":
        return age >= 65 or bool({"Hypertension", "Type 2 diabetes mellitus", "Chronic kidney disease"} & set(dx))
    if inj == "note_allergy_conflict":
        return True
    if inj == "high_cr":
        return "Chronic kidney disease" not in dx  # CKD already makes creatinine high
    return True


def apply_dx_effects(inj, p):
    """Some injections need a diagnosis to make sense."""
    dx = p["dx"]
    need = {"high_glucose": "Type 2 diabetes mellitus", "missing_hba1c": "Type 2 diabetes mellitus",
            "med_instruction_missing": "Type 2 diabetes mellitus", "low_fev1": "COPD", "missing_pft": "COPD",
            "missing_pulm_clearance": "COPD", "elevated_inr": "Atrial fibrillation",
            "note_antithrombotic_conflict": "Atrial fibrillation", "glp1": "Obesity"}.get(inj)
    if need and need not in dx:
        dx.append(need)
    if inj == "note_allergy_conflict" and p["allergies"].startswith("No known"):
        p["allergies"] = "Penicillin (hives)"


# ---------------------------------------------------------------------------
# build one case
# ---------------------------------------------------------------------------
def make_case(idx, proc, n):
    info = PROC[proc]
    pid, sid = f"P{idx:03d}", f"S{idx:03d}"
    sdate = date(2026, 11, 9) + timedelta(days=(idx * 3) % 26)
    while sdate.weekday() >= 5:
        sdate += timedelta(days=1)
    sex = "Female" if proc == "Radical Mastectomy" else R.choice(["Female", "Male"])
    if proc == "Coronary Artery Bypass Graft" and n == 1:
        sex = "Male"
    age = R.randint(*info["ages"])
    if proc == "Coronary Artery Bypass Graft" and n == 1:
        age = 68
    k = R.choices([0, 1, 2, 3], [25, 35, 28, 12])[0]
    if proc == "Coronary Artery Bypass Graft":
        dx = [info["indication"], "Hypertension", "Hyperlipidemia"] + R.sample(
            ["Type 2 diabetes mellitus", "Chronic kidney disease", "COPD", "Obesity", "Obstructive sleep apnea",
             "Gastroesophageal reflux disease"], k=R.choice([0, 1, 1, 2]))
    else:
        dx = [info["indication"]] + R.sample(OTHER_DX, k=k)
    if proc == "Coronary Artery Bypass Graft" and n == 1:
        dx = [info["indication"], "Hypertension", "Hyperlipidemia", "Type 2 diabetes mellitus"]
    p = dict(sex=sex, age=age, dx=dx, allergies=R.choice(ALLERGIES))
    first = R.choice(FIRST_F if sex == "Female" else FIRST_M)
    p["name"] = f"{first} {R.choice(LAST)}"
    p["mrn"] = f"SYN{R.randint(100000, 999999)}"
    p["dob"] = (sdate - timedelta(days=age * 365 + R.randint(0, 360))).isoformat()
    h = rnd(152, 170, 0) if sex == "Female" else rnd(165, 188, 0)
    bmi = rnd(33, 41) if "Obesity" in dx else rnd(21, 29.5)
    p["height_cm"], p["weight_kg"], p["bmi"] = h, round(bmi * (h / 100) ** 2, 1), bmi
    p["smoking"] = R.choice(["Never", "Never", "Former", "Current"]) if "COPD" not in dx else R.choice(["Former", "Current"])
    p["anes_hx"] = "Prior postoperative nausea and vomiting" if R.random() < 0.1 else "None documented"

    # ---- choose injected problems --------------------------------------------
    chosen = []
    if n % 5 == 0:
        pass  # clean case
    elif proc == "Coronary Artery Bypass Graft" and n == 1:
        chosen = list(SHOWCASE)
        for inj in chosen:
            apply_dx_effects(inj, p)
    else:
        want = R.choices([1, 2, 3, 4], [10, 35, 35, 20])[0] if proc == "Coronary Artery Bypass Graft" \
            else R.choices([1, 2, 3], [40, 40, 20])[0]
        pool = POOLS[proc][:]
        R.shuffle(pool)
        for inj in pool:
            if len(chosen) >= want:
                break
            if eligible(inj, p, proc, chosen):
                chosen.append(inj)
                apply_dx_effects(inj, p)
    inj = set(chosen)
    if "mh_history" in inj:
        p["anes_hx"] = "Personal history of malignant hyperthermia (2011, treated with dantrolene)"
    if "difficult_airway" in inj:
        p["anes_hx"] = "Difficult airway - required video laryngoscope and bougie (2019)"
    if proc == "Coronary Artery Bypass Graft" and n == 1:
        p["anes_hx"] = "None documented"
        p["allergies"] = "No known drug allergies"

    female = sex == "Female"
    side = side_for(sid, proc)
    case = dict(surgery_id=sid, patient_id=pid, procedure=proc, laterality=side, surgery_date=sdate.isoformat(),
                surgery_time=R.choice(["07:30", "09:00", "10:45", "12:30", "14:00"]), surgery_location=f"{info['loc']} {R.randint(1, 4)}",
                surgeon=info["surgeon"], planned_anesthesia=info["anes"], postoperative_location=info["postop"],
                case_class="Elective")
    patient = dict(patient_id=pid, mrn=p["mrn"], name=p["name"], dob=p["dob"], age=age, sex=sex,
                   height_cm=p["height_cm"], weight_kg=p["weight_kg"], bmi=p["bmi"], smoking_status=p["smoking"],
                   diagnoses="; ".join(p["dx"]), allergies=p["allergies"], anesthesia_complication_history=p["anes_hx"])

    # ---- medications ---------------------------------------------------------
    meds = []
    seen = set()
    for dx_ in p["dx"]:
        for (name, dose, route, freq, instr) in MEDS.get(dx_, []):
            if dx_ == "Atrial fibrillation" and name == "Apixaban" and "elevated_inr" in inj:
                name, dose, freq, instr = "Warfarin", "5 mg", "Daily", "Hold 5 days before surgery per cardiology"
            if name in seen:
                continue
            seen.add(name)
            meds.append(dict(medication_id=ID("M"), patient_id=pid, medication_name=name, dose=dose, route=route,
                             frequency=freq, preop_instruction=instr, status="Active"))
    if "Type 2 diabetes mellitus" in p["dx"] and R.random() < 0.35 or ("med_instruction_missing" in inj and R.random() < 0.5):
        if "Insulin glargine" not in seen:
            meds.append(dict(medication_id=ID("M"), patient_id=pid, medication_name="Insulin glargine", dose="24 units",
                             route="SC", frequency="Nightly", preop_instruction="Take 80% of usual dose the night before surgery", status="Active"))
            seen.add("Insulin glargine")
    if "med_instruction_missing" in inj:
        targets = [m for m in meds if m["medication_name"] in ("Metformin", "Insulin glargine")]
        if R.random() < 0.3 or not targets:
            meds.append(dict(medication_id=ID("M"), patient_id=pid, medication_name="Empagliflozin", dose="10 mg",
                             route="PO", frequency="Daily", preop_instruction="", status="Active"))
        else:
            R.choice(targets)["preop_instruction"] = ""
    if "glp1" in inj:
        meds.append(dict(medication_id=ID("M"), patient_id=pid, medication_name="Semaglutide", dose="1 mg",
                         route="SC", frequency="Weekly", preop_instruction="", status="Active"))
    if "antithrombotic_no_plan" in inj:
        at = [m for m in meds if m["medication_name"] in C.ANTITHROMBOTICS]
        if at:
            for m in at:
                m["preop_instruction"] = ""
        else:
            meds.append(dict(medication_id=ID("M"), patient_id=pid, medication_name="Clopidogrel", dose="75 mg",
                             route="PO", frequency="Daily", preop_instruction="", status="Active"))

    # ---- labs ------------------------------------------------------------------
    chart_stub = dict(case=case, patient=dict(patient, diagnoses=p["dx"]), consents=[])
    reqs = C.applicable_requirements(chart_stub)
    lab_panels = [r["item"] for r in reqs if r["item_type"] == "lab"]
    # optional extras sometimes drawn anyway
    for extra in ("CBC", "BMP"):
        if extra not in lab_panels and R.random() < 0.35:
            lab_panels.append(extra)
    if "elevated_inr" in inj and "Coagulation panel" not in lab_panels:
        lab_panels.append("Coagulation panel")
    if ("high_k" in inj or "low_k" in inj or "high_cr" in inj or "low_na" in inj or "high_glucose" in inj) and "BMP" not in lab_panels:
        lab_panels.append("BMP")
    if ("low_hgb" in inj or "low_plt" in inj) and "CBC" not in lab_panels:
        lab_panels.append("CBC")
    if "Type 2 diabetes mellitus" in p["dx"] and "POC glucose" not in lab_panels:
        lab_panels.append("POC glucose")
    if "missing_hcg" in inj:
        lab_panels.remove("Pregnancy test")
    if "missing_hba1c" in inj and "HbA1c" in lab_panels:
        lab_panels.remove("HbA1c")
    if "missing_knee_bmp" in inj and "BMP" in lab_panels:
        lab_panels.remove("BMP")

    required_30 = [r["item"] for r in reqs if r["item_type"] == "lab" and r["validity_days"] == 30]
    target_panel = R.choice(required_30) if required_30 else None
    if "missing_lab" in inj and target_panel:
        lab_panels.remove(target_panel)

    pat_visit = sdate - timedelta(days=R.randint(5, 18))
    labs = []

    def add_lab(panel, test, value, unit, lo, hi, when):
        flag = ""
        v = C.num(value)
        if v is not None and lo != "" and v < float(lo):
            flag = "L"
        if v is not None and hi != "" and v > float(hi):
            flag = "H"
        if isinstance(value, str) and value not in ("Negative", "No growth", "None seen") and C.num(value) is None:
            flag = "Abnormal"
        crit = (test == "Potassium" and v is not None and (v >= 6.0 or v <= 3.0)) or \
               (test == "Hemoglobin" and v is not None and v < 7) or (test == "Serum hCG" and value == "Positive")
        if crit:
            flag = "Critical"
        labs.append(dict(lab_id=ID("L"), surgery_id=sid, patient_id=pid, panel=panel, test_name=test,
                         result_value=value, unit=unit, reference_low=lo, reference_high=hi, flag=flag,
                         collection_date=when.isoformat(), result_status="Final"))

    dm = "Type 2 diabetes mellitus" in p["dx"]
    ckd = "Chronic kidney disease" in p["dx"]
    for panel in lab_panels:
        when = pat_visit
        if panel == "HbA1c":
            when = sdate - timedelta(days=R.randint(10, 70))
        if panel == "Pregnancy test":
            when = sdate - timedelta(days=R.randint(1, 5))
        if "outdated_lab" in inj and panel == target_panel:
            when = sdate - timedelta(days=R.randint(45, 80))
        if "outdated_lab" in inj and target_panel is None and panel == "HbA1c":
            when = sdate - timedelta(days=R.randint(120, 160))
        if panel == "CBC":
            hgb = rnd(12.1, 14.8) if female else rnd(13.6, 16.4)
            if "low_hgb" in inj:
                hgb = 8.7 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(7.6, 9.4)
            plt = rnd(165, 355, 0) if "low_plt" not in inj else rnd(62, 88, 0)
            add_lab(panel, "WBC", rnd(4.6, 10.2), "10^3/uL", 4.0, 11.0, when)
            add_lab(panel, "Hemoglobin", hgb, "g/dL", 12.0 if female else 13.5, 15.5 if female else 17.5, when)
            add_lab(panel, "Hematocrit", round(hgb * 3 + R.uniform(-1, 1), 1), "%", 35.5 if female else 38.3, 44.9 if female else 48.6, when)
            add_lab(panel, "Platelets", plt, "10^3/uL", 150, 400, when)
        elif panel == "BMP":
            k = rnd(3.7, 4.8)
            if "high_k" in inj:
                k = 5.9 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(5.7, 6.3)
            if "low_k" in inj:
                k = rnd(2.8, 3.1)
            na = rnd(136, 143, 0) if "low_na" not in inj else rnd(124, 128, 0)
            cr = (rnd(0.6, 0.95, 2) if female else rnd(0.75, 1.15, 2))
            if age > 75:
                cr = min(cr, 0.9)
            if ckd:
                cr = rnd(1.7, 2.4, 2)
            if "high_cr" in inj:
                cr = rnd(1.8, 2.6, 2)
            glu = rnd(115, 168, 0) if dm else rnd(76, 108, 0)
            if "high_glucose" in inj:
                glu = 268 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(232, 310, 0)
            add_lab(panel, "Sodium", na, "mmol/L", 135, 145, when)
            add_lab(panel, "Potassium", k, "mmol/L", 3.5, 5.1, when)
            add_lab(panel, "Chloride", rnd(99, 106, 0), "mmol/L", 98, 107, when)
            add_lab(panel, "CO2", rnd(23, 29, 0), "mmol/L", 22, 29, when)
            add_lab(panel, "BUN", rnd(9, 19, 0) if not (ckd or "high_cr" in inj) else rnd(28, 42, 0), "mg/dL", 7, 20, when)
            add_lab(panel, "Creatinine", cr, "mg/dL", 0.59 if female else 0.74, 1.04 if female else 1.35, when)
            add_lab(panel, "Glucose", glu, "mg/dL", 70, 99, when)
            add_lab(panel, "Calcium", rnd(8.8, 10.0), "mg/dL", 8.6, 10.3, when)
            add_lab(panel, "eGFR", egfr(cr, age, female), "mL/min/1.73m2", 60, "", when)
        elif panel == "Coagulation panel":
            inr = rnd(0.9, 1.1)
            pt = rnd(11.4, 13.2)
            if "elevated_inr" in inj:
                inr = 2.1 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(2.0, 2.9)
                pt = round(inr * 11.2 + R.uniform(-0.5, 0.5), 1)
            add_lab(panel, "PT", pt, "sec", 11.0, 13.5, when)
            add_lab(panel, "INR", inr, "ratio", 0.8, 1.2, when)
            add_lab(panel, "PTT", rnd(26, 34, 0), "sec", 25, 35, when)
        elif panel == "Liver function tests":
            hi = "high_lft" in inj
            add_lab(panel, "AST", rnd(15, 33, 0) if not hi else rnd(165, 240, 0), "U/L", 10, 40, when)
            add_lab(panel, "ALT", rnd(11, 36, 0) if not hi else rnd(190, 280, 0), "U/L", 7, 56, when)
            add_lab(panel, "Alkaline phosphatase", rnd(48, 112, 0) if not hi else rnd(180, 260, 0), "U/L", 44, 147, when)
            add_lab(panel, "Total bilirubin", rnd(0.3, 1.0) if not hi else rnd(2.4, 3.6), "mg/dL", 0.1, 1.2, when)
        elif panel == "Albumin":
            add_lab(panel, "Albumin", rnd(3.6, 4.6) if "low_albumin" not in inj else rnd(2.4, 2.8), "g/dL", 3.5, 5.0, when)
        elif panel == "HbA1c":
            a1c = (rnd(6.3, 7.8) if dm else rnd(4.9, 5.6))
            if "high_glucose" in inj:
                a1c = 9.4 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(9.0, 10.8)
            add_lab(panel, "HbA1c", a1c, "%", 4.0, 5.6, when)
        elif panel == "POC glucose":
            g = rnd(112, 176, 0)
            if "high_glucose" in inj:
                g = 254 if (proc == "Coronary Artery Bypass Graft" and n == 1) else rnd(225, 295, 0)
            add_lab(panel, "POC glucose", g, "mg/dL", 70, 140, when)
        elif panel == "Urinalysis":
            pos = "positive_ua" in inj
            add_lab(panel, "UA leukocyte esterase", "Positive (2+)" if pos else "Negative", "text", "", "", when)
            add_lab(panel, "UA nitrite", "Positive" if pos else "Negative", "text", "", "", when)
            add_lab(panel, "UA WBC", rnd(30, 60, 0) if pos else rnd(0, 4, 0), "/hpf", 0, 5, when)
            add_lab(panel, "UA bacteria", "Many" if pos else "None seen", "text", "", "", when)
        elif panel == "Urine culture":
            add_lab(panel, "Urine culture", ">100,000 CFU/mL Escherichia coli" if "positive_ua" in inj else "No growth",
                    "text", "", "", when)
        elif panel == "Pregnancy test":
            add_lab(panel, "Serum hCG", "Positive" if "positive_hcg" in inj else "Negative", "text", "", "", when)

    # ---- diagnostics -----------------------------------------------------------
    diags = []
    cabg = proc == "Coronary Artery Bypass Graft"
    ekg_req = any(r["item"] == "EKG" for r in reqs)
    if (ekg_req or R.random() < 0.2) and "missing_ekg" not in inj:
        when = sdate - timedelta(days=R.randint(3, 25))
        if "outdated_ekg" in inj:
            when = sdate - timedelta(days=(R.randint(45, 80) if cabg else R.randint(120, 200)))
        if "Atrial fibrillation" in p["dx"]:
            interp, comp = "Atrial fibrillation, controlled ventricular rate (78 bpm)", "No change"
        elif cabg:
            interp, comp = "Sinus rhythm, 72 bpm; Q waves in II, III, aVF consistent with old inferior infarct", "No change"
        else:
            interp, comp = R.choice(["Normal sinus rhythm, 74 bpm", "Sinus rhythm, 68 bpm; normal axis",
                                     "Sinus bradycardia, 56 bpm; otherwise normal"]), ("No prior" if R.random() < 0.4 else "No change")
        if "new_ekg_abn" in inj:
            interp, comp = R.choice(["Sinus rhythm with new 1.5 mm ST depression in V4-V6",
                                     "New left bundle branch block",
                                     "New atrial fibrillation with rapid ventricular response (118 bpm)"]), "New finding"
        diags.append(dict(test_id=ID("T"), surgery_id=sid, patient_id=pid, test_type="EKG", test_date=when.isoformat(),
                          result_value="", result_unit="", interpretation=interp, compared_to_prior=comp, status="Final"))
    if cabg and "missing_echo" not in inj:
        ef = rnd(50, 60, 0) if "low_ef" not in inj else rnd(25, 32, 0)
        diags.append(dict(test_id=ID("T"), surgery_id=sid, patient_id=pid, test_type="Echocardiogram",
                          test_date=(sdate - timedelta(days=R.randint(10, 90))).isoformat(), result_value=ef, result_unit="% EF",
                          interpretation=f"LVEF {ef}%; " + ("normal LV size, mild inferior hypokinesis" if ef >= 50 else "dilated LV with global hypokinesis"),
                          compared_to_prior="No prior", status="Final"))
    if "COPD" in p["dx"] and (cabg or R.random() < 0.4) and "missing_pft" not in inj:
        fev = rnd(56, 74, 0) if "low_fev1" not in inj else rnd(36, 46, 0)
        diags.append(dict(test_id=ID("T"), surgery_id=sid, patient_id=pid, test_type="Pulmonary function test",
                          test_date=(sdate - timedelta(days=R.randint(20, 200))).isoformat(), result_value=fev, result_unit="% predicted FEV1",
                          interpretation=f"FEV1 {fev}% predicted, FEV1/FVC 0.{R.randint(55, 66)}; " + ("moderate" if fev >= 50 else "severe") + " obstruction",
                          compared_to_prior="No prior", status="Final"))

    # ---- imaging ---------------------------------------------------------------
    imgs = []
    it, rep = IMAGING[proc]
    rep = rep.format(side=side.lower(), Side=side)
    imgs.append(dict(imaging_id=ID("I", 3), surgery_id=sid, patient_id=pid, imaging_type=it,
                     imaging_date=(sdate - timedelta(days=R.randint(14, 60))).isoformat(), report=rep, status="Final"))
    if cabg and "missing_cxr" not in inj:
        imgs.append(dict(imaging_id=ID("I", 3), surgery_id=sid, patient_id=pid, imaging_type="Chest X-ray",
                         imaging_date=(sdate - timedelta(days=R.randint(3, 20))).isoformat(),
                         report="No acute cardiopulmonary process." + (" Hyperinflation consistent with COPD." if "COPD" in p["dx"] else ""),
                         status="Final"))

    # ---- clearances ------------------------------------------------------------
    clears = []
    if cabg and "missing_cardiology" not in inj:
        pend = "pending_cardiology" in inj
        req_d = sdate - timedelta(days=R.randint(12, 30))
        clears.append(dict(clearance_id=ID("C"), surgery_id=sid, patient_id=pid, clearance_type="Cardiology assessment",
                           status="Pending" if pend else "Completed", requested_date=req_d.isoformat(),
                           completed_date="" if pend else (req_d + timedelta(days=R.randint(2, 7))).isoformat(),
                           assessment_note="" if pend else "Appropriate candidate for surgical revascularization; continue aspirin and beta blocker."))
    if "COPD" in p["dx"] and proc in ("Laparoscopic Cholecystectomy", "Radical Mastectomy", "Coronary Artery Bypass Graft") \
            and "missing_pulm_clearance" not in inj:
        req_d = sdate - timedelta(days=R.randint(12, 30))
        clears.append(dict(clearance_id=ID("C"), surgery_id=sid, patient_id=pid, clearance_type="Pulmonary assessment",
                           status="Completed", requested_date=req_d.isoformat(),
                           completed_date=(req_d + timedelta(days=R.randint(2, 7))).isoformat(),
                           assessment_note="COPD stable on current inhalers; acceptable pulmonary risk. Incentive spirometry post-op."))

    # ---- consents --------------------------------------------------------------
    consents = []
    signed = (sdate - timedelta(days=R.randint(1, 10))).isoformat()
    types = ["Surgery consent", "Anesthesia consent"] + (["Blood consent"] if proc in ("Radical Mastectomy", "Coronary Artery Bypass Graft") else [])
    for t in types:
        status = "Signed"
        if t == "Surgery consent" and "missing_surgery_consent" in inj:
            status = "Missing"
        if t == "Anesthesia consent" and ({"missing_anesthesia_consent", "consent_conflict"} & inj):
            status = "Missing"
        if t == "Blood consent" and "missing_blood_consent" in inj:
            status = "Missing"
        if t == "Blood consent" and "blood_refusal" in inj:
            status = "Refused"
        consents.append(dict(consent_id=ID("CO"), surgery_id=sid, patient_id=pid, consent_type=t, status=status,
                             signed_date=signed if status in ("Signed", "Refused") else ""))

    # ---- blood bank ------------------------------------------------------------
    blood = None
    if proc in ("Radical Mastectomy", "Coronary Artery Bypass Graft"):
        ts = sdate - timedelta(days=(R.randint(1, 2) if "expired_ts" not in inj else R.randint(6, 9)))
        refusing = "blood_refusal" in inj
        blood = dict(blood_record_id=ID("B", 3), surgery_id=sid, patient_id=pid,
                     abo_rh=R.choice(["O+", "O+", "A+", "A+", "B+", "AB+", "O-", "A-"]),
                     antibody_screen="Positive" if "antibody_pos" in inj else "Negative",
                     type_screen_date=ts.isoformat(), type_screen_expires=(ts + timedelta(days=3)).isoformat(),
                     prbc_crossmatched_units=(0 if (refusing or "no_crossmatch" in inj or not cabg) else 2),
                     ffp_units_available=("Not applicable - refuses blood" if refusing else ("4" if cabg else "On request")),
                     platelet_units_available=("Not applicable - refuses blood" if refusing else ("2" if cabg else "On request")))

    # ---- past surgeries --------------------------------------------------------
    past = []
    for pp in R.sample(["Appendectomy", "Hernia repair", "Cesarean section", "Tonsillectomy", "Cataract surgery",
                        "Carpal tunnel release", "Colonoscopy with polypectomy"], k=R.choices([0, 1, 2], [40, 40, 20])[0]):
        if pp == "Cesarean section" and not female:
            continue
        past.append(dict(history_id=ID("PS"), patient_id=pid, prior_procedure=pp,
                         procedure_year=R.randint(max(1990, sdate.year - age + 18), 2024),
                         anesthesia_type="General", prior_anesthesia_issue=p["anes_hx"] if p["anes_hx"] != "None documented" else "None documented"))

    # ---- H&P note --------------------------------------------------------------
    notes = []
    note_findings = []
    if "hp_missing" not in inj:
        nd = sdate - timedelta(days=(R.randint(3, 20) if "hp_outdated" not in inj else R.randint(42, 75)))
        nid = ID("N", 3)
        he = f"{'She' if female else 'He'}"
        hpi = {
            "Laparoscopic Cholecystectomy": f"{age}-year-old {sex.lower()} with recurrent postprandial RUQ pain; ultrasound shows cholelithiasis. Presents for elective laparoscopic cholecystectomy.",
            "Radical Mastectomy": f"{age}-year-old female with biopsy-proven invasive ductal carcinoma of the {side.lower()} breast. Presents for radical mastectomy after multidisciplinary tumor board review.",
            "Knee Arthroscopy": f"{age}-year-old {sex.lower()} with mechanical {side.lower()} knee pain and locking; MRI shows medial meniscus tear. Presents for elective arthroscopy.",
            "Ureteroscopy with Stent Placement": f"{age}-year-old {sex.lower()} with intermittent {side.lower()} flank pain; CT shows 6 mm proximal ureteral stone. Presents for ureteroscopy and stent placement.",
            "Coronary Artery Bypass Graft": f"{age}-year-old {sex.lower()} with exertional angina; catheterization shows three-vessel coronary artery disease. Presents for elective CABG.",
        }[proc]
        ros = "Denies chest pain, shortness of breath, fever, or recent illness."
        if "note_new_symptoms" in inj:
            sym = ("Reports two episodes of chest pressure at rest over the past 3 days, each lasting about 10 minutes and relieved by nitroglycerin."
                   if cabg else R.choice([
                       "Reports new chest tightness with walking one block over the past week; has not seen a doctor for this.",
                       "Reports fever to 101.2 F and productive cough for the past 3 days.",
                       "Reports new shortness of breath climbing one flight of stairs over the past two weeks and ankle swelling."]))
            hpi += " " + sym
            ros = "Positive as noted in HPI; otherwise negative."
            note_findings.append(C.note_finding("NOTE_NEW_SYMPTOMS", sym, [nid]))
        allergy_line = p["allergies"]
        if "note_allergy_conflict" in inj:
            allergy_line = "NKDA"
            note_findings.append(C.note_finding("NOTE_ALLERGY_CONFLICT",
                                                f"H&P says NKDA; allergy list says {p['allergies']}", [nid, pid]))
        med_line = "; ".join(f"{m['medication_name']} {m['dose']} {m['frequency']}" for m in meds) or "None"
        fam = "Noncontributory."
        if "note_mh_family" in inj:
            fam = ("Brother developed a very high fever and muscle rigidity during anesthesia for an appendectomy "
                   "and was transferred to the ICU; the family was told to warn doctors before any surgery.")
            note_findings.append(C.note_finding("NOTE_MH_FAMILY_HISTORY", fam, [nid]))
        heart = "Irregularly irregular rhythm, rate controlled; no murmurs." if "Atrial fibrillation" in p["dx"] else "Regular rate and rhythm; no murmurs, rubs, or gallops."
        lungs = "Mildly diminished breath sounds bilaterally; no wheezes or crackles." if "COPD" in p["dx"] else "Clear to auscultation bilaterally."
        if "note_new_symptoms" in inj and "fever" in hpi:
            lungs = "Scattered rhonchi in the right lower lobe."
        mall = R.choice(["Mallampati II", "Mallampati II", "Mallampati III"]) if "difficult_airway" not in inj else "Mallampati IV, limited mouth opening"
        exam = (f"Vitals: BP {R.randint(118, 148)}/{R.randint(68, 88)}, HR {R.randint(60, 88)}, SpO2 {R.randint(94, 99)}% RA, BMI {p['bmi']}.\n"
                f"General: No acute distress.\nAirway: {mall}; full neck range of motion.\nHeart: {heart}\nLungs: {lungs}")
        if "note_exam_missing" in inj:
            exam = "Physical exam: deferred to day of surgery."
            note_findings.append(C.note_finding("NOTE_EXAM_INCOMPLETE", "H&P has no heart or lung exam", [nid]))
        plan = f"Proceed with {(side + ' ' if side else '').lower()}{proc.lower()} as scheduled pending pre-operative review."
        if "consent_conflict" in inj:
            plan += " Surgical and anesthesia consents signed and in chart."
            note_findings.append(C.note_finding("NOTE_CONSENT_CONFLICT",
                                                "H&P says anesthesia consent signed; consent record says missing", [nid]))
        if "note_antithrombotic_conflict" in inj:
            at = next(m for m in meds if m["medication_name"] in C.ANTITHROMBOTICS)
            sent = (f"{he} states {he.lower()} was not told to stop {at['medication_name'].lower()} and plans to keep "
                    f"taking it until the day of surgery.")
            plan += " " + sent
            note_findings.append(C.note_finding("NOTE_ANTITHROMBOTIC_CONFLICT",
                                                f"Med list says '{at['preop_instruction']}' but H&P: {sent}", [nid, at["medication_id"]]))
        text = (f"HISTORY AND PHYSICAL\nDate: {nd.isoformat()}  Author: {info['surgeon']}\n\n"
                f"HPI: {hpi}\nPMH: {'; '.join(p['dx'])}\n"
                f"PSH: {'; '.join(x['prior_procedure'] for x in past) or 'None'}\n"
                f"Medications: {med_line}\nAllergies: {allergy_line}\n"
                f"Social: Smoking status {p['smoking'].lower()}.\nFamily history: {fam}\nROS: {ros}\n\n{exam}\n\n"
                f"Assessment/Plan: {p['dx'][0]}. {plan}")
        notes.append(dict(note_id=nid, surgery_id=sid, patient_id=pid, note_type="History and Physical",
                          note_date=nd.isoformat(), author=info["surgeon"], note_text=text))

    chart = dict(case=case, patient=dict(patient, diagnoses=p["dx"]), meds=meds, labs=labs, diagnostics=diags,
                 imaging=imgs, clearances=clears, consents=consents, blood=blood, notes=notes, past_surgeries=past)
    findings = C.evaluate_structured(chart) + note_findings
    return dict(case=case, patient=patient, meds=meds, labs=labs, diags=diags, imgs=imgs, clears=clears,
                consents=consents, blood=blood, notes=notes, past=past, injected=chosen, findings=findings)


# ---------------------------------------------------------------------------
# write files
# ---------------------------------------------------------------------------
def write(name, rows, fields):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main():
    TEST_N = {5, 7, 13, 18}  # 4 per procedure -> 20 held-out cases (one clean)
    cases = []
    idx = 0
    for proc in C.PROCEDURES:
        for n in range(20):
            idx += 1
            c = make_case(idx, proc, n)
            c["split"] = "test" if n in TEST_N else "dev"
            cases.append(c)

    T = lambda key: [r for c in cases for r in (c[key] if isinstance(c[key], list) else ([c[key]] if c[key] else []))]
    write("patients.csv", T("patient"), ["patient_id", "mrn", "name", "dob", "age", "sex", "height_cm", "weight_kg", "bmi",
                                         "smoking_status", "diagnoses", "allergies", "anesthesia_complication_history"])
    write("surgical_cases.csv", [dict(c["case"], split=c["split"]) for c in cases],
          ["surgery_id", "patient_id", "procedure", "laterality", "surgery_date", "surgery_time", "surgery_location", "surgeon",
           "planned_anesthesia", "postoperative_location", "case_class", "split"])
    write("medications.csv", T("meds"), ["medication_id", "patient_id", "medication_name", "dose", "route", "frequency",
                                         "preop_instruction", "status"])
    write("lab_results.csv", T("labs"), ["lab_id", "surgery_id", "patient_id", "panel", "test_name", "result_value", "unit",
                                         "reference_low", "reference_high", "flag", "collection_date", "result_status"])
    write("diagnostic_tests.csv", T("diags"), ["test_id", "surgery_id", "patient_id", "test_type", "test_date", "result_value",
                                               "result_unit", "interpretation", "compared_to_prior", "status"])
    write("imaging.csv", T("imgs"), ["imaging_id", "surgery_id", "patient_id", "imaging_type", "imaging_date", "report", "status"])
    write("clearances.csv", T("clears"), ["clearance_id", "surgery_id", "patient_id", "clearance_type", "status",
                                          "requested_date", "completed_date", "assessment_note"])
    write("consents.csv", T("consents"), ["consent_id", "surgery_id", "patient_id", "consent_type", "status", "signed_date"])
    write("blood_products.csv", T("blood"), ["blood_record_id", "surgery_id", "patient_id", "abo_rh", "antibody_screen",
                                             "type_screen_date", "type_screen_expires", "prbc_crossmatched_units",
                                             "ffp_units_available", "platelet_units_available"])
    write("clinical_notes.csv", T("notes"), ["note_id", "surgery_id", "patient_id", "note_type", "note_date", "author", "note_text"])
    write("past_surgeries.csv", T("past"), ["history_id", "patient_id", "prior_procedure", "procedure_year", "anesthesia_type",
                                            "prior_anesthesia_issue"])

    # criteria files (what the hospital "policy" says)
    write("procedure_requirements.csv",
          [dict(r, condition=C.CONDITION_TEXT[r["condition"]], validity_days=r["validity_days"] or "",
                missing_actions=" | ".join(f"{a}:{b}" for a, b in r["missing_actions"])) for r in C.REQUIREMENTS],
          ["requirement_id", "procedure", "item_type", "item", "condition", "validity_days", "missing_actions", "description"])
    write("readiness_rules.csv",
          [dict(finding_code=a, category=b, rule=c, nurse_actions=" | ".join(d_), anesthesia_actions=" | ".join(e),
                source="note" if a.startswith("NOTE_") else "structured")
           for a, b, c, d_, e in C.VALUE_RULES + C.NOTE_FINDINGS],
          ["finding_code", "category", "rule", "nurse_actions", "anesthesia_actions", "source"])
    write("action_catalog.csv", [dict(action_code=k, role=v[0], action=v[1]) for k, v in C.ACTION_CATALOG.items()],
          ["action_code", "role", "action"])

    # answer key -- HIDE FROM THE AI
    gt_cases, gt_find = [], []
    for c in cases:
        acts = C.actions_by_role(c["findings"])
        gt_cases.append(dict(surgery_id=c["case"]["surgery_id"], patient_id=c["case"]["patient_id"],
                             procedure=c["case"]["procedure"], split=c["split"],
                             injected_scenarios=" | ".join(c["injected"]) or "none",
                             expected_status=C.status_from_findings(c["findings"]),
                             expected_findings=" | ".join(f["finding_code"] for f in c["findings"]),
                             expected_nurse_actions=" | ".join(acts["nurse"]),
                             expected_anesthesia_actions=" | ".join(acts["anesthesia"]),
                             note_only_findings=" | ".join(f["finding_code"] for f in c["findings"] if f["source"] == "note")))
        for f in c["findings"]:
            gt_find.append(dict(surgery_id=c["case"]["surgery_id"], finding_code=f["finding_code"], category=f["category"],
                                source=f["source"], detail=f["detail"], nurse_actions=" | ".join(f["actions"]["nurse"]),
                                anesthesia_actions=" | ".join(f["actions"]["anesthesia"]),
                                evidence_ids=" | ".join(f["evidence_ids"])))
    os.makedirs(os.path.join(OUT, "answer_key"), exist_ok=True)
    write("answer_key/ground_truth_cases.csv", gt_cases, list(gt_cases[0].keys()))
    write("answer_key/ground_truth_findings.csv", gt_find, list(gt_find[0].keys()))
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
