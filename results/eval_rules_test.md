# Evaluation: rules on test split (20 cases)

| Role | Precision | Recall | F1 | Note-only recall | Status accuracy |
|---|---|---|---|---|---|
| nurse | 1.00 | 0.82 | 0.90 | 0/5 | 18/20 |
| anesthesia | 1.00 | 0.83 | 0.91 | 0/3 | 18/20 |

## Recall by finding type (nurse)

| Finding | Caught |
|---|---|
| NOTE_ALLERGY_CONFLICT | 0/1 |
| NOTE_ANTITHROMBOTIC_CONFLICT | 0/1 |
| NOTE_MH_FAMILY_HISTORY | 0/1 |
| NOTE_NEW_SYMPTOMS | 0/1 |
| NOTE_EXAM_INCOMPLETE | 0/1 |
| MISSING:CBC | 1/1 |
| ABNORMAL_SODIUM | 1/1 |
| LATEX_ALLERGY | 1/1 |
| HYPERGLYCEMIA | 1/1 |
| OBSTRUCTIVE_SLEEP_APNEA | 1/1 |
| OUTDATED:Type and screen | 1/1 |
| BLOOD_REFUSAL | 1/1 |
| MALIGNANT_HYPERTHERMIA_RISK | 1/1 |
| ELEVATED_CREATININE | 4/4 |
| MISSING:Urinalysis | 1/1 |
| MISSING:HbA1c | 1/1 |
| ANTITHROMBOTIC_NO_PLAN | 1/1 |
| MISSING:H&P | 1/1 |
| SGLT2_NO_INSTRUCTION | 2/2 |
| OUTDATED:H&P | 2/2 |
| OUTDATED:EKG | 1/1 |
| POSITIVE_ANTIBODY_SCREEN | 1/1 |
| METFORMIN_NO_INSTRUCTION | 1/1 |

## Recall by finding type (anesthesia)

| Finding | Caught |
|---|---|
| NOTE_ANTITHROMBOTIC_CONFLICT | 0/1 |
| NOTE_MH_FAMILY_HISTORY | 0/1 |
| NOTE_NEW_SYMPTOMS | 0/1 |
| ABNORMAL_SODIUM | 1/1 |
| HYPERGLYCEMIA | 1/1 |
| MISSING:Pulmonary assessment | 1/1 |
| OBSTRUCTIVE_SLEEP_APNEA | 1/1 |
| BLOOD_REFUSAL | 1/1 |
| MALIGNANT_HYPERTHERMIA_RISK | 1/1 |
| PONV_HISTORY | 1/1 |
| ELEVATED_CREATININE | 4/4 |
| ANTITHROMBOTIC_NO_PLAN | 1/1 |
| DIFFICULT_AIRWAY | 1/1 |
| POSITIVE_ANTIBODY_SCREEN | 1/1 |
| SEVERE_OBSTRUCTION | 1/1 |
