"""
End-to-end pipeline: Module 1 -> Module 2 -> Module 3 -> Module 4.

    from preop.pipeline import run_case
    result = run_case("S082", role="anesthesia")            # uses the LLM (or mock if no key)
    result = run_case("S082", role="nurse", engine="rules")  # rules-only baseline, no AI

Every result has the same shape so the app and the evaluation can treat both engines alike.
"""
from __future__ import annotations

import json
import os

from . import criteria as C
from . import data as D
from . import prompts as P
from .llm import LLM

CACHE_DIR = os.path.join(D.ROOT, "results", "cache")


# ---------------------------------------------------------------------------
# Rules-only baseline (structured fields only, cannot read notes)
# ---------------------------------------------------------------------------
def rules_next_steps(chart, role):
    findings = C.evaluate_structured(chart)
    acts = []
    for f in findings:
        for code in f["actions"][role]:
            if code not in [a["code"] for a in acts]:
                acts.append(dict(code=code, reason=f["detail"], evidence_ids=f["evidence_ids"],
                                 priority="high" if f["category"] in ("critical", "clinical") else "medium"))
    status = C.status_from_findings(findings)
    return dict(status=status, status_reason=f"{len(findings)} rule finding(s) on structured data.",
                actions=acts, other_considerations=[], findings=findings)


def rules_summary(chart, role, steps):
    c = chart["case"]
    bullets = [f"{c['procedure']} on {c['surgery_date']} {c['surgery_time']}"]
    bullets += [f"⚠ {f['detail']}" for f in steps["findings"]]
    return dict(headline=f"{steps['status']} - rules-only check ({len(steps['findings'])} finding(s))",
                sections=[dict(title="Rule findings", bullets=bullets)])


# ---------------------------------------------------------------------------
# LLM pipeline
# ---------------------------------------------------------------------------
def _cache_path(llm, surgery_id, name):
    safe = f"{llm.provider}_{llm.model}".replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, safe, f"{surgery_id}_{name}.json")


def _cached(llm, surgery_id, name, fn, use_cache=True):
    path = _cache_path(llm, surgery_id, name)
    if use_cache and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    out = fn()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    return out


def module2_qa(llm, packet):
    s, u = P.qa_prompt(packet)
    return llm.complete_json(s, u)


def module3_summary(llm, packet, qa, role):
    s, u = P.summary_prompt(packet, qa, role)
    return llm.complete_json(s, u)


def module4_next_steps(llm, packet, qa, role, procedure):
    s, u = P.next_steps_prompt(packet, qa, role, procedure)
    out = llm.complete_json(s, u)
    allowed = C.catalog_for_role(role)
    clean, seen = [], set()
    for a in out.get("actions", []):
        code = str(a.get("code", "")).strip().upper()
        if code in allowed and code not in seen:
            seen.add(code)
            clean.append(dict(code=code, reason=a.get("reason", ""), evidence_ids=a.get("evidence_ids", []),
                              priority=a.get("priority", "medium")))
        elif code not in allowed and code:
            out.setdefault("other_considerations", []).append(f"(unrecognized code {code}) {a.get('reason', '')}")
    out["actions"] = clean
    if out.get("status") not in C.STATUS_ORDER:
        out["status"] = "Needs clinical review"
    return out


def run_case(surgery_id, role="nurse", engine="llm", llm=None, use_cache=True, data_dir=D.DEFAULT_DATA):
    assert role in C.ROLES
    m1 = D.module1_identify_surgery(surgery_id, data_dir)
    chart = D.build_chart(surgery_id, data_dir)
    if engine == "llm":
        llm = llm or LLM()
    if engine == "rules" or llm.is_mock:
        steps = rules_next_steps(chart, role)
        label = "rules" if engine == "rules" else "mock (no API key: rules output shown)"
        return dict(surgery_id=surgery_id, role=role, engine=label, module1=m1, qa=None,
                    summary=rules_summary(chart, role, steps), next_steps=steps)
    packet = D.chart_to_packet(chart)
    qa = _cached(llm, surgery_id, "qa", lambda: module2_qa(llm, packet), use_cache)
    summary = _cached(llm, surgery_id, f"summary_{role}", lambda: module3_summary(llm, packet, qa, role), use_cache)
    steps = _cached(llm, surgery_id, f"next_{role}",
                    lambda: module4_next_steps(llm, packet, qa, role, chart["case"]["procedure"]), use_cache)
    return dict(surgery_id=surgery_id, role=role, engine=f"{llm.provider}:{llm.model}", module1=m1, qa=qa,
                summary=summary, next_steps=steps)


def action_text(code):
    return C.ACTION_CATALOG.get(code, ("", code))[1]
