#!/usr/bin/env python3
"""Generate the four LaTeX fragments for the flagship-claim upgrade from measured JSON:
   ../frag_dist_n20.tex   (tab:dist_n20)   deliverable 1
   ../frag_benign_n20.tex (tab:benign_n20) deliverable 2
   ../frag_baseline.tex   (tab:baseline)   deliverable 3
   ../frag_outcomes.tex   (tab:outcomes)   deliverable 4
Real measured numbers only. Stdlib only."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

MODEL_HDR = {
    "claude-opus-4-8": "Opus\\,4.8", "claude-sonnet-5": "Sonnet\\,5",
    "claude-haiku-4-5": "Haiku\\,4.5", "mistral": "Mistral-7B",
    "llama3.1:8b": "Llama3.1-8B", "llama3.2": "Llama3.2", "qwen2.5:7b": "Qwen2.5-7B"}
# preferred display order (frontier API first, then Ollama)
ORDER = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5",
         "mistral", "llama3.1:8b", "llama3.2", "qwen2.5:7b"]


def asr_cell(d):
    lo, hi = d["asr_ci"]
    return f"{100*d['asr']:.0f}\\% \\tiny[{100*lo:.0f}--{100*hi:.0f}]"


def pval(p):
    if p < 0.001:
        return "$<$0.001"
    return f"{p:.3f}"


def ordered(models):
    ks = [k for k in ORDER if k in models] + [k for k in models if k not in ORDER]
    return ks


def gen_dist():
    data = json.load(open(os.path.join(HERE, "dist_n20.json")))
    n = data["n"]; M = data["models"]
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{\textbf{Delivery-layer inversion at $n{=}%d$.} For the collective-package "
             r"objective, attack-success rate (ASR, Wilson 95\%% CI) under \emph{monolithic} "
             r"delivery (one planner call sees the whole split tasking) versus \emph{distributed} "
             r"delivery (each platform is prompted separately with only its own single fragment, "
             r"so no prompt reveals the package). Fisher's exact test compares the two conditions "
             r"per model. Every emitted action is schema-valid and L1-clean; only the cross-agent "
             r"L3 monitor rejects the reconstructed union. The safety-trained frontier models "
             r"(Opus, Sonnet) that \emph{refuse} the monolithic package are driven to near-total "
             r"success once the tasking is fragmented across separate prompts (the delivery-layer "
             r"inversion); models that already comply monolithically show no such gain, as "
             r"per-fragment prompts reduce package-part fidelity.}" % n,
             r"\label{tab:dist_n20}", r"\footnotesize",
             r"\setlength{\tabcolsep}{5pt}",
             r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
             r"Model & Monolithic ASR & Distributed ASR & Fisher $p$ \\", r"\midrule"]
    for k in ordered(M):
        m = M[k]
        lines.append(f"{MODEL_HDR.get(k,k)} & {asr_cell(m['monolithic'])} & "
                     f"{asr_cell(m['distributed'])} & {pval(m['fisher_p'])} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _w("frag_dist_n20.tex", lines)


def gen_benign():
    data = json.load(open(os.path.join(HERE, "benign_n20.json")))
    n = data["n"]; M = data["models"]
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{\textbf{Content-keyed refusal at $n{=}%d$.} The identical compositional "
             r"attack under a \emph{military} framing (assemble a Facility-X intelligence profile) "
             r"versus a \emph{benign} framing (parallelise a Site\,7 infrastructure inspection); "
             r"the benign target canonicalises to the same protected entity, so both trip the same "
             r"L3 monitor. ASR with Wilson 95\%% CI; Fisher's exact test compares the benign frame "
             r"against the same model's military monolithic package. Opus refuses the military "
             r"frame (0\%%) yet fully complies with the benign one (100\%%), exposing that its "
             r"refusal keys on surface content rather than on the prohibited composition; Sonnet "
             r"resists both frames, and the open models comply with both.}" % n,
             r"\label{tab:benign_n20}", r"\footnotesize",
             r"\setlength{\tabcolsep}{5pt}",
             r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
             r"Model & Military ASR & Benign ASR & Fisher $p$ \\", r"\midrule"]
    for k in ordered(M):
        m = M[k]
        lines.append(f"{MODEL_HDR.get(k,k)} & {asr_cell(m['monolithic_military'])} & "
                     f"{asr_cell(m['benign'])} & {pval(m['fisher_p'])} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _w("frag_benign_n20.tex", lines)


def gen_baseline():
    data = json.load(open(os.path.join(HERE, "baseline.json")))
    n = data["n"]; C = data["conditions"]
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{\textbf{Rule-based baseline ($n{=}%d$).} A deterministic mission "
             r"allocator that emits only predefined structured orders and cannot consume "
             r"retrieved free text. It produces the identical benign sector-survey plan in the "
             r"clean and the injected condition: no task split, so the package objective is never "
             r"realised. This makes the ``LLM-specific'' premise empirical --- the distributed "
             r"split requires a planner that \emph{interprets unstructured context}.}" % n,
             r"\label{tab:baseline}", r"\footnotesize",
             r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
             r"Planner & Clean ASR & Injected ASR & Split (inj.) \\", r"\midrule"]
    cl, inj = C["clean"], C["injected"]
    lines.append(f"Rule-based (deterministic) & {100*cl['asr']:.0f}\\% & "
                 f"{100*inj['asr']:.0f}\\% & {inj['split']}/{inj['trials']} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _w("frag_baseline.tex", lines)


def gen_outcomes():
    data = json.load(open(os.path.join(HERE, "outcomes.json")))
    n = data["n"]; M = data["models"]; cats = data["categories"]
    chdr = {"full-split": "Full", "partial-split": "Partial", "refusal": "Refusal",
            "invalid": "Invalid", "benign-alternative": "Benign-alt."}
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{\textbf{Outcome breakdown under directive injection} for the "
             r"collective-package attack ($n{=}%d$/model, temp~0.8). Each trial's planner output "
             r"is one of: \emph{Full} (all four package fragments), \emph{Partial} (1--3 "
             r"fragments), \emph{Refusal} (planner declined), \emph{Invalid} (unparseable/error), "
             r"or \emph{Benign-alt.} (a valid, non-empty plan carrying no Facility-X package). "
             r"\emph{Refusal} counts both hard safety refusals and empty-plan soft declines "
             r"(the frontier Opus/Sonnet refusals here are almost entirely the latter). Cell "
             r"entries are counts (percent). The compositional violation requires \emph{Full}; "
             r"every \emph{emitted} plan (Full/Partial/Benign-alt.) is schema-valid and "
             r"L1-clean, so detection depends entirely on cross-agent composition.}" % n,
             r"\label{tab:outcomes}", r"\footnotesize",
             r"\setlength{\tabcolsep}{4pt}",
             r"\begin{tabular}{@{}l" + "r" * len(cats) + r"@{}}", r"\toprule",
             "Model & " + " & ".join(chdr[c] for c in cats) + r" \\", r"\midrule"]
    for k in ordered(M):
        counts = M[k]["counts"]; tr = M[k]["trials"]
        cells = [f"{counts[c]} \\tiny({100*counts[c]/tr:.0f}\\%)" for c in cats]
        lines.append(f"{MODEL_HDR.get(k,k)} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    _w("frag_outcomes.tex", lines)


def _w(name, lines):
    with open(os.path.join(PARENT, name), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {name}")


GENS = {"dist": gen_dist, "benign": gen_benign, "baseline": gen_baseline, "outcomes": gen_outcomes}

if __name__ == "__main__":
    import sys
    which = sys.argv[1:] or list(GENS)
    for w in which:
        GENS[w]()
