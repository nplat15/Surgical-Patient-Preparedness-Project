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
