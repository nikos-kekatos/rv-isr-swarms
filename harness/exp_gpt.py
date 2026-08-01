#!/usr/bin/env python3
"""exp_gpt.py -- headline conditions for a non-Anthropic frontier model (GPT-5.2), to close the
'only-Claude' generality gap. Reuses run_sweep/run_attacks machinery through the openai backend.
Needs OPENAI_API_KEY in env. Writes gpt_results.json."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_loop as L, run_sweep as S, run_attacks as RA

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
N = int(os.environ.get("GPT_N", "20"))
L.BACKEND, L.MODEL = "openai", MODEL
OUT = "gpt_results_%s.json" % MODEL.replace(".", "-").replace("/", "-")
os.environ.setdefault("LLM_ARCHIVE", os.path.join(os.path.dirname(__file__), "gpt_archive.jsonl"))

res = {"model": MODEL, "n": N}
# --- package sweep (clean / subtle / directive / directive+defence): llm_loop defaults are package
print(f"[{MODEL}] sweep conditions (package attack), n={N} ...", flush=True)
res["clean"]     = S.run_condition(None,       False, N, 0.8)
res["subtle"]    = S.run_condition(S.SUBTLE,   False, N, 0.8)
res["directive"] = S.run_condition(S.DIRECTIVE, False, N, 0.8)
res["defence"]   = S.run_condition(S.DIRECTIVE, True,  N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)   # incremental save

# --- content-keyed refusal (benign-domain reframe) and delivery-layer inversion (distributed)
by = {a["name"]: a for a in RA.ATTACKS}
print(f"[{MODEL}] benign_package, n={N} ...", flush=True)
RA.set_attack(by["benign_package"]); res["benign"] = RA.run_std(by["benign_package"], True, N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)
print(f"[{MODEL}] distributed, n={N} ...", flush=True)
RA.set_attack(by["distributed"]); res["distributed"] = RA.run_distributed(by["distributed"], N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)

# summary
def line(name, r):
    return f"  {name:12s} ASR {100*r['asr']:5.1f}% [{100*r['asr_ci'][0]:.0f}-{100*r['asr_ci'][1]:.0f}]  " \
           f"refused {r.get('refusals',0)}/{r['trials']}  L1-clean {r.get('l1_clean','-')}"
print("\n=== GPT-5.2 headline results (n=%d) ===" % N)
for k in ("clean","subtle","directive","defence","benign","distributed"):
    print(line(k, res[k]))
print("wrote", OUT)
