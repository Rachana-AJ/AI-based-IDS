"""Shared feature schema and transformations for training and inference."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

FEATURES = (
    "duration",
    "src_port",
    "dst_port",
    "proto",
    "src_bytes",
    "dst_bytes",
    "src_pkts",
    "dst_pkts",
    "src_ip_bytes",
    "dst_ip_bytes",
)

LOG_FEATURES = (
    "duration",
    "src_bytes",
    "dst_bytes",
    "src_pkts",
    "dst_pkts",
    "src_ip_bytes",
    "dst_ip_bytes",
)

PROTOCOL_TO_ID = {"tcp": 1, "udp": 2, "icmp": 3}
CLASS_TO_ID = {
    "normal": 0,
    "scanning": 1,
    "dos": 2,
    "ddos": 3,
    "ransomware": 4,
    "backdoor": 5,
}
CLASS_NAMES = tuple(CLASS_TO_ID)


def _protocol_id(value: Any) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in PROTOCOL_TO_ID:
            return float(PROTOCOL_TO_ID[normalized])
        try:
            value = float(normalized)
        except ValueError as exc:
            raise ValueError(f"Unsupported protocol value: {value!r}") from exc

    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported protocol value: {value!r}") from exc

    if not np.isfinite(numeric) or numeric not in (1.0, 2.0, 3.0):
        raise ValueError(f"Unsupported protocol value: {value!r}")
    return numeric


def _validated_values(values: Mapping[str, Any]) -> list[float]:
    if not isinstance(values, Mapping):
        raise ValueError("features must be a JSON object")

    missing = [name for name in FEATURES if name not in values]
    extra = [name for name in values if name not in FEATURES]
    if missing or extra:
        raise ValueError(
            f"Feature keys mismatch; missing={missing}, unexpected={extra}"
        )

    row: list[float] = []
    for name in FEATURES:
        value = _protocol_id(values[name]) if name == "proto" else values[name]
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not np.isfinite(numeric):
            raise ValueError(f"{name} must be finite")
        if numeric < 0:
            raise ValueError(f"{name} must be non-negative")
        row.append(numeric)

    for name in LOG_FEATURES:
        index = FEATURES.index(name)
        row[index] = float(np.log1p(row[index]))
    return row


def prepare_live_features(values: Mapping[str, Any]) -> np.ndarray:
    """Validate and transform one ESP feature object into model input order."""
    return np.asarray([_validated_values(values)], dtype=np.float64)


def prepare_training_features(frame: pd.DataFrame) -> np.ndarray:
    """Apply the same protocol encoding and log transforms to dataset rows."""
    missing = [name for name in FEATURES if name not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing feature columns: {missing}")

    selected = frame.loc[:, FEATURES].copy()
    selected["proto"] = selected["proto"].map(
        lambda value: _protocol_id(value)
    )
    for name in FEATURES:
        selected[name] = pd.to_numeric(selected[name], errors="coerce")

    values = selected.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Dataset features contain missing or non-finite values")
    if (values < 0).any():
        raise ValueError("Dataset features contain negative values")

    for name in LOG_FEATURES:
        selected[name] = np.log1p(selected[name])
    return selected.to_numpy(dtype=np.float64)
