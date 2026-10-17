# Evaluation: rules on all split (100 cases)

| Role | Precision | Recall | F1 | Note-only recall | Status accuracy |
|---|---|---|---|---|---|
| nurse | 1.00 | 0.84 | 0.91 | 0/29 | 94/100 |
| anesthesia | 1.00 | 0.89 | 0.94 | 0/14 | 94/100 |

## Recall by finding type (nurse)

| Finding | Caught |
|---|---|
| NOTE_ALLERGY_CONFLICT | 0/6 |
| NOTE_CONSENT_CONFLICT | 0/5 |
| NOTE_EXAM_INCOMPLETE | 0/4 |
| NOTE_MH_FAMILY_HISTORY | 0/3 |
| NOTE_NEW_SYMPTOMS | 0/6 |
| NOTE_ANTITHROMBOTIC_CONFLICT | 0/5 |
| NEW_EKG_ABNORMALITY | 1/1 |
| MISSING:Anesthesia consent | 9/9 |
| OBSTRUCTIVE_SLEEP_APNEA | 10/10 |
| LATEX_ALLERGY | 12/12 |
| MISSING:Surgery consent | 6/6 |
| ABNORMAL_SODIUM | 2/2 |
| ELEVATED_INR | 3/3 |
| ELEVATED_CREATININE | 17/17 |
| METFORMIN_NO_INSTRUCTION | 6/6 |
| OUTDATED:EKG | 6/6 |
| MALIGNANT_HYPERTHERMIA_RISK | 8/8 |
| MISSING:CBC | 3/3 |
| SGLT2_NO_INSTRUCTION | 3/3 |
| MISSING:H&P | 4/4 |
| POSITIVE_ANTIBODY_SCREEN | 3/3 |
| ANTITHROMBOTIC_NO_PLAN | 6/6 |
| OUTDATED:H&P | 4/4 |
| MISSING:Blood consent | 3/3 |
| MISSING:HbA1c | 7/7 |
| HYPERGLYCEMIA | 6/6 |
| GLP1_AGONIST | 7/7 |
| MISSING:Pregnancy test | 1/1 |
| MISSING:EKG | 2/2 |
| ABNORMAL_POTASSIUM | 7/7 |
| BLOOD_REFUSAL | 4/4 |
| OUTDATED:Type and screen | 1/1 |
| POSITIVE_PREGNANCY | 1/1 |
| MISSING:Urinalysis | 1/1 |
| OUTDATED:Urinalysis | 1/1 |
| INSULIN_NO_INSTRUCTION | 1/1 |
| MISSING:Crossmatched PRBC (2 units) | 2/2 |
| LOW_HEMOGLOBIN | 3/3 |
| ELEVATED_LFTS | 1/1 |
| PENDING_CLEARANCE | 1/1 |
| MISSING:Coagulation panel | 1/1 |
| MISSING:Chest X-ray | 1/1 |

## Recall by finding type (anesthesia)

| Finding | Caught |
|---|---|
| NOTE_MH_FAMILY_HISTORY | 0/3 |
| NOTE_NEW_SYMPTOMS | 0/6 |
| NOTE_ANTITHROMBOTIC_CONFLICT | 0/5 |
| NEW_EKG_ABNORMALITY | 1/1 |
| MISSING:Anesthesia consent | 9/9 |
| MISSING:Pulmonary assessment | 6/6 |
| OBSTRUCTIVE_SLEEP_APNEA | 10/10 |
| DIFFICULT_AIRWAY | 4/4 |
| ABNORMAL_SODIUM | 2/2 |
| ELEVATED_INR | 3/3 |
| ELEVATED_CREATININE | 17/17 |
| PONV_HISTORY | 6/6 |
| MALIGNANT_HYPERTHERMIA_RISK | 8/8 |
| POSITIVE_ANTIBODY_SCREEN | 3/3 |
| ANTITHROMBOTIC_NO_PLAN | 6/6 |
| HYPERGLYCEMIA | 6/6 |
| GLP1_AGONIST | 7/7 |
| ABNORMAL_POTASSIUM | 7/7 |
| BLOOD_REFUSAL | 4/4 |
| POSITIVE_PREGNANCY | 1/1 |
| INSULIN_NO_INSTRUCTION | 1/1 |
| MISSING:Crossmatched PRBC (2 units) | 2/2 |
| LOW_HEMOGLOBIN | 3/3 |
| ELEVATED_LFTS | 1/1 |
| MISSING:Pulmonary function test | 1/1 |
| SEVERE_OBSTRUCTION | 1/1 |
