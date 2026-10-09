"""Monitoring receiver: decimation to 96 MHz and Welch spectrogram rows (spec §3)."""
from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly, welch

from . import FS_MON, FS_SIM

SNAP_MON = 4096                 # monitor samples kept per snapshot
WARMUP_SIM = 2304               # simulation samples discarded per snapshot (768 at monitor rate)
DECIM = int(round(FS_SIM / FS_MON))
N_SIM = SNAP_MON * DECIM + WARMUP_SIM
NFFT = 512


def awgn(rng: np.random.Generator, shape: tuple[int, ...], n0: float, fs: float) -> np.ndarray:
    """Complex white noise with PSD n0 (power / Hz) at sample rate fs."""
    s = np.sqrt(n0 * fs / 2)
    return (s * (rng.standard_normal(shape, dtype=np.float32)
                 + 1j * rng.standard_normal(shape, dtype=np.float32))).astype(np.complex64)


def to_monitor(y: np.ndarray) -> np.ndarray:
    """Decimate by 3 and drop the warm-up; returns (..., SNAP_MON) complex64."""
    z = resample_poly(y, 1, DECIM, axis=-1)
    return z[..., WARMUP_SIM // DECIM: WARMUP_SIM // DECIM + SNAP_MON].astype(np.complex64)


def spectrogram_db(z: np.ndarray) -> np.ndarray:
    """One Welch PSD row per snapshot: (n_snap, 512) float32, dB(power/Hz), -48..+48 MHz."""
    _, p = welch(z, fs=FS_MON, window="hann", nperseg=NFFT, noverlap=NFFT // 2,
                 detrend=False, return_onesided=False, scaling="density", axis=-1)
    return (10 * np.log10(np.fft.fftshift(p, axes=-1) + 1e-30)).astype(np.float32)
