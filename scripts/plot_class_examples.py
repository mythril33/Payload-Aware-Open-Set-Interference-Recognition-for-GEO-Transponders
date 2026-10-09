"""One paired example per stage-A class: same plan, carriers and noise; only the cause differs."""
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from geosim.classes import DEFAULT_RANGES, LABELS, sample
from geosim.plan import monitor_freqs

INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
BLUES = LinearSegmentedColormap.from_list("blues", ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
TITLES = {"clean": "Temiz", "cw": "CW", "swept_cw": "Süpürülen CW", "unauthorized": "Plansız taşıyıcı",
          "overdrive": "Aşırı sürme"}
out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/figures/class_examples.png")
seed, bw = 12, 36e6
# strong, easy-to-see interferers and a quiet link, for illustration only
ranges = replace(DEFAULT_RANGES, c_over_i_db=(12.0, 15.0), psd_offset_db=(0.0, 2.0), cn_up_db=(28.0, 30.0),
                 cn_dn_db=(28.0, 30.0), ibo_nominal_db=(11.0, 12.0), ibo_overdrive_db=(1.0, 2.0))
res = {lab: sample(lab, bw, seed, ranges) for lab in LABELS}
f = monitor_freqs() / 1e6
keep = np.abs(f) <= 26
ref = max(r.spec_db[:, keep].max() for r in res.values())
fig, axes = plt.subplots(2, 5, figsize=(13, 4.6), dpi=150, facecolor=SURFACE, sharex=True,
                         gridspec_kw={"height_ratios": [1, 9], "hspace": 0.06, "wspace": 0.08})
for j, lab in enumerate(LABELS):
    r = res[lab]
    top, ax = axes[0, j], axes[1, j]
    top.fill_between(f[keep], 0, (r.mask_db[keep] > -30).astype(float), color="#b9b8b2", lw=0)
    top.set(ylim=(0, 1), yticks=[])
    top.set_title(TITLES[lab], fontsize=10, color=INK, loc="left")
    for s in top.spines.values():
        s.set_visible(False)
    im = ax.imshow(r.spec_db[:, keep] - ref, aspect="auto", cmap=BLUES, vmin=-45, vmax=0,
                   extent=(f[keep][0], f[keep][-1], 1.28, 0), interpolation="nearest")
    ax.set_xlabel("Frekans kayması (MHz)", color=MUTED, fontsize=8)
    ax.tick_params(colors=MUTED, labelsize=8)
    for s in ax.spines.values():
        s.set_color("#b9b8b2")
    if j:
        ax.set_yticks([])
axes[1, 0].set_ylabel("Zaman (s)", color=MUTED, fontsize=8)
axes[0, 0].set_ylabel("Plan", color=MUTED, fontsize=8, rotation=0, ha="right", va="center")
cb = fig.colorbar(im, ax=axes, fraction=0.012, pad=0.01)
cb.set_label("Güç yoğunluğu (dB, tepeye göre)", color=MUTED, fontsize=8)
cb.ax.tick_params(colors=MUTED, labelsize=8)
cb.outline.set_visible(False)
fig.suptitle("Aynı senaryo, beş sınıf: plan, taşıyıcılar ve gürültü ortak; yalnızca girişim nedeni farklı",
             x=0.125, ha="left", fontsize=11, color=INK)
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, bbox_inches="tight")
for lab, r in res.items():
    i = r.meta["interferer"]
    print(lab, "IBO", round(r.meta["actual_ibo_db"], 1), {k: (round(v, 2) if isinstance(v, float) else v)
                                                          for k, v in i.items() if k in ("f0", "f_lo", "f_hi", "c_over_i_db", "period")})
