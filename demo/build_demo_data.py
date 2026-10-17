"""Export cases for the demo page (demo/preop_demo.html). Run from repo root."""
import csv, json, os, sys
sys.path.insert(0, os.getcwd())
from preop import criteria as C, data as D
from preop.pipeline import rules_next_steps
key = {r["surgery_id"]: r for r in csv.DictReader(open("surgical_patient_dataset_v2/answer_key/ground_truth_cases.csv"))}
WHY = {"always": "All surgical patients", "female_18_50": "Female, age 18-50", "diabetes": "Diabetic", "copd": "COPD",
       "not_refusing_blood": "Blood may be needed",
       "age65_or_cardiac_noncabg": "Age 65+ or cardiac history", "knee_bmp": "Age 65+ or HTN / diabetes / CKD"}

def why(r, ch):
    if r["condition"] == "always" and r["procedure"] != "All":
        return f"Standard for {ch['case']['procedure']}"
    return WHY.get(r["condition"], C.CONDITION_TEXT[r["condition"]])

def checklist_row(r, ch):
    s = C.requirement_status(ch, r)
    st, on, valid = s["status"], s["on_file"], r["validity_days"]
    if st == "ok":
        note = on
    elif st == "outdated":
        note = f"{on} · expires before surgery" if r["item"] == "Type and screen" else f"{on} · older than {valid} days"
    elif st == "pending":
        note = on
    elif r["item_type"] == "blood" and on:
        note = f"{on} (2 needed)"
    else:
        note = "Not signed" if r["item_type"] == "consent" else "Not in chart"
    return dict(item=r["item"], type=r["item_type"], status=st, note=note, why=why(r, ch))
cases = []
for c in D.list_cases():
    sid = c["surgery_id"]; ch = D.build_chart(sid)
    rules = {}
    for role in C.ROLES:
        s = rules_next_steps(ch, role)
        rules[role] = dict(status=s["status"], actions=[dict(code=a["code"], reason=a["reason"], evidence_ids=a["evidence_ids"], priority=a["priority"]) for a in s["actions"]])
    p = dict(ch["patient"]); p["diagnoses"] = "; ".join(p["diagnoses"])
    k = key[sid]
    cases.append(dict(id=sid, split=c["split"], case=ch["case"], patient=p, meds=ch["meds"], labs=ch["labs"],
        diags=ch["diagnostics"], imaging=ch["imaging"], clearances=ch["clearances"], consents=ch["consents"],
        blood=ch["blood"], notes=ch["notes"], packet=D.chart_to_packet(ch),
        reqs=[checklist_row(r, ch) for r in C.applicable_requirements(ch)],
        rules=rules, key=dict(status=k["expected_status"], nurse=[x for x in k["expected_nurse_actions"].split(" | ") if x], anesthesia=[x for x in k["expected_anesthesia_actions"].split(" | ") if x])))
out = dict(cases=cases, criteria={p: C.criteria_document(p) for p in C.PROCEDURES},
           catalog={code: dict(role=r, text=t, steps=C.ACTION_FOLLOW_UP[code][0], done=C.ACTION_FOLLOW_UP[code][1])
                    for code, (r, t) in C.ACTION_CATALOG.items()})
data = json.dumps(out, separators=(",", ":")).replace("</", "<\\/")
tpl = open("demo/template.html", encoding="utf-8").read()
open("demo/preop_demo.html", "w", encoding="utf-8").write(tpl.replace("/*__DATA__*/null", data))
print("cases", len(cases), "bytes", len(data))
