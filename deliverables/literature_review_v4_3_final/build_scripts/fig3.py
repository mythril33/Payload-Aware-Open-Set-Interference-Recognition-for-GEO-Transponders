import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import sys
out = sys.argv[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
fig, ax = plt.subplots(figsize=(7.2, 3.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 50); ax.axis("off")
def box(x, y, w, h, title, body, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=fc, ec="#444", lw=0.7))
    ax.text(x + w/2, y + h - 2.6, title, ha="center", va="center", fontsize=6.6, weight="bold")
    ax.text(x + w/2, y + (h - 5)/2, body, ha="center", va="center", fontsize=5.5, linespacing=1.18)
def arrow(x1, y1, x2, y2, ls="-", c="#333", txt=None, tx=0, ty=0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, lw=0.9, ls=ls, color=c, shrinkA=0, shrinkB=0))
    if txt: ax.text(tx, ty, txt, fontsize=5.2, ha="center", va="center", color=c, style="italic")
W, H, Y = 17.0, 24.0, 21.0
xs = [1.0, 21.0, 41.0, 61.0]
box(xs[0], Y, W, H, "D1  Mechanism", "CW, swept CW,\nunauthorized carrier,\nCuC, ASI, cross-pol,\npayload IM, overdrive,\npulsed / burst,\nbroadband; benign\nlook-alikes", "#fbe4e4")
box(xs[1], Y, W, H, "D2  Entry plane", "EP-U0 / EP-U1 / EP-P /\nEP-D / EP-R\n+ transformations\nexperienced: IMUX,\nTWTA AM/AM-AM/PM,\nOMUX, depolarization,\nreceiver response", "#fff0d6")
box(xs[2], Y, W, H, "D3  Observables", "power, PSD,\nspectrogram, short or\ncontiguous IQ, co / cross\npolarization, carrier\nplan, host side info,\ncancellation residual,\ncalibration state", "#e3eef8")
box(xs[3], Y, W + 21.0, H, "D4  Identifiability (conditional)", "Axis A, minimal observation set:\nA0 co-pol PSD/spectrogram; A1 + one added\nobservation (P plan, X cross-pol, Q contiguous IQ,\nH host residual, G geometry); A2 external evidence;\nA\u2205 none identified\nAxis B, dominant confounder: B-N nuisance level,\nB-P payload physics, B-I missing side information\nEvidence status: shown / not shown", "#e6f2e6")
for i in range(3):
    arrow(xs[i] + W + 0.4, Y + H/2, xs[i + 1] - 0.4, Y + H/2)
box(1.0, 1.5, 98.0, 13.0, "D5  Strength of evidence (grades every link D1→D4)",
    "E1 analytical derivation  ·  E2 standards reference model  ·  E3 controlled simulation  ·  E4 laboratory hardware\n"
    "E5 operational field measurement  ·  E6 secondary, vendor or unverified claim     (grades describe evidence type, not source prestige)", "#f1eef7")
for x in [xs[0] + W/2, xs[1] + W/2, xs[2] + W/2, xs[3] + (W + 21)/2]:
    arrow(x, 14.9, x, Y - 0.5, ls="--", c="#5b4b8a")
ax.text(50.0, 48.6, "Mechanism–Observation–Evidence (MOE) framework: a proposed synthesis device, not a validated algorithm", fontsize=6.4, ha="center", weight="bold")
fig.savefig(out + ".svg", bbox_inches="tight", pad_inches=0.03)
fig.savefig(out + ".png", dpi=300, bbox_inches="tight", pad_inches=0.03)
