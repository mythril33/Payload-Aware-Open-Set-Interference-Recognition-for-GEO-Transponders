import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import sys
out = sys.argv[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "mathtext.fontset": "dejavusans"})
rows = [
 ("O1", "Band / total power", "gross level change, alarm", "cannot localize or separate mechanisms"),
 ("O2", "Co-polar PSD (averaged)", "spectral location and shape;\nCW vs. wideband; IM regrowth shape", "CuC nearly invisible at high C/I; IM vs.\ncoincident external energy ambiguous"),
 ("O3", "Spectrogram (time-resolved PSD)", "swept CW, pulsed / burst, on-off cycling", "needs RBW, dwell and frame rate\nmatched to sweep or burst timing"),
 ("O4", "+ operator carrier plan", "planned vs. unplanned occupancy;\npredicted IM product locations", "plan must be current and complete;\nlegitimate PCMA must be flagged"),
 ("O5", "+ cross-polar observation", "leakage consistency test\n(co/cross correlation)", "synchronized, frequency-aligned receivers;\nEP-U1 vs. EP-D coupling can remain confounded"),
 ("O6", "Short IQ snapshots", "modulation and higher-order statistics", "short records limit cyclic resolution;\nsnapshots are not contiguous"),
 ("O7", "Contiguous IQ", "spectral correlation; hidden symbol rates", "longer records as the hidden carrier\nweakens; cycle frequencies must differ"),
 ("O8", "+ host-carrier side information", "host cancellation residual (CuC)", "decodable host, known pulse shaping,\ncarrier and timing lock"),
 ("O9", "External evidence", "source attribution: geolocation, CID,\noperator coordination", "second satellite and ephemeris; cooperative\nCID; administrative records"),
]
fig, ax = plt.subplots(figsize=(7.2, 5.3))
ax.set_xlim(-1, 100); ax.set_ylim(-2, len(rows) * 6.2 + 6); ax.axis("off")
hdr_y = len(rows) * 6.2 + 2.6
for x, t in [(3.4, "Level"), (9, "Observation at the monitor"), (36, "What it can add (conditionally)"), (66, "Assumptions / remaining confounders")]:
    ax.text(x, hdr_y, t, fontsize=6.4, weight="bold", va="center")
shade = ["#f4f6fa", "#eef3f8", "#e8f0f6", "#e0ebf3", "#d8e6f0", "#d0e1ee", "#c7dbeb", "#bfd5e8", "#f6efe2"]
for i, (lvl, obs, adds, assum) in enumerate(rows):
    y = (len(rows) - 1 - i) * 6.2
    ax.add_patch(FancyBboxPatch((0.5, y), 99, 5.4, boxstyle="round,pad=0.0,rounding_size=0.6", fc=shade[i], ec="#9aa8b8", lw=0.5))
    ax.text(5.0, y + 2.7, lvl, fontsize=6.6, weight="bold", ha="center", va="center")
    ax.text(9, y + 2.7, obs, fontsize=6.0, va="center")
    ax.text(36, y + 2.7, adds, fontsize=5.6, va="center", linespacing=1.1)
    ax.text(66, y + 2.7, assum, fontsize=5.4, va="center", color="#3a2a1a", linespacing=1.1)
ax.add_patch(FancyArrowPatch((1.2, len(rows) * 6.2 - 1.0), (1.2, 6.8), arrowstyle="-|>", mutation_scale=6, lw=0.8, color="#555"))
ax.text(50, -1.2, "Left arrow: increasing data rate, side-information and synchronization requirements.\nLevels are not strictly nested: O4, O5, O8 and O9 are side channels whose availability is operator- and link-specific.\n"
        "An entry under ‘what it can add’ is a conditional possibility under the listed assumptions, not a demonstrated recognition result.",
        fontsize=5.2, ha="center", va="top")
fig.savefig(out + ".svg", bbox_inches="tight", pad_inches=0.03)
fig.savefig(out + ".png", dpi=300, bbox_inches="tight", pad_inches=0.03)
