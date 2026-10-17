# Surgical Patient Preparedness - Synthetic Dataset v2

100 fictional adult patients, 20 per procedure (laparoscopic cholecystectomy, radical mastectomy, knee arthroscopy,
ureteroscopy with stent placement, CABG). Built by `generate_v2.py` (standard library only, fixed seed).

Compared with v1, every lab has a **real-looking value, reference range and flag**, so the system can recommend next
steps based on *what the values are*, not only whether a document exists.

## Files the AI may see

| File | Contents |
|---|---|
| `patients.csv` | name, MRN, DOB, age, sex, height/weight/BMI, smoking, diagnoses, allergies, anesthesia history |
| `surgical_cases.csv` | procedure, date/time, OR, surgeon, planned anesthesia, post-op unit, `split` (dev/test - bookkeeping, hidden from the AI) |
| `medications.csv` | drug, dose, route, frequency, **pre-op instruction** (blank = none documented) |
| `lab_results.csv` | CBC, BMP (+eGFR), coags (PT/INR/PTT), LFTs, albumin, HbA1c, POC glucose, urinalysis, urine culture, serum hCG |
| `diagnostic_tests.csv` | EKG (with change from prior), echocardiogram (EF), PFTs (FEV1 % predicted) |
| `imaging.csv` | procedure imaging report; chest X-ray for CABG |
| `clearances.csv` | cardiology / pulmonary assessments: Completed or Pending |
| `consents.csv` | surgery, anesthesia, blood: Signed / Missing / Refused |
| `blood_products.csv` | ABO/Rh, antibody screen, type & screen date and expiration, crossmatched PRBC, FFP, platelets |
| `clinical_notes.csv` | full H&P: HPI, PMH, meds, allergies, family history, ROS, airway, heart and lung exam |
| `past_surgeries.csv` | prior procedures and anesthesia issues |

## Criteria files (the hospital's "policy" - included in the AI prompt)

| File | Contents |
|---|---|
| `procedure_requirements.csv` | what each procedure requires, when, and how recent it must be |
| `readiness_rules.csv` | value/history rules (e.g., K > 5.5) and which nurse/anesthesia actions they trigger |
| `action_catalog.csv` | the order set: every action code, which role owns it, and its wording |

## Answer key - NEVER give to the AI

`answer_key/ground_truth_cases.csv`: expected status, findings, and expected **nurse** and **anesthesia** actions per case.
`answer_key/ground_truth_findings.csv`: one row per finding with evidence record IDs and whether it is visible in
structured data or **only in the H&P text**.

## What's in the cases

* 20 clean cases (4 per procedure); the rest have 1-4 injected problems such as missing or expired labs, abnormal
  values (low Hgb, high K, high INR on warfarin, hyperglycemia, positive urine culture, positive pregnancy test), missing
  consents, blood refusal, expired type & screen, positive antibody screen, missing crossmatch, low EF, severe COPD,
  pending clearances, blood thinners or diabetes drugs without pre-op instructions, GLP-1 agonists, MH or difficult-airway history.
* **Note-only problems** (only findable by reading the H&P): new chest pain / dyspnea / fever, allergy list vs H&P
  conflict, consent conflict, family history suggesting malignant hyperthermia, patient still taking a blood thinner the
  med list says to hold, H&P missing a heart/lung exam.
* Expected statuses (all 100 cases): Ready 21 · Outstanding items 34 · Needs clinical review 40 · Recommend hold 5
  (positive pregnancy test, K ≥ 6.0 or ≤ 3.0, Hgb < 7). The test split has no "Recommend hold" case.
* Showcase case **S082**: 68-year-old man for CABG with K 5.9, INR 2.1 on warfarin with no hold plan, Hgb 8.7,
  glucose 268 / HbA1c 9.4, no crossmatched blood, and rest chest pressure documented only in the H&P.
* Split: 80 dev / 20 test, 4 test cases per procedure (`split` column).

All thresholds and windows (labs 30 days, HbA1c 90, EKG 90 or 30 for CABG, hCG 7, type & screen 3) are teaching
rules, **not clinical guidelines**.
