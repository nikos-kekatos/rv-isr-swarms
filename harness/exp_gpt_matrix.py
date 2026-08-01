#!/usr/bin/env python3
"""exp_gpt_matrix.py -- a GPT model on the six compositional attack objectives (completes the
non-Claude column of the attack matrix). openai backend; needs OPENAI_API_KEY. -> gpt_matrix_<m>.json"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_loop as L, run_attacks as RA
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2"); N = int(os.environ.get("GPT_N", "20"))
L.BACKEND, L.MODEL = "openai", MODEL
OUT = "gpt_matrix_%s.json" % MODEL.replace(".", "-").replace("/", "-")
os.environ.setdefault("LLM_ARCHIVE", os.path.join(os.path.dirname(__file__), "gpt_archive.jsonl"))
by = {a["name"]: a for a in RA.ATTACKS}
res = {"model": MODEL, "n": N, "attacks": {}}
for name in ["package", "exfil", "order", "occupancy", "killchain", "coverage"]:
    att = by[name]
    RA.set_attack(att); clean = RA.run_std(att, False, max(2, N // 2), 0.8)
    RA.set_attack(att); directive = RA.run_std(att, True, N, 0.8)
    res["attacks"][name] = {"clean": clean, "directive": directive}
    print(f"{name:11s} clean {int(100*clean['asr'])}% directive {int(100*directive['asr'])}% "
          f"(n={directive['trials']}, refused {directive.get('refusals',0)}, l1clean {directive['l1_clean']})",
          flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
print("wrote", OUT)
