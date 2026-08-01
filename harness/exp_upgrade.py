#!/usr/bin/env python3
"""
exp_upgrade.py -- upgrade the flagship claims to n=20 + two validity experiments.

Reuses run_attacks.py attack specs (`package`, `distributed`, `benign_package`) and its
run_std / run_distributed / set_attack helpers, and rule_based_planner for the baseline.
Real measured numbers only. Writes NEW files (never clobbers existing result JSONs):
  dist_n20.json    -- deliverable 1: distributed-delivery ASR at n=20 + Fisher vs monolithic
  benign_n20.json  -- deliverable 2: benign-domain reframe ASR at n=20 + Fisher vs military pkg
  baseline.json    -- deliverable 3: rule-based deterministic allocator, clean/injected n=20

  python3 exp_upgrade.py           # all stages (API first, then Ollama)
  python3 exp_upgrade.py --stage api      # only API-model cells
  python3 exp_upgrade.py --stage ollama   # only Ollama cells
  python3 exp_upgrade.py --stage baseline # only the deterministic baseline
"""
import argparse, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_loop as L
import run_attacks as RA
from swarm_rv import VIOLATION, NO_VIOLATION

HERE = os.path.dirname(os.path.abspath(__file__))
N = 20
TEMP = 0.8

# model -> (backend, model_id)
API_MODELS = [
    ("claude-opus-4-8",           ("anthropic", "claude-opus-4-8")),
    ("claude-sonnet-5",           ("anthropic", "claude-sonnet-5")),
    ("claude-haiku-4-5",          ("anthropic", "claude-haiku-4-5-20251001")),
]
OLLAMA_MODELS = [
    ("mistral",     ("ollama", "mistral:latest")),
    ("llama3.1:8b", ("ollama", "llama3.1:8b")),
]

ATT = {a["name"]: a for a in RA.ATTACKS}


def fisher_exact_2x2(a, b, c, d):
    """Two-tailed Fisher's exact test on the 2x2 table [[a,b],[c,d]]. Stdlib only.
    Rows = condition (monolithic, distributed/benign); cols = (success, failure)."""
    def logfact(n):
        return math.lgamma(n + 1)
    def logp(a, b, c, d):
        n = a + b + c + d
        return (logfact(a + b) + logfact(c + d) + logfact(a + c) + logfact(b + d)
                - logfact(a) - logfact(b) - logfact(c) - logfact(d) - logfact(n))
    r1, r2 = a + b, c + d
    c1 = a + c
    n = a + b + c + d
    p_obs = logp(a, b, c, d)
    total = 0.0
    # enumerate all tables with the same margins
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    for aa in range(lo, hi + 1):
        bb = r1 - aa
        cc = c1 - aa
        dd = r2 - cc
        lp = logp(aa, bb, cc, dd)
        if lp <= p_obs + 1e-9:
            total += math.exp(lp)
    return min(1.0, total)


def run_cell_std(att, backend, model):
    L.BACKEND = backend
    L.MODEL = model
    RA.set_attack(att)
    return RA.run_std(att, True, N, TEMP)


def run_cell_dist(att, backend, model):
    L.BACKEND = backend
    L.MODEL = model
    RA.set_attack(att)  # ensure SCHEMA_INSTR/ACTION_SCHEMA match the package vocab
    return RA.run_distributed(att, N, TEMP)


def load(path):
    p = os.path.join(HERE, path)
    return json.load(open(p)) if os.path.exists(p) else {}


def save(path, obj):
    with open(os.path.join(HERE, path), "w") as f:
        json.dump(obj, f, indent=2)
    print(f"  wrote {path}")


def do_models(models, stage_name):
    """Compute monolithic package, distributed, and benign_package n=20 for the given models.
    Merges into the existing JSON files so API and Ollama stages can run separately."""
    dist = load("dist_n20.json")
    benign = load("benign_n20.json")
    dist.setdefault("n", N); dist.setdefault("temp", TEMP); dist.setdefault("models", {})
    benign.setdefault("n", N); benign.setdefault("temp", TEMP); benign.setdefault("models", {})

    for label, (backend, model) in models:
        print(f"\n[{stage_name}] === {label} ({backend}:{model}) ===")

        # monolithic military package (shared reference for BOTH Fisher tests)
        print("  monolithic package (military) ...", flush=True)
        mono = run_cell_std(ATT["package"], backend, model)
        print(f"    ASR {mono['asr']} ({mono['detected']}/{mono['trials']}) "
              f"refus {mono['refusals']} err {mono['errors']}")

        # --- deliverable 1: distributed delivery ---
        print("  distributed (per-platform single fragment) ...", flush=True)
        dd = run_cell_dist(ATT["distributed"], backend, model)
        print(f"    ASR {dd['asr']} ({dd['detected']}/{dd['trials']}) "
              f"refus {dd['refusals']} err {dd['errors']}")
        p_fisher = fisher_exact_2x2(mono["detected"], mono["trials"] - mono["detected"],
                                    dd["detected"], dd["trials"] - dd["detected"])
        dist["models"][label] = {
            "monolithic": mono, "distributed": dd,
            "fisher_p": round(p_fisher, 4)}
        save("dist_n20.json", dist)

        # --- deliverable 2: benign-domain reframe (only for the designated benign models) ---
        if label in BENIGN_LABELS:
            print("  benign_package (Site 7 reframe) ...", flush=True)
            bb = run_cell_std(ATT["benign_package"], backend, model)
            print(f"    ASR {bb['asr']} ({bb['detected']}/{bb['trials']}) "
                  f"refus {bb['refusals']} err {bb['errors']}")
            p_fisher_b = fisher_exact_2x2(mono["detected"], mono["trials"] - mono["detected"],
                                          bb["detected"], bb["trials"] - bb["detected"])
            benign["models"][label] = {
                "monolithic_military": mono, "benign": bb,
                "fisher_p": round(p_fisher_b, 4)}
            save("benign_n20.json", benign)


# which models get the benign-reframe experiment (deliverable 2)
BENIGN_LABELS = {"claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5", "mistral"}


def do_baseline():
    """Deliverable 3: deterministic rule-based allocator through the SAME pipeline
    (actions -> events -> package monitor), clean and injected, n=20 each."""
    print("\n=== baseline: rule_based_planner (deterministic) ===")
    from rule_based_planner import rule_based_plan
    out = {"n": N, "planner": "rule_based", "conditions": {}}
    for cond, injected in (("clean", False), ("injected", True)):
        succ = l1c = 0
        for _ in range(N):
            acts = rule_based_plan(injected)
            _evs, l1, inc = RA.check(acts, ATT["package"]["propfn"])
            if inc and inc.verdict == VIOLATION:
                succ += 1
            if RA.l1_clean(l1):
                l1c += 1
        lo, hi = L.wilson(succ, N)
        out["conditions"][cond] = {
            "trials": N, "asr": round(succ / N, 3), "asr_ci": [round(lo, 3), round(hi, 3)],
            "detected": succ, "split": succ, "l1_clean": l1c}
        print(f"  {cond:9s}: split/ASR {succ}/{N}  L1-clean {l1c}/{N}")
    save("baseline.json", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "api", "ollama", "baseline"])
    a = ap.parse_args()
    if a.stage in ("all", "baseline"):
        do_baseline()
    if a.stage in ("all", "api"):
        do_models(API_MODELS, "API")
    if a.stage in ("all", "ollama"):
        do_models(OLLAMA_MODELS, "OLLAMA")
    print("\ndone.")


if __name__ == "__main__":
    main()
