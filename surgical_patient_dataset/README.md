# Surgical Patient Preparedness — Fully Synthetic Dataset

100 fictional adult patients (18–90), 20 cases per procedure: laparoscopic cholecystectomy, radical mastectomy, knee arthroscopy, ureteroscopy with stent placement, and coronary artery bypass graft.

## Data layout
- `patients.csv`: demographics, diagnoses, history, allergies
- `surgical_cases.csv`: one master overview per case (100 cases)
- `past_surgeries.csv`: zero or more previous procedures per patient
- `medications.csv`: synthetic active medication records
- `lab_results.csv`: dated laboratory results (missing tests represented by absent rows)
- `diagnostic_tests.csv`: dated EKG results when present
- `imaging.csv`: text interpretations only, not real medical images
- `clearances.csv`: fictional assessment documentation
- `consents.csv`: each consent's applicability and status
- `blood_products.csv`: fictional blood availability data
- `clinical_notes.csv`: fictional H&P text
- `procedure_requirements.csv`: illustrative teaching-case requirements, **NOT clinical guidelines**
- `ground_truth.csv`: case-level expected missing/review items for evaluation

Join using `patient_id` and, for case-specific records, `surgery_id`. `ground_truth.csv` should be hidden from the AI during inference.

## Important caveats
All data are fictional. Do not use for patient care or actual surgical clearance. The requirements (including a 90-day demonstration window for dated tests) are arbitrary educational rules, **not evidence-based clinical criteria**. Status means *documentation review status*, never clinical fitness for surgery. For actual clinical application, obtain clinician-approved institution-specific requirements.

## Reproducibility
The archive includes `generate_surgical_dataset.py`, which uses only the Python standard library and a fixed random seed. Run `python generate_surgical_dataset.py` from a folder with write access (the script's output path can be changed).

## Development suggestion
Use 80 cases for development and hold out 20 for evaluation, stratifying by procedure and scenario. Validate structured records independently of narrative notes.
