"""Extract the TWTA curves of EN 302 307-1 Figures H.2 and H.3 from the PDF's vector paths.

Usage: python scripts/digitize_twta_figures.py <en_30230701v010401p.pdf> [out.json]
Needs poppler's pdftocairo. The curves are drawn as vector polylines, so the values are
read from path vertices and calibrated against the plot's grid lines, not traced from pixels.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def page_paths(pdf: str, page: int):
    with tempfile.TemporaryDirectory() as d:
        svg = Path(d) / "p.svg"
        subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, str(svg)], check=True)
        text = svg.read_text()
    out = []
    for attrs in re.findall(r"<path ([^>]*?)/>", text, flags=re.S):
        d = re.search(r'\bd="([^"]*)"', attrs).group(1)
        if "C" in d:                       # glyph outlines and markers, not data or grid
            continue
        pts = np.array([[float(a), float(b)] for a, b in re.findall(r"[ML]\s*(-?[\d.]+)\s+(-?[\d.]+)", d)])
        m = re.search(r'transform="matrix\(([^)]*)\)"', attrs)
        if m:
            a, b, c, dd, e, f = (float(v) for v in m.group(1).split(","))
            pts = np.column_stack([a * pts[:, 0] + c * pts[:, 1] + e, b * pts[:, 0] + dd * pts[:, 1] + f])
        stroke = re.search(r'stroke="([^"]*)"', attrs)
        out.append((stroke.group(1) if stroke else None, pts))
    return out


def grid(paths, box):
    """Sorted x of long vertical and y of long horizontal straight lines inside box."""
    x0, x1, y0, y1 = box
    xs, ys = [], []
    for _, p in paths:
        if len(p) != 2:
            continue
        (ax, ay), (bx, by) = p
        if abs(ax - bx) < 0.05 and abs(ay - by) > 0.5 * (y1 - y0) and x0 - 2 <= ax <= x1 + 2:
            xs.append(ax)
        if abs(ay - by) < 0.05 and abs(ax - bx) > 0.5 * (x1 - x0) and y0 - 2 <= ay <= y1 + 2:
            ys.append(ay)

    def uniq(v):
        v = np.sort(np.array(v))
        return v[np.concatenate([[True], np.diff(v) > 0.5])] if len(v) else v
    return uniq(xs), uniq(ys)


def curve(paths, colour, box, markers=False):
    """Data vertices of one colour inside box, sorted by x.

    markers=True: the curve is drawn with square markers (5-vertex closed paths); use their centres.
    Otherwise concatenate the polyline pieces, skipping the legend sample (a long 2-point line).
    """
    x0, x1, y0, y1 = box
    pts = []
    for c, p in paths:
        if c != colour or p[:, 0].min() < x0 - 5 or p[:, 0].max() > x1 + 5 or p[:, 1].min() < y0 - 5 or p[:, 1].max() > y1 + 5:
            continue
        if markers:
            if len(p) == 5 and np.ptp(p[:, 0]) < 8 and np.ptp(p[:, 1]) < 8:
                pts.append([[p[:, 0].min() + np.ptp(p[:, 0]) / 2, p[:, 1].min() + np.ptp(p[:, 1]) / 2]])
        elif not (len(p) == 2 and abs(p[0, 0] - p[1, 0]) > 10):
            pts.append(p)
    pts = np.concatenate(pts)
    return pts[np.argsort(pts[:, 0], kind="stable")]


NAVY, MAGENTA = "rgb(0%, 0%, 50%)", "rgb(100%, 0%, 100%)"


def extract(pdf, page, box, x_range, power_range, phase_range, step_db, markers=False, n_x_lines=None):
    paths = page_paths(pdf, page)
    xs, ys = grid(paths, box)
    xs = xs[:n_x_lines] if n_x_lines else xs          # drop a frame edge that is not a tick
    fx = lambda x: x_range[0] + (x - xs[0]) / (xs[-1] - xs[0]) * (x_range[1] - x_range[0])
    top, bottom = ys[0], ys[-1]
    fy = lambda y, r: r[1] + (y - top) / (bottom - top) * (r[0] - r[1])
    pw, ph = curve(paths, NAVY, box, markers), curve(paths, MAGENTA, box, markers)
    lo = np.ceil(max(fx(pw[0, 0]), fx(ph[0, 0]), x_range[0]) / step_db - 1e-6) * step_db
    hi = np.floor(min(fx(pw[-1, 0]), fx(ph[-1, 0]), x_range[1]) / step_db + 1e-6) * step_db
    grid_in = np.arange(lo, hi + 1e-9, step_db)
    resample = lambda p, r: np.interp(grid_in, fx(p[:, 0]), fy(p[:, 1], r))
    return {"calibration": {"grid_x_pt": [float(xs[0]), float(xs[-1])], "grid_y_pt": [float(top), float(bottom)],
                            "n_vertices_power": int(len(pw)), "n_vertices_phase": int(len(ph)),
                            "drawn_input_range_db": [round(float(fx(pw[0, 0])), 2), round(float(fx(pw[-1, 0])), 2)]},
            "input_power_db": grid_in.round(3).tolist(),
            "output_power_db": resample(pw, power_range).round(3).tolist(),
            "phase_deg": resample(ph, phase_range).round(2).tolist()}


if __name__ == "__main__":
    pdf = sys.argv[1]
    out = {
        "source": "ETSI EN 302 307-1 V1.4.1, Annex H.7; digitized from the PDF's vector paths",
        "nonlinearized_ka_twta_fig_h3": extract(pdf, 70, (135, 455, 100, 350), (-20, 6), (-16, 0), (-10, 70), 0.5),
        "linearized_ku_twta_fig_h2": extract(pdf, 69, (140, 460, 240, 395), (-30, 6), (-26, 0), (0, 30), 1.0,
                                             markers=True, n_x_lines=19),
    }
    target = Path(sys.argv[2] if len(sys.argv) > 2 else "src/geosim/data/dvbs2_twta.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1))
    for k in ("nonlinearized_ka_twta_fig_h3", "linearized_ku_twta_fig_h2"):
        v = out[k]
        print(k, v["calibration"])
        for i in range(0, len(v["input_power_db"]), max(1, len(v["input_power_db"]) // 13)):
            print(f"   Pin {v['input_power_db'][i]:6.1f}  Pout {v['output_power_db'][i]:7.2f} dB  phase {v['phase_deg'][i]:6.2f} deg")
