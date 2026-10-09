"""Mean downlink spectrum of one carrier plan through the linear and the TWTA chain."""
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from geosim.plan import monitor_freqs
from geosim.scenario import ScenarioConfig, simulate

BLUE, ORANGE, INK, MUTED, SURFACE = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#fcfcfb"
out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/figures/psd_linear_vs_twta.png")
cfg = ScenarioConfig(bandwidth=36e6, ibo_db=3.0, cn_up_db=40.0, cn_dn_db=40.0, seed=21)
f = monitor_freqs() / 1e6


def mean_db(r):
    p = np.mean(10 ** (r.spec_db / 10), axis=0)
    return 10 * np.log10(p / p.max())


lin, twta = simulate(replace(cfg, linear=True)), simulate(cfg)
a, b = mean_db(lin), mean_db(twta)
fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
ax.fill_between(f, -70, np.where(lin.mask_db > -30, 5, -70), color="#e9e8e4", lw=0, label="Planlı taşıyıcılar")
ax.plot(f, a, color=BLUE, lw=2, label="Doğrusal zincir")
ax.plot(f, b, color=ORANGE, lw=2, label=f"TWTA (DVB-S2 Şekil H.3), IBO {cfg.ibo_db:.0f} dB")
ax.set(xlim=(-30, 30), ylim=(-60, 5), xlabel="Transponder merkezinden frekans kayması (MHz)",
       ylabel="Güç yoğunluğu (dB, tepeye göre)")
ax.set_title("Aynı taşıyıcı planı, iki zincir: TWTA taşıyıcı aralarını intermodülasyonla dolduruyor",
             loc="left", fontsize=11, color=INK)
ax.grid(axis="y", color="#e3e2de", lw=0.8)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax.spines[s].set_color("#b9b8b2")
ax.tick_params(colors=MUTED)
ax.xaxis.label.set_color(MUTED)
ax.yaxis.label.set_color(MUTED)
ax.legend(frameon=False, loc="lower center", ncol=3, labelcolor=INK, fontsize=9)
fig.tight_layout()
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out)
gap = (lin.mask_db <= -60) & (np.abs(f) < 17)
print(f"plan: {len(lin.meta['plan'])} carriers; gap bins: {gap.sum()}; "
      f"gap level linear {a[gap].mean():.1f} dB, TWTA {b[gap].mean():.1f} dB; OBO {twta.meta['obo_db']:.2f} dB")
