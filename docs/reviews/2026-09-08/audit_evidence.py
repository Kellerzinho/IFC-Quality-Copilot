"""Read-only recomputation of archived benchmark evidence for the research review.

Run from the project root with its existing Python environment. No LLM calls,
model edits, or writes to archived evidence occur. Only the adjacent JSON is saved.
The constant-answer probe is a post-hoc metric stress test, not a held-out baseline.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.experiment.evaluator import GroundTruth, Evaluator
from src.experiment.per_issue import mcnemar_exact
from src.models import Issue


def natural_key(item):
    return (item["element_guid"], item["issue_type"], item.get("check_property", ""))


def main():
    evidence = {"datasets": {}, "archives": {}, "method": "Archived outputs rescored; no model execution. Constant REI 120 probe is exploratory, not physical validation."}
    truths = {}
    evaluator = Evaluator()
    for dataset in ("predio", "casa"):
        path = ROOT / "data" / "evaluation" / dataset / "ground_truth.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        truth = GroundTruth.from_yaml(path)
        truths[dataset] = truth
        classes = {}
        for item in raw["items"]:
            classes.setdefault(item["equivalence_id"], item)
        evidence["datasets"][dataset] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "items": len(raw["items"]), "classes": len(classes),
            "confidence_items": dict(Counter(i["confidence"] for i in raw["items"])),
            "confidence_classes": dict(Counter(i["confidence"] for i in classes.values())),
            "source_kind_items": dict(Counter(i["source_kind"] for i in raw["items"])),
            "verified_items": sum(i["verified"] for i in raw["items"]),
        }

    prefixes = {"4070_on": "20260813T", "4060_on": "20260814T", "4070_off": "20260818T185722", "5050_on": "20260818T190222"}
    outcomes_by_arm = {}
    for arm, prefix in prefixes.items():
        matches = list((ROOT / "dist").glob(f"RESULTADO_IFCQC_{prefix}*.zip"))
        if len(matches) != 1:
            raise ValueError(f"Ambiguous archive: {arm}")
        path = matches[0]
        model_rows = defaultdict(list)
        metadata_rows = []
        mismatches = 0
        truth_mismatches = 0
        primary_counts = Counter()
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.endswith("/run_0.json"):
                    continue
                summary = json.loads(archive.read(name))
                meta = summary["metadata"]
                model = meta["model_name"]
                dataset = meta["dataset_key"]
                truth = truths[dataset]
                metadata_rows.append({
                    "model": model, "dataset": dataset,
                    "prompt": meta["prompt_version"],
                    "replica": meta["replica_index"],
                    "ground_truth_hash_matches": meta["ground_truth_sha256"] == evidence["datasets"][dataset]["sha256"],
                    "issue_counts": summary["issue_counts"],
                    "simulation": summary["review_proxy"]["simulation"],
                    "ids_post_skip": summary["review_proxy"]["ids_post_skip"],
                })
                rows = [json.loads(line) for line in archive.read(name.replace(".json", "_issues.jsonl")).decode("utf-8").splitlines() if line.strip()]
                for row in rows:
                    issue = Issue(id=row["issue_id"], element_guid=row["element_guid"], element_class=row["element_class"], issue_type=row["issue_type"], severity="medium", description="Archived outcome audit", context={"check_property": row["check_property"]})
                    gt = truth.get_for_issue(issue)
                    if gt is None:
                        raise ValueError(f"Missing GT: {dataset}/{row['issue_id']}")
                    truth_mismatches += int(row["expected"] != gt.expected_value or row["accepted_alternatives"] != gt.accepted_alternatives)
                    values = row["top_values"]
                    hit1 = bool(values) and evaluator._suggestion_matches(issue, values[0], gt)
                    hit3 = any(evaluator._suggestion_matches(issue, v, gt) for v in values[:3])
                    mismatches += int(hit1 != row["match_top1"]) + int(hit3 != row["match_top3"])
                    row.update(dataset=dataset, equivalence_id=gt.equivalence_id, gt_confidence=gt.confidence)
                    if row["reused_from"] is None:
                        primary_counts[dataset] += 1
                    if row["check_property"] == "FireRating":
                        row["constant_REI_120_hit"] = evaluator._suggestion_matches(issue, "REI 120", gt)
                    model_rows[model].append(row)
        model_summary = {}
        representatives = {}
        for model, rows in sorted(model_rows.items()):
            classes = defaultdict(list)
            for row in rows:
                classes[(row["dataset"], row["equivalence_id"])].append(row)
            if any(len({r["match_top1"] for r in group}) != 1 for group in classes.values()):
                raise ValueError("Nonhomogeneous class; mean-class treatment needed")
            representatives[model] = {key: group[0] for key, group in classes.items()}
            reps = list(representatives[model].values())
            fire = [r for r in rows if "constant_REI_120_hit" in r]
            fire_cls = [r for r in reps if "constant_REI_120_hit" in r]
            model_summary[model] = {
                "items": len(rows), "classes": len(reps),
                "top1_items": sum(r["match_top1"] for r in rows) / len(rows),
                "top1_classes": sum(r["match_top1"] for r in reps) / len(reps),
                "top3_items": sum(r["match_top3"] for r in rows) / len(rows),
                "top3_classes": sum(r["match_top3"] for r in reps) / len(reps),
                "gt_confidence_class_accuracy": {c: {"n": len(sub), "top1": sum(r["match_top1"] for r in sub)/len(sub)} for c in ("high", "medium", "low") if (sub := [r for r in reps if r["gt_confidence"] == c])},
                "fire_constant_REI120": {"items": len(fire), "item_hits": sum(r["constant_REI_120_hit"] for r in fire), "classes": len(fire_cls), "class_hits": sum(r["constant_REI_120_hit"] for r in fire_cls)},
                "official_candidates": sum(r["has_official_candidates"] for r in rows),
                "grounding_sources": dict(Counter("+".join(r["grounding_sources"]) for r in rows)),
            }
        outcomes_by_arm[arm] = representatives
        evidence["archives"][arm] = {
            "path": str(path.relative_to(ROOT)), "stages": len(metadata_rows),
            "verdict_mismatches": mismatches, "reference_value_mismatches": truth_mismatches,
            "primary_counts": dict(primary_counts), "stage_checks": metadata_rows,
            "models": model_summary,
        }
    paired = {}
    for model, on in outcomes_by_arm["4070_on"].items():
        off = outcomes_by_arm["4070_off"][model]
        if set(on) != set(off):
            raise ValueError("Unpaired classes")
        b = sum(on[k]["match_top1"] and not off[k]["match_top1"] for k in on)
        c = sum(off[k]["match_top1"] and not on[k]["match_top1"] for k in on)
        paired[model] = {"n": len(on), "only_on": b, "only_off": c, "delta_pp": 100*(c-b)/len(on), "mcnemar_unadjusted": mcnemar_exact(b,c)}
    b = sum(p["only_on"] for p in paired.values())
    c = sum(p["only_off"] for p in paired.values())
    evidence["paired_ablation"] = {"models": paired, "pooled": {"n_model_classes": sum(p["n"] for p in paired.values()), "only_on": b, "only_off": c, "naive_mcnemar": mcnemar_exact(b,c), "caution": "Pooled McNemar assumes independence across model-class pairs; the same classes occur across models. Not a cluster-adjusted inference."}}
    output = Path(__file__).with_name("evidence_audit.json")
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"datasets": evidence["datasets"], "paired": evidence["paired_ablation"], "checks": {arm: {k: info[k] for k in ("stages", "verdict_mismatches", "reference_value_mismatches", "primary_counts")} for arm,info in evidence["archives"].items()}, "fire_probe": evidence["archives"]["4070_on"]["models"]["gemma2:9b"]["fire_constant_REI120"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
