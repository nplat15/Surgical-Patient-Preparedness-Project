"""Session-local chart updates for work completed in the classroom demo."""
from __future__ import annotations

from . import criteria as C


DAY_OF_TESTS = {
    "Hemoglobin": ("CBC", "g/dL", {"g/dL": 1.0, "g/L": 0.1}),
    "Platelets": ("CBC", "10^3/uL", {"10^3/uL": 1.0, "10^9/L": 1.0}),
    "INR": ("Coagulation panel", "ratio", {"ratio": 1.0}),
    "Sodium": ("BMP", "mmol/L", {"mmol/L": 1.0, "mEq/L": 1.0}),
    "Potassium": ("BMP", "mmol/L", {"mmol/L": 1.0, "mEq/L": 1.0}),
    "Creatinine": ("BMP", "mg/dL", {"mg/dL": 1.0, "umol/L": 1 / 88.4}),
    "POC glucose": ("POC glucose", "mg/dL", {"mg/dL": 1.0, "mmol/L": 18.0182}),
    "AST": ("Liver function tests", "U/L", {"U/L": 1.0}),
    "ALT": ("Liver function tests", "U/L", {"U/L": 1.0}),
    "Total bilirubin": ("Liver function tests", "mg/dL", {"mg/dL": 1.0, "umol/L": 1 / 17.1}),
}

DAY_OF_LAB_ACTIONS = {
    "NOTIFY_LOW_HGB": ("Hemoglobin",),
    "NOTIFY_LOW_PLATELETS": ("Platelets",),
    "NOTIFY_ELEVATED_INR": ("INR",),
    "REPEAT_BMP": ("Sodium", "Potassium"),
    "NOTIFY_RENAL_FUNCTION": ("Creatinine",),
    "POC_GLUCOSE_DAY_OF": ("POC glucose",),
    "INSULIN_INSTRUCTIONS": ("POC glucose",),
    "NOTIFY_ELEVATED_LFTS": ("AST", "ALT", "Total bilirubin"),
}


def _actions_for_requirement(req, status):
    if req["item"] == "Anesthesia consent":
        # Notifying anesthesia does not itself complete the consent discussion.
        return {("anesthesia", "OBTAIN_ANESTHESIA_CONSENT")}
    if req["item_type"] == "clearance" and status["status"] == "pending":
        return {("nurse", "FOLLOW_UP_CLEARANCE")}
    return set(req["missing_actions"])


def apply_completed_actions(chart, completed_actions, cpap_status=None, day_of_values=None):
    """Return a chart view with requirements completed in this browser session reflected."""
    completed_actions = set(completed_actions)
    updated = dict(chart)
    if cpap_status is not None:
        updated["session_cpap_status"] = cpap_status
    day_of_values = day_of_values or {}
    if day_of_values:
        updated["labs"] = [dict(row) for row in chart["labs"]]
        updated["session_day_of_labs"] = []
        for test, entry in day_of_values.items():
            panel, default_unit, unit_factors = DAY_OF_TESTS[test]
            unit = entry.get("unit", default_unit)
            if unit not in unit_factors:
                raise ValueError(f"Unsupported unit {unit!r} for {test}")
            value = float(entry["value"])
            prior = C.latest_lab(chart, test)
            rule_value = value * unit_factors[unit]
            reference_low = C.num(prior.get("reference_low")) if prior else None
            reference_high = C.num(prior.get("reference_high")) if prior else None
            flag = ("L" if reference_low is not None and rule_value < reference_low else
                    "H" if reference_high is not None and rule_value > reference_high else "")
            row = {
                "lab_id": f"DAYOF-{chart['case']['surgery_id']}-{test.replace(' ', '-')}",
                "surgery_id": chart["case"]["surgery_id"],
                "patient_id": chart["case"]["patient_id"],
                "panel": panel,
                "test_name": test,
                "result_value": str(value),
                "unit": unit,
                "reference_low": prior.get("reference_low", "") if prior else "",
                "reference_high": prior.get("reference_high", "") if prior else "",
                "flag": flag,
                "collection_date": chart["case"]["surgery_date"],
                "result_status": "Day-of (session)",
                "rule_value": rule_value,
                "session_day_of": True,
            }
            if prior:
                row["prior_value"] = prior["result_value"]
                row["prior_unit"] = prior["unit"]
                row["prior_date"] = prior["collection_date"]
            updated["labs"].append(row)
            updated["session_day_of_labs"].append(row)
    updated["consents"] = [dict(row) for row in chart["consents"]]
    completed_requirements = set(chart.get("session_completed_requirements", ()))
    completed_items = list(chart.get("session_completed_items", ()))

    for req in C.applicable_requirements(updated):
        status = C.requirement_status(updated, req)
        if status["status"] == "ok":
            continue
        required_actions = _actions_for_requirement(req, status)
        if not required_actions or not required_actions.issubset(completed_actions):
            continue

        key = (req["item_type"], req["item"])
        completed_requirements.add(key)
        completed_items.append(dict(type=req["item_type"], item=req["item"]))

        if req["item_type"] == "consent":
            row = next((r for r in updated["consents"] if r["consent_type"] == req["item"]), None)
            if row is None:
                row = dict(consent_type=req["item"], consent_id="Session completion")
                updated["consents"].append(row)
            row.update(status="Signed (this session)", signed_date="Completed in this session")

    updated["session_completed_requirements"] = completed_requirements
    updated["session_completed_items"] = completed_items
    return updated
