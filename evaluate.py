"""
Stage 5 evaluation: compare the system's next steps with the answer key.

    python evaluate.py --engine rules --split test          # rules-only baseline (no API key needed)
    python evaluate.py --engine llm   --split test          # the AI pipeline (needs an API key)
    python evaluate.py --engine llm   --split dev --limit 10

Scores, per role:
  * precision  - of the actions the system recommended, how many were expected
  * recall     - of the expected actions, how many the system recommended
  * F1         - balance of the two
  * note-only recall - recall on actions that can ONLY be found by reading the H&P text
  * status accuracy  - did it choose the right overall status
Also lists recall by finding type, so you can see what it misses.

The answer key is read here and ONLY here. The AI never sees it.
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

from preop import criteria as C
from preop import data as D
from preop.llm import LLM
from preop.pipeline import run_case

KEY_DIR = os.path.join(D.DEFAULT_DATA, "answer_key")
OUT_DIR = os.path.join(D.ROOT, "results")


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def split_codes(s):
    return {x.strip() for x in (s or "").split("|") if x.strip()}


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["rules", "llm"], default="rules")
    ap.add_argument("--split", choices=["dev", "test", "all"], default="test")
    ap.add_argument("--roles", nargs="+", default=list(C.ROLES))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    cases = read(os.path.join(KEY_DIR, "ground_truth_cases.csv"))
    findings = read(os.path.join(KEY_DIR, "ground_truth_findings.csv"))
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]
    cases = cases[: args.limit] if args.limit else cases
    llm = LLM() if args.engine == "llm" else None
    label = "rules" if args.engine == "rules" else f"{llm.provider}:{llm.model}"
    if llm is not None and llm.is_mock:
        print("WARNING: no API key found, 'llm' is running in MOCK mode (rules output). Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")

    rows = []
    totals = {r: defaultdict(int) for r in args.roles}
    by_finding = {r: defaultdict(lambda: [0, 0]) for r in args.roles}
    for i, gt in enumerate(cases, 1):
        sid = gt["surgery_id"]
        f_case = [f for f in findings if f["surgery_id"] == sid]
        for role in args.roles:
            res = run_case(sid, role=role, engine=args.engine, llm=llm, use_cache=not args.no_cache)
            pred = {a["code"] for a in res["next_steps"]["actions"]}
            exp = split_codes(gt[f"expected_{role}_actions"])
            struct_codes = set().union(*[split_codes(f[f"{role}_actions"]) for f in f_case if f["source"] == "structured"] or [set()])
            note_codes = set().union(*[split_codes(f[f"{role}_actions"]) for f in f_case if f["source"] == "note"] or [set()]) - struct_codes
            tp, fp, fn = len(pred & exp), len(pred - exp), len(exp - pred)
            t = totals[role]
            t["tp"] += tp; t["fp"] += fp; t["fn"] += fn
            t["note_exp"] += len(note_codes); t["note_hit"] += len(note_codes & pred)
            t["n"] += 1; t["status_ok"] += int(res["next_steps"]["status"] == gt["expected_status"])
            for f in f_case:
                codes = split_codes(f[f"{role}_actions"])
                if codes:
                    key = f["finding_code"].split(":")[0] + (":" + f["finding_code"].split(":")[1] if ":" in f["finding_code"] else "")
                    by_finding[role][key][1] += 1
                    by_finding[role][key][0] += int(codes <= pred)
            rows.append(dict(surgery_id=sid, procedure=gt["procedure"], role=role, expected_status=gt["expected_status"],
                             predicted_status=res["next_steps"]["status"], tp=tp, fp=fp, fn=fn,
                             missed=" | ".join(sorted(exp - pred)), extra=" | ".join(sorted(pred - exp)),
                             note_only_expected=" | ".join(sorted(note_codes))))
        print(f"[{i}/{len(cases)}] {sid} done")

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = f"{args.engine}_{args.split}"
    with open(os.path.join(OUT_DIR, f"eval_{tag}_cases.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    md = [f"# Evaluation: {label} on {args.split} split ({len(cases)} cases)", "",
          "| Role | Precision | Recall | F1 | Note-only recall | Status accuracy |", "|---|---|---|---|---|---|"]
    for role in args.roles:
        t = totals[role]
        p, r, f1 = prf(t["tp"], t["fp"], t["fn"])
        nr = f"{t['note_hit']}/{t['note_exp']}" if t["note_exp"] else "n/a"
        md.append(f"| {role} | {p:.2f} | {r:.2f} | {f1:.2f} | {nr} | {t['status_ok']}/{t['n']} |")
    for role in args.roles:
        md += ["", f"## Recall by finding type ({role})", "", "| Finding | Caught |", "|---|---|"]
        for k, (hit, n) in sorted(by_finding[role].items(), key=lambda kv: kv[1][0] / kv[1][1]):
            md.append(f"| {k} | {hit}/{n} |")
    text = "\n".join(md)
    with open(os.path.join(OUT_DIR, f"eval_{tag}.md"), "w") as f:
        f.write(text + "\n")
    print("\n" + text)


if __name__ == "__main__":
    main()
