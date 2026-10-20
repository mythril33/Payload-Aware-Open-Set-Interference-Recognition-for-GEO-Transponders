"""DVB carrier identification (DVB-CID) overlay after ETSI TS 103 129 V1.1.2 (P18 `cid_overlay`).

A CID is a legitimate spread-spectrum BPSK signal that the uplink modulator adds
under its own host carrier, so it enters the uplink and passes the payload. The
bit stream follows the specification:

- frame: 22-bit unique word (alternately 0x147147 / 0x2b8eb8), two halves of
  32-bit identifier + 5-bit content ID + 24-bit information + CRC-8 + 42-bit
  BCH(111, 69) parity (clause 5.1);
- scrambling of all non-UW bits with x^9 + x^5 + 1, initial state 0x41, reset
  per frame (5.2); 4x repetition (5.3); differential encoding (5.4);
- 4096 chips per bit from the x^15 + x^14 + 1 LFSR (5.5); BPSK (5.6);
  root-raised-cosine alpha = 0.35 (5.7); chip rate 224 kHz for hosts >= 512 kBd,
  112 kHz below; PSD relative to the host centre PSD from Table 6 (5.8);
  +220 Hz offset, no spectrum inversion (5.9).

Conventions the specification leaves to figures are fixed by its test vectors:
the chipping LFSR reproduces the stated first 32 chips 0x5091E364 and the CRC-8
check digit of the clause 4.1 example is 0x75. The scrambler has no test vector
and uses the same register convention [to verify]. Not modelled: the close-in
phase-noise mask (clause 6), host power reduction (Annex B: an order of magnitude
smaller than the CID's own interference) and optional content fields; the
transmitted content is the mandatory format field only (sequence "0-0").
"""
from __future__ import annotations

from numbers import Integral

import numpy as np
from scipy.signal import resample_poly

from . import FS_SIM
from .events import _real, _request, _rng
from .waveform import Carrier

ROLLOFF = 0.35
CHIPS_PER_BIT = 4096
REPETITION = 4
UNIQUE_WORDS = (0x147147, 0x2B8EB8)
CRC8_POLY = 0xD5                                  # x^8 + x^7 + x^6 + x^4 + x^2 + 1, MSB first
BCH_FACTORS = ((0, 4, 7), (0, 2, 3, 4, 7), (0, 1, 2, 3, 4, 5, 7), (0, 6, 7), (0, 2, 4, 6, 7), (0, 4, 5, 6, 7))
CHIP_LFSR_STATE = (0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0)   # printed x^15 ... x^1
SCRAMBLER_STATE = (0, 0, 1, 0, 0, 0, 0, 0, 1)                     # 0x41, printed x^9 ... x^1
FREQUENCY_OFFSET_HZ = 220.0
FORMAT_INFORMATION = 0x000001                     # content ID 0, CID format revision
SPAN_CHIPS = 8                                    # one-sided RRC truncation [assumption]
LOW_SPS = 8                                       # chips are shaped at 8 samples/chip, then resampled
# (lower bound in kBd, PSD relative to host centre PSD in dB), Table 6
PSD_TABLE = ((16384, -17.5), (8192, -18.5), (4096, -21.5), (2048, -24.5), (128, -27.5))
SOURCES = ("ETSI TS 103 129 V1.1.2 (2014-03)", "ITU-R S.2062-0 Table 3")


def _bits(value: int, width: int) -> list[int]:
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def crc8(bits) -> int:
    """Clause 5.1.2 CRC-8, register initialised to 0xFF, MSB first."""
    crc = 0xFF
    for bit in bits:
        feedback = ((crc >> 7) & 1) ^ int(bit)
        crc = (crc << 1) & 0xFF
        if feedback:
            crc ^= CRC8_POLY
    return crc


def check_digits(guid: int) -> int:
    """check_digits_octet of a 64-bit DVB CID Global Unique Identifier (clause 4.1)."""
    return crc8(_bits(guid, 64))


def _poly(exponents) -> int:
    return sum(1 << e for e in exponents)


def _poly_mul(a: int, b: int) -> int:
    out = 0
    while b:
        if b & 1:
            out ^= a
        a, b = a << 1, b >> 1
    return out


def _poly_mod(a: int, m: int) -> int:
    degree = m.bit_length() - 1
    while a and a.bit_length() - 1 >= degree:
        a ^= m << (a.bit_length() - 1 - degree)
    return a


def bch_generator() -> int:
    g = 1
    for factor in BCH_FACTORS:
        g = _poly_mul(g, _poly(factor))
    return g


def bch_parity(data_bits) -> list[int]:
    """42 parity bits of the shortened BCH(111, 69) code; first data bit is the x^68 coefficient."""
    if len(data_bits) != 69:
        raise ValueError("BCH data must be 69 bits")
    d = 0
    for bit in data_bits:
        d = (d << 1) | int(bit)
    return _bits(_poly_mod(d << 42, bch_generator()), 42)


def _lfsr(state, taps, n: int, output_feedback: bool) -> np.ndarray:
    """Fibonacci LFSR; state printed from the highest stage; feedback enters stage 1."""
    s = list(state)                               # s[0] = highest stage
    out = np.empty(n, np.uint8)
    for i in range(n):
        feedback = s[len(s) - taps[0]] ^ s[len(s) - taps[1]]
        out[i] = feedback if output_feedback else s[0]
        s = s[1:] + [feedback]
    return out


def chip_pattern() -> np.ndarray:
    return _lfsr(CHIP_LFSR_STATE, (15, 14), CHIPS_PER_BIT, output_feedback=False)


def scramble(bits) -> list[int]:
    sequence = _lfsr(SCRAMBLER_STATE, (9, 5), len(bits), output_feedback=True)
    return [int(b) ^ int(s) for b, s in zip(bits, sequence)]


def frame_bits(guid: int, index: int) -> list[int]:
    """One 244-bit CID frame with content ID 0 in both halves, after scrambling."""
    halves = []
    for part in (guid >> 32, guid & 0xFFFFFFFF):
        protected = _bits(part, 32) + _bits(0, 5) + _bits(FORMAT_INFORMATION, 24)
        protected += _bits(crc8(protected), 8)
        halves += protected + bch_parity(protected)
    return _bits(UNIQUE_WORDS[index % 2], 22) + scramble(halves)


def bit_stream(guid: int) -> np.ndarray:
    """Differentially encoded bits over one full period (two frames, run twice for parity)."""
    repeated = []
    for index in range(2):
        repeated += frame_bits(guid, index) * REPETITION
    raw = np.array(repeated * 2, np.uint8)
    return np.bitwise_xor.accumulate(raw)          # d[n] = b[n] xor d[n - 1], d[-1] = 0 [assumption]


def chip_rate(host_symbol_rate: float) -> float:
    return 224e3 if host_symbol_rate >= 512e3 else 112e3


def relative_psd_db(host_symbol_rate: float) -> float:
    for lower, level in PSD_TABLE:
        if host_symbol_rate >= lower * 1e3:
            return level
    raise ValueError("ETSI TS 103 129 Table 6 starts at 128 kBd")


def _rrc_taps(sps: int, span: int) -> np.ndarray:
    t = np.arange(-span * sps, span * sps + 1) / sps
    a = ROLLOFF
    with np.errstate(divide="ignore", invalid="ignore"):
        h = (np.sin(np.pi * t * (1 - a)) + 4 * a * t * np.cos(np.pi * t * (1 + a))) / (np.pi * t * (1 - (4 * a * t) ** 2))
    h[t == 0] = 1 - a + 4 * a / np.pi
    edge = np.isclose(np.abs(t), 1 / (4 * a))
    h[edge] = a / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * a)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * a)))
    return h * np.sqrt(sps / np.sum(h ** 2))     # unit average power for unit-variance chips


class _Cid:
    def __init__(self, host: Carrier, guid: int, start_chip: int, start_sample: int, phase: float):
        self.host, self.guid = host, guid
        self.rc = chip_rate(host.symbol_rate)
        self.psd_db = relative_psd_db(host.symbol_rate)
        self.power = host.power * self.rc / host.symbol_rate * 10 ** (self.psd_db / 10)
        self.frequency = host.f0 + FREQUENCY_OFFSET_HZ
        self.start_chip, self.start_sample, self.phase = start_chip, start_sample, phase
        self.pattern, self.bits = chip_pattern(), bit_stream(guid)
        # hi-rate samples per chip = FS_SIM / rc = up / down exactly
        self.up, self.down = (9000, 7) if self.rc == 224e3 else (18000, 7)
        self.up //= LOW_SPS
        self.taps = _rrc_taps(LOW_SPS, SPAN_CHIPS)

    def chips(self, k: np.ndarray) -> np.ndarray:
        k = k + self.start_chip
        bit = self.bits[(k // CHIPS_PER_BIT) % len(self.bits)]
        return 1.0 - 2.0 * (self.pattern[k % CHIPS_PER_BIT] ^ bit)

    def window(self, s0: int, n: int) -> np.ndarray:
        """Unit-power baseband CID for hi-rate samples s0 ... s0 + n - 1 (absolute sample index)."""
        per_chip = self.up * LOW_SPS / self.down    # hi-rate samples per chip
        margin = SPAN_CHIPS + 4
        rel = s0 - self.start_sample
        k0 = 7 * int(np.floor((rel / per_chip - margin) / 7))        # chip start on a common sample grid
        k1 = int(np.ceil((rel + n) / per_chip)) + margin
        up = np.zeros((k1 - k0) * LOW_SPS)
        up[::LOW_SPS] = self.chips(np.arange(k0, k1))
        shaped = np.convolve(up, self.taps)[SPAN_CHIPS * LOW_SPS:][: up.size]
        hi = resample_poly(shaped, self.up, self.down)
        offset = rel - int(round(k0 * per_chip))
        return hi[offset: offset + n]


def cid_overlay(rng: np.random.Generator, plan: list[Carrier], bandwidth: float):
    """DVB-CID under every planned carrier; returns (generate(rng, t0, n, fs), metadata).

    Identifiers, frame timing and carrier phases are drawn here; the waveform is a
    continuous function of absolute time, so successive snapshots continue the same
    CID frames. ``generate`` ignores its rng.
    """
    carriers, bandwidth, _ = _request(rng, plan, bandwidth, 0.0)
    cids = []
    for host in carriers:
        if host.symbol_rate < 128e3:
            raise ValueError("ETSI TS 103 129 Table 6 starts at 128 kBd")
        mac = int(rng.integers(0, 2 ** 48)) & ~(0x03 << 40) | (0x02 << 40)   # unicast, locally administered
        guid = (mac >> 24) << 40 | 0xFFFF << 24 | (mac & 0xFFFFFF)          # MAC-48 in EUI-64 (clause 4.1)
        cids.append(_Cid(host, guid, int(rng.integers(0, 2 * 2 * 244 * REPETITION * CHIPS_PER_BIT)),
                         int(rng.integers(0, 18000)), float(rng.uniform(0, 2 * np.pi))))

    def generate(rng_event, t0, n, fs):
        _rng(rng_event)
        starts = np.asarray(t0, float)
        if starts.ndim != 1 or not starts.size or not np.isfinite(starts).all() or np.any(starts < 0) \
                or np.any(np.diff(starts) <= 0):
            raise ValueError("t0 must be finite, nonnegative, strictly increasing snapshot start times")
        if isinstance(n, (bool, np.bool_)) or not isinstance(n, Integral) or n < 1:
            raise ValueError("n must be a positive integer")
        if _real(fs, "fs") != FS_SIM:
            raise ValueError("the CID chip timing is defined on the FS_SIM grid")
        first = starts * fs
        if np.max(np.abs(first - np.round(first))) > 1e-6:
            raise ValueError("snapshot starts must fall on the simulation sample grid")
        out = np.zeros((len(starts), int(n)), np.complex64)
        for c in cids:
            for row, s0 in enumerate(np.round(first).astype(np.int64)):
                t = (s0 + np.arange(n)) / fs
                carrier = np.exp(1j * (2 * np.pi * ((c.frequency * t) % 1.0) + c.phase))
                out[row] += (np.sqrt(c.power) * c.window(int(s0), int(n)) * carrier).astype(np.complex64)
        return out

    metadata = {"kind": "cid_overlay", "injection_stage": "uplink", "legitimate": True, "expected_label": "clean",
                "power_reference": "host carrier centre PSD",
                "cids": [{"host_f0": c.host.f0, "host_symbol_rate": c.host.symbol_rate, "chip_rate": c.rc,
                          "relative_psd_db": c.psd_db, "power": float(c.power), "f_center": c.frequency,
                          "guid": f"{c.guid:016x}", "check_digits": f"{check_digits(c.guid):02x}",
                          "start_chip": c.start_chip} for c in cids],
                "sources": list(SOURCES)}
    return generate, metadata
