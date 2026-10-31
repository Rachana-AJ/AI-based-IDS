"""Train the fixed six-class model and save artifacts for live inference."""

import argparse
import json
import pprint
import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from .pipeline import (
    CLASS_NAMES,
    CLASS_TO_ID,
    FEATURES,
    LOG_FEATURES,
    PROTOCOL_TO_ID,
    prepare_training_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "dataset" / "train_test_network.csv"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models"
MAX_DURATION = 12000
RANDOM_STATE = 42
PROFILE_COUNT = 5
PROFILE_CONFIDENCE_THRESHOLD = 0.95


class MulticlassModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(10, 22),
            nn.LeakyReLU(0.1),
            nn.Linear(22, 16),
            nn.LeakyReLU(0.1),
            nn.Linear(16, 14),
            nn.LeakyReLU(0.1),
            nn.Linear(14, 12),
            nn.LeakyReLU(0.1),
            nn.Linear(12, 6),
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.layers(values)


def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")

    data = pd.read_csv(path)
    if "type" not in data.columns:
        raise ValueError("Dataset must contain the 'type' target column")

    labels = data["type"].astype("string").str.strip().str.lower()
    data = data.loc[labels.isin(CLASS_TO_ID)].copy()
    data["type"] = labels.loc[data.index].map(CLASS_TO_ID)
    if data.empty:
        raise ValueError("Dataset contains none of the six configured classes")

    missing = [name for name in FEATURES if name not in data.columns]
    if missing:
        raise ValueError(f"Dataset is missing feature columns: {missing}")

    data["proto"] = (
        data["proto"]
        .astype("string")
        .str.strip()
        .str.lower()
        .map(PROTOCOL_TO_ID)
    )
    for name in FEATURES:
        data[name] = pd.to_numeric(data[name], errors="coerce")

    numeric = data.loc[:, FEATURES].to_numpy(dtype=np.float64)
    valid = np.isfinite(numeric).all(axis=1)
    valid &= data["duration"].to_numpy(dtype=np.float64) <= MAX_DURATION
    valid &= (numeric >= 0).all(axis=1)
    data = data.loc[valid].copy()
    if data.empty:
        raise ValueError("No valid rows remain after cleaning the dataset")

    class_counts = data["type"].value_counts()
    missing_classes = [
        name for name, class_id in CLASS_TO_ID.items()
        if class_counts.get(class_id, 0) < 2
    ]
    if missing_classes:
        raise ValueError(
            "Each class needs at least two valid rows for a stratified split; "
            f"insufficient classes: {missing_classes}"
        )

    features = prepare_training_features(data)
    targets = data["type"].to_numpy(dtype=np.int64)
    return features, targets


def _raw_profile(row: np.ndarray) -> dict[str, int | float]:
    profile: dict[str, int | float] = {}
    for index, name in enumerate(FEATURES):
        value = float(row[index])
        if name in LOG_FEATURES:
            value = float(np.expm1(value))
        profile[name] = int(value) if value.is_integer() else value
    return profile


def export_esp_profiles(
    transformed_test: np.ndarray,
    targets: np.ndarray,
    predictions: np.ndarray,
    confidences: np.ndarray,
) -> None:
    """Export a small random-choice pool of confidently correct held-out rows."""
    profiles: dict[str, list[dict[str, int | float]]] = {}
    for class_id, class_name in enumerate(CLASS_NAMES):
        eligible = np.flatnonzero(
            (targets == class_id)
            & (predictions == class_id)
            & (confidences >= PROFILE_CONFIDENCE_THRESHOLD)
        )
        if eligible.size == 0:
            raise ValueError(
                f"No correctly classified {class_name} holdout sample reached "
                f"{PROFILE_CONFIDENCE_THRESHOLD:.0%} confidence; cannot generate "
                "ESP demo profiles."
            )
        ranked = eligible[np.argsort(confidences[eligible])[::-1]]
        profiles[class_name.upper()] = [
            _raw_profile(transformed_test[index])
            for index in ranked[:PROFILE_COUNT]
        ]

    source = (
        '"""Randomly selected held-out dataset profiles for lab demonstration."""\n'
        "PROFILES = "
        + pprint.pformat(profiles, width=88, sort_dicts=False)
        + "\n"
    )
    esp_root = PROJECT_ROOT.parent / "esp_related_files"
    for device_dir in (esp_root / "esp_1", esp_root / "esp_2"):
        if not device_dir.is_dir():
            raise FileNotFoundError(f"ESP firmware directory not found: {device_dir}")
        (device_dir / "profiles.py").write_text(source, encoding="utf-8")


def train(dataset_path: Path, model_dir: Path) -> None:
    random.seed(RANDOM_STATE)
    np.random.seed(RANDOM_STATE)
    torch.manual_seed(RANDOM_STATE)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RANDOM_STATE)

    raw_features, targets = load_dataset(dataset_path)
    x_train, x_test, y_train, y_test = train_test_split(
        raw_features,
        targets,
        test_size=0.30,
        random_state=RANDOM_STATE,
        stratify=targets,
    )

    profile_features = x_test.copy()
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train).astype(np.float32)
    x_test = scaler.transform(x_test).astype(np.float32)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = MulticlassModel().to(device)
    train_data = TensorDataset(
        torch.from_numpy(x_train),
        torch.from_numpy(y_train.astype(np.int64)),
    )
    generator = torch.Generator().manual_seed(RANDOM_STATE)
    loader = DataLoader(
        train_data,
        batch_size=512,
        shuffle=True,
        generator=generator,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_function = nn.CrossEntropyLoss()

    for epoch in range(50):
        model.train()
        total_loss = 0.0
        for features, labels in loader:
            features, labels = features.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = loss_function(model(features), labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(
            f"Epoch {epoch + 1:02d}/50 - "
            f"loss {total_loss / len(loader):.4f}"
        )

    model.eval()
    with torch.no_grad():
        probabilities = torch.softmax(
            model(torch.from_numpy(x_test).to(device)),
            dim=1,
        )
    predicted_ids = probabilities.argmax(dim=1).cpu().numpy()
    confidences = probabilities.max(dim=1).values.cpu().numpy()
    print(
        classification_report(
            y_test,
            predicted_ids,
            labels=list(range(len(CLASS_NAMES))),
            target_names=list(CLASS_NAMES),
            digits=4,
            zero_division=0,
        )
    )
    export_esp_profiles(profile_features, y_test, predicted_ids, confidences)

    model_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {key: value.detach().cpu() for key, value in model.state_dict().items()},
        model_dir / "ids_model.pth",
    )
    joblib.dump(scaler, model_dir / "ids_scaler.pkl")
    metadata = {
        "feature_order": list(FEATURES),
        "class_to_id": CLASS_TO_ID,
        "class_names": list(CLASS_NAMES),
        "protocol_to_id": PROTOCOL_TO_ID,
        "log1p_features": list(LOG_FEATURES),
        "random_state": RANDOM_STATE,
        "max_duration": MAX_DURATION,
    }
    (model_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(f"Saved model and preprocessing artifacts to: {model_dir}")
    print("Generated held-out demo profile pools in both ESP firmware folders.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    train(args.dataset, args.model_dir)


if __name__ == "__main__":
    main()
