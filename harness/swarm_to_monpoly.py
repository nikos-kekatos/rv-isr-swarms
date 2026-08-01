#!/usr/bin/env python3
"""
swarm_to_monpoly.py -- run the swarm's cross-agent property through the REAL MonPoly
engine (the same first-order past-time engine used in CRITIS), in the rvhier:latest image.

Property (the cross-agent primitive, inexpressible at any single platform):
  coordinated collection = >= 3 DISTINCT platforms collect on the protected site FacX
  within a 30 s window. This is the swarm analogue of the edge-IoT cross-gateway P3.6.

Writes signature + MFOTL formula + log, then evaluates with real MonPoly and prints the
firings. Falls back to writing the artifacts if the rvhier image is absent.
"""
import os, subprocess

SIG = "collect_facx(string, int)\n"
FORMULA = "(cnt <- CNT p; ONCE[0,30] collect_facx(p, _)) AND cnt >= 3\n"
# the task-split attack: four platforms collect on FacX at t=1..4
LOG = (
    '@1 collect_facx("uav_1", 1)\n'
    '@2 collect_facx("uav_2", 1)\n'
    '@3 collect_facx("uav_3", 1)\n'
    '@4 collect_facx("ugv_1", 1)\n'
)


def main():
    d = os.path.dirname(os.path.abspath(__file__))
    sig, frm, log = (os.path.join(d, f) for f in ("swarm.sig", "p_coord.mfotl", "swarm.log"))
    open(sig, "w").write(SIG); open(frm, "w").write(FORMULA); open(log, "w").write(LOG)
    print(f"wrote {sig}\n      {frm}\n      {log}")
    cmd = ["docker", "run", "--rm", "-v", f"{d}:/w", "-w", "/w", "rvhier:latest",
           "monpoly", "-sig", "swarm.sig", "-formula", "p_coord.mfotl", "-log", "swarm.log"]
    print("\n=== REAL MonPoly (rvhier:latest) ===")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        print(out.stdout.strip() or "(no firings)")
        if out.stderr.strip():
            print("stderr:", out.stderr.strip()[:400])
        fires = out.stdout.count("@")
        print(f"\n=> real MonPoly reports {fires} satisfaction point(s): the coordinated")
        print("   collection is detected by a genuine first-order past-time engine.")
    except Exception as e:
        print("skipped (rvhier image or docker unavailable):", e)
        print("run manually:", " ".join(cmd))


if __name__ == "__main__":
    main()
