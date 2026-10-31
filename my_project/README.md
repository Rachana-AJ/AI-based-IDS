# IoT intrusion detection backend

The firmware sends dataset-derived demo flow-profile messages over MQTT. The backend
validates the ten features, applies the same protocol encoding, `log1p`
transforms, and saved scaler used during training, then returns a model
prediction. The ESP's `attack_type` is retained as a reported value for
comparison; it is never used as the model target during live inference.

## Train the model

From this directory, install dependencies and train from the bundled CSV:

```powershell
python -m pip install -r requirements.txt
python -m backend.train_model
```

The default dataset is `dataset/train_test_network.csv`. Training writes
`models/ids_model.pth`, `models/ids_scaler.pkl`, and `models/metadata.json`.
The split is stratified (70/30, seed 42); the scaler is fitted only on the
training partition.

## Run the MQTT inference service

Start Mosquitto, then run from this directory:

```powershell
python -m uvicorn backend.service:app --host 127.0.0.1 --port 8000
```

Set `MQTT_HOST` and `MQTT_PORT` if the broker is not on the local machine.
Set `AUTO_BLOCK_CONFIDENCE` and `AUTO_BLOCK_CONSECUTIVE` to tune the defensive
rule; defaults are 0.90 and three consecutive predictions of the same
non-normal class. A blocked device is rejected by the backend and receives a
`BLOCK` command. This is a lab demonstration, not a network-level isolation
mechanism.

The dashboard can later consume:

- `GET /api/health`
- `GET /api/devices`
- `GET /api/events?limit=100`
- `POST /api/devices/{device_id}/command` with `{"command":"BLOCK"}` or
  `{"command":"UNBLOCK"}` (also supports `STATUS` and `NORMAL`)

CORS defaults to localhost ports used by common frontend dev servers. Set
`FRONTEND_ORIGINS` to a comma-separated list of exact origins if the eventual
design uses different local origins.

## ESP setup and stable addresses

Copy each device's matching `config.py`, `main.py`, and its existing
MicroPython `umqtt.simple` dependency to that board once. The ESP executes
`main.py` at boot; it does not need Thonny's Run button after deployment.
`esp_1` is ESP-A and `esp_2` is ESP-B, each with separate MQTT data, control,
and status topics. Both devices currently use the broker address configured in
their local config files.

Use the router's DHCP reservation feature to keep the PC/broker address stable,
and point both ESP configs at that reserved address. Reserve each ESP's Wi-Fi
MAC address too if a stable device IP is useful. This avoids static-IP
collisions and does not require a hard-coded subnet/gateway in the firmware.
The reservation itself is a one-time router setup; the powerbank startup is
automatic after firmware and Wi-Fi settings have been installed.
ESP8266 boards require a 2.4 GHz Wi-Fi network. The ESP-B currently reports
that it cannot find the Wi-Fi SSID stored in its config, and that SSID does not
match the PC's current Wi-Fi network. Update both local ESP configs with the
same 2.4 GHz network credentials as the PC before expecting live telemetry;
do not send the password in chat.

Keep the local Wi-Fi credentials private. Do not publish firmware config files
or broker credentials in a public repository.

The firmware randomly selects from small per-class pools of held-out dataset
rows that the trained model classified correctly at high confidence. Training
generates `profiles.py` in both ESP folders. These are demo feature records,
not measurements from the ESP network interface and not generated attack
traffic. The model still runs on every message and its result is not replaced
by the ESP's requested simulation label. `data_origin` marks these messages as
`dataset_profile_demo`; do not present this profile replay as evidence of
real-world detection performance.
