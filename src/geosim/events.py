"""Controlled overlapping-uplink and adjacent-satellite event hypotheses.

Factories return ``(generate, metadata)`` with the usual geosim callback
``generate(rng, t0, n, fs) -> complex64[len(t0), n]``. Symbols and initial
phases are independent between requested windows, as for planned carriers.

An under-carrier event is injected before the wanted transponder payload;
its C/I uses the total planned uplink power of one. An adjacent-satellite
event is already a received downlink waveform: its callback has nominal
power ``10**(-C/I/10)`` and the dual simulator multiplies its amplitude by
the square root of the interference-free wanted receiver-feed power. It
must not pass through the wanted satellite's TWTA or be counted as receiver
noise. No interfering satellite payload, antenna pattern, direction or
orbital geometry is inferred here. These simulator causes are not uniquely
identifiable from the aggregate spectrum alone.
"""
from __future__ import annotations

from dataclasses import asdict
from numbers import Integral, Real

import numpy as np

from . import FS_SIM
from .interferers import InfeasibleCarrierError
from .plan import SYMBOL_RATES
from .waveform import MODULATIONS, ROLLOFFS, Carrier, constellation, generate_carrier, samples_per_symbol


def _real(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _rng(value):
    if not isinstance(value, np.random.Generator):
        raise ValueError("rng must be a numpy.random.Generator")


def _request(rng, plan, bandwidth, c_over_i_db):
    _rng(rng)
    bandwidth = _real(bandwidth, "bandwidth")
    if bandwidth not in (36e6, 72e6):
        raise ValueError("bandwidth must be 36e6 or 72e6 Hz")
    ci = _real(c_over_i_db, "c_over_i_db")
    if not -100 <= ci <= 100:
        raise ValueError("c_over_i_db must be in [-100, 100] dB")
    if not isinstance(plan, (tuple, list)) or not plan:
        raise ValueError("plan must contain at least one Carrier")
    carriers = []
    for item in plan:
        if not isinstance(item, Carrier):
            raise ValueError("plan entries must be Carrier objects")
        values = {key: _real(getattr(item, key), f"carrier {key}")
                  for key in ("f0", "symbol_rate", "alpha", "power")}
        if values["symbol_rate"] <= 0 or not 0 < values["alpha"] <= 1 or values["power"] <= 0:
            raise ValueError("carrier rate, roll-off and power must be positive")
        if not isinstance(item.mod, str) or (item.code_rate is not None and not isinstance(item.code_rate, str)):
            raise ValueError("carrier modulation and code rate must be strings")
        carrier = Carrier(**values, mod=item.mod, code_rate=item.code_rate)
        if abs(carrier.f0) + carrier.occupied_bw / 2 > bandwidth / 2 + 1e-6:
            raise ValueError("planned carrier occupied spectrum exceeds bandwidth")
        samples_per_symbol(carrier.symbol_rate, FS_SIM)
        try:
            constellation(carrier.mod, carrier.code_rate)
        except (ValueError, KeyError) as error:
            raise ValueError("unsupported planned carrier modulation or code rate") from error
        carriers.append(carrier)
    if not np.isclose(sum(c.power for c in carriers), 1.0, rtol=1e-6, atol=1e-8):
        raise ValueError("total planned carrier power must be one")
    return carriers, bandwidth, ci


def _waveform(carrier):
    def generate(rng, t0, n, fs):
        _rng(rng)
        starts = np.asarray(t0)
        if (starts.ndim != 1 or not starts.size or starts.dtype.kind not in "iuf"
                or not np.isfinite(starts).all() or np.any(starts < 0)
                or np.any(np.diff(starts) <= 0)):
            raise ValueError("t0 must be finite, nonnegative, strictly increasing snapshot start times")
        if isinstance(n, (bool, np.bool_)) or not isinstance(n, Integral) or n < 1:
            raise ValueError("n must be a positive integer")
        sample_rate = _real(fs, "fs")
        if sample_rate <= 0 or abs(carrier.f0) + carrier.occupied_bw / 2 >= sample_rate / 2:
            raise ValueError("fs must be positive and resolve the complete carrier spectrum")
        samples_per_symbol(carrier.symbol_rate, sample_rate)
        return generate_carrier(rng, carrier, len(starts), int(n), sample_rate)
    return generate


def _metadata(kind, stage, reference, carrier, ci):
    return {"kind": kind, "injection_stage": stage, "c_over_i_db": ci,
            "power_reference": reference, "carrier": asdict(carrier),
            "f_lo": carrier.f0 - carrier.occupied_bw / 2,
            "f_hi": carrier.f0 + carrier.occupied_bw / 2,
            "identifiability": "The simulator source is not uniquely identifiable from aggregate spectra alone."}


def carrier_under_carrier(rng: np.random.Generator, plan: list[Carrier], bandwidth: float,
                          c_over_i_db: float):
    """Draw an independent modulated uplink entirely within a planned victim.

    C/I is relative to *all* planned uplink carriers, not just the victim.
    ``victim_c_over_i_db`` records the corresponding victim-power ratio.
    Equal occupied widths are allowed when the narrowest supported victim
    leaves no room for a strictly narrower carrier. Containment refers to
    ideal occupied bands; finite observation windows can show FFT leakage.
    """
    carriers, _, ci = _request(rng, plan, bandwidth, c_over_i_db)
    options = [(index, [(rs, alpha) for rs in SYMBOL_RATES for alpha in ROLLOFFS
                        if rs * (1 + alpha) <= victim.occupied_bw + 1e-8])
               for index, victim in enumerate(carriers)]
    options = [(index, fits) for index, fits in options if fits]
    if not options:
        raise InfeasibleCarrierError("no planned victim can contain a supported modulated carrier")
    index, fits = options[int(rng.integers(len(options)))]
    victim = carriers[index]
    rs, alpha = fits[int(rng.integers(len(fits)))]
    half_slack = max(0.0, (victim.occupied_bw - rs * (1 + alpha)) / 2)
    carrier = Carrier(f0=float(rng.uniform(victim.f0 - half_slack, victim.f0 + half_slack)),
                      symbol_rate=float(rs), alpha=float(alpha),
                      mod=MODULATIONS[int(rng.integers(len(MODULATIONS)))], power=float(10 ** (-ci / 10)))
    metadata = _metadata("carrier_under_carrier", "uplink", "total_planned_uplink", carrier, ci)
    metadata.update(victim_index=index, victim=asdict(victim),
                    victim_c_over_i_db=float(ci + 10 * np.log10(victim.power)))
    return _waveform(carrier), metadata


def adjacent_satellite(rng: np.random.Generator, plan: list[Carrier], bandwidth: float,
                       c_over_i_db: float):
    """Draw a received in-band carrier for post-downlink-coupling injection.

    Placement is independent of the wanted operator plan. Its received
    power ratio is a scalar engineering assumption, not an antenna or
    satellite-separation calculation. The callback's nominal power must be
    scaled by the wanted receiver-feed power at the injection point.
    """
    _, bandwidth, ci = _request(rng, plan, bandwidth, c_over_i_db)
    options = [(rs, alpha) for rs in SYMBOL_RATES for alpha in ROLLOFFS
               if rs * (1 + alpha) <= bandwidth]
    rs, alpha = options[int(rng.integers(len(options)))]
    extent = (bandwidth - rs * (1 + alpha)) / 2
    carrier = Carrier(f0=float(rng.uniform(-extent, extent)), symbol_rate=float(rs), alpha=float(alpha),
                      mod=MODULATIONS[int(rng.integers(len(MODULATIONS)))], power=float(10 ** (-ci / 10)))
    return _waveform(carrier), _metadata("adjacent_satellite", "downlink", "wanted_receiver_feed", carrier, ci)
