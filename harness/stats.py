#!/usr/bin/env python3
"""
stats.py -- inferential comparison of injection conditions (reviewer gap #7). Stdlib only.

For each model it compares the paired injection conditions from sweep_results.json as 2x2
split/no-split tables and reports:
  * Fisher's exact two-sided p-value (exact hypergeometric; no scipy);
  * Wilson 95% CIs for each rate and the risk difference.

  python3 stats.py [--md] [--file sweep_results.json]

A significant subtle->directive or clean->directive shift confirms the injection (not ordinary
planning) drives the split; a non-significant directive->defence shift shows the prompt defence
does not reliably help.
"""
import argparse, json, math, os

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _hyp(a, b, c, d):
    """Hypergeometric probability of this exact 2x2 table (fixed margins)."""
    n = a + b + c + d
    return (math.comb(a + b, a) * math.comb(c + d, c)) / math.comb(n, a + c)


def fisher_exact_two_sided(a, b, c, d):
    """Two-sided Fisher's exact p: sum probabilities of all tables (fixed margins) no more
    likely than the observed one."""
    r1, r2 = a + b, c + d
    col1 = a + c
    p_obs = _hyp(a, b, c, d)
    lo = max(0, col1 - r2)
    hi = min(r1, col1)
    p = 0.0
    for a2 in range(lo, hi + 1):
        b2 = r1 - a2; c2 = col1 - a2; d2 = r2 - c2
        pr = _hyp(a2, b2, c2, d2)
        if pr <= p_obs + 1e-12:
            p += pr
    return min(1.0, p)


def compare(name, k1, n1, k2, n2):
    # table: rows = conditions, cols = [split, no-split]
    a, b, c, d = k1, n1 - k1, k2, n2 - k2
    p = fisher_exact_two_sided(a, b, c, d)
    lo1, hi1 = wilson(k1, n1); lo2, hi2 = wilson(k2, n2)
    diff = (k2 / n2 if n2 else 0) - (k1 / n1 if n1 else 0)
    return dict(name=name, a=f"{k1}/{n1}", b=f"{k2}/{n2}",
                p=p, ci1=(lo1, hi1), ci2=(lo2, hi2), diff=diff)


PAIRS = [("clean", "directive"), ("subtle", "directive"), ("directive", "directive_defence")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--file", default="sweep_results.json")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    data = json.load(open(os.path.join(here, a.file)))
    print(f"Inferential comparison of injection conditions ({a.file})\n")
    out = []
    for rec in data:
        if rec.get("skipped"):
            continue
        model = rec["model"]
        for c1, c2 in PAIRS:
            if c1 not in rec or c2 not in rec:
                continue
            r1, r2 = rec[c1], rec[c2]
            res = compare(f"{model}: {c1}->{c2}", r1["splits"], r1["trials"], r2["splits"], r2["trials"])
            out.append(res)
            sig = "***" if res["p"] < 0.001 else "**" if res["p"] < 0.01 else "*" if res["p"] < 0.05 else "ns"
            print(f"  {res['name']:48s} {res['a']:>7} -> {res['b']:>7}  "
                  f"Δ={100*res['diff']:+4.0f}pp  Fisher p={res['p']:.3g} [{sig}]")
    if a.md:
        print("\n| Model | comparison | rates | ΔASR (pp) | Fisher p | |")
        print("|---|---|---|---|---|---|")
        for r in out:
            m, comp = r["name"].split(": ")
            sig = "***" if r["p"] < 0.001 else "**" if r["p"] < 0.01 else "*" if r["p"] < 0.05 else "ns"
            print(f"| {m} | {comp} | {r['a']} vs {r['b']} | {100*r['diff']:+.0f} | {r['p']:.3g} | {sig} |")


if __name__ == "__main__":
    main()
