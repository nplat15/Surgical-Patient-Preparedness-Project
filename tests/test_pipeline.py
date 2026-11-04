"""Quick checks. Run:  python -m pytest -q   (or: python tests/test_pipeline.py)"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preop import criteria as C
from preop import data as D
from preop import pipeline as PL
from preop.llm import parse_json


class FakeLLM:
    """Stands in for a real model so the LLM code path can be tested offline."""
    provider, model, is_mock = "fake", "fake", False

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        if "Module 2" in system:
            return {"answers": [{"question_id": "Q1", "answer": "CABG", "evidence_ids": ["S082"]}]}
        if "Module 3" in system:
            return {"headline": "Not ready", "sections": [{"title": "Cardiac", "bullets": ["⚠ chest pressure at rest"]}]}
        return {"status": "Needs clinical review", "status_reason": "x",
                "actions": [{"code": "evaluate_new_symptoms", "reason": "rest angina", "evidence_ids": ["N082"]},
                            {"code": "EVALUATE_NEW_SYMPTOMS", "reason": "duplicate"},
                            {"code": "DRAW_CBC", "reason": "nurse code, wrong role"}],
                "other_considerations": []}


def test_answer_key_never_in_packet():
    packet = D.chart_to_packet(D.build_chart("S082"))
    assert "expected" not in packet.lower() and "split" not in packet.lower()


def test_rules_baseline_matches_structured_answer_key():
    key = os.path.join(D.DEFAULT_DATA, "answer_key", "ground_truth_findings.csv")
    rows = list(csv.DictReader(open(key)))
    for sid in {r["surgery_id"] for r in rows}:
        exp = {r["finding_code"] for r in rows if r["surgery_id"] == sid and r["source"] == "structured"}
        got = {f["finding_code"] for f in C.evaluate_structured(D.build_chart(sid))}
        assert exp == got, (sid, exp ^ got)


def test_llm_path_cleans_actions(tmp_path=None):
    PL.CACHE_DIR = os.path.join(D.ROOT, "results", "cache_test")
    fake = FakeLLM()
    res = PL.run_case("S082", role="anesthesia", engine="llm", llm=fake, use_cache=False)
    codes = [a["code"] for a in res["next_steps"]["actions"]]
    assert codes == ["EVALUATE_NEW_SYMPTOMS"]          # normalized, de-duplicated, wrong-role code dropped
    assert any("DRAW_CBC" in x for x in res["next_steps"]["other_considerations"])
    assert len(fake.calls) == 3                         # Module 2, 3, 4
    assert "chest pressure at rest" in fake.calls[0][1]  # the note text reached the model


def test_parse_json_handles_code_fences():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


def test_module1():
    m1 = D.module1_identify_surgery("S082")
    assert m1["case"]["procedure"] == "Coronary Artery Bypass Graft"
    assert any(r["item"] == "Crossmatched PRBC (2 units)" for r in m1["requirements"])



def test_every_action_has_follow_up():
    from preop import criteria as C
    assert set(C.ACTION_FOLLOW_UP) == set(C.ACTION_CATALOG)


def test_quick_items_never_move_a_case():
    from preop import schedule as S
    for x in S.board():
        if x["state"] in ("later", "resched"):
            assert S.slow_reqs(x), x["id"]  # a missing consent, H&P or EKG alone is done in pre-op
    assert S.by_id()["S052"]["state"] == "open"  # anesthesia consent + H&P missing: no move


def test_one_missing_lab_is_a_small_move_later():
    from preop import schedule as S
    x = S.by_id()["S014"]                         # 09:00, CBC missing
    assert x["state"] == "later" and S.suggested_time(x)["to"]["time"] == "10:00"
    assert S.by_id()["S029"]["state"] == "open"   # latex allergy: stays first, lab drawn on arrival
    assert S.by_id()["S039"]["state"] == "open"   # type and screen alone is blood bank work, not a move


def test_latex_allergy_is_first_case_in_its_room():
    from preop import schedule as S
    sg = S.suggested_time(S.by_id()["S076"])           # 14:00 behind S067 at 09:00
    assert sg["first"] and sg["to"]["time"] == "09:00" and [i for i, _ in sg["also"]] == ["S067"]
    for sid, s in S.resched_plan().items():
        if S.latex(S.by_id()[sid]):
            assert s["start"] == S.DAY_START, sid      # rescheduled latex cases land in the first slot
    moves = {}
    for d in sorted({x["case"]["surgery_date"] for x in S.board()}):
        for g in S.day_suggestions(d):
            if g["to"]:
                for i, t in [(g["x"]["id"], g["to"]), *g.get("also", ())]:
                    moves[i] = (i, *t.values())
    cs = [x for x in S.cases(tuple(sorted(moves.values()))) if not x.get("off")]
    room = lambda x: [y for y in cs if y is not x and y["case"]["surgery_date"] == x["case"]["surgery_date"]
                      and y["case"]["surgery_location"] == x["case"]["surgery_location"]]
    for x in cs:                                        # with every suggestion applied: latex first, nothing overlaps
        assert not (S.latex(x) and any(S.start(y) < S.start(x) for y in room(x))), x["id"]
        assert not any(S.start(y) < S.end(x) and S.start(x) < S.end(y) for y in room(x)), x["id"]


def test_roster_gives_students_their_own_case():
    import threading
    from preop.classroom import SHOWCASE, Roster
    from preop import schedule as S
    roster, tokens = Roster(), []
    threads = [threading.Thread(target=lambda i=i: tokens.append(roster.join(f"student {i}"))) for i in range(40)]
    for t in threads: t.start()
    for t in threads: t.join()
    sids = [roster.get(t)["sid"] for t in tokens]
    assert len(roster) == 40 and len(set(sids)) == 40   # a whole class signing in at once, no repeats
    assert SHOWCASE not in sids and all(S.by_id()[s]["state"] != "ready" for s in sids)


def test_patient_banner_has_no_stray_html_closing_tag():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Banner QA")
    student.button[0].click().run()

    banner = next(item.value for item in student.markdown if item.value.startswith('<div class="banner">'))
    assert "\n" not in banner
    assert "</div>" in banner
    assert not student.exception, student.exception


def test_completed_anesthesia_consent_updates_session_chart_and_checklist():
    from preop import schedule as S
    from preop import workflow as W

    chart = D.build_chart("S052")
    req = next(r for r in C.applicable_requirements(chart) if r["item"] == "Anesthesia consent")
    assert C.requirement_status(chart, req)["status"] == "missing"

    updated = W.apply_completed_actions(chart, {("anesthesia", "OBTAIN_ANESTHESIA_CONSENT")})

    assert C.requirement_status(updated, req)["status"] == "ok"
    assert S.checklist_row(req, updated)["status"] == "ok"
    consent = next(c for c in updated["consents"] if c["consent_type"] == "Anesthesia consent")
    assert consent["status"] == "Signed (this session)"
    assert C.requirement_status(chart, req)["status"] == "missing"


def test_clearance_and_outside_test_requests_do_not_complete_requirements():
    from preop import schedule as S
    from preop import workflow as W

    chart = D.build_chart("S003")
    clearance_req = next(
        req for req in C.applicable_requirements(chart)
        if req["item"] == "Pulmonary assessment"
    )
    requested = W.apply_completed_actions(
        chart, {("anesthesia", "REQUEST_PULMONARY_CLEARANCE")},
    )
    assert C.requirement_status(requested, clearance_req)["status"] == "pending"
    assert next(row for row in requested["clearances"]
                if row["clearance_type"] == "Pulmonary assessment")["status"] == "Pending"
    assert ("clearance", "Pulmonary assessment") not in requested["session_completed_requirements"]

    followed_up = W.apply_completed_actions(
        requested, {("nurse", "FOLLOW_UP_CLEARANCE")},
    )
    assert C.requirement_status(followed_up, clearance_req)["status"] == "pending"

    def state_for(updated):
        return S.sched_state({
            "reqs": [S.checklist_row(req, updated)
                     for req in C.applicable_requirements(updated)],
            "rules": {role: PL.rules_next_steps(updated, role) for role in C.ROLES},
            "patient": updated["patient"],
        })

    assert state_for(requested) == "resched"
    assert state_for(followed_up) == "resched"

    chart = dict(D.build_chart("S082"))
    chart["patient"] = dict(
        chart["patient"],
        diagnoses=[*chart["patient"]["diagnoses"], "COPD"],
    )
    for item, action_code, role, collection, field, kind in (
        ("Echocardiogram", "REQUEST_ECHO", "anesthesia", "diagnostics", "test_type", "diagnostic"),
        ("Pulmonary function test", "REQUEST_PFT", "anesthesia", "diagnostics", "test_type", "diagnostic"),
        ("Chest X-ray", "OBTAIN_CHEST_XRAY", "nurse", "imaging", "imaging_type", "imaging"),
    ):
        req = next(req for req in C.applicable_requirements(chart)
                   if req["item"] == item and req["item_type"] == kind)
        chart_without_result = dict(chart)
        chart_without_result[collection] = [
            row for row in chart[collection] if row[field] != item
        ]
        assert C.requirement_status(chart_without_result, req)["status"] == "missing"
        result_requested = W.apply_completed_actions(
            chart_without_result, {(role, action_code)},
        )
        assert C.requirement_status(result_requested, req)["status"] == "missing"
        assert (kind, item) not in result_requested["session_completed_requirements"]
        assert state_for(result_requested) == "resched"


def test_anesthesia_consent_completion_survives_role_switch():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Consent QA")
    student.button[0].click().run()
    student.button(key="pt_S052").click().run()
    student.segmented_control[1].set_value("anesthesia").run()
    student.radio(key="dec|S052|anesthesia|OBTAIN_ANESTHESIA_CONSENT").set_value("Accept").run()
    student.radio(key="consent-answer|S052").set_value("yes").run()
    assert any("Completed in this session" in item.value for item in student.markdown)

    student.segmented_control[1].set_value("nurse").run()
    checklist = next(item.value for item in student.markdown if "Pre-op checklist" in item.value)
    assert "<td><b>Anesthesia consent</b></td><td>Completed in this session</td>" in checklist
    assert not student.exception, student.exception


def test_refused_anesthesia_consent_creates_hold_without_signing():
    from preop import schedule as S
    from preop import workflow as W

    chart = D.build_chart("S052")
    req = next(r for r in C.applicable_requirements(chart) if r["item"] == "Anesthesia consent")
    pending = W.apply_completed_actions(chart, set(), consent_status="pending")
    assert C.requirement_status(pending, req)["status"] == "missing"
    refused = W.apply_completed_actions(chart, set(), consent_status="refused")
    consent = next(c for c in refused["consents"] if c["consent_type"] == "Anesthesia consent")

    assert consent["status"] == "Refused"
    assert C.requirement_status(refused, req)["status"] == "refused"
    assert S.checklist_row(req, refused)["status"] == "refused"
    assert C.requirement_status(chart, req)["status"] == "missing"
    steps = PL.rules_next_steps(refused, "anesthesia")
    assert steps["status"] == "Recommend hold"
    assert "RESCHEDULE_AFTER_CONSENT_REFUSAL" in {action["code"] for action in steps["actions"]}
    assert S.sched_state({"reqs": [S.checklist_row(r, refused) for r in C.applicable_requirements(refused)],
                          "rules": {role: PL.rules_next_steps(refused, role) for role in C.ROLES},
                          "patient": chart["patient"]}) == "hold"


def test_anesthesia_consent_refusal_control_records_a_distinct_response():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Consent refusal QA")
    student.button[0].click().run()
    student.button(key="pt_S052").click().run()
    student.segmented_control[1].set_value("anesthesia").run()
    student.radio(key="dec|S052|anesthesia|OBTAIN_ANESTHESIA_CONSENT").set_value("Accept").run()
    student.radio(key="consent-answer|S052").set_value("no").run()
    student.selectbox(key="consent-outcome|S052").set_value("refused").run()

    assert student.session_state["consent_status|S052"] == "refused"
    assert any("Anesthesia consent refused" in item.value for item in student.warning)
    assert any("Clinical hold — team review required" in item.value for item in student.markdown)
    checklist = next(item.value for item in student.markdown if "Pre-op checklist" in item.value)
    assert "Refused" in checklist
    assert not student.exception, student.exception


def test_computerized_ekg_updates_expired_checklist_and_anesthesia_review():
    from preop import schedule as S
    from preop import workflow as W

    chart = D.build_chart("S097")
    req = next(r for r in C.applicable_requirements(chart) if r["item"] == "EKG")
    assert C.requirement_status(chart, req)["status"] == "outdated"

    updated = W.apply_completed_actions(
        chart, set(), ekg_machine_reading="Sinus Bradycardia",
        ekg_nurse_note="Machine shows a slow rhythm; nurse documented pulse for review.",
    )
    reading = updated["session_machine_ekgs"][0]
    assert C.requirement_status(updated, req)["status"] == "ok"
    assert S.checklist_row(req, updated)["status"] == "ok"
    assert "Computerized reading from the machine" in reading["interpretation"]
    assert "nurse documented pulse" in reading["interpretation"]
    assert reading["compared_to_prior"] == "Not assessed"

    steps = PL.rules_next_steps(updated, "anesthesia")
    assert steps["status"] == "Needs clinical review"
    action = next(a for a in steps["actions"] if a["code"] == "REVIEW_COMPUTERIZED_EKG")
    assert action["reason"] == "New EKG reading: Sinus Bradycardia"
    assert "NOTIFY_EKG_ABNORMALITY" in {
        code for finding in steps["findings"] for code in finding["actions"]["nurse"]
    }
    assert C.COMPUTERIZED_EKG_GUIDANCE["Sinus Bradycardia"][1] == (
        "Evaluate heart rate, symptoms, and medication history."
    )


def test_computerized_ekg_review_tasks_cover_findings_and_disposition():
    from preop import workflow as W

    assert set(C._EKG_REVIEW_GROUPS) == set(C.COMPUTERIZED_EKG_GUIDANCE)
    for reading in C.COMPUTERIZED_EKG_GUIDANCE:
        tasks = C.computerized_ekg_review_tasks(reading)
        assert tasks
        assert C.COMPUTERIZED_EKG_GUIDANCE[reading][1] in tasks[-1]

    chart = W.apply_completed_actions(
        D.build_chart("S097"), set(), ekg_machine_reading="Sinus Bradycardia",
    )
    for disposition, category, action_count in (
        ("proceed", "routine", 0),
        ("move_later", "clinical", 0),
        ("reschedule", "clinical", 0),
        ("clinical_hold", "critical", 0),
    ):
        chart["session_ekg_anesthesia_disposition"] = disposition
        steps = PL.rules_next_steps(chart, "anesthesia")
        ekg_finding = next(f for f in steps["findings"]
                           if f["finding_code"] == "COMPUTERIZED_EKG_REVIEW")
        assert ekg_finding["category"] == category
        assert len([a for a in steps["actions"]
                    if a["code"] == "REVIEW_COMPUTERIZED_EKG"]) == action_count


def test_computerized_ekg_entry_is_visible_to_anesthesia_in_app():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("EKG QA")
    student.button[0].click().run()

    student.button(key="pt_S095").click().run()
    student.segmented_control[1].set_value("anesthesia").run()
    student.radio(key="dec|S095|anesthesia|REQUEST_PULMONARY_CLEARANCE").set_value("Accept").run()
    clearance_tasks = C.ACTION_FOLLOW_UP["REQUEST_PULMONARY_CLEARANCE"][0]
    for index in range(len(clearance_tasks)):
        student.checkbox(
            key=f"todo|S095|anesthesia|REQUEST_PULMONARY_CLEARANCE|{index}",
        ).check().run()
    student.session_state["session_ekg|S095"] = {
        "reading": "Sinus Bradycardia",
        "note": "",
    }
    student.run()
    student.radio(key="dec|S095|anesthesia|REVIEW_COMPUTERIZED_EKG").set_value("Accept").run()
    review_tasks = C.computerized_ekg_review_tasks("Sinus Bradycardia")
    for index in range(len(review_tasks)):
        student.checkbox(
            key=f"todo|S095|anesthesia|REVIEW_COMPUTERIZED_EKG|{index}",
        ).check().run()
    student.selectbox(key="ekg-disposition|S095").set_value("clinical_hold").run()
    dashboard = "\n".join(item.value for item in student.markdown)
    assert "Anesthesia disposition: Clinical hold" in dashboard
    assert "Rescheduling may still be needed while outside work is pending:" in dashboard
    assert "Pulmonary assessment" in dashboard
    assert "🟣" in student.button(key="pt_S095").label

    student.button(key="pt_S097").click().run()
    student.segmented_control[1].set_value("nurse").run()
    student.radio(key="dec|S097|nurse|OBTAIN_EKG").set_value("Accept").run()
    student.selectbox(key="ekg-reading|S097").set_value("Sinus Bradycardia")
    student.text_area(key="ekg-note|S097").set_value("Pulse documented for anesthesia.")
    student.button(key="FormSubmitter:ekg-form|S097-Record EKG reading").click().run()
    student.segmented_control[1].set_value("anesthesia").run()

    assert any(item.value == "New EKG reading: Sinus Bradycardia" for item in student.info)
    assert all("Pulse documented for anesthesia" not in item.value for item in student.info)
    assert any(item.key == "dec|S097|anesthesia|REVIEW_COMPUTERIZED_EKG"
               for item in student.radio)
    student.radio(key="dec|S097|anesthesia|REVIEW_COMPUTERIZED_EKG").set_value("Accept").run()
    review_tasks = C.computerized_ekg_review_tasks("Sinus Bradycardia")
    for index in range(len(review_tasks)):
        student.checkbox(key=f"todo|S097|anesthesia|REVIEW_COMPUTERIZED_EKG|{index}").check().run()
    disposition_key = "ekg-disposition|S097"
    assert any(item.key == disposition_key for item in student.selectbox)
    student.selectbox(key=disposition_key).set_value("clinical_hold").run()
    assert student.session_state["ekg-disposition-value|S097"] == "clinical_hold"
    assert any("Anesthesia disposition: Clinical hold" in item.value
               for item in student.markdown)
    assert "🟣" in student.button(key="pt_S097").label

    student.button(key="view-ekg|S097").click().run()
    assert student.session_state["chart-section"] == "Tests & Imaging"
    ekg_chart = next(item.value for item in student.markdown
                     if "<table" in item.value and "SESSION-EKG-S097" in item.value)
    assert "Pulse documented for anesthesia" in ekg_chart
    student.segmented_control[1].set_value("nurse").run()
    student.button(key="chart-nav|S097|Tests & Imaging").click().run()
    assert not any(item.key == "ekg-reading|S097" for item in student.selectbox)
    student.button(key="edit-ekg|S097").click().run()
    assert any(item.key == "ekg-reading|S097" for item in student.selectbox)
    student.selectbox(key="ekg-reading|S097").set_value("Atrial Flutter")
    student.button(key="FormSubmitter:ekg-form|S097-Record EKG reading").click().run()
    assert len(student.session_state["history|S097|ekg"]) == 1
    assert student.session_state["session_ekg|S097"]["reading"] == "Atrial Flutter"
    assert "ekg-disposition-value|S097" not in student.session_state
    assert "completed|S097|anesthesia|REVIEW_COMPUTERIZED_EKG" not in student.session_state
    assert not any(item.key == "ekg-reading|S097" for item in student.selectbox)
    assert not student.exception, student.exception


def test_cpap_response_updates_role_specific_findings():
    from preop import workflow as W

    chart = D.build_chart("S078")
    finding = next(f for f in C.evaluate_structured(chart)
                   if f["finding_code"] == "OBSTRUCTIVE_SLEEP_APNEA")
    assert finding["actions"]["nurse"] == ["BRING_CPAP"]

    brought = PL.rules_next_steps(
        W.apply_completed_actions(chart, {("nurse", "BRING_CPAP")}, "brought"),
        "anesthesia",
    )
    assert "CPAP_NOT_BROUGHT" not in {a["code"] for a in brought["actions"]}

    not_brought_chart = W.apply_completed_actions(chart, {("nurse", "BRING_CPAP")}, "not_brought")
    anesthesia = PL.rules_next_steps(not_brought_chart, "anesthesia")
    action = next(a for a in anesthesia["actions"] if a["code"] == "CPAP_NOT_BROUGHT")
    assert "did not bring CPAP" in action["reason"]
    assert "hospital CPAP" in action["reason"]
    nurse = PL.rules_next_steps(not_brought_chart, "nurse")
    assert "BRING_CPAP" not in {a["code"] for a in nurse["actions"]}


def test_cpap_not_brought_is_shown_to_anesthesia_in_app():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("CPAP QA")
    student.button[0].click().run()
    student.button(key="pt_S078").click().run()
    student.radio(key="dec|S078|nurse|BRING_CPAP").set_value("Accept").run()
    student.radio(key="cpap|S078").set_value("not_brought").run()

    assert student.session_state["completed|S078|nurse|BRING_CPAP"]
    assert student.session_state["cpap_status|S078"] == "not_brought"
    student.segmented_control[1].set_value("anesthesia").run()
    assert any("Rule finding: Patient did not bring CPAP" in item.value
               for item in student.warning)
    assert any(item.key == "dec|S078|anesthesia|CPAP_NOT_BROUGHT"
               for item in student.radio)
    assert not student.exception, student.exception


def test_day_of_values_use_project_thresholds_and_prompt_anesthesia_review():
    from preop import workflow as W

    chart = D.build_chart("S078")
    updated = W.apply_completed_actions(
        chart, set(), day_of_values={"POC glucose": {"value": 11.2, "unit": "mmol/L"}})
    newest = C.latest_lab(updated, "POC glucose")
    assert newest["result_value"] == "11.2" and newest["unit"] == "mmol/L"
    assert newest["prior_value"] and newest["prior_date"]
    assert newest["rule_value"] > 200

    anesthesia = PL.rules_next_steps(updated, "anesthesia")
    actions = {action["code"] for action in anesthesia["actions"]}
    assert "UPDATE_ANESTHESIA_PLAN" in actions
    assert "GLYCEMIC_PLAN" in actions
    review = next(f for f in anesthesia["findings"] if f["finding_code"] == "DAY_OF_VALUES_REVIEW")
    assert "11.2 mmol/L" in review["detail"]

    within_rule_threshold = W.apply_completed_actions(
        chart, set(), day_of_values={"POC glucose": {"value": 10.0, "unit": "mmol/L"}})
    findings = C.evaluate_structured(within_rule_threshold)
    review = next(finding for finding in findings if finding["finding_code"] == "DAY_OF_VALUES_REVIEW")
    assert "10.0 mmol/L" in review["detail"]
    assert "UPDATE_ANESTHESIA_PLAN" in review["actions"]["anesthesia"]


def test_day_of_value_flag_uses_reference_range_not_day_of_label():
    from preop import workflow as W

    chart = D.build_chart("S078")
    for value, expected in ((240, "H"), (50, "L"), (100, "")):
        updated = W.apply_completed_actions(
            chart, set(), day_of_values={"POC glucose": {"value": value, "unit": "mg/dL"}})
        newest = C.latest_lab(updated, "POC glucose")
        assert newest["flag"] == expected


def test_day_of_value_entry_appears_in_anesthesia_review():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Day-of QA")
    student.button[0].click().run()
    student.button(key="pt_S078").click().run()
    student.radio(key="dec|S078|nurse|INSULIN_INSTRUCTIONS").set_value("Accept").run()

    assert any(item.key == "dayof-value|S078|POC glucose" for item in student.number_input)
    student.number_input(key="dayof-value|S078|POC glucose").set_value(240)
    student.button(key="FormSubmitter:dayof-form|S078|POC glucose-Record POC glucose").click().run()
    assert any(item.key == "dec|S078|nurse|INSULIN_INSTRUCTIONS" for item in student.radio)
    assert not student.session_state.get("completed|S078|nurse|INSULIN_INSTRUCTIONS")
    for index in range(3):
        student.checkbox(key=f"todo|S078|nurse|INSULIN_INSTRUCTIONS|{index}").check().run()
    assert student.session_state["completed|S078|nurse|INSULIN_INSTRUCTIONS"]

    student.segmented_control[1].set_value("anesthesia").run()
    assert any(item.key == "dec|S078|anesthesia|UPDATE_ANESTHESIA_PLAN"
               for item in student.radio)
    assert any("Day-of values to review" in item.value for item in student.warning)
    key_values = next(item.value for item in student.markdown
                      if "<table" in item.value and "DAYOF-S078-POC-glucose" in item.value)
    assert "240.0 mg/dL" in key_values and "261 mg/dL" in key_values
    assert "H" in key_values
    assert not student.exception, student.exception

    student.segmented_control[1].set_value("nurse").run()
    student.button(key="chart-nav|S078|Labs").click().run()
    assert not any(item.key == "dayof-value|S078|POC glucose" for item in student.number_input)
    student.button(key="edit-lab|S078|POC glucose").click().run()
    student.number_input(key="dayof-value|S078|POC glucose").set_value(220)
    student.button(key="FormSubmitter:dayof-form|S078|POC glucose-Record POC glucose").click().run()
    assert student.session_state["history|S078|lab:POC glucose"]
    assert not any(item.key == "dayof-value|S078|POC glucose" for item in student.number_input)
    assert not student.exception, student.exception


def test_lab_team_pending_result_does_not_close_day_of_todo():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Pending lab QA")
    student.button[0].click().run()
    student.button(key="pt_S078").click().run()
    student.radio(key="dec|S078|nurse|INSULIN_INSTRUCTIONS").set_value("Accept").run()
    student.button(key="lab-pending|S078|POC glucose").click().run()

    assert student.session_state["dayof_pending|S078"]["POC glucose"]
    for index in range(3):
        student.checkbox(key=f"todo|S078|nurse|INSULIN_INSTRUCTIONS|{index}").check().run()
    assert any(item.key == "dec|S078|nurse|INSULIN_INSTRUCTIONS" for item in student.radio)
    assert not student.session_state.get("completed|S078|nurse|INSULIN_INSTRUCTIONS")

    student.number_input(key="dayof-value|S078|POC glucose").set_value(100)
    student.button(key="FormSubmitter:dayof-form|S078|POC glucose-Record POC glucose").click().run()
    assert student.session_state["completed|S078|nurse|INSULIN_INSTRUCTIONS"]
    assert not student.session_state["dayof_pending|S078"].get("POC glucose")
    assert not student.exception, student.exception


def test_ekg_pending_result_does_not_close_ekg_todo():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Pending EKG QA")
    student.button[0].click().run()
    student.button(key="pt_S097").click().run()
    student.radio(key="dec|S097|nurse|OBTAIN_EKG").set_value("Accept").run()
    student.button(key="ekg-pending|S097").click().run()

    assert student.session_state["session_ekg_pending|S097"]
    for index in range(3):
        student.checkbox(key=f"todo|S097|nurse|OBTAIN_EKG|{index}").check().run()
    assert any(item.key == "dec|S097|nurse|OBTAIN_EKG" for item in student.radio)
    assert not student.session_state.get("completed|S097|nurse|OBTAIN_EKG")
    assert not student.exception, student.exception


def test_missing_medication_last_dose_finding_is_nurse_only():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Medication role QA")
    student.button[0].click().run()
    student.button(key="pt_S004").click().run()

    student.segmented_control[1].set_value("anesthesia").run()
    assert all("Record last dose amount and date for" not in item.value
               for item in student.warning)
    assert not any(item.key == "dec|S004|anesthesia|VERIFY_MEDICATION_LAST_DOSE"
                   for item in student.radio)

    student.segmented_control[1].set_value("nurse").run()
    assert any("Rule finding: Record last dose amount and date for: Apixaban" in item.value
               for item in student.warning)
    assert not student.exception, student.exception


def test_completed_todo_stays_saved_after_accepting_next_step():
    from streamlit.testing.v1 import AppTest

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Completed task QA")
    student.button[0].click().run()
    student.button(key="pt_S097").click().run()
    student.radio(key="dec|S097|nurse|DRAW_HBA1C").set_value("Accept").run()
    student.checkbox(key="todo|S097|nurse|DRAW_HBA1C|0").check().run()
    student.radio(key="dec|S097|nurse|OBTAIN_EKG").set_value("Accept").run()
    assert student.session_state["todo|S097|nurse|DRAW_HBA1C|0"]
    assert not student.session_state["todo|S097|nurse|DRAW_HBA1C|1"]

    for index in (1, 2):
        student.checkbox(key=f"todo|S097|nurse|DRAW_HBA1C|{index}").check().run()

    completed_key = "completed|S097|nurse|DRAW_HBA1C"
    assert student.session_state[completed_key]
    assert not any(item.key and item.key.startswith("todo|S097|nurse|DRAW_HBA1C|")
                   for item in student.checkbox)

    student.radio(key="dec|S097|nurse|OBTAIN_CHEST_XRAY").set_value("Accept").run()
    assert student.session_state[completed_key]
    assert any("Completed in this session" in item.value for item in student.markdown)
    assert any("Obtain order and draw HbA1c." in item.value for item in student.markdown)
    assert not student.exception, student.exception


def test_recent_held_medication_dose_notifies_anesthesia_and_tracks_corrections():
    from streamlit.testing.v1 import AppTest
    from datetime import date
    from preop import workflow as W

    app = os.path.join(D.ROOT, "app.py")
    student = AppTest.from_file(app, default_timeout=60).run()
    student.text_input[0].input("Medication dose QA")
    student.button[0].click().run()
    student.button(key="pt_S004").click().run()
    student.radio(key="dec|S004|nurse|VERIFY_MEDICATION_LAST_DOSE").set_value("Accept").run()

    for index in range(3):
        student.checkbox(key=f"todo|S004|nurse|VERIFY_MEDICATION_LAST_DOSE|{index}").check().run()
    dose_date = date.fromisoformat(D.build_chart("S004")["case"]["surgery_date"])
    student.date_input(key="med-dose-date|S004|M0007").set_value(dose_date)
    student.button(key="FormSubmitter:med-dose-form|S004|M0007-Record last dose").click().run()
    assert "M0007" not in student.session_state.get("med-dose|S004", {})

    student.radio(key="med-dose-within|S004|M0007").set_value("yes")
    student.button(key="FormSubmitter:med-dose-form|S004|M0007-Record last dose").click().run()
    assert student.session_state["completed|S004|nurse|VERIFY_MEDICATION_LAST_DOSE"]
    assert student.session_state["med-dose|S004"]["M0007"]["within_hold_period"]

    student.segmented_control[1].set_value("anesthesia").run()
    assert any(item.key == "dec|S004|anesthesia|REVIEW_RECENT_MEDICATION_DOSE"
               for item in student.radio)
    assert any(item.value == "Apixaban taken within hold period." for item in student.info)
    assert all("Reported dose within documented hold period" not in item.value
               for item in student.warning)
    dose_chart = W.apply_completed_actions(
        D.build_chart("S004"), set(), medication_doses=student.session_state["med-dose|S004"],
        track_medication_doses=True,
    )
    dose_finding = next(finding for finding in C.evaluate_structured(dose_chart)
                        if finding["finding_code"] == "MEDICATION_DOSE_WITHIN_HOLD")
    assert "Reported dose within documented hold period: Apixaban 5 mg" in dose_finding["detail"]

    student.segmented_control[1].set_value("nurse").run()
    student.button(key="chart-nav|S004|Medications").click().run()
    assert not any(item.key == "med-dose-amount|S004|M0007" for item in student.number_input)
    student.button(key="edit-medication|S004|M0007").click().run()
    student.number_input(key="med-dose-amount|S004|M0007").set_value(7.5)
    student.button(key="FormSubmitter:med-dose-form|S004|M0007-Record last dose").click().run()
    assert student.session_state["history|S004|medication:M0007"]
    assert not any(item.key == "med-dose-amount|S004|M0007" for item in student.number_input)
    assert not student.session_state.get("completed|S004|nurse|VERIFY_MEDICATION_LAST_DOSE")

    student.segmented_control[1].set_value("anesthesia").run()
    student.button(key="chart-nav|S004|Pre-Op Readiness").click().run()
    assert any(item.value == "Apixaban taken within hold period." for item in student.info)
    assert not student.exception, student.exception


def test_simultaneous_llm_requests_call_the_model_once():
    import threading
    import time
    PL.CACHE_DIR = os.path.join(D.ROOT, "results", "cache_test")
    calls = []
    slow = lambda: (calls.append(1), time.sleep(0.2), {"ok": True})[-1]
    path = PL._cache_path(FakeLLM(), "S001", "concurrency")
    if os.path.exists(path):
        os.remove(path)
    out = []
    threads = [threading.Thread(target=lambda: out.append(PL._cached(FakeLLM(), "S001", "concurrency", slow))) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(calls) == 1 and out == [{"ok": True}] * 8


def test_two_students_do_not_share_changes():
    from streamlit.testing.v1 import AppTest
    app = os.path.join(D.ROOT, "app.py")

    def join(name):
        at = AppTest.from_file(app, default_timeout=60).run()
        at.text_input[0].input(name)
        at.button[0].click().run()
        assert not at.exception, at.exception
        return at

    a, b = join("Ana"), join("Ben")
    assert a.session_state.sid != b.session_state.sid
    move = next(x for x in a.button if x.key in ("sg_apply", "sg_hold"))  # the first assigned case has a schedule suggestion
    move.click().run()
    assert a.session_state.moves and not b.run().session_state.moves
    again = AppTest.from_file(app, default_timeout=60)
    again.query_params["u"] = a.query_params["u"]                           # page refresh keeps the student's patient
    assert again.run().session_state.sid == a.session_state.sid


def test_project_team_can_reset_everyone():
    from streamlit.testing.v1 import AppTest
    app = os.path.join(D.ROOT, "app.py")
    os.environ["PREOP_TEAM_CODE"] = "test-code"
    try:
        student = AppTest.from_file(app, default_timeout=60).run()
        student.text_input[0].input("Ana")
        student.button[0].click().run()
        assert student.session_state.sid

        team = AppTest.from_file(app, default_timeout=60).run()
        team.sidebar.text_input[0].input("wrong").run()
        assert not team.sidebar.button                                       # still locked
        team.sidebar.text_input[0].input("test-code").run()
        team.sidebar.checkbox[0].check().run()
        team.sidebar.button[0].click().run()
        assert not team.exception, team.exception

        student.run()
        assert [t.label for t in student.main.text_input] == ["Your name"]  # back to sign-in
    finally:
        del os.environ["PREOP_TEAM_CODE"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
