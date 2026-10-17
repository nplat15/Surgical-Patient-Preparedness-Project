# Pre-Op Readiness Prototype

Class project prototype (Group: April Walter, Mombo Ngu, Nikolas Platon, Willie Robinson).

The system reads a surgical patient's chart and tells the **pre-op nurse** and the **anesthesiologist**, each from
their own point of view, whether the patient is ready for surgery and **what to do next**: draw labs, obtain consents,
request clearances, order blood, review abnormal values, and so on. A human accepts or declines every suggestion.

> All patients are fictional. The criteria in `preop/criteria.py` are **teaching rules, not clinical guidelines**.
> Do not use for real patient care.

## How it maps to our milestones

| Module (Milestone 3) | AI task | Approach | Code |
|---|---|---|---|
| 1. Surgery Identification | none (lookup) | rule-based query | `preop/data.py: module1_identify_surgery` |
| 2. Question Answering | QA over structured data + H&P | context engineering (LLM) | `preop/prompts.py: qa_prompt` |
| 3. Summarization | role-specific summary | context engineering (LLM) | `preop/prompts.py: summary_prompt` |
| 4. Next steps | compare chart to criteria, pick actions from the role's order set | context engineering (LLM) | `preop/prompts.py: next_steps_prompt` |

The hospital "criteria document" and each role's "order set" (`action_catalog.csv`) are put into the Module 4 prompt.
A **rules-only baseline** applies the same criteria to structured fields but cannot read the H&P, so we can show what the AI adds.

## Quick start

```bash
pip install -r requirements.txt

# 1. (optional) rebuild the dataset - same output every time
python surgical_patient_dataset_v2/generate_v2.py

# 2. mock EHR tab (works without an API key using the rules engine)
streamlit run app.py

# 3. evaluation
python evaluate.py --engine rules --split test          # baseline, free
export ANTHROPIC_API_KEY=sk-...                          # or OPENAI_API_KEY + PREOP_LLM_PROVIDER=openai + PREOP_LLM_MODEL=<model>
python evaluate.py --engine llm --split dev --limit 5    # try a few dev cases first
python evaluate.py --engine llm --split test            # final held-out run (do this once)

# 4. tests
python tests/test_pipeline.py
```

LLM outputs are cached in `results/cache/` so re-running does not re-bill. Delete the cache after changing prompts.
Cost guide: one case = 1 QA call + 2 calls per role (5 calls for both roles).

## Folder layout

```
preop/criteria.py     teaching criteria: requirements, value rules, action catalog (single source of truth)
preop/data.py         loads CSVs, builds a patient "chart", Module 1, chart -> text packet for the LLM
preop/prompts.py      Module 2/3/4 prompts
preop/llm.py          Anthropic / OpenAI / mock client
preop/pipeline.py     runs Modules 1-4 (LLM or rules-only)
app.py                Streamlit mock EHR "Pre-Op Readiness" tab with Nurse / Anesthesiologist switch
evaluate.py           scores output against the answer key (precision, recall, note-only recall, status accuracy)
surgical_patient_dataset_v2/   richer synthetic dataset (see its README)
surgical_patient_dataset/      original v1 dataset (unchanged)
results/              evaluation reports, decisions log, LLM cache
```

## Baseline results (rules only, no AI)

Test split, 20 held-out cases:

| Role | Precision | Recall | F1 | Note-only recall | Status accuracy |
|---|---|---|---|---|---|
| nurse | 1.00 | 0.82 | 0.90 | 0/5 | 18/20 |
| anesthesia | 1.00 | 0.83 | 0.91 | 0/3 | 18/20 |

The baseline is perfect on structured fields by design (it uses the same rules that built the answer key) and
catches **none** of the problems that only appear in the H&P text: new symptoms, allergy and consent conflicts,
a family history suggesting malignant hyperthermia, a patient who says they are still taking a blood thinner, or an H&P
with no heart/lung exam. The AI's job is to match the baseline on structured data **and** catch those.

## Things to keep honest in the write-up

* The answer key was produced from the same criteria the AI is given, so scores measure whether the AI applies
  our rules correctly, not whether the rules are clinically right.
* Only 20 held-out cases; one or two misses move the numbers a lot.
* Do not tune prompts on the test split. Use `--split dev` while developing.
* Do not send MIMIC data to a cloud LLM without checking PhysioNet's rules.

## Demo page (no setup)

`demo/preop_demo.html` is the same mock EHR as a single web page. Inside claude.ai it can ask Claude to run the
nurse or anesthesiologist review on the viewer's own Claude account (one call per case and role, combining Modules 2-4).
Rebuild it after changing the dataset or criteria: `python demo/build_demo_data.py`.
