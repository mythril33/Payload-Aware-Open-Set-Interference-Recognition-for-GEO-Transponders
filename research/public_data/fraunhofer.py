"""Small readers for the published Fraunhofer FIOT/LC laboratory data.

The publisher labels are GNSS interference labels, never B2/GEO labels. LC
files contain receiver features, not IQ. Released FIOT NPY crops are rendered
RGB spectrogram images (512 x 243 x 3 int32), not calibrated PSD or raw IQ.
FIOT crops from one recording must
remain in one partition. No downloading, fitting or B2 observation access occurs
here. Empty LC records are returned explicitly so callers report abstentions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path, PurePosixPath
import re
from typing import Iterator

import numpy as np

CLASSES = {0: "None", 1: "Noise", 2: "Chirp", 3: "FreqHopper", 4: "Modulated",
           5: "Multitone", 6: "Pulsed", 7: "Cw", 8: "Tone"}
LC_COLUMNS = 308
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SPLIT_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 2048
FIOT_SHAPE = (512, 243, 3)


class DataError(ValueError):
    pass


class SplitLeakage(DataError):
    pass


@dataclass(frozen=True)
class SampleRef:
    path: str
    label: int
    recording_id: str
    crop: int | None
    subjammer: int
    power: float


@dataclass(frozen=True)
class Sample(SampleRef):
    values: np.ndarray
    sha256: str


def _kind(kind):
    if kind not in ("lc", "fiot"):
        raise DataError("kind must be lc (receiver features) or fiot (spectrogram crops)")


def parse_split(path, *, kind="lc") -> list[SampleRef]:
    """Parse the publisher's four columns, retaining its actual class IDs.

    Power and sub-jammer metadata are carried for auditing, not model inputs.
    The five-digit recording ID, without the FIOT crop suffix, is the split unit.
    """
    _kind(kind)
    source = Path(path)
    if source.stat().st_size > MAX_SPLIT_BYTES:
        raise DataError("split file exceeds the bounded metadata limit")
    rows, seen = [], set()
    prefix = "data_LC" if kind == "lc" else "data_FIOT"
    pattern = re.compile(r"([0-9]{5})\.npy" if kind == "lc" else r"([0-9]{5})_([0-5])\.npy")
    for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 4:
            raise DataError(f"split line {number} must have filename/class/subjammer/power")
        relative = PurePosixPath(fields[0])
        if (len(relative.parts) != 2 or relative.parts[0] != prefix
                or "\\" in fields[0] or relative.as_posix() != fields[0]):
            raise DataError("unexpected publisher path or traversal")
        match = pattern.fullmatch(relative.name)
        if match is None or fields[0] in seen:
            raise DataError("invalid or repeated publisher filename")
        try:
            label, subjammer, power = int(fields[1]), int(fields[2]), float(fields[3])
        except ValueError as error:
            raise DataError("invalid class or metadata value") from error
        if label not in CLASSES or subjammer < -1 or not math.isfinite(power):
            raise DataError("unsupported class, subjammer or nonfinite power metadata")
        rows.append(SampleRef(fields[0], label, match[1], None if kind == "lc" else int(match[2]), subjammer, power))
        seen.add(fields[0])
    if not rows:
        raise DataError("empty publisher split")
    return rows


def audit_partitions(train: list[SampleRef], test: list[SampleRef]) -> dict:
    """Refuse recording leakage, including different crops or modalities.

    This checks the published recording ID, not a stronger unprovided session,
    vehicle or acquisition-day identity. Those generalization axes remain unknown.
    """
    if not train or not test:
        raise DataError("both train and test metadata populations are required")
    identities = []
    for rows in (train, test):
        labels = {}
        for row in rows:
            if row.recording_id in labels and labels[row.recording_id] != row.label:
                raise DataError("one recording has inconsistent native class labels")
            labels[row.recording_id] = row.label
        identities.append(set(labels))
    overlap = identities[0] & identities[1]
    if overlap:
        raise SplitLeakage(f"train/test share {len(overlap)} recording IDs, including crops")
    def describe(rows):
        return {"samples": len(rows), "recordings": len({r.recording_id for r in rows}),
                "class_counts": dict(sorted(Counter(r.label for r in rows).items()))}
    return {"split_unit": "publisher_recording_id", "train": describe(train), "test": describe(test),
            "recording_overlap": 0, "session_independence": "UNKNOWN_NOT_PROVIDED"}


def iter_records(root, rows: list[SampleRef], *, kind="lc", max_records=MAX_RECORDS) -> Iterator[Sample]:
    """Read one bounded numeric NPY at a time; never enables pickle.

    ``root`` is the extracted data_LC/data_lc or data_FIOT directory itself.
    Selection, including optional crop-0 selection, must be made from metadata
    before this call, without using held-out signal values or test scores.
    Empty LC arrays are valid availability observations; callers must count them.
    """
    _kind(kind)
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS or not 0 < len(rows) <= max_records:
        raise DataError("select 1..2048 recording/crop rows before bounded loading")
    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise DataError("an existing extracted data directory is required")
    for row in rows:
        if not isinstance(row, SampleRef):
            raise DataError("parse publisher split metadata before loading")
        prefix = "data_LC" if kind == "lc" else "data_FIOT"
        expected_name = row.recording_id + ("" if kind == "lc" else "_" + str(row.crop)) + ".npy"
        if (not re.fullmatch(r"[0-9]{5}", row.recording_id) or row.label not in CLASSES
                or row.path != prefix + "/" + expected_name
                or (kind == "lc" and row.crop is not None)
                or (kind == "fiot" and (type(row.crop) is not int or row.crop not in range(6)))):
            raise DataError("sample metadata differs from the selected publisher representation")
        filename = PurePosixPath(row.path).name
        source = directory / filename
        if source.is_symlink() or not source.is_file() or not 0 < source.stat().st_size <= MAX_FILE_BYTES:
            raise DataError("missing, aliased or oversized numeric data file")
        with source.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise DataError("numeric data file exceeds the read budget")
        try:
            values = np.load(io.BytesIO(raw), allow_pickle=False)
        except (ValueError, OSError, EOFError) as error:
            raise DataError("invalid numeric NPY; object/pickle arrays are not accepted") from error
        if not isinstance(values, np.ndarray) or values.dtype.kind not in "iuf" or not np.isfinite(values).all():
            raise DataError("finite real numeric values required")
        if kind == "lc" and (values.ndim != 2 or values.shape[1] != LC_COLUMNS or not 0 <= values.shape[0] <= 10):
            raise DataError("LC data must have 0..10 timesteps and 308 documented receiver columns")
        if kind == "fiot" and (values.shape != FIOT_SHAPE or values.dtype != np.dtype("int32")
                               or values.min() < 0 or values.max() > 255):
            raise DataError("released FIOT crops must be 512x243x3 int32 RGB images, not IQ or calibrated power")
        yield Sample(row.path, row.label, row.recording_id, row.crop, row.subjammer, row.power,
                     values, hashlib.sha256(raw).hexdigest())
