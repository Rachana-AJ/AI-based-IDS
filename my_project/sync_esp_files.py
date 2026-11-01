import serial
import time
from pathlib import Path

def exec_raw(s, cmd, timeout=5):
    s.write(cmd.encode('utf-8') + b'\x04')
    start = time.time()
    buf = b""
    while time.time() - start < timeout:
        if s.in_waiting:
            buf += s.read(s.in_waiting)
            if b'OK' in buf and b'>' in buf[buf.find(b'OK')+2:]:
                break
        time.sleep(0.05)
    return buf.decode('latin1', errors='replace')

def upload_file(s, local_path: Path, remote_filename: str):
    print(f"  Uploading {local_path.name} -> {remote_filename}...")
    content = local_path.read_bytes()
    # Open file for writing
    exec_raw(s, f"f = open('{remote_filename}', 'wb')\n")
    chunk_size = 512
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i+chunk_size]
        # send chunk write
        chunk_repr = repr(chunk)
        exec_raw(s, f"f.write({chunk_repr})\n")
    exec_raw(s, "f.close()\n")
    # Verify file size
    res = exec_raw(s, f"import os; print('SIZE:', os.stat('{remote_filename}')[6])\n")
    print(f"  Result: {res.strip()}")

def sync_device(port, src_dir: Path):
    print(f"\n==========================================")
    print(f"Syncing {port} from {src_dir.name}...")
    print(f"==========================================")
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.dtr = False
    s.rts = False
    s.timeout = 2
    try:
        s.open()
    except Exception as e:
        print(f"ERROR: Could not open {port}: {e}")
        print("  -> A background process (like run_terminal or Thonny) may be holding the port open.")
        print("  -> Run 'Stop-Process -Name python -Force' in PowerShell or replug the USB.")
        return False
    
    # Enter raw REPL with retry attempts
    entered = False
    for attempt in range(4):
        s.write(b'\r\x03\x03\x03')  # Send multiple Ctrl+C interrupts
        time.sleep(0.3)
        s.reset_input_buffer()
        s.write(b'\x01')            # Send Ctrl+A for raw REPL
        time.sleep(0.4)
        resp = s.read(s.in_waiting)
        if b'raw REPL' in resp:
            entered = True
            break
        # If not entering, try a quick soft reset then Ctrl+C
        s.write(b'\x04')
        time.sleep(0.3)

    if not entered:
        print(f"Failed to enter raw REPL on {port}. Last response: {resp}")
        s.close()
        return False

    upload_file(s, src_dir / "config.py", "config.py")
    upload_file(s, src_dir / "profiles.py", "profiles.py")
    upload_file(s, src_dir / "main.py", "main.py")

    print(f"  Rebooting {port} (Ctrl-D)...")
    s.write(b'\x04')  # Soft reboot
    time.sleep(0.5)
    s.write(b'\x02')  # Exit raw REPL
    s.close()
    print(f"  Sync complete for {port}!")
    return True

WORKSPACE_ROOT = Path(r"c:\Users\deepu\Documents\Project_Major")
sync_device("COM9", WORKSPACE_ROOT / "esp_related_files" / "esp_1")
sync_device("COM13", WORKSPACE_ROOT / "esp_related_files" / "esp_2")
