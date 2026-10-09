"""Transponder blocks: IMUX, channel amplifier, TWTA, OMUX (spec §2.4-§2.7)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import cheby1, cheby2, ellip, freqz, oaconvolve, sosfilt, sosfreqz

DATA = Path(__file__).parent / "data"

# ---------------------------------------------------------------- filters


@dataclass(frozen=True)
class LinearFilter:
    """Either IIR second-order sections (real) or FIR taps (complex), at sample rate fs."""
    fs: float
    sos: np.ndarray | None = None
    fir: np.ndarray | None = None

    def apply(self, x: np.ndarray) -> np.ndarray:
        if self.sos is not None:
            return sosfilt(self.sos, x, axis=-1).astype(np.complex64)
        taps = self.fir.reshape((1,) * (x.ndim - 1) + (-1,))
        return oaconvolve(x, taps, mode="full", axes=-1)[..., :x.shape[-1]].astype(np.complex64)

    def response(self, f_hz: np.ndarray) -> np.ndarray:
        w = 2 * np.pi * np.asarray(f_hz) / self.fs
        return sosfreqz(self.sos, worN=w)[1] if self.sos is not None else freqz(self.fir, 1, worN=w)[1]


@lru_cache(maxsize=1)
def _etsi_fir() -> dict:
    with np.load(DATA / "mux_fir.npz") as d:
        return {k: d[k] for k in d.files}


def _mux(kind: str, bandwidth: float, fs: float, model: str) -> LinearFilter:
    """Low-pass equivalent of the input or output multiplexer filter.

    "etsi":   FIR built from the ETSI TR 102 376-2 Annex E tables (36 MHz transponder, 40 MHz
              spacing), scaled per EN 302 307-1 H.7. Available at 288 MHz for 36 and 72 MHz.
    "cheby2": Chebyshev II approximation of the same filters from Dimitrov (2016): IMUX order 7,
              34 dB, 23 MHz edge; OMUX order 5, 38 dB, 28.6 MHz edge; any bandwidth and rate.
    "generic": the project's first placeholder (elliptic IMUX, Chebyshev I OMUX).
    """
    k, nyq = bandwidth / 36e6, fs / 2
    if model == "etsi":
        d = _etsi_fir()
        key = f"{kind}_{bandwidth / 1e6:.0f}"
        if key not in d or abs(fs - float(d["fs"])) > 1:
            raise ValueError(f"no ETSI table filter for {key} at {fs / 1e6:.0f} MHz; use model='cheby2'")
        return LinearFilter(fs, fir=d[key])
    if model == "cheby2":
        order, att, edge = (7, 34, 23e6) if kind == "imux" else (5, 38, 28.6e6)
        return LinearFilter(fs, sos=cheby2(order, att, edge * k / nyq, output="sos"))
    if model == "generic":
        if kind == "imux":
            return LinearFilter(fs, sos=ellip(6, 0.1, 40, (bandwidth / 2) / nyq, output="sos"))
        return LinearFilter(fs, sos=cheby1(4, 0.1, 1.1 * (bandwidth / 2) / nyq, output="sos"))
    raise ValueError(f"unknown filter model {model!r}")


def imux(bandwidth: float, fs: float, model: str = "etsi") -> LinearFilter:
    return _mux("imux", bandwidth, fs, model)


def omux(bandwidth: float, fs: float, model: str = "etsi") -> LinearFilter:
    return _mux("omux", bandwidth, fs, model)


# ---------------------------------------------------------------- amplifiers
# Saleh 1981 TWT coefficients as commonly quoted; not yet checked against the paper.
A_A, B_A, A_P, B_P = 2.1587, 1.1517, 4.0033, 9.1040


@dataclass(frozen=True)
class Amplifier:
    """Memoryless AM/AM, AM/PM. r_sat: input amplitude at saturation; a_max: output amplitude there."""
    name: str
    r_sat: float
    a_max: float
    small_signal_gain: float
    table: tuple | None = None       # (pin_db, gain_db, phase_rad), pin relative to saturation

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.table is None:
            r2 = np.abs(x) ** 2
            return (x * (A_A / (1 + B_A * r2)) * np.exp(1j * A_P * r2 / (1 + B_P * r2))).astype(x.dtype)
        pin_db, gain_db, phase = self.table
        p = 10 * np.log10(np.maximum(np.abs(x) ** 2, 1e-30))
        g = 10 ** (np.interp(p, pin_db, gain_db) / 20)
        return (x * g * np.exp(1j * np.interp(p, pin_db, phase))).astype(x.dtype)

    def linear(self, x: np.ndarray) -> np.ndarray:
        """Linear reference chain: small-signal gain, no compression, no AM/PM."""
        return (self.small_signal_gain * x).astype(x.dtype)

    def drive_gain(self, nominal_power: float, ibo_db: float) -> float:
        """Fixed channel-amplifier voltage gain putting nominal_power at the given input back-off.

        IBO = 10 log10(r_sat^2 / E|x|^2), referenced to single-carrier saturation.
        """
        return float(np.sqrt(self.r_sat ** 2 * 10 ** (-ibo_db / 10) / nominal_power))

    def obo_db(self, y: np.ndarray) -> float:
        return float(10 * np.log10(self.a_max ** 2 / np.mean(np.abs(y) ** 2)))


def _table_amp(name: str, key: str) -> Amplifier:
    d = json.loads((DATA / "dvbs2_twta.json").read_text())[key]
    pin, pout, ph = (np.array(d[k], float) for k in ("input_power_db", "output_power_db", "phase_deg"))
    pout = pout - pout.max()                       # 0 dB = saturated output
    pin = pin - pin[np.argmax(pout)]               # 0 dB = input at saturation
    gain = pout - pin
    ph = ph - ph[0]                                # AM/PM is relative; zero at the lowest drawn drive
    # below the drawn range: constant gain (linear), phase -> 0; above: continue the last 2 dB trend
    n = int(round(2 / (pin[1] - pin[0])))
    hi = pin[-1] + 12.0
    gain_hi = gain[-1] + (gain[-1] - gain[-1 - n]) / 2 * 12.0
    ph_hi = ph[-1] + (ph[-1] - ph[-1 - n]) / 2 * 12.0
    pin_x = np.concatenate([[-300.0], pin, [hi]])
    gain_x = np.concatenate([[gain[0]], gain, [gain_hi]])
    ph_x = np.radians(np.concatenate([[0.0], ph, [ph_hi]]))
    return Amplifier(name, 1.0, 1.0, float(10 ** (gain[0] / 20)), (pin_x, gain_x, ph_x))


@lru_cache(maxsize=None)
def amplifier(name: str = "dvbs2_nl") -> Amplifier:
    """"dvbs2_nl": non-linearized Ka-band TWTA, EN 302 307-1 Figure H.3 (digitized from the PDF).
    "dvbs2_lin": linearized Ku-band TWTA, Figure H.2. "saleh": classic Saleh coefficients."""
    if name == "saleh":
        r_sat = 1 / np.sqrt(B_A)
        return Amplifier(name, float(r_sat), float(A_A * r_sat / (1 + B_A * r_sat ** 2)), A_A)
    if name == "dvbs2_nl":
        return _table_amp(name, "nonlinearized_ka_twta_fig_h3")
    if name == "dvbs2_lin":
        return _table_amp(name, "linearized_ku_twta_fig_h2")
    raise ValueError(f"unknown amplifier {name!r}")
