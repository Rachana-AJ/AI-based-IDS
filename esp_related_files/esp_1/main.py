import sys
import uselect
import network
import random
import time
import machine
import ujson

from umqtt.simple import MQTTClient

import config
from profiles import PROFILES


# ============================================================
# PLAN B1 - IoT INTRUSION DETECTION NODE
# ============================================================
#
# Hardware:
#
# D1 / GPIO5 -> 220 ohm -> GREEN LED -> GND
# D2 / GPIO4 -> 220 ohm -> RED LED   -> GND
#
# States:
#
# NORMAL  -> Green ON, Red OFF
# ATTACK  -> Green ON, Red OFF
# BLOCKED -> Green OFF, Red ON
#
# The ESP automatically starts this program after power-up.
# ============================================================


# ============================================================
# LED PINS
# ============================================================

GREEN_LED = machine.Pin(5, machine.Pin.OUT)
RED_LED = machine.Pin(4, machine.Pin.OUT)


# ============================================================
# STATES
# ============================================================

STATE_NORMAL = "NORMAL"
STATE_ATTACK = "ATTACK"
STATE_BLOCKED = "BLOCKED"


device_state = STATE_NORMAL

current_attack = "NONE"

mqtt_client = None

sequence_number = 0


# ============================================================
# LED CONTROL
# ============================================================

def led_off():
    GREEN_LED.value(0)
    RED_LED.value(0)


def led_normal():
    # Wi-Fi connected and sending data: GREEN ON, RED OFF
    GREEN_LED.value(1)
    RED_LED.value(0)


def led_attack():
    # Attack in progress (sending data before ML intervention): GREEN ON, RED OFF
    GREEN_LED.value(1)
    RED_LED.value(0)


def led_blocked():
    # Blocked by ML / IDS: Stop sending data, isolate node, RED ON, GREEN OFF
    GREEN_LED.value(0)
    RED_LED.value(1)


# ============================================================
# CHANGE DEVICE STATE
# ============================================================

def set_state(new_state):

    global device_state

    device_state = new_state

    if new_state == STATE_NORMAL:

        led_normal()

    elif new_state == STATE_ATTACK:

        led_attack()

    elif new_state == STATE_BLOCKED:

        led_blocked()

    print()
    print("--------------------------------")
    print("Device :", config.DEVICE_ID)
    print("State  :", device_state)
    print("Attack :", current_attack)
    print("--------------------------------")


# ============================================================
# WIFI
# ============================================================

def connect_wifi():

    wifi = network.WLAN(network.STA_IF)

    wifi.active(True)

    if wifi.isconnected():

        print("Wi-Fi already connected")
        print("IP:", wifi.ifconfig()[0])

        return wifi

    print()
    print("Connecting to Wi-Fi...")
    print("SSID:", config.WIFI_SSID)

    wifi.connect(
        config.WIFI_SSID,
        config.WIFI_PASSWORD
    )

    timeout = 20

    while not wifi.isconnected() and timeout > 0:

        print(".", end="")

        time.sleep(1)

        timeout -= 1

    print()

    if wifi.isconnected():

        print("Wi-Fi connected")
        print("IP:", wifi.ifconfig()[0])

        return wifi

    print("Wi-Fi connection failed")

    return None


# ============================================================
# MQTT STATUS
# ============================================================

def publish_status(status):

    global mqtt_client

    if mqtt_client is None:

        return

    message = {

        "device_id": config.DEVICE_ID,

        "status": status,

        "state": device_state,

        "attack_type": current_attack

    }

    try:

        mqtt_client.publish(

            config.STATUS_TOPIC,

            ujson.dumps(message)

        )

        print()
        print("STATUS SENT")
        print(ujson.dumps(message))

    except Exception as e:

        print(
            "Status publish error:",
            e
        )


# ============================================================
# MQTT CALLBACK
# ============================================================

# ============================================================
# COMMAND PROCESSING (MQTT & SERIAL)
# ============================================================

def process_command(command):
    global current_attack

    if command == "NORMAL":
        current_attack = "NONE"
        set_state(STATE_NORMAL)
        publish_status("NORMAL")

    elif command == "BLOCK":
        # ML detected malicious packet flow: activate RED LED and isolate node!
        set_state(STATE_BLOCKED)
        publish_status("BLOCKED")

    elif command == "UNBLOCK":
        current_attack = "NONE"
        set_state(STATE_NORMAL)
        publish_status("UNBLOCKED")

    elif command == "STATUS":
        publish_status("STATUS")

    elif command == "ATTACK" or command.startswith("ATTACK:"):
        attack_type = "DOS" if command == "ATTACK" else command.split(":", 1)[1].strip()
        supported_attacks = (
            "DOS",
            "DDOS",
            "SCANNING",
            "RANSOMWARE",
            "BACKDOOR",
        )
        if attack_type not in supported_attacks:
            print("Unsupported attack simulation:", attack_type)
        elif device_state == STATE_BLOCKED:
            print("Device is currently BLOCKED; ignoring attack command.")
        else:
            current_attack = attack_type
            set_state(STATE_ATTACK)
            publish_status("ATTACK_STARTED")

    else:
        print("Unknown command:", command)


def mqtt_callback(topic, message):
    try:
        topic_text = topic.decode()
        command = message.decode().strip().upper()
    except Exception:
        print("Invalid MQTT command")
        return

    print()
    print("======================================")
    print("MQTT COMMAND RECEIVED")
    print("Topic  :", topic_text)
    print("Command:", command)
    print("======================================")
    process_command(command)


# Poll standard input for USB serial commands (e.g. from run_terminal.py)
poll_stdin = uselect.poll()
poll_stdin.register(sys.stdin, uselect.POLLIN)

def check_serial_command():
    while poll_stdin.poll(0):
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().upper()
            if cmd:
                print()
                print("======================================")
                print("SERIAL COMMAND RECEIVED:", cmd)
                print("======================================")
                process_command(cmd)
        except Exception:
            break


# ============================================================
# CONNECT TO MQTT
# ============================================================

def connect_mqtt():

    global mqtt_client

    print()
    print("Connecting to MQTT broker...")
    print("Server:", config.MQTT_SERVER)
    print("Port  :", config.MQTT_PORT)

    try:

        client_id = config.DEVICE_ID

        mqtt_client = MQTTClient(

            client_id,

            config.MQTT_SERVER,

            port=config.MQTT_PORT,

            keepalive=60

        )

        mqtt_client.set_callback(
            mqtt_callback
        )

        mqtt_client.connect()

        print("MQTT connected!")

        mqtt_client.subscribe(
            config.CONTROL_TOPIC
        )

        print(
            "Subscribed:",
            config.CONTROL_TOPIC.decode()
        )

        publish_status(
            "ONLINE"
        )

        return True

    except Exception as e:

        print()
        print("MQTT connection failed:")
        print(e)

        mqtt_client = None

        return False


def choose_profile(pool):
    return pool[random.getrandbits(16) % len(pool)]


# ============================================================
# NORMAL FEATURE VALUES
# ============================================================

def create_normal_features():

    # --------------------------------------------------------
    # 10 features used by the ML model
    #
    # duration
    # src_port
    # dst_port
    # proto
    # src_bytes
    # dst_bytes
    # src_pkts
    # dst_pkts
    # src_ip_bytes
    # dst_ip_bytes
    # --------------------------------------------------------

    return choose_profile(PROFILES["NORMAL"])


# ============================================================
# ATTACK FEATURE VALUES
# ============================================================

def create_attack_features():

    profile_pool = PROFILES.get(current_attack)
    if not profile_pool:
        raise ValueError("No demo profiles for attack type: " + current_attack)
    return choose_profile(profile_pool)


# ============================================================
# NORMAL MESSAGE
# ============================================================

def create_normal_message():

    global sequence_number

    sequence_number += 1

    features = create_normal_features()

    return {

        "device_id": config.DEVICE_ID,

        "mode": "normal",

        "attack_type": "NONE",

        "device_status": "OK",

        "data_origin": "dataset_profile_demo",

        "sequence": sequence_number,

        "features": features

    }


# ============================================================
# ATTACK MESSAGE
# ============================================================

def create_attack_message():

    global sequence_number

    sequence_number += 1

    features = create_attack_features()

    return {

        "device_id": config.DEVICE_ID,

        "mode": "attack",

        "attack_type": current_attack,

        "device_status": "ABNORMAL",

        "data_origin": "dataset_profile_demo",

        "sequence": sequence_number,

        "features": features

    }


# ============================================================
# PUBLISH NORMAL DATA
# ============================================================

def publish_normal_data():

    if device_state == STATE_BLOCKED:

        return

    message = create_normal_message()

    payload = ujson.dumps(message)

    try:

        mqtt_client.publish(

            config.DATA_TOPIC,

            payload

        )

        print()
        print("NORMAL DATA SENT")
        print(payload)

    except Exception as e:

        print(
            "Publish error:",
            e
        )


# ============================================================
# PUBLISH ATTACK DATA
# ============================================================

def publish_attack_data():

    if device_state == STATE_BLOCKED:

        return

    message = create_attack_message()

    payload = ujson.dumps(message)

    try:

        mqtt_client.publish(

            config.DATA_TOPIC,

            payload

        )

        print()
        print("ATTACK DATA SENT")
        print(payload)

    except Exception as e:

        print(
            "Attack publish error:",
            e
        )


# ============================================================
# STARTUP
# ============================================================

print()
print("======================================")
print("PLAN B1 IoT INTRUSION DETECTION NODE")
print("======================================")
print("Device:", config.DEVICE_ID)
print("======================================")


# Keep LEDs OFF during connection establishment
led_off()


# Connect Wi-Fi

wifi = connect_wifi()


# ============================================================
# MAIN CONNECTION LOOP
# ============================================================

while wifi is None:

    print()
    print("Waiting for Wi-Fi...")

    time.sleep_ms(config.MQTT_RETRY_INTERVAL_MS)

    wifi = connect_wifi()


# ============================================================
# MQTT CONNECTION
# ============================================================

mqtt_connected = False

while not mqtt_connected:

    mqtt_connected = connect_mqtt()

    if not mqtt_connected:

        print()
        print(
            "MQTT unavailable."
        )

        print(
            "Retrying in 5 seconds..."
        )

        time.sleep_ms(config.MQTT_RETRY_INTERVAL_MS)


# Wi-Fi and MQTT connected: start in NORMAL mode and turn GREEN LED ON!
set_state(
    STATE_NORMAL
)


# ============================================================
# DATA LOOP
# ============================================================

last_publish = time.ticks_ms()


while True:

    try:

        # ----------------------------------------------------
        # Check incoming MQTT commands
        # ----------------------------------------------------

        if mqtt_client is not None:

            mqtt_client.check_msg()


        # ----------------------------------------------------
        # Check incoming USB Serial commands
        # ----------------------------------------------------

        check_serial_command()


        # ----------------------------------------------------
        # Current time
        # ----------------------------------------------------

        now = time.ticks_ms()


        # ====================================================
        # NORMAL
        # ====================================================

        if device_state == STATE_NORMAL:

            if time.ticks_diff(

                now,
                last_publish

            ) >= config.NORMAL_INTERVAL_MS:

                publish_normal_data()

                last_publish = now


        # ====================================================
        # ATTACK
        # ====================================================

        elif device_state == STATE_ATTACK:

            if time.ticks_diff(

                now,
                last_publish

            ) >= config.ATTACK_INTERVAL_MS:

                publish_attack_data()

                last_publish = now


        # ====================================================
        # BLOCKED
        # ====================================================

        elif device_state == STATE_BLOCKED:

            # No telemetry is sent.

            pass


        # ----------------------------------------------------
        # Small delay
        # ----------------------------------------------------

        time.sleep_ms(10)


    except Exception as e:

        print()
        print("======================================")
        print("SYSTEM ERROR")
        print("======================================")
        print(e)


        # ====================================================
        # Try to reconnect Wi-Fi
        # ====================================================

        try:

            wifi = network.WLAN(
                network.STA_IF
            )

            if not wifi.isconnected():
                led_off()
                print(
                    "Wi-Fi disconnected."
                )

                wifi = connect_wifi()


            # =================================================
            # Reconnect MQTT
            # =================================================

            print(
                "Attempting MQTT reconnect..."
            )

            mqtt_connected = connect_mqtt()

            if mqtt_connected:

                print(
                    "MQTT reconnected."
                )

                last_publish = time.ticks_ms()
                if device_state == STATE_BLOCKED:
                    led_blocked()
                else:
                    led_normal()

            else:
                led_off()
                print(
                    "MQTT reconnect failed."
                )

                time.sleep_ms(config.MQTT_RETRY_INTERVAL_MS)


        except Exception as reconnect_error:

            print()
            print(
                "Reconnect failed:"
            )

            print(
                reconnect_error
            )

            time.sleep_ms(config.MQTT_RETRY_INTERVAL_MS)
