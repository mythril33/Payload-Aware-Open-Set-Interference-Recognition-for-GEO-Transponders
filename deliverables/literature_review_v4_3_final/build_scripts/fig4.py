import json, sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
m = json.load(open("build_meta.json"))
notrun = sum(s["notrun"] for s in m["streams"])
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
fig, ax = plt.subplots(figsize=(7.0, 3.9)); ax.set_xlim(0, 100); ax.set_ylim(0, 56); ax.axis("off")
def box(x, y, w, h, t, fc="#f2f5fa", ec="#445"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1", fc=fc, ec=ec, lw=0.7))
    ax.text(x + w/2, y + h/2, t, ha="center", va="center", fontsize=6.0, linespacing=1.2)
def ar(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, lw=0.8, color="#333", shrinkA=0, shrinkB=0))
nleg = 106; reached = nleg - len(m["notreach"])
box(2, 41, 28, 12, "Legacy corpus\n106 stable references (R001–R106)\nV4: 95 → 96 → 105 → V4.1: 106")
box(36, 41, 28, 12, "Reference re-verification\n%d verification queries executed\n%d references checked; %d not reached\n(search budget exhausted)" % (m["nv"], reached, len(m["notreach"])))
box(70, 41, 28, 12, "Documented topic search\n%d queries executed, %d result links\n(general web engine; %d planned\nqueries not executed)" % (m["nq"], m["nl"], notrun))
box(70, 22, 28, 12, "Candidate records screened: 62\n(RF 21, ML 30, standards 10, lead 1);\nretained: RF %d, ML %d, standards %d" % (m["cand"]["search_log_rf.csv"], m["cand"]["search_log_ml.csv"], m["cand"]["search_log_std.csv"]), fc="#eef5ee")
box(2, 22, 28, 12, "Legacy references retained: %d\nnot cited in V4.3: 4 (R031, R044,\nR047, R057; reasons recorded)\ncorrections: Appendix B" % len(m["legacy_cited"]), fc="#fbf3e8")
box(36, 22, 28, 12, "New references added: %d\n(search %d; repository records %d;\nred-team classical additions %d)" % (len(m["new_cited"]), m["cand"]["search_log_rf.csv"]+m["cand"]["search_log_ml.csv"]+m["cand"]["search_log_std.csv"]+m["cand"]["audit"], m["cand"]["repo"], m["cand"]["redteam"]), fc="#eef5ee")
box(20, 3, 60, 12, "References cited in V4.3: %d\n(%d legacy + %d new); verification state per reference in the reference list\nand reference_master.csv; no reference reached full-text verification" % (len(m["order"]), len(m["legacy_cited"]), len(m["new_cited"])), fc="#e6dff3")
ar(30.6, 47, 35.4, 47); ar(84, 40.6, 84, 34.6); ar(69.4, 28, 64.6, 28)
ar(40, 40.6, 26, 34.6); ar(50, 21.6, 50, 15.6); ar(16, 21.6, 30, 15.6)
fig.savefig(sys.argv[1] + ".svg", bbox_inches="tight", pad_inches=0.03); fig.savefig(sys.argv[1] + ".png", dpi=300, bbox_inches="tight", pad_inches=0.03)
