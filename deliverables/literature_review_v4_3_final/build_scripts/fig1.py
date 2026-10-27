import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import sys
out = sys.argv[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "mathtext.fontset": "dejavusans"})
fig, ax = plt.subplots(figsize=(7.2, 5.0))
ax.set_xlim(0, 100); ax.set_ylim(-14, 66); ax.axis("off")
FS = 5.7
def box(x, y, w, h, text, fc="#ffffff", ec="#333333", lw=0.7, fs=FS, dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.8", fc=fc, ec=ec, lw=lw, ls="--" if dashed else "-"))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs, linespacing=1.15)
def arrow(x1, y1, x2, y2, color="#222222", lw=0.8, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=5.5, color=color, lw=lw, ls=ls, shrinkA=0, shrinkB=0))
planes = [(0.0, 12.6, "EP-U0", "ground\ntransmitter"), (13.4, 24.2, "EP-U1", "uplink entry\n(Rx antenna)"),
          (25.0, 64.0, "EP-P", "payload-internal\nreceiver → IMUX → TWTA → OMUX"), (64.8, 78.6, "EP-D", "downlink entry\n(post-OMUX)"),
          (79.4, 100.0, "EP-R", "monitoring receiver\nand observables")]
cols = ["#f2f5fa", "#edf5ed", "#fbf3e8", "#edf5ed", "#f2eff8"]
for (x0, x1, a, b), c in zip(planes, cols):
    ax.add_patch(FancyBboxPatch((x0, 0), x1 - x0, 54, boxstyle="square,pad=0", fc=c, ec="#b5b5b5", lw=0.5))
    ax.text((x0 + x1)/2, 61.6, a, ha="center", va="center", fontsize=7.0, weight="bold", color="#222")
    ax.text((x0 + x1)/2, 57.4, b, ha="center", va="center", fontsize=5.4, color="#333")
for y, p in [(33, "co"), (12, "x")]:
    box(1.0, y - 3.5, 10.6, 7, "Earth stations\n$x_{\\mathrm{%s}}(t)$" % p, fs=5.5)
    box(14.6, y - 3.5, 8.4, 7, "Satellite\nRx antenna", fs=5.5)
    box(26.0, y - 3.5, 7.6, 7, "Receiver,\ndown-\nconverter", fs=5.2)
    box(36.0, y - 3.5, 6.4, 7, "IMUX")
    box(45.0, y - 3.5, 7.8, 7, "TWTA\n$g_c$, $\\mathcal{G}\\{\\cdot\\}$", fc="#ffe9c9", fs=5.3)
    box(55.4, y - 3.5, 6.6, 7, "OMUX")
    box(66.0, y - 3.5, 11.6, 7, "Sat. Tx ant.,\npath, monitor\nantenna", fs=5.3)
    box(80.6, y - 3.5, 8.4, 7, "Receiver\n$\\mathcal{R}\\{\\cdot\\}$")
    box(90.6, y - 3.5, 8.6, 7, "PSD,\nspectrogram,\nIQ: $y_{\\mathrm{%s}}$" % p, fc="#e6dff3", fs=4.9)
    for x1, x2 in [(11.8, 14.4), (23.2, 25.8), (33.8, 35.8), (42.6, 44.8), (53.0, 55.2), (62.2, 65.8), (77.8, 80.4), (89.2, 90.4)]:
        arrow(x1, y, x2, y)
    ax.text(29.8, y - 5.6, "$\\phi_{\\mathrm{LO,%s}}$" % p, fontsize=5.6, ha="center", color="#444")
    ax.text(64.1, y + 2.1, "$z_{\\mathrm{%s}}$" % p, fontsize=6.0, ha="center")
for xa, lab in [(13.0, "$\\kappa_u$, $\\kappa_{u,q}$"), (64.4, "$\\kappa_d$")]:
    arrow(xa - 1.0, 30.0, xa + 1.0, 15.6, color="#1f5fa8", ls="--"); arrow(xa - 1.0, 15.0, xa + 1.0, 29.4, color="#1f5fa8", ls="--")
    ax.text(xa + 1.8, 22.3, lab, color="#1f5fa8", fontsize=6.2, ha="left", va="center")
ax.text(91.5, 22.3, "$\\kappa_R$", color="#1f5fa8", fontsize=6.2, ha="center", va="center")
arrow(84.0, 28.8, 84.0, 16.2, color="#1f5fa8", ls="--"); arrow(86.0, 16.2, 86.0, 28.8, color="#1f5fa8", ls="--")
box(13.8, 43.0, 10.0, 9.0, "Uplink-entry\n$i_{u,m}$: CW,\nswept, unauth.,\nCuC, uplink ASI", fc="#fbe4e4", ec="#a33333", fs=4.8)
arrow(18.8, 42.8, 18.8, 36.7, color="#a33333")
box(27.5, 43.0, 32.0, 9.0, "Payload-generated (internal): intermodulation,\ncompression / overdrive, AM/PM, weak-carrier\nsuppression, receiver nonlinearity,\npassive intermodulation (PIM)", fc="#ffe9c9", ec="#b26b00", fs=5.0)
arrow(48.9, 42.8, 48.9, 36.7, color="#b26b00")
box(65.3, 43.0, 12.8, 9.0, "Downlink-entry $i_{d,l}$:\nadjacent-satellite\ndownlink, terrestrial\nemitters", fc="#fbe4e4", ec="#a33333", fs=5.2)
arrow(71.7, 42.8, 71.7, 36.7, color="#a33333")
box(80.0, 43.0, 19.4, 9.0, "Receiver plane: feed leakage\n$\\kappa_R$, $n_d$, gain/flatness\ncalibration, spurs, clipping,\nLO offset, co/cross sync", fc="#ebe6f5", ec="#5b4b8a", fs=4.9)
arrow(83.0, 42.8, 83.0, 36.7, color="#5b4b8a")
ax.text(6.3, 22.3, "terminal faults:\nmispointing, feed\nmisalignment,\nexcess EIRP,\nwrong frequency", fontsize=5.0, ha="center", va="center", color="#444")
ax.text(19.0, 4.0, "$n_u(t)$", fontsize=5.4, ha="center", color="#444")
box(80.4, 1.2, 19.0, 5.6, "conditional side information:\ncarrier plans (may be stale),\nhost-carrier parameters", ec="#5b4b8a", dashed=True, fs=5.0)
ax.text(50.0, -6.5, "Each polarization has its own payload chain and down-converter. A cross-polar copy coupled at EP-U1 ($\\kappa_u$: common; $\\kappa_{u,q}$: one earth station)\n"
        "is filtered and distorted by the receiving chain with that chain's carriers; a copy coupled at EP-D ($\\kappa_d$) and downlink-entry interferers bypass the payload;\n"
        "$\\kappa_R$ is the monitoring feed's own leakage. Scalar couplings are a simplification: real coupling is complex-valued, frequency-dependent and not necessarily reciprocal.",
        fontsize=5.1, ha="center", va="center", color="#222")
fig.savefig(out + ".svg", bbox_inches="tight", pad_inches=0.03)
fig.savefig(out + ".png", dpi=300, bbox_inches="tight", pad_inches=0.03)
