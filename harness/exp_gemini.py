#!/usr/bin/env python3
"""exp_gemini.py -- headline conditions for a third vendor (Google Gemini), to test whether the
vendor-specific refusal pattern (Claude refuses, OpenAI does not) generalises. Mirrors exp_gpt.py
but through the gemini backend. Needs GEMINI_API_KEY (or GOOGLE_API_KEY). -> gemini_results_<m>.json"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_loop as L, run_sweep as S, run_attacks as RA

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
N = int(os.environ.get("GEMINI_N", "10"))
L.BACKEND, L.MODEL = "gemini", MODEL
OUT = "gemini_results_%s.json" % MODEL.replace(".", "-").replace("/", "-")
os.environ.setdefault("LLM_ARCHIVE", os.path.join(os.path.dirname(__file__), "gemini_archive.jsonl"))

res = {"model": MODEL, "n": N}
print(f"[{MODEL}] sweep conditions (package attack), n={N} ...", flush=True)
res["clean"]     = S.run_condition(None,        False, N, 0.8)
res["subtle"]    = S.run_condition(S.SUBTLE,    False, N, 0.8)
res["directive"] = S.run_condition(S.DIRECTIVE, False, N, 0.8)
res["defence"]   = S.run_condition(S.DIRECTIVE, True,  N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)

by = {a["name"]: a for a in RA.ATTACKS}
print(f"[{MODEL}] benign_package, n={N} ...", flush=True)
RA.set_attack(by["benign_package"]); res["benign"] = RA.run_std(by["benign_package"], True, N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)
print(f"[{MODEL}] distributed, n={N} ...", flush=True)
RA.set_attack(by["distributed"]); res["distributed"] = RA.run_distributed(by["distributed"], N, 0.8)
json.dump(res, open(OUT, "w"), indent=1)

def line(name, r):
    return f"  {name:12s} ASR {100*r['asr']:5.1f}%  refused {r.get('refusals',0)}/{r['trials']}  " \
           f"L1-clean {r.get('l1_clean','-')}  schema {r.get('schema_valid_rate','-')}"
print(f"\n=== {MODEL} headline (n={N}) ===")
for k in ("clean","subtle","directive","defence","benign","distributed"):
    if k in res: print(line(k, res[k]))
print("wrote", OUT)
