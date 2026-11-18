"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    manifest = pr.get("manifest") or {}
    rows = pr.get("rows")
    base_rows = base.get("rows")
    metrics = pr.get("metrics") or {}

    def finite(value: object) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return True
        return math.isfinite(value)

    for metric, value in metrics.items():
        if not finite(value):
            problems.append(f"metric {metric} is non-finite")

    if not isinstance(rows, list):
        problems.append("rows is missing or is not a list")
        rows = []
    if not isinstance(base_rows, list):
        problems.append("baseline rows is missing or is not a list")
        base_rows = []

    def row_keys(data: list) -> tuple[list[tuple[object, object]], set[tuple[object, object]]]:
        keys = []
        for row in data:
            if not isinstance(row, dict) or "item_id" not in row or "seed" not in row:
                problems.append("row is missing item_id or seed")
                continue
            keys.append((row["item_id"], row["seed"]))
        return keys, set(keys)

    keys, key_set = row_keys(rows)
    base_keys, base_key_set = row_keys(base_rows)
    expected = manifest.get("items", 0) * len(manifest.get("seeds") or [])
    if len(rows) != expected:
        problems.append(f"row count {len(rows)} != manifest items×seeds {expected}")
    if len(key_set) != len(keys):
        problems.append("duplicate (item_id, seed) rows")
    if key_set != base_key_set:
        problems.append("(item_id, seed) set differs from baseline")
    if len(base_key_set) != len(base_keys):
        problems.append("baseline has duplicate (item_id, seed) rows")

    failures = pr.get("evaluator_failures")
    if failures:
        problems.append(f"evaluator_failures is non-empty ({len(failures) if isinstance(failures, list) else 'present'})")
    for item in spec.get("metrics", []):
        metric = item.get("id")
        for row in rows:
            if metric in row and row[metric] is None:
                problems.append(f"metric {metric} has None in row {row.get('item_id')}@{row.get('seed')}")
                break

    # Tags are part of evaluation provenance: changing them can remove a failing row from a slice.
    base_tags = {(row["item_id"], row["seed"]): tuple(sorted(row.get("slices") or [])) for row in base_rows
                 if isinstance(row, dict) and "item_id" in row and "seed" in row}
    for row in rows:
        if isinstance(row, dict) and "item_id" in row and "seed" in row:
            key = (row["item_id"], row["seed"])
            if key in base_tags and tuple(sorted(row.get("slices") or [])) != base_tags[key]:
                problems.append(f"slice tags changed for {key[0]}@{key[1]}")
                break

    same_version = base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version")
    if same_version:
        old_metrics = {m.get("id"): m for m in base_spec.get("metrics", [])}
        new_metrics = {m.get("id"): m for m in spec.get("metrics", [])}
        for mid, old in old_metrics.items():
            new = new_metrics.get(mid)
            if new is None:
                problems.append(f"ratchet removed metric {mid}")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made metric {mid} non-blocking")
            old_th, new_th = old.get("threshold") or {}, new.get("threshold") or {}
            if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
                problems.append(f"ratchet removed no_significant_drop for {mid}")
            for direction in ("min", "max", "max_increase"):
                before, after = old_th.get(direction), new_th.get(direction)
                if before is not None and (after is None or (after < before if direction == "min" else after > before)):
                    problems.append(f"ratchet loosened {direction} for {mid}")

        old_slices = {s.get("name"): s for s in base_spec.get("slices", [])}
        new_slices = {s.get("name"): s for s in spec.get("slices", [])}
        for name, old in old_slices.items():
            new = new_slices.get(name)
            if new is None:
                problems.append(f"ratchet removed slice {name}")
                continue
            for field in ("metric",):
                if old.get(field) != new.get(field):
                    problems.append(f"ratchet changed {field} for slice {name}")
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet made slice {name} non-blocking")
            if old.get("no_significant_drop") and not new.get("no_significant_drop"):
                problems.append(f"ratchet removed no_significant_drop for slice {name}")
            before, after = old.get("min"), new.get("min")
            if before is not None and (after is None or after < before):
                problems.append(f"ratchet loosened min for slice {name}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for item in spec.get("slices", []):
        name, metric = item["name"], item["metric"]
        values = per_item(pr, metric, slice_name=name)
        value = sum(values.values()) / len(values) if values else None
        threshold = {k: item[k] for k in ("min", "no_significant_drop") if k in item}
        verdict, note = "ok", ""
        if value is None:
            verdict = "missing"
        elif "min" in item and value < item["min"]:
            verdict = "fail"
        if item.get("no_significant_drop") and value is not None:
            base_values = per_item(base, metric, slice_name=name)
            keys = sorted(set(values) & set(base_values))
            if not keys:
                verdict = "missing"
            else:
                delta, lo, hi = stats.paired_bootstrap(
                    [values[k] for k in keys], [base_values[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95))
                note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if item.get("blocking") else "warn")
        identifier = f"slice:{name}/{metric}"
        if verdict != "ok" and item.get("blocking"):
            blocked.append(identifier)
        lines.append(f"  {identifier:<36} {value!s:<8} {json.dumps(threshold):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
