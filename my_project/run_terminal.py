"""IoT Intrusion Detection System - Real-time Terminal Monitor.

Provides:
1. PyTorch Multi-class ML Inference Engine on live telemetry flow records.
2. Port 1884 MQTT Proxy (transparent forwarding for mobile MQTT apps on hotspot).
3. Direct USB Serial hardware bridge for zero-drop packet capture and control.
4. Interactive terminal prompt for console debugging and device control.
"""

import os
import sys

# Ensure immediate unbuffered console output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import json
import time
import socket
import threading
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import paho.mqtt.client as mqtt
from backend.service import InferenceEngine, DeviceState, MODEL_DIR
from backend.pipeline import CLASS_NAMES

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

class ColorFormatter:
    @staticmethod
    def header(msg):
        return f"{CYAN}{BOLD}{msg}{RESET}"
    @staticmethod
    def normal(msg):
        return f"{GREEN}{msg}{RESET}"
    @staticmethod
    def attack(msg):
        return f"{RED}{BOLD}{msg}{RESET}"
    @staticmethod
    def warning(msg):
        return f"{YELLOW}{msg}{RESET}"

class TerminalIDSApp:
    def __init__(self, host="127.0.0.1", broker_port=1883, proxy_port=1884):
        self.host = host
        self.broker_port = broker_port
        self.proxy_port = proxy_port
        self.running = True
        self.serial_connections = []
        self.seen_packets = set()
        try:
            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            _s.connect(("8.8.8.8", 80))
            self.local_ip = _s.getsockname()[0]
            _s.close()
        except Exception:
            self.local_ip = "10.154.43.194"

        print(ColorFormatter.header("Loading PyTorch Intrusion Detection Engine & Scaler..."), flush=True)
        self.engine = InferenceEngine(MODEL_DIR)
        self.state = DeviceState()

        # Connect to Mosquitto
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="terminal-ids-runner"
        )
        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message

    def print_banner(self):
        print(f"\n{CYAN}{'='*80}{RESET}", flush=True)
        print(f"{CYAN}{BOLD}   IoT INTRUSION DETECTION SYSTEM - REAL-TIME TERMINAL & MONITOR{RESET}", flush=True)
        print(f"{CYAN}{'='*80}{RESET}", flush=True)
        print(f"  {BOLD}ML Model:{RESET} PyTorch 6-Class Multi-layer Perceptron ({self.engine.device})", flush=True)
        print(f"  {BOLD}Scaler:{RESET} Scikit-Learn StandardScaler (10 flow features, log1p)", flush=True)
        print(f"  {BOLD}Classes:{RESET} {', '.join(CLASS_NAMES)}", flush=True)
        print(f"  {BOLD}Defense Policy:{RESET} Auto-block on 3 consecutive attack alerts (>= 90% conf)", flush=True)
        print(f"  {BOLD}Monitor Dashboard:{RESET} {GREEN}{BOLD}http://localhost:5173{RESET} (or {GREEN}http://{self.local_ip}:5173{RESET} on phone)", flush=True)
        print(f"  {BOLD}Backend API:{RESET} {GREEN}http://localhost:8000{RESET} (Unified in real-time)", flush=True)
        print(f"  {BOLD}Mobile MQTT App:{RESET} Connect Play Store App to {GREEN}{self.local_ip}:{self.proxy_port}{RESET}", flush=True)
        print(f"  {BOLD}Hardware Nodes:{RESET} COM9 (ESP-A), COM13 (ESP-B)", flush=True)
        print(f"{CYAN}{'-'*80}{RESET}", flush=True)
        print(f"  {BOLD}Interactive Terminal Commands:{RESET}", flush=True)
        print(f"    {YELLOW}attack <device> <type>{RESET}  - Simulate attack (e.g. 'attack ESP-A DOS', DDOS, SCANNING)", flush=True)
        print(f"    {GREEN}normal <device>{RESET}         - Return device to normal traffic (e.g. 'normal ESP-A')", flush=True)
        print(f"    {GREEN}unblock <device>{RESET}        - Unblock device (e.g. 'unblock ESP-A')", flush=True)
        print(f"    {CYAN}status{RESET}                  - Show live device state table", flush=True)
        print(f"    {RED}quit / q{RESET}                - Stop monitor", flush=True)
        print(f"{CYAN}{'='*80}{RESET}\n", flush=True)

    def start_proxy(self):
        def proxy_thread():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(('0.0.0.0', self.proxy_port))
                server.listen(10)
                server.settimeout(1.0)
            except Exception as e:
                print(ColorFormatter.warning(f"[PROXY] Note on port {self.proxy_port}: {e}"), flush=True)
                return

            def forward(src, dst):
                try:
                    while self.running:
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

            while self.running:
                try:
                    client_sock, addr = server.accept()
                    broker_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    broker_sock.connect((self.host, self.broker_port))
                    t1 = threading.Thread(target=forward, args=(client_sock, broker_sock), daemon=True)
                    t2 = threading.Thread(target=forward, args=(broker_sock, client_sock), daemon=True)
                    t1.start()
                    t2.start()
                except socket.timeout:
                    continue
                except Exception:
                    break
            server.close()

        threading.Thread(target=proxy_thread, daemon=True).start()

    def on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(ColorFormatter.attack(f"[MQTT] Connection failed: {reason_code}"), flush=True)
            return
        client.subscribe("iot/+/data", qos=1)
        client.subscribe("iot/+/status", qos=1)
        client.subscribe("iot/+/control", qos=1)
        print(ColorFormatter.normal(f"[MQTT] Connected to Mosquitto {self.host}:{self.broker_port} and subscribed to iot/#"), flush=True)

    def process_telemetry(self, device_id: str, payload: dict, source="MQTT"):
        seq = payload.get("sequence", "?")
        packet_key = (device_id, seq)
        if seq != "?" and packet_key in self.seen_packets:
            return
        if seq != "?":
            self.seen_packets.add(packet_key)
            if len(self.seen_packets) > 2000:
                self.seen_packets.clear()

        features = payload.get("features")
        if not features:
            return

        prediction, confidence, probabilities = self.engine.predict_full(features)
        reported = payload.get("attack_type", "NONE")
        now_str = datetime.now().strftime("%H:%M:%S")

        should_block = self.state.record_prediction(device_id, payload, prediction, confidence, probabilities)
        is_blocked = self.state.is_blocked(device_id)

        is_attack = (prediction != "normal")
        status_color = ColorFormatter.attack if is_attack else ColorFormatter.normal
        pred_label = f"[{prediction.upper()} ({confidence*100:.1f}%)]"
        reported_label = f"reported={reported}"

        flow_summary = (
            f"proto={features.get('proto')} "
            f"src_b={features.get('src_bytes')} dst_b={features.get('dst_bytes')} "
            f"pkts={features.get('src_pkts')}+{features.get('dst_pkts')} "
            f"dur={features.get('duration')}"
        )

        match_badge = f"{GREEN}[MATCH]{RESET}" if (prediction.lower() == reported.lower() or (prediction == 'normal' and reported in ('NONE', 'normal'))) else f"{YELLOW}[MISMATCH]{RESET}"

        print(f"\n{DIM}[{now_str}]{RESET} {BOLD}{device_id}{RESET} (seq #{seq} via {source}) -> {status_color(pred_label)} {reported_label} {match_badge}", flush=True)
        print(f"       {DIM}Features:{RESET} {flow_summary}", flush=True)

        if should_block:
            print(f"{RED}{BOLD}***************************************************************{RESET}", flush=True)
            print(f"{RED}{BOLD}>>> [DEFENSE ACTION] AUTOMATIC BLOCK TRIGGERED FOR {device_id}! <<<{RESET}", flush=True)
            print(f"{RED}    Reason: {prediction.upper()} detected 3 consecutive times with confidence >= 90%{RESET}", flush=True)
            print(f"{RED}    Sending BLOCK command (Node will activate RED LED and isolate)...{RESET}", flush=True)
            print(f"{RED}{BOLD}***************************************************************{RESET}", flush=True)
            self.send_command(device_id, "BLOCK")
        elif is_blocked:
            print(f"{YELLOW}       [DEFENSE STATUS: BLOCKED] Device is in blocked state. Telemetry rejected.{RESET}", flush=True)

    def on_mqtt_message(self, client, userdata, message):
        try:
            topic = message.topic
            payload_str = message.payload.decode("utf-8")
            parts = topic.split("/")
            if len(parts) != 3 or parts[0] != "iot":
                return
            device_id, channel = parts[1], parts[2]

            if channel == "status":
                data = json.loads(payload_str)
                self.state.record_status(device_id, data)
                st = data.get("status", "UNKNOWN")
                print(f"{CYAN}[DEVICE STATUS]{RESET} {BOLD}{device_id}{RESET}: {st} (State: {data.get('state')}, Attack: {data.get('attack_type')})", flush=True)
            elif channel == "data":
                data = json.loads(payload_str)
                self.process_telemetry(device_id, data, source="Wi-Fi MQTT")
            elif channel == "control":
                print(f"{MAGENTA}[CONTROL BUS]{RESET} {device_id} <- {payload_str}", flush=True)
        except Exception:
            pass

    def send_command(self, device_id: str, command: str):
        command = command.strip().upper()
        print(ColorFormatter.warning(f"[COMMAND ISSUED] {device_id} <- {command}"), flush=True)

        # Publish to MQTT control topic
        try:
            self.client.publish(f"iot/{device_id}/control", command, qos=1)
        except Exception as e:
            print(f"MQTT publish error: {e}", flush=True)

        # Also forward over USB Serial if device is connected
        for port, dev_id, ser in self.serial_connections:
            if dev_id == device_id and ser and ser.is_open:
                try:
                    ser.write(f"{command}\n".encode('utf-8'))
                except Exception:
                    pass

        if command in ("UNBLOCK", "NORMAL"):
            self.state.set_blocked(device_id, False)
            print(ColorFormatter.normal(f"[SERVER] {device_id} UNBLOCKED."), flush=True)
        elif command == "BLOCK":
            self.state.set_blocked(device_id, True)

    def print_status_table(self):
        print(f"\n{CYAN}{'-'*75}{RESET}", flush=True)
        print(f"{BOLD}{'DEVICE':<10} {'STATUS':<12} {'STATE':<12} {'BLOCKED':<10} {'LAST PREDICTION':<18} {'CONF':<8}{RESET}")
        print(f"{CYAN}{'-'*75}{RESET}", flush=True)
        for dev in self.state.device_snapshot():
            d_id = dev.get("device_id", "UNKNOWN")
            st = dev.get("device_status", "ONLINE")
            state = dev.get("state", "NORMAL")
            bl = str(dev.get("blocked", False))
            pred = dev.get("prediction", "N/A")
            conf = f"{dev.get('confidence', 0)*100:.1f}%" if dev.get("confidence") else "N/A"
            color = RED if dev.get("blocked") else GREEN
            print(f"{color}{d_id:<10} {st:<12} {state:<12} {bl:<10} {pred:<18} {conf:<8}{RESET}", flush=True)
        print(f"{CYAN}{'-'*75}{RESET}\n", flush=True)

    def serial_listener_loop(self, port, device_id):
        import serial
        try:
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = 115200
            ser.dtr = False
            ser.rts = False
            ser.timeout = 1
            ser.open()
            self.serial_connections.append((port, device_id, ser))
            print(ColorFormatter.normal(f"[HARDWARE BRIDGE] Connected to {port} for {device_id}"), flush=True)

            # Soft reboot so board starts main.py cleanly
            ser.write(b"\r\x03\x03\r\x04")
            time.sleep(0.5)

            buf = ""
            while self.running:
                if ser.in_waiting:
                    chunk = ser.read(ser.in_waiting).decode('latin1', errors='replace')
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                data = json.loads(line)
                                if "features" in data:
                                    self.process_telemetry(device_id, data, source=f"Hardware {port}")
                                elif "status" in data:
                                    self.state.record_status(device_id, data)
                                    print(f"{CYAN}[DEVICE STATUS]{RESET} {BOLD}{device_id}{RESET} ({port}): {data.get('status')} (State: {data.get('state')})", flush=True)
                            except Exception:
                                pass
                        elif any(k in line for k in ("Wi-Fi connected", "IP:", "MQTT connected", "Subscribed:", "Connecting to Wi-Fi", "Wi-Fi already connected", "PLAN B1")):
                            print(f"{DIM}[{device_id} on {port}]{RESET} {line}", flush=True)
                time.sleep(0.05)
            ser.close()
        except Exception as e:
            print(ColorFormatter.warning(f"[HARDWARE BRIDGE] {port} ({device_id}) not on USB -> Listening over Wi-Fi MQTT"), flush=True)

    def start_api_server(self, port=8000):
        def uvicorn_worker():
            try:
                import uvicorn
                from backend.service import app as api_app
                api_app.state.engine = self.engine
                api_app.state.state = self.state
                api_app.state.app_ref = self

                class ApiBridge:
                    def __init__(self, parent):
                        self.parent = parent
                        self.client = parent.client
                    def publish_command(self, dev_id, cmd):
                        self.parent.send_command(dev_id, cmd)

                api_app.state.mqtt = ApiBridge(self)

                config = uvicorn.Config(
                    api_app,
                    host="0.0.0.0",
                    port=port,
                    log_level="error",
                    access_log=False,
                )
                server = uvicorn.Server(config)
                server.run()
            except Exception as e:
                print(f"[API SERVER] Port {port} notice: {e}", flush=True)

        threading.Thread(target=uvicorn_worker, daemon=True).start()

    def start(self):
        self.serial_connections = []
        self.start_proxy()
        self.start_api_server(port=8000)
        self.print_banner()

        try:
            self.client.connect_async(self.host, self.broker_port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(ColorFormatter.attack(f"Could not connect to MQTT broker: {e}"), flush=True)

        t1 = threading.Thread(target=self.serial_listener_loop, args=("COM9", "ESP-A"), daemon=True)
        t2 = threading.Thread(target=self.serial_listener_loop, args=("COM13", "ESP-B"), daemon=True)
        t1.start()
        t2.start()

        time.sleep(1)

    def stop(self):
        self.running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

def main():
    app = TerminalIDSApp()
    app.start()

    print(ColorFormatter.header(">>> Live Intrusion Detection System is RUNNING and MONITORING... <<<\n"), flush=True)

    try:
        while True:
            cmd = input().strip()
            if not cmd:
                continue
            parts = cmd.split()
            verb = parts[0].lower()

            if verb in ("q", "quit", "exit"):
                print(ColorFormatter.warning("Stopping monitor..."), flush=True)
                break
            elif verb == "status":
                app.print_status_table()
            elif verb in ("normal", "unblock", "block") and len(parts) >= 2:
                device = parts[1].upper()
                app.send_command(device, verb.upper())
            elif verb == "attack" and len(parts) >= 2:
                device = parts[1].upper()
                attack_type = parts[2].upper() if len(parts) >= 3 else "DOS"
                app.send_command(device, f"ATTACK:{attack_type}")
            else:
                print(f"Commands: 'attack <device> <type>', 'normal <device>', 'unblock <device>', 'status', 'quit'", flush=True)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        app.stop()

if __name__ == "__main__":
    main()
