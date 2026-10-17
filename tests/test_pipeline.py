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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
