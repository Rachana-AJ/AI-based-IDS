"""MQTT inference service and local REST API for a future dashboard."""

import json
import logging
import os
import re
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import paho.mqtt.client as mqtt
import torch
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .decision import ConsecutiveDetectionPolicy
from .pipeline import (
    CLASS_NAMES,
    FEATURES,
    LOG_FEATURES,
    PROTOCOL_TO_ID,
    prepare_live_features,
)
from .train_model import MulticlassModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("MODEL_DIR", PROJECT_ROOT / "models"))
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "ids-backend")
AUTO_BLOCK_CONFIDENCE = float(os.getenv("AUTO_BLOCK_CONFIDENCE", "0.90"))
AUTO_BLOCK_CONSECUTIVE = int(os.getenv("AUTO_BLOCK_CONSECUTIVE", "3"))
LOG = logging.getLogger("ids.backend")


class InferenceEngine:
    def __init__(self, model_dir: Path) -> None:
        model_path = model_dir / "ids_model.pth"
        scaler_path = model_dir / "ids_scaler.pkl"
        metadata_path = model_dir / "metadata.json"
        if (
            not model_path.is_file()
            or not scaler_path.is_file()
            or not metadata_path.is_file()
        ):
            raise FileNotFoundError(
                "Trained artifacts are missing. Run "
                "'python -m backend.train_model' first."
            )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("feature_order") != list(FEATURES):
            raise ValueError("Model metadata feature order does not match the service")
        if metadata.get("class_names") != list(CLASS_NAMES):
            raise ValueError("Model metadata class order does not match the service")
        if metadata.get("protocol_to_id") != PROTOCOL_TO_ID:
            raise ValueError("Model metadata protocol mapping does not match the service")
        if metadata.get("log1p_features") != list(LOG_FEATURES):
            raise ValueError("Model metadata log transforms do not match the service")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = MulticlassModel().to(self.device)
        state = torch.load(model_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()
        self.scaler = joblib.load(scaler_path)
        self._lock = threading.Lock()

    def predict(self, features: dict[str, Any]) -> tuple[str, float]:
        pred, conf, _ = self.predict_full(features)
        return pred, conf

    def predict_full(self, features: dict[str, Any]) -> tuple[str, float, dict[str, float]]:
        prepared = prepare_live_features(features)
        scaled = self.scaler.transform(prepared).astype(np.float32)
        tensor = torch.from_numpy(scaled).to(self.device)
        with self._lock, torch.no_grad():
            probabilities = torch.softmax(self.model(tensor), dim=1)[0]
        class_id = int(probabilities.argmax().item())
        probs_dict = {
            CLASS_NAMES[i]: round(float(probabilities[i].item()), 4)
            for i in range(len(CLASS_NAMES))
        }
        return CLASS_NAMES[class_id], float(probabilities[class_id].item()), probs_dict


class DeviceState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.devices: dict[str, dict[str, Any]] = {}
        self.blocked: set[str] = set()
        self.events: deque[dict[str, Any]] = deque(maxlen=500)
        self.policy = ConsecutiveDetectionPolicy(
            confidence_threshold=AUTO_BLOCK_CONFIDENCE,
            required_count=AUTO_BLOCK_CONSECUTIVE,
        )
        self.total_flows: int = 0
        self.clean_streak: int = 0
        self.total_attacks: int = 0
        self.class_counts: dict[str, int] = {c: 0 for c in CLASS_NAMES}
        self.ws_clients: list[Any] = []

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_event(self, event: dict[str, Any]) -> None:
        with self.lock:
            self.events.appendleft({"timestamp": self._timestamp(), **event})

    def device_snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {**value, "blocked": device_id in self.blocked}
                for device_id, value in sorted(self.devices.items())
            ]

    def event_snapshot(self, limit: int) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.events)[:limit]

    def is_blocked(self, device_id: str) -> bool:
        with self.lock:
            return device_id in self.blocked

    def record_status(self, device_id: str, payload: dict[str, Any]) -> None:
        with self.lock:
            device = self.devices.setdefault(
                device_id,
                {"device_id": device_id, "last_seen": None},
            )
            device.update(
                {
                    "last_seen": self._timestamp(),
                    "device_status": payload.get("status", "UNKNOWN"),
                    "state": payload.get("state", "UNKNOWN"),
                    "reported_attack_type": payload.get("attack_type", "UNKNOWN"),
                }
            )
        self.add_event(
            {
                "device_id": device_id,
                "kind": "status",
                "status": payload.get("status", "UNKNOWN"),
                "state": payload.get("state", "UNKNOWN"),
            }
        )

    def record_prediction(
        self,
        device_id: str,
        payload: dict[str, Any],
        prediction: str,
        confidence: float,
        probabilities: dict[str, float] | None = None,
    ) -> bool:
        features = payload.get("features", {})
        with self.lock:
            self.total_flows += 1
            self.class_counts[prediction] = self.class_counts.get(prediction, 0) + 1
            if prediction == "normal":
                self.clean_streak += 1
            else:
                self.total_attacks += 1
                self.clean_streak = 0

            device = self.devices.setdefault(
                device_id,
                {"device_id": device_id, "last_seen": None},
            )
            device.update(
                {
                    "last_seen": self._timestamp(),
                    "device_status": payload.get("device_status", "ONLINE"),
                    "state": payload.get("state", "UNKNOWN"),
                    "prediction": prediction,
                    "confidence": confidence,
                    "probabilities": probabilities or {},
                    "reported_attack_type": payload.get("attack_type", "NONE"),
                    "data_origin": payload.get(
                        "data_origin",
                        "legacy_or_unspecified",
                    ),
                    "sequence": payload.get("sequence"),
                    "features": features,
                }
            )
            should_block = (
                device_id not in self.blocked
                and self.policy.observe(device_id, prediction, confidence)
            )
            if should_block:
                self.blocked.add(device_id)
        self.add_event(
            {
                "device_id": device_id,
                "kind": "prediction",
                "prediction": prediction,
                "confidence": confidence,
                "probabilities": probabilities or {},
                "features": features,
                "reported_attack_type": payload.get("attack_type", "NONE"),
                "data_origin": payload.get("data_origin", "legacy_or_unspecified"),
                "sequence": payload.get("sequence"),
            }
        )
        if should_block:
            self.add_event(
                {
                    "device_id": device_id,
                    "kind": "automatic_block",
                    "reason": (
                        f"{prediction.upper()} repeated at confidence "
                        f">= {AUTO_BLOCK_CONFIDENCE:.0%}"
                    ),
                }
            )
        return should_block

    def set_blocked(self, device_id: str, blocked: bool) -> None:
        with self.lock:
            if blocked:
                self.blocked.add(device_id)
            else:
                self.blocked.discard(device_id)
                self.policy.reset(device_id)
            self.devices.setdefault(
                device_id,
                {"device_id": device_id, "last_seen": None},
            )["blocked"] = blocked
        self.add_event(
            {
                "device_id": device_id,
                "kind": "block" if blocked else "unblock",
                "source": "server",
            }
        )


class MqttRuntime:
    def __init__(self, engine: InferenceEngine, state: DeviceState) -> None:
        self.engine = engine
        self.state = state
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def start(self) -> None:
        self.start_proxy()
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.client.loop_start()

    def start_proxy(self, proxy_port: int = 1884) -> None:
        def proxy_thread():
            import socket
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(('0.0.0.0', proxy_port))
                server.listen(10)
                server.settimeout(1.0)
            except Exception as e:
                LOG.warning("Proxy bind warning on port %s: %s", proxy_port, e)
                return

            def forward(src, dst):
                try:
                    while True:
                        data = src.recv(4096)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try: src.close()
                    except: pass
                    try: dst.close()
                    except: pass

            while True:
                try:
                    client_sock, _ = server.accept()
                    broker_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    broker_sock.connect((MQTT_HOST, MQTT_PORT))
                    threading.Thread(target=forward, args=(client_sock, broker_sock), daemon=True).start()
                    threading.Thread(target=forward, args=(broker_sock, client_sock), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
            server.close()

        threading.Thread(target=proxy_thread, daemon=True).start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: Any,
        _flags: dict[str, Any],
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if reason_code.is_failure:
            LOG.error("MQTT connection failed: %s", reason_code)
            return
        client.subscribe("iot/+/data", qos=1)
        client.subscribe("iot/+/status", qos=1)
        LOG.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)

    @staticmethod
    def _device_from_topic(topic: str, channel: str) -> str:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "iot" or parts[2] != channel:
            raise ValueError(f"Unexpected MQTT topic: {topic}")
        device_id = parts[1]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", device_id):
            raise ValueError(f"Invalid device ID in topic: {topic}")
        return device_id

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be a JSON object")

            channel = message.topic.rsplit("/", 1)[-1]
            device_id = self._device_from_topic(message.topic, channel)
            if payload.get("device_id") != device_id:
                raise ValueError("Payload device_id does not match MQTT topic")

            if channel == "status":
                self.state.record_status(device_id, payload)
                return
            if channel != "data":
                raise ValueError(f"Unsupported MQTT channel: {channel}")
            if self.state.is_blocked(device_id):
                LOG.warning("Ignoring telemetry from server-blocked device %s", device_id)
                return

            features = payload.get("features")
            prediction, confidence, probabilities = self.engine.predict_full(features)
            should_block = self.state.record_prediction(
                device_id,
                payload,
                prediction,
                confidence,
                probabilities,
            )
            LOG.info(
                "%s predicted %s at %.3f (reported=%s)",
                device_id,
                prediction,
                confidence,
                payload.get("attack_type", "NONE"),
            )
            if should_block:
                self.publish_command(device_id, "BLOCK")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            LOG.warning("Rejected MQTT message on %s: %s", message.topic, exc)
        except Exception:
            LOG.exception("Failed to process MQTT message on %s", message.topic)

    def publish_command(self, device_id: str, command: str) -> None:
        info = self.client.publish(
            f"iot/{device_id}/control",
            command,
            qos=1,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"Failed to publish {command} to {device_id}: MQTT rc={info.rc}"
            )


class CommandResponse(BaseModel):
    command: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    engine = InferenceEngine(MODEL_DIR)
    state = DeviceState()
    runtime = MqttRuntime(engine, state)
    runtime.start()
    app.state.engine = engine
    app.state.state = state
    app.state.mqtt = runtime
    try:
        yield
    finally:
        runtime.stop()


app = FastAPI(
    title="IoT Intrusion Detection API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    runtime: MqttRuntime | None = getattr(app.state, "mqtt", None)
    if runtime is None:
        return {"status": "starting", "mqtt_connected": False}
    return {
        "status": "ok",
        "mqtt_connected": runtime.client.is_connected(),
        "classes": list(CLASS_NAMES),
        "features": list(FEATURES),
    }


@app.get("/api/devices")
def devices() -> list[dict[str, Any]]:
    state: DeviceState = app.state.state
    return state.device_snapshot()


@app.get("/api/events")
def events(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    state: DeviceState = app.state.state
    return state.event_snapshot(limit)


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    state: DeviceState = app.state.state
    with state.lock:
        return {
            "total_flows": state.total_flows,
            "clean_streak": state.clean_streak,
            "total_attacks": state.total_attacks,
            "total_blocked": len(state.blocked),
            "class_counts": dict(state.class_counts),
            "policy": {
                "threshold": AUTO_BLOCK_CONFIDENCE,
                "required_count": AUTO_BLOCK_CONSECUTIVE,
            },
        }


class SimulationRequest(BaseModel):
    device_id: str = "ESP-A"
    attack_type: str = "DOS"


@app.post("/api/simulate")
def simulate(req: SimulationRequest) -> dict[str, Any]:
    engine: InferenceEngine = app.state.engine
    state: DeviceState = app.state.state
    atype = req.attack_type.upper()
    is_normal = (atype in ("NONE", "NORMAL"))

    mock_features = {
        "proto": "udp" if not is_normal else "tcp",
        "src_bytes": 1024.0 if not is_normal else 573.0,
        "dst_bytes": 0.0 if not is_normal else 1420.0,
        "src_pkts": 120.0 if not is_normal else 5.0,
        "dst_pkts": 0.0 if not is_normal else 6.0,
        "duration": 0.015 if not is_normal else 0.85,
        "conn_state": 1 if not is_normal else 2,
        "service": 0 if not is_normal else 80,
        "history": 1 if not is_normal else 0,
        "direction": 0,
    }

    pred, conf, probs = engine.predict_full(mock_features)
    payload = {
        "device_id": req.device_id,
        "sequence": 9999,
        "attack_type": atype,
        "features": mock_features,
        "data_origin": "simulated",
    }
    should_block = state.record_prediction(
        req.device_id,
        payload,
        pred,
        conf,
        probs,
    )
    return {
        "device_id": req.device_id,
        "prediction": pred,
        "confidence": conf,
        "probabilities": probs,
        "should_block": should_block,
        "features": mock_features,
    }


@app.post("/api/devices/{device_id}/command")
def send_device_command(device_id: str, request: CommandResponse) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", device_id):
        raise HTTPException(status_code=400, detail="Invalid device ID")
    cmd = request.command.strip().upper()
    valid_prefixes = ("BLOCK", "UNBLOCK", "STATUS", "NORMAL", "ATTACK")
    if not any(cmd == v or cmd.startswith(v) for v in valid_prefixes):
        raise HTTPException(status_code=400, detail="Unsupported device command")

    runtime: MqttRuntime = app.state.mqtt
    state: DeviceState = app.state.state
    if cmd == "BLOCK":
        state.set_blocked(device_id, True)
    elif cmd in ("UNBLOCK", "NORMAL"):
        state.set_blocked(device_id, False)
    try:
        runtime.publish_command(device_id, cmd)
    except (RuntimeError, ValueError) as exc:
        LOG.exception("Unable to send command to %s", device_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"device_id": device_id, "command": cmd}
