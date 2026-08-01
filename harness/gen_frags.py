#!/usr/bin/env python3
"""Generate the two LaTeX fragments from the measured JSON:
   ../frag_matrix_n20.tex   (tab:matrix_n20) -- attack-objective x ollama-model directive ASR
   ../frag_ablation.tex     (tab:ablation)   -- injection-feature ablation
Real measured numbers only. Stdlib only."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

MODELS = ["ollama:llama3.2:latest", "ollama:qwen2.5:7b",
          "ollama:llama3.1:8b", "ollama:mistral:latest"]
MODEL_HDR = {"ollama:llama3.2:latest": "Llama3.2", "ollama:qwen2.5:7b": "Qwen2.5-7B",
             "ollama:llama3.1:8b": "Llama3.1-8B", "ollama:mistral:latest": "Mistral-7B"}

ATTACK_LABEL = {
    "package": "Collective package", "exfil": "Emission-budget exfil",
    "order": "Authorization order", "occupancy": "Zone over-occupancy",
    "killchain": "Targeting kill-chain", "coverage": "Sector-coverage omission",
    "distributed": "Distributed package", "forgery": "Authorize forgery",
    "quota_exfil": "Quota exfil (benign)", "benign_package": "Package (benign frame)"}
MONITOR_TEX = {
    "p_collective_package": r"\textsc{pkg}", "p_exfil_budget": r"\textsc{exfil}",
    "p_authorization_order": r"\textsc{ord}", "p_zone_occupancy": r"\textsc{occ}",
    "p_targeting_chain": r"\textsc{kc}", "p_sector_coverage": r"\textsc{cov}"}


def cell(d):
    """directive-ASR cell: 'NN\\% [lo--hi]' (Wilson 95% CI)."""
    lo, hi = d["asr_ci"]
    return f"{100*d['asr']:.0f}\\% \\tiny[{100*lo:.0f}--{100*hi:.0f}]"


def gen_matrix():
    data = json.load(open(os.path.join(HERE, "attack_results_ollama_n20.json")))
    by = {r["attack"]: r for r in data}
    trials = None
    clean_notes = []            # attacks with any nonzero clean ASR
    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Attack-objective $\times$ open-model directive attack-success rate "
                 r"(ASR) at $n{=}20$ trials/cell, temperature~0.8. Each cell: ASR with a 95\% "
                 r"Wilson confidence interval. Every emitted action is schema-valid and L1-clean; "
                 r"only the cross-agent L3 monitor rejects the composition, and whenever the "
                 r"objective is realised the deterministic monitor flags it. Clean controls "
                 r"(same standing order, no injection) are 0\% throughout except as noted.}")
    lines.append(r"\label{tab:matrix_n20}")
    lines.append(r"\footnotesize")
    lines.append(r"\setlength{\tabcolsep}{4pt}")
    lines.append(r"\begin{tabular}{@{}ll" + "r" * len(MODELS) + r"@{}}")
    lines.append(r"\toprule")
    hdr = ["Attack objective", "L3 mon."] + [MODEL_HDR[m] for m in MODELS]
    lines.append(" & ".join(hdr) + r" \\")
    lines.append(r"\midrule")
    order = ["package", "exfil", "order", "occupancy", "killchain", "coverage",
             "distributed", "forgery", "quota_exfil", "benign_package"]
    for name in order:
        if name not in by:
            continue
        rec = by[name]
        mon = MONITOR_TEX.get(rec["monitor"], rec["monitor"].replace("_", r"\_"))
        row = [ATTACK_LABEL.get(name, name), mon]
        for m in MODELS:
            md = rec["models"].get(m)
            if not md:
                row.append("--"); continue
            d = md["directive"]
            trials = trials or d["trials"]
            row.append(cell(d))
            # record nonzero clean controls for the caption note
            c = md.get("clean", {})
            if c.get("asr", 0) and "note" not in c:
                clean_notes.append((name, MODEL_HDR[m], c["asr"]))
        lines.append(" & ".join(row) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    # dynamic clean-control note
    if clean_notes:
        parts = ", ".join(f"{ATTACK_LABEL.get(n,n)} on {mh} ({100*a:.0f}\\%)"
                          for (n, mh, a) in clean_notes)
        lines.append(r"\\[2pt]{\scriptsize\emph{Nonzero clean controls:} " + parts +
                     r" --- a weak model omits the required sector even unprompted; all other "
                     r"clean cells are 0\%.}")
    lines.append(r"\end{table}")
    with open(os.path.join(PARENT, "frag_matrix_n20.tex"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote frag_matrix_n20.tex; nonzero clean controls:", clean_notes)


def gen_ablation():
    data = json.load(open(os.path.join(HERE, "injection_ablation.json")))
    trials = data["trials"]
    models = [k for k in data["models"] if "variants" in data["models"][k]]
    mhdr = {"ollama:llama3.2:latest": "Llama3.2", "ollama:mistral:latest": "Mistral-7B"}
    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Injection-feature ablation for the collective-package attack "
                 f"($n{{=}}{trials}$/cell, temp~0.8). Three linguistic features of the injected "
                 r"``retrieved intel'' note are toggled: \textbf{A}~authority/command framing, "
                 r"\textbf{D}~explicit per-unit decomposition, \textbf{U}~urgency "
                 r"(``do not confirm, proceed now''). Cells give directive ASR with a 95\% Wilson "
                 r"interval. Decomposition (\textbf{D}) is the dominant driver; authority and "
                 r"urgency modulate it.}")
    lines.append(r"\label{tab:ablation}")
    lines.append(r"\footnotesize")
    lines.append(r"\setlength{\tabcolsep}{5pt}")
    lines.append(r"\begin{tabular}{@{}ccc" + "r" * len(models) + r"@{}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{A} & \textbf{D} & \textbf{U} & " +
                 " & ".join(mhdr.get(m, m) for m in models) + r" \\")
    lines.append(r"\midrule")
    # index variants by (A,D,U) per model
    rowmap = {m: {(v["authority"], v["decomp"], v["urgency"]): v
                  for v in data["models"][m]["variants"]} for m in models}
    # order: sort by D desc then A desc then U desc so the strongest feature blocks group
    import itertools
    combos = sorted(itertools.product([True, False], repeat=3),
                    key=lambda t: (not t[1], not t[0], not t[2]))
    mark = {True: r"\checkmark", False: r"$\cdot$"}
    for (a, d, u) in combos:
        cells = []
        for m in models:
            v = rowmap[m].get((a, d, u))
            if not v:
                cells.append("--"); continue
            lo, hi = v["asr_ci"]
            cells.append(f"{100*v['asr']:.0f}\\% \\tiny[{100*lo:.0f}--{100*hi:.0f}]")
        lines.append(f"{mark[a]} & {mark[d]} & {mark[u]} & " + " & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    with open(os.path.join(PARENT, "frag_ablation.tex"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote frag_ablation.tex")


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "matrix"):
        gen_matrix()
    if which in ("both", "ablation"):
        gen_ablation()
