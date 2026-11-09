"""Generate every number the paper prints, from the campaign aggregates.

Writes paper/generated/numbers.tex, a list of key -> value definitions. The
LaTeX source never contains a result number: it calls \\Num{key}, and an
unknown key stops the build. So a number in the PDF cannot disagree with the
aggregates, and paper/generated/numbers.json lists each value with the file
and field it came from, for audit.

Key scheme (':' separated):
    p1:<stage>:<metric>:<stat>      pooled campaign 1, seeds 0-9
    p2:<metric>:<stat>              pooled campaign 2, seeds 0-9 (stage scorer_bench)
    c3:<stage>:<metric>:<stat>      campaign 3, seeds 0-9
    h:<name>:<field>                hypotheses (orig, rep, pool, diff, lo, hi, sd, replicated)
    prov:<name>                     provenance (commits, wall times, seed counts)
<stat> is one of mean, sd, min, max, pm ("mean \\pm sd", for math mode).

Usage:  .venv/bin/python paper/make_numbers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments"
OUT = ROOT / "paper" / "generated"


def f3(x: float) -> str:
    return f"{x:.3f}"


def signed(x: float) -> str:
    return f"{x:+.3f}".replace("-", "$-$").replace("+", "$+$")


class Numbers:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sources: dict[str, str] = {}

    def put(self, key: str, value: str, source: str) -> None:
        if key in self.values:
            raise KeyError(f"duplicate key {key}")
        self.values[key] = value
        self.sources[key] = source

    def summary(self, prefix: str, s: dict, source: str) -> None:
        self.put(f"{prefix}:mean", f3(s["mean"]), source)
        self.put(f"{prefix}:sd", f3(s["sd"]), source)
        self.put(f"{prefix}:min", f3(s["min"]), source)
        self.put(f"{prefix}:max", f3(s["max"]), source)
        self.put(f"{prefix}:pm", f"{f3(s['mean'])} \\pm {f3(s['sd'])}", source)


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"missing {path}: run the campaigns first (experiments/README.md)")
    return json.loads(path.read_text())


def main() -> int:
    n = Numbers()

    # --- pooled campaigns 1 and 2 (seeds 0-9) --------------------------------
    for tag, folder in (("p1", "campaign1"), ("p2", "campaign2")):
        path = EXP / "pooled" / folder / "aggregate.json"
        pooled = load(path)
        rel = str(path.relative_to(ROOT))
        if pooled["provenance"]["seeds"] != list(range(10)):
            sys.exit(f"{rel}: expected seeds 0..9, got {pooled['provenance']['seeds']}")
        for stage, metrics in pooled["metrics"].items():
            for name, s in metrics.items():
                prefix = f"{tag}:{stage}:{name}" if tag == "p1" else f"{tag}:{name}"
                n.summary(prefix, s, f"{rel} metrics.{stage}.{name}")
        for name, h in pooled["hypotheses"].items():
            short = name.split("_")[0]  # H1 .. H8
            src = f"{rel} hypotheses.{name}"
            n.put(f"h:{short}:orig", f"{h['original']['n_positive']}/{h['original']['n_seeds']}", src)
            n.put(f"h:{short}:rep", f"{h['replication']['n_positive']}/{h['replication']['n_seeds']}", src)
            n.put(f"h:{short}:pool", f"{h['pooled']['n_positive']}/{h['pooled']['n_seeds']}", src)
            n.put(f"h:{short}:replicated", "yes" if h["replicated"] else "no", src)
            n.put(f"h:{short}:poolsupported", "yes" if h["pooled"]["supported"] else "no", src)
            n.put(f"h:{short}:diff", signed(h["mean_diff"]), src)
            n.put(f"h:{short}:sd", f3(h["sd_diff"]), src)
            n.put(f"h:{short}:lo", signed(min(h["per_seed_diff"])), src)
            n.put(f"h:{short}:hi", signed(max(h["per_seed_diff"])), src)
        for part in ("original", "replication"):
            prov = pooled["provenance"][part]
            n.put(f"prov:{tag}:{part}:commit", prov["git_commit"][:7], f"{rel} provenance.{part}.git_commit")

    # Wall times come from the campaign aggregates themselves.
    for key, folder in (("c1", "campaign"), ("c1rep", "campaign_rep"), ("c2", "campaign2"), ("c2rep", "campaign2_rep")):
        path = EXP / folder / "aggregate.json"
        agg = load(path)
        if agg["failures"]:
            sys.exit(f"{path}: recorded failures; the paper cannot be built from it")
        n.put(f"prov:{key}:wall", f"{agg['wall_time_s']:.0f}", f"{path.relative_to(ROOT)} wall_time_s")

    # --- campaign 3 (seeds 0-9) ----------------------------------------------
    path = EXP / "campaign3" / "aggregate.json"
    c3 = load(path)
    rel = str(path.relative_to(ROOT))
    if c3["failures"]:
        sys.exit(f"{rel}: recorded failures; the paper cannot be built from it")
    if c3["provenance"]["seeds"] != list(range(10)):
        sys.exit(f"{rel}: expected seeds 0..9, got {c3['provenance']['seeds']}")
    for stage, metrics in c3["metrics"].items():
        for name, s in metrics.items():
            n.summary(f"c3:{stage}:{name}", s, f"{rel} metrics.{stage}.{name}")
    for name, h in c3["hypotheses"].items():
        short = name.split("_")[0]  # H7s, H9, H10
        src = f"{rel} hypotheses.{name}"
        n.put(f"h:{short}:pool", f"{h['n_positive']}/{h['n_seeds']}", src)
        n.put(f"h:{short}:poolsupported", "yes" if h["supported"] else "no", src)
        n.put(f"h:{short}:diff", signed(h["mean_diff"]), src)
        n.put(f"h:{short}:sd", f3(h["sd_diff"]), src)
        n.put(f"h:{short}:lo", signed(min(h["per_seed_diff"])), src)
        n.put(f"h:{short}:hi", signed(max(h["per_seed_diff"])), src)
    n.put("prov:c3:commit", c3["provenance"]["git_commit"][:7], f"{rel} provenance.git_commit")
    n.put("prov:c3:wall", f"{c3['wall_time_s']:.0f}", f"{rel} wall_time_s")

    # --- pre-registered cross-checks: the build stops if one fails --------------
    p1 = load(EXP / "pooled" / "campaign1" / "aggregate.json")["metrics"]
    p2 = load(EXP / "pooled" / "campaign2" / "aggregate.json")["metrics"]["scorer_bench"]
    arm, split = c3["metrics"]["arm_control"], c3["metrics"]["split_counterfactual"]
    checks = {
        # Same seed, same data: campaign 3's full arm is campaign 2's full arm (ten seeds).
        "full_arm_reproduces_campaign2": arm["OS-full+MSP:auroc"]["per_seed"] == p2["OS-full+MSP:auroc"]["per_seed"],
        # The campaign-3 models are campaign 1's models.
        "unseen_accuracy_equals_campaign1": (
            split["CNN1D:unseen_acc"]["per_seed"] == p1["modulation"]["cnn_overall_acc"]["per_seed"]
            and split["MLP:unseen_acc"]["per_seed"] == p1["modulation"]["mlp_overall_acc"]["per_seed"]
        ),
        # Shrinkage 1 is a scaled identity: the ranking is the Euclidean score's.
        "shrinkage_one_equals_euclidean": all(
            abs(a - b) < 1e-12
            for a, b in zip(arm["CE+mahalanobis@1:auroc"]["per_seed"], arm["CE+distance:auroc"]["per_seed"])
        ),
        # One CE model per seed: campaign 2's MSP is campaign 1's MSP.
        "campaign2_msp_equals_campaign1": p2["CE+MSP:auroc"]["per_seed"] == p1["open_set"]["msp_auroc"]["per_seed"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        sys.exit(f"cross-checks failed: {failed}")
    print("cross-checks passed:", ", ".join(checks))

    # --- design counts, read back from a per-seed file as a check --------------
    seed0 = load(EXP / "campaign2" / "scorer_bench_seed0.json")
    report = seed0["variants"]["CE+MSP"]["report"]
    n.put("design:n_known_test", str(report["n_known"]), "experiments/campaign2/scorer_bench_seed0.json")
    n.put("design:n_unknown_test", str(report["n_unknown"]), "experiments/campaign2/scorer_bench_seed0.json")
    for role, count in seed0["frames"].items():
        n.put(f"design:frames:{role}", str(count), "experiments/campaign2/scorer_bench_seed0.json frames")
    arm0 = load(EXP / "campaign3" / "arm_control_seed0.json")["variants"]
    for arm_name in ("OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP"):
        n.put(f"design:outliers:{arm_name}", str(arm0[arm_name]["train_outliers"]),
              "experiments/campaign3/arm_control_seed0.json train_outliers")
    split0 = load(EXP / "campaign3" / "split_counterfactual_seed0.json")["models"]["MLP"]
    n.put("design:n_seen_test", str(split0["seen_devices_new_frames"]["overall"]["n"]),
          "experiments/campaign3/split_counterfactual_seed0.json")
    n.put("design:n_unseen_test", str(split0["unseen_devices"]["overall"]["n"]),
          "experiments/campaign3/split_counterfactual_seed0.json")

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Generated by paper/make_numbers.py from the campaign aggregates. Do not edit.",
        "\\makeatletter",
        "\\newcommand{\\Num}[1]{\\@ifundefined{num@#1}{\\errmessage{Unknown number key: #1}}{\\@nameuse{num@#1}}}",
    ]
    lines += [f"\\@namedef{{num@{key}}}{{{value}}}" for key, value in sorted(n.values.items())]
    lines.append("\\makeatother")
    (OUT / "numbers.tex").write_text("\n".join(lines) + "\n")
    (OUT / "numbers.json").write_text(
        json.dumps({k: {"value": n.values[k], "source": n.sources[k]} for k in sorted(n.values)}, indent=1)
    )
    print(f"wrote {len(n.values)} numbers to {OUT / 'numbers.tex'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
