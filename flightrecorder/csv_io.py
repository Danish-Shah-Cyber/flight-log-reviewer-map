from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .model import FlightSample


def write_samples(path: str | Path, samples: Iterable[FlightSample]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FlightSample.column_names())
        writer.writeheader()
        for sample in samples:
            writer.writerow(sample.to_dict())


def read_samples(path: str | Path) -> list[FlightSample]:
    samples: list[FlightSample] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            try:
                values: dict[str, object] = {}
                for name in FlightSample.column_names():
                    raw = row.get(name)
                    if raw is None or raw == "":
                        continue
                    if name in {"mode", "source_integrity"}:
                        values[name] = raw
                    elif name == "armed":
                        values[name] = raw.strip().lower() in {"1", "true", "yes"}
                    else:
                        values[name] = float(raw)
                samples.append(FlightSample(**values))
            except ValueError as error:
                raise ValueError(f"Invalid value on CSV row {row_number}: {error}") from error
    if not samples:
        raise ValueError("The CSV contains no flight samples")
    samples.sort(key=lambda sample: sample.time_s)
    return samples
