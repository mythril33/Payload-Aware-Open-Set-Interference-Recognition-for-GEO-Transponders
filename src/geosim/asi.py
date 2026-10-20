"""Uplink adjacent-satellite interference (ASI) from an adjacent GSO network's earth station (K5, P18).

An earth station of an adjacent network points at its own satellite. Its
off-axis radiation toward our satellite is a co-frequency, co-polar carrier
that enters our receive antenna, so the event passes IMUX, TWTA and OMUX like
any uplink signal. Single-entry geometry follows the ITU Radiocommunication
Bureau uplink C/I method (R19-WRS20-C-0013, eq. 11-12): with co-coverage and
equal path loss, the PSD ratio at the satellite input is

    C/I_psd = Gmax - G(phi) - delta_eirp_density_db

where Gmax is the interfering antenna's boresight gain, G(phi) its gain toward
our satellite and delta_eirp_density_db its on-axis EIRP density relative to
our planned carriers. phi is the angle between the interferer's actual
boresight and our satellite.

Sources and assumptions (P18 section 2):
- Separation: two-degree GSO spacing (FCC 47 CFR Part 25). The topocentric angle
  of a 2-degree geocentric spacing is 2 x 42164 km / slant range: 2.06 deg at low
  elevation (Brooker, AIAA: +/-2.08 deg at 10 deg elevation) to 2.36 deg at the
  sub-satellite point.
- Pattern "S.1428": ITU-R S.1428-1 complete reference pattern (main lobe
  Gmax - 2.5e-3 (D phi / lambda)^2, first-sidelobe plateau G1, then the
  29 - 25 log phi design objective of ITU-R S.580-6). Gmax = 20 log(D/lambda)
  + 7.7 dBi (+8.4 above D/lambda = 100), from the same Recommendation.
- Pattern "S.465": the older ITU-R S.465-6 envelope 32 - 25 log phi from
  phi_min = max(1 deg, 100 lambda/D) (D/lambda >= 50) or max(2 deg, 114
  (D/lambda)^-1.09) (D/lambda < 50); it defines no main lobe, so inside and near
  phi_min the larger of the S.1428-1 gain and the S.465 value at phi_min is used.
- Pointing error: magnitude 0-0.4 half-power beamwidths, theta_3dB = 69.3 lambda/D
  (ITU-R F.699-6 recommends 4.1), in a uniformly random direction [assumption;
  0.4 theta_3dB costs the interferer 1.9 dB on its own link and is 0.78 deg for
  0.75 m, matching Brooker's ~0.8 deg for sub-metre Ku VSATs peaked by hand].
- Antenna diameters 0.75-2.4 m [assumption; VSAT to SNG sizes].
- Delta EIRP density -3...+6 dB [assumption; +6 dB covers a misconfigured uplink].
- 20-80 % of the interferer's occupied band overlaps planned carriers [class
  definition, not physics]: with no overlap it is an unauthorized carrier in a
  gap, fully inside one carrier it is a carrier-under-carrier event.
Coordinated stations in an FCC Ku filing sit at 23.6-31.2 dB uplink C/I; the
mispointed and misconfigured tail reaches a few dB.

geosim.events.adjacent_satellite is the downlink counterpart (a received
carrier injected after the wanted payload); this factory feeds the uplink
interferer slot of simulate/simulate_dual, like carrier_under_carrier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .events import _metadata, _request, _waveform
from .interferers import InfeasibleCarrierError
from .plan import SYMBOL_RATES
from .waveform import MODULATIONS, ROLLOFFS, Carrier

C_LIGHT = 299_792_458.0
PATTERNS = ("S.1428", "S.465")
PLACEMENT_GRID = 4001                                   # candidate centres per symbol rate and roll-off
SOURCES = ("ITU BR R19-WRS20-C-0013 eq. 11-12", "ITU-R S.1428-1", "ITU-R S.580-6", "ITU-R S.465-6",
           "ITU-R F.699-6 recommends 4.1", "FCC 47 CFR Part 25 two-degree spacing",
           "Brooker, AIAA, antenna pointing accuracy")


@dataclass(frozen=True)
class AsiRanges:
    frequency_hz: float = 14.25e9                       # Ku uplink, 13.75-14.5 GHz band
    diameters_m: tuple = (0.75, 0.96, 1.2, 1.8, 2.4)
    separation_deg: tuple = (2.06, 2.36)                # topocentric angle of 2-degree spacing
    pointing_error_beamwidths: tuple = (0.0, 0.4)
    delta_eirp_density_db: tuple = (-3.0, 6.0)
    s465_probability: float = 0.5                       # else the S.1428-1 / S.580 pattern
    overlap: tuple = (0.2, 0.8)                         # fraction of the interferer band inside the plan

    def __post_init__(self):
        if not 10.7e9 <= self.frequency_hz <= 30e9:
            raise ValueError("ITU-R S.1428-1 covers 10.7-30 GHz")
        if not self.diameters_m or min(self.diameters_m) * self.frequency_hz / C_LIGHT < 33.3:
            raise ValueError("diameters must give D/lambda >= 33.3 (implemented S.465-6 range)")
        for name in ("separation_deg", "pointing_error_beamwidths", "delta_eirp_density_db", "overlap"):
            lo, hi = getattr(self, name)
            if not lo <= hi:
                raise ValueError(f"{name} must be an ordered interval")
        if not 0 <= self.s465_probability <= 1 or not (0 <= self.overlap[0] and self.overlap[1] <= 1):
            raise ValueError("s465_probability and overlap must lie in [0, 1]")
        if self.pointing_error_beamwidths[0] < 0 or self.separation_deg[0] <= 0:
            raise ValueError("pointing error must be nonnegative and separation positive")


DEFAULT_RANGES = AsiRanges()


def beamwidth_deg(d_over_lambda: float) -> float:
    """Half-power beamwidth from ITU-R F.699-6: D/lambda ~ 69.3 / theta."""
    return 69.3 / d_over_lambda


def s1428_gain_dbi(phi_deg: float, d_over_lambda: float) -> tuple[float, str]:
    """ITU-R S.1428-1 reference gain at phi and the pattern region it falls in."""
    phi, dl = abs(phi_deg), d_over_lambda
    if dl < 20:
        raise ValueError("ITU-R S.1428-1 starts at D/lambda = 20")
    if dl <= 100:
        gmax, g1, phi_r = 20 * np.log10(dl) + 7.7, 29 - 25 * np.log10(95 / dl), 95 / dl
    else:
        gmax, g1, phi_r = 20 * np.log10(dl) + 8.4, -1 + 15 * np.log10(dl), 15.85 * dl ** -0.6
    phi_m = 20 / dl * np.sqrt(gmax - g1)
    if phi < phi_m:
        return float(gmax - 2.5e-3 * (dl * phi) ** 2), "main_lobe"
    if phi < phi_r:
        return float(g1), "first_sidelobe"
    if dl <= 100:
        if phi <= 33.1:
            return float(29 - 25 * np.log10(phi)), "sidelobe"
        if phi <= 80:
            return -9.0, "far"
        return (-5.0 if dl <= 25 else (-4.0 if phi <= 120 else -9.0)), "far"
    if phi < 10:
        return float(29 - 25 * np.log10(phi)), "sidelobe"
    if phi < 34.1:
        return float(34 - 30 * np.log10(phi)), "sidelobe"
    return (-7.0 if 80 <= phi < 120 else -12.0), "far"


def max_gain_dbi(d_over_lambda: float) -> float:
    return s1428_gain_dbi(0.0, d_over_lambda)[0]


def s465_phi_min_deg(d_over_lambda: float) -> float:
    """Smallest off-axis angle where the ITU-R S.465-6 envelope applies (D/lambda >= 33.3)."""
    if d_over_lambda >= 50:
        return float(max(1.0, 100.0 / d_over_lambda))
    return float(max(2.0, 114.0 * d_over_lambda ** -1.09))


def gain_dbi(phi_deg: float, d_over_lambda: float, pattern: str) -> tuple[float, str]:
    """Gain toward phi for one of PATTERNS; returns (gain, region)."""
    if pattern not in PATTERNS:
        raise ValueError(f"pattern must be one of {PATTERNS}")
    gain, region = s1428_gain_dbi(phi_deg, d_over_lambda)
    if pattern == "S.1428":
        return gain, region
    if d_over_lambda < 33.3:
        raise ValueError("S.465-6 phi_min is implemented for D/lambda >= 33.3")
    phi = abs(phi_deg)
    envelope = 32 - 25 * np.log10(max(phi, s465_phi_min_deg(d_over_lambda))) if phi < 48 else -10.0
    return (gain, region) if gain >= envelope else (float(envelope), "s465_envelope")


def draw_geometry(rng: np.random.Generator, ranges: AsiRanges = DEFAULT_RANGES) -> dict:
    diameter = float(ranges.diameters_m[int(rng.integers(len(ranges.diameters_m)))])
    d_over_lambda = diameter * ranges.frequency_hz / C_LIGHT
    pattern = "S.465" if rng.uniform() < ranges.s465_probability else "S.1428"
    separation = float(rng.uniform(*ranges.separation_deg))
    theta = beamwidth_deg(d_over_lambda)
    error = float(rng.uniform(*ranges.pointing_error_beamwidths) * theta)
    direction = float(rng.uniform(0, 360))          # 0 deg: boresight error points at our satellite
    off_axis = float(np.hypot(separation - error * np.cos(np.radians(direction)),
                              error * np.sin(np.radians(direction))))
    delta = float(rng.uniform(*ranges.delta_eirp_density_db))
    gmax = max_gain_dbi(d_over_lambda)
    gain, region = gain_dbi(off_axis, d_over_lambda, pattern)
    return {"diameter_m": diameter, "d_over_lambda": float(d_over_lambda), "pattern": pattern,
            "beamwidth_deg": theta, "separation_deg": separation, "pointing_error_deg": error,
            "pointing_direction_deg": direction, "off_axis_deg": off_axis, "pattern_region": region,
            "max_gain_dbi": gmax, "gain_toward_victim_dbi": gain, "discrimination_db": gmax - gain,
            "own_link_pointing_loss_db": float(12 * (error / theta) ** 2),
            "delta_eirp_density_db": delta, "c_over_i_psd_db": gmax - gain - delta}


def overlap_fraction(f_lo, f_hi, plan: list[Carrier]):
    """Fraction of [f_lo, f_hi] covered by the planned carriers' occupied bands (broadcasts over arrays)."""
    f_lo, f_hi = np.asarray(f_lo, float), np.asarray(f_hi, float)
    covered = sum(np.maximum(0.0, np.minimum(f_hi, c.f0 + c.occupied_bw / 2) - np.maximum(f_lo, c.f0 - c.occupied_bw / 2))
                  for c in plan)
    out = np.minimum(1.0, covered / (f_hi - f_lo))
    return float(out) if out.ndim == 0 else out


def place_carrier(rng: np.random.Generator, plan: list[Carrier], bandwidth: float, overlap: tuple):
    """Uniform (rate, roll-off), then a uniform centre among those meeting the overlap range."""
    options = []
    for rs in SYMBOL_RATES:
        for alpha in ROLLOFFS:
            width = rs * (1 + alpha)
            if width > bandwidth:
                continue
            f0 = np.linspace(-(bandwidth - width) / 2, (bandwidth - width) / 2, PLACEMENT_GRID)
            frac = overlap_fraction(f0 - width / 2, f0 + width / 2, plan)
            ok = f0[(frac >= overlap[0]) & (frac <= overlap[1])]
            if ok.size:
                options.append((rs, alpha, ok))
    if not options:
        raise InfeasibleCarrierError("no supported carrier meets the adjacent-satellite overlap range")
    rs, alpha, ok = options[int(rng.integers(len(options)))]
    return float(rs), float(alpha), float(ok[int(rng.integers(ok.size))])


def adjacent_satellite_uplink(rng: np.random.Generator, plan: list[Carrier], bandwidth: float,
                              ranges: AsiRanges = DEFAULT_RANGES):
    """Draw one uplink ASI carrier; returns (generate(rng, t0, n, fs), metadata).

    The adjacent network's carrier plan is independent of ours, so the interferer's
    rate and roll-off are drawn from the supported set and its centre uniformly among
    positions whose overlap with our plan lies in ``ranges.overlap``. Its PSD is
    C/I_psd below the plan's mean PSD; ``c_over_i_db`` is relative to the total
    planned uplink power of one.
    """
    carriers, bandwidth, _ = _request(rng, plan, bandwidth, 0.0)     # C/I comes from the geometry
    geometry = draw_geometry(rng, ranges)
    rs, alpha, f0 = place_carrier(rng, carriers, bandwidth, ranges.overlap)
    mean_psd = sum(c.power for c in carriers) / sum(c.symbol_rate for c in carriers)
    carrier = Carrier(f0=f0, symbol_rate=rs, alpha=alpha, mod=MODULATIONS[int(rng.integers(len(MODULATIONS)))],
                      power=float(mean_psd * rs * 10 ** (-geometry["c_over_i_psd_db"] / 10)))
    metadata = _metadata("adjacent_satellite", "uplink", "total_planned_uplink", carrier,
                         float(-10 * np.log10(carrier.power)))
    metadata.update(c_over_i_psd_db=geometry["c_over_i_psd_db"], geometry=geometry,
                    overlap_fraction=overlap_fraction(metadata["f_lo"], metadata["f_hi"], carriers),
                    ranges=asdict(ranges), sources=list(SOURCES))
    return _waveform(carrier), metadata
