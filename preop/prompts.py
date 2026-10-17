"""
Prompts for the three LLM modules (context engineering).

Module 2  Question Answering   - role independent, answers fixed readiness questions with evidence IDs
Module 3  Summarization        - role-specific readiness summary
Module 4  Next steps           - role-specific actions picked from the role's order set + status
"""
from __future__ import annotations

import json

from . import criteria as C

SAFETY = ("This is a class prototype using fully synthetic patients. The criteria are teaching rules, not clinical "
          "guidelines. Never invent values that are not in the chart. If something is not in the chart, say it is not documented.")

ROLE_GUIDE = {
    "nurse": ("The user is a PRE-OP NURSE. Focus on: consents and paperwork, labs/tests that need to be drawn or obtained, "
              "patient instructions (medications to hold, CPAP, etc.), following up on pending items, notifying the right "
              "provider about abnormal values, and OR safety set-up (latex, malignant hyperthermia). The nurse does not "
              "diagnose or change the anesthetic plan."),
    "anesthesia": ("The user is an ANESTHESIOLOGIST. Focus on: cardiac and pulmonary risk, abnormal labs that change the "
                   "anesthetic or whether to proceed, anticoagulation and bleeding risk, blood availability, airway and prior "
                   "anesthesia problems, perioperative glucose, needed clearances or further testing, and whether the case "
                   "should proceed as scheduled."),
}
ROLE_LABEL = {"nurse": "Pre-op nurse", "anesthesia": "Anesthesiologist"}

QA_QUESTIONS = [
    ("Q1", "What procedure is scheduled, when, and what anesthesia is planned?"),
    ("Q2", "What is the status of each consent (surgery, anesthesia, blood)? Note any refusal."),
    ("Q3", "What are the most recent values and dates for hemoglobin, platelets, INR, potassium, sodium, creatinine, glucose/POC glucose, HbA1c, albumin and liver tests? Flag any abnormal value."),
    ("Q4", "Are there other abnormal lab results (urinalysis, urine culture, pregnancy test)?"),
    ("Q5", "What is the most recent EKG (date, interpretation, change from prior)? What do echo and PFTs show, if present?"),
    ("Q6", "What is the status of each clearance (cardiology, pulmonary)?"),
    ("Q7", "What is the blood bank status (type and screen date and expiration, antibody screen, crossmatched units)?"),
    ("Q8", "Which medications need pre-op instructions (blood thinners, diabetes medicines, GLP-1 agonists) and are instructions documented?"),
    ("Q9", "What anesthesia history, airway concerns and allergies are documented?"),
    ("Q10", "Is there an H&P? Give its date and whether it includes a heart and lung exam. Does it report any new symptoms or recent illness?"),
    ("Q11", "Does the H&P disagree with any structured record (allergies, consents, medication instructions, history)? Describe each disagreement."),
]


def qa_prompt(packet):
    system = ("You are Module 2 (Question Answering) of a pre-operative readiness assistant. You read a patient's chart "
              "and answer fixed questions precisely. " + SAFETY)
    qs = "\n".join(f"{qid}. {q}" for qid, q in QA_QUESTIONS)
    user = (f"CHART:\n{packet}\n\nQUESTIONS:\n{qs}\n\n"
            'Return JSON: {"answers": [{"question_id": "Q1", "answer": "...", "evidence_ids": ["L0001", ...]}]}. '
            "Answer every question. evidence_ids must be record IDs shown in square brackets in the chart.")
    return system, user


def summary_prompt(packet, qa, role):
    sections = {
        "nurse": ["Procedure & timing", "Consents & documentation", "Labs & tests (done / missing / abnormal)",
                  "Medication instructions", "Safety & precautions"],
        "anesthesia": ["Procedure & planned anesthesia", "Cardiac", "Pulmonary & airway",
                       "Key labs (Hgb, platelets, coags, electrolytes, renal, glucose)", "Medications affecting anesthesia",
                       "Blood availability", "Anesthesia history & allergies"],
    }[role]
    system = ("You are Module 3 (Summarization) of a pre-operative readiness assistant. " + ROLE_GUIDE[role] + " " + SAFETY)
    user = (f"QA FINDINGS (from Module 2):\n{json.dumps(qa, indent=1)}\n\nCHART:\n{packet}\n\n"
            f"Write a concise pre-op readiness summary for the {ROLE_LABEL[role]}. Use these sections in order: "
            f"{', '.join(sections)}. Under each section give 1-4 short bullet points with the actual values and dates; "
            "mark abnormal or missing items with '⚠'. Keep the whole summary under 220 words.\n"
            'Return JSON: {"headline": "one sentence on overall readiness for this role", "sections": '
            '[{"title": "...", "bullets": ["..."]}]}')
    return system, user


def next_steps_prompt(packet, qa, role, procedure):
    catalog = C.catalog_for_role(role)
    system = ("You are Module 4 (Next-Step Generation) of a pre-operative readiness assistant. " + ROLE_GUIDE[role] +
              " You compare the chart against the hospital's pre-op criteria and recommend next steps. A human reviews "
              "every recommendation before anything is done. " + SAFETY)
    user = (f"HOSPITAL PRE-OP CRITERIA:\n{C.criteria_document(procedure)}\n\n"
            f"ORDER SET FOR THE {ROLE_LABEL[role].upper()} (the only action codes you may use):\n"
            + "\n".join(f"- {k}: {v}" for k, v in catalog.items()) +
            f"\n\nQA FINDINGS (from Module 2):\n{json.dumps(qa, indent=1)}\n\nCHART:\n{packet}\n\n"
            "Instructions:\n"
            "1. Check every required item for this procedure and patient: present, signed, and within its validity window "
            "(count days from the result date to the surgery date).\n"
            "2. Check every value and history rule, including what can only be found by reading the H&P text.\n"
            f"3. Recommend each applicable action from the {ROLE_LABEL[role]} order set ONCE. Do not use codes from other roles. "
            "Do not recommend actions for items that are present, valid and normal.\n"
            "4. Put anything important that has no matching code in other_considerations (free text).\n"
            "5. Set status using section C of the criteria (Ready / Outstanding items / Needs clinical review / Recommend hold). "
            "Status is about the whole case, so it is the same for every role.\n"
            'Return JSON: {"status": "...", "status_reason": "one sentence", '
            '"actions": [{"code": "CODE", "reason": "short reason with the value/date", "evidence_ids": ["..."], '
            '"priority": "high|medium|low"}], "other_considerations": ["..."]}')
    return system, user
