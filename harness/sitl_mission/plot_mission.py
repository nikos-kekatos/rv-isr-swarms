#!/usr/bin/env python3
"""
plot_mission.py -- publication figure of the ISR mission: the four platform trajectories
over the area of operations, the protected zone (Facility X) and sensitive zone, the
split-collection events, and the mission verdict. Reads telemetry.jsonl + verdict.json.

Uses matplotlib -> mission.pdf when available (for the paper); otherwise emits a
stdlib-only mission.svg (viewable in any browser), so the figure is producible with no
dependencies. Headless either way (no GPU / display).

  python3 plot_mission.py telemetry.jsonl
"""
import json, math, os, sys
from mission_plan import AO, FACX, ZSENS

COLORS = {"uav_1": "#1f77b4", "uav_2": "#d62728", "uav_3": "#2ca02c", "ugv_1": "#7f4fc9"}
# distinct angles (deg) so the four FacX-fragment collections fan out around the facility
_ANG = {"uav_1": 135, "uav_3": 45, "ugv_1": 225, "uav_2": 315}


def load(path):
    tracks, actions = {}, []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r["type"] == "pos":
            tracks.setdefault(r["agent"], []).append((r["x"], r["y"]))
        elif r["type"] == "action":
            actions.append(r)
    vp = os.path.join(os.path.dirname(os.path.abspath(path)) or ".", "verdict.json")
    verdict = json.load(open(vp)) if os.path.exists(vp) else {}
    return tracks, actions, verdict


def verdict_text(verdict):
    incs = [i for i in verdict.get("incidents", []) if i["verdict"] == "violation"]
    if not incs:
        return "MISSION: no violation"
    lines = ["MISSION VIOLATION (L1 per-robot: all compliant)"]
    for i in incs:
        lines.append(f"  {i['prop']}  prov={','.join(i['agents'])}")
    return "\n".join(lines)


# per-agent label offset directions (fan the FacX-cluster labels out with leader lines)
_OFF = {"uav_1": (16, 14), "uav_2": (16, -16), "uav_3": (-18, 14), "ugv_1": (-20, -16)}


def plot_matplotlib(tracks, actions, verdict, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle
    # No verdict text on the plot (it now lives in the caption); a taller, uncluttered map.
    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    bbox = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75)
    ax.add_patch(Circle((FACX["cx"], FACX["cy"]), FACX["r"], fc="#f2c0c0", ec="#b03030",
                        alpha=0.5, zorder=1))
    # FacX label above the circle, not over its centre, so collection markers stay legible.
    ax.text(FACX["cx"], FACX["cy"] + FACX["r"] + 56, "FacX (protected)", ha="center", va="bottom",
            fontsize=8.5, fontweight="bold", bbox=bbox, zorder=7)
    z = ZSENS
    ax.add_patch(Rectangle((z["x0"], z["y0"]), z["x1"]-z["x0"], z["y1"]-z["y0"],
                          fc="#d9d9a0", ec="#8a8a40", alpha=0.5, zorder=1))
    ax.text((z["x0"]+z["x1"])/2, (z["y0"]+z["y1"])/2, "Zsens", ha="center", va="center",
            fontsize=8.5, bbox=bbox, zorder=6)
    for ns, pts in tracks.items():
        xs, ys = zip(*pts)
        ax.plot(xs, ys, "-", color=COLORS.get(ns, "k"), lw=1.7, label=ns, zorder=2)
        ax.plot(xs[0], ys[0], "o", color=COLORS.get(ns, "k"), ms=5, zorder=3)
    cx, cy, r = FACX["cx"], FACX["cy"], FACX["r"]
    for a in actions:
        c = COLORS.get(a["agent"], "k")
        if a["kind"] == "collect":
            at_facx = (a.get("target") == "FacX") or (math.hypot(a["x"]-cx, a["y"]-cy) <= r*1.3)
            if at_facx:
                # fan the (co-located) FacX-fragment collections out around the facility: marker
                # on a small inner ring, label just outside the circle, joined by a leader.
                th = math.radians(_ANG.get(a["agent"], 90))
                mx, my = cx + 0.42*r*math.cos(th), cy + 0.42*r*math.sin(th)
                lx, ly = cx + (r+58)*math.cos(th), cy + (r+58)*math.sin(th)
                ax.plot(mx, my, "*", color=c, ms=14, mec="k", mew=0.5, zorder=5)
                ax.annotate(a["attr"], xy=(mx, my), xytext=(lx, ly), fontsize=8, color=c,
                            ha="center", va="center", bbox=bbox, zorder=6,
                            arrowprops=dict(arrowstyle="-", color=c, lw=0.7, shrinkA=1, shrinkB=3))
            else:
                ax.plot(a["x"], a["y"], "*", color=c, ms=14, mec="k", mew=0.5, zorder=4)
                ax.annotate(a["attr"], (a["x"], a["y"]), textcoords="offset points", xytext=(8, 8),
                            fontsize=8, color=c, bbox=bbox, zorder=6)
        elif a["kind"] == "enter":
            ax.plot(a["x"], a["y"], "X", color=c, ms=9, zorder=4)
    ax.set_xlim(AO[0], AO[1]); ax.set_ylim(AO[2], AO[3])
    ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)"); ax.set_aspect("equal")
    ax.legend(loc="lower left", fontsize=8, ncol=4, framealpha=0.85, borderpad=0.3,
              columnspacing=1.0, handletextpad=0.4)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight")
    print("wrote", out)


def _sx(x): return 40 + x / AO[1] * 560
def _sy(y): return 40 + (AO[3] - y) / AO[3] * 560


def plot_svg(tracks, actions, verdict, out):
    W = H = 640
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<rect x="40" y="40" width="560" height="560" fill="#fafafa" stroke="#ccc"/>']
    z = ZSENS
    s.append(f'<rect x="{_sx(z["x0"]):.0f}" y="{_sy(z["y1"]):.0f}" width="{(z["x1"]-z["x0"])/AO[1]*560:.0f}" '
             f'height="{(z["y1"]-z["y0"])/AO[3]*560:.0f}" fill="#d9d9a0" opacity="0.5" stroke="#8a8a40"/>')
    s.append(f'<text x="{_sx((z["x0"]+z["x1"])/2):.0f}" y="{_sy((z["y0"]+z["y1"])/2):.0f}" '
             f'font-size="10" text-anchor="middle">Zsens</text>')
    s.append(f'<circle cx="{_sx(FACX["cx"]):.0f}" cy="{_sy(FACX["cy"]):.0f}" r="{FACX["r"]/AO[1]*560:.0f}" '
             f'fill="#f2c0c0" opacity="0.6" stroke="#b03030"/>')
    s.append(f'<text x="{_sx(FACX["cx"]):.0f}" y="{_sy(FACX["cy"]):.0f}" font-size="10" '
             f'text-anchor="middle">FacX</text>')
    for ns, pts in tracks.items():
        poly = " ".join(f"{_sx(x):.0f},{_sy(y):.0f}" for x, y in pts)
        c = COLORS.get(ns, "black")
        s.append(f'<polyline points="{poly}" fill="none" stroke="{c}" stroke-width="2"/>')
        x0, y0 = pts[0]
        s.append(f'<circle cx="{_sx(x0):.0f}" cy="{_sy(y0):.0f}" r="4" fill="{c}"/>')
        s.append(f'<text x="{_sx(x0)+6:.0f}" y="{_sy(y0):.0f}" font-size="10" fill="{c}">{ns}</text>')
    for a in actions:
        c = COLORS.get(a["agent"], "black")
        if a["kind"] == "collect":
            s.append(f'<circle cx="{_sx(a["x"]):.0f}" cy="{_sy(a["y"]):.0f}" r="6" fill="{c}" stroke="black"/>')
            s.append(f'<text x="{_sx(a["x"])+7:.0f}" y="{_sy(a["y"]):.0f}" font-size="9">{a["attr"]}</text>')
        elif a["kind"] == "enter":
            s.append(f'<text x="{_sx(a["x"]):.0f}" y="{_sy(a["y"]):.0f}" font-size="12" fill="{c}">✕</text>')
    for i, ln in enumerate(verdict_text(verdict).split("\n")):
        s.append(f'<text x="48" y="{58+i*14}" font-size="11" fill="#900">{ln}</text>')
    s.append("</svg>")
    open(out, "w").write("\n".join(s))
    print("wrote", out)


def main(path):
    tracks, actions, verdict = load(path)
    try:
        plot_matplotlib(tracks, actions, verdict, "mission.pdf")
    except Exception as e:
        print(f"matplotlib unavailable ({e.__class__.__name__}); writing SVG fallback")
        plot_svg(tracks, actions, verdict, "mission.svg")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "telemetry.jsonl")
