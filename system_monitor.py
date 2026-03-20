import os
import time
import psutil
from datetime import datetime
import logging


# Email config
# Fill these in before running. For Gmail, use an App Password, not your real
# password: https://myaccount.google.com/apppasswords
EMAIL_SENDER   = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECEIVER = "alert_receiver@gmail.com"
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587

# Alert thresholds 
THRESHOLDS = {
    "cpu":     {"warning": 70,  "critical": 90},
    "ram":     {"warning": 80,  "critical": 90},
    "storage": {"warning": 85,  "critical": 90},
    "network": {"spike_mb": 50},   # MB/s — flag anything above this as a spike
}

# Alert level labels
WARNING  = "WARNING"
CRITICAL = "CRITICAL"

# Alert cooldown 
# Stores the last time an alert was sent for each metric key (e.g. "cpu_critical")
# so we don't flood the inbox when a metric stays above threshold for a long time.
ALERT_COOLDOWN_SECONDS = 1800  # 30 minutes
_last_alert_time: dict = {}

def _is_on_cooldown(alert_key: str) -> bool:
    """Return True if this alert was already sent within the cooldown window."""
    last = _last_alert_time.get(alert_key)
    if last is None:
        return False
    return (time.time() - last) < ALERT_COOLDOWN_SECONDS

def _mark_alert_sent(alert_key: str):
    """Record the current time as the last send time for this alert key."""
    _last_alert_time[alert_key] = time.time()

#  Network spike persistence tracker
# Count how many consecutive checks each direction has been above the spike threshold.
# An alert only fires once it has been sustained for NETWORK_SPIKE_CONSECUTIVE checks.
NETWORK_SPIKE_CONSECUTIVE = 3   # Must spike on 3 checks in a row (~21 seconds) to alert
_net_spike_count = {"upload": 0, "download": 0}


def send_alert(level, subject, body, alert_key: str):
    """
    Send an alert email in a background thread so the monitor loop never blocks.

    alert_key: unique string like "cpu_critical" used to track cooldown per metric.
               If this key was alerted within ALERT_COOLDOWN_SECONDS, the call is dropped.
    """
    import threading

    # Cooldown check (happens on the main thread, before spawning)
    if _is_on_cooldown(alert_key):
        remaining = int(ALERT_COOLDOWN_SECONDS - (time.time() - _last_alert_time[alert_key]))
        print(f"[COOLDOWN] '{alert_key}' alert suppressed. Next allowed in {remaining}s.")
        return

    # Mark sent immediately so rapid consecutive calls don't all slip through
    # before the first thread finishes
    _mark_alert_sent(alert_key)

    def _send():
        import smtplib
        from email.mime.text import MIMEText

        full_subject = f"[{level}] System Monitor — {subject}"
        msg = MIMEText(body)
        msg["Subject"] = full_subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECEIVER

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
            print(f"[ALERT SENT] {full_subject}")
            logging.warning(f"ALERT SENT: {full_subject} | {body}")
        except smtplib.SMTPAuthenticationError:
            print("[ERROR] Email authentication failed. Check EMAIL_SENDER / EMAIL_PASSWORD.")
        except smtplib.SMTPConnectError:
            print(f"[ERROR] Could not connect to SMTP server {SMTP_HOST}:{SMTP_PORT}.")
        except Exception as e:
            print(f"[ERROR] Failed to send alert email: {e}")

    # daemon=True so the thread won't block the process from exiting on Ctrl+C
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def evaluate_alerts(cpu_usage, ram_info, storage_list, net_upload, net_download):
    """
    Compare current metrics against thresholds and fire alerts where needed.
    Two levels: WARNING < CRITICAL. Critical always fires its own email.
    Cooldown and consecutive-spike logic prevent alert storms.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # CPU 
    if isinstance(cpu_usage, (int, float)):
        if cpu_usage > THRESHOLDS["cpu"]["critical"]:
            send_alert(
                CRITICAL,
                f"CPU usage at {cpu_usage}%",
                f"[{timestamp}] CPU usage has exceeded the critical threshold.\n"
                f"Current: {cpu_usage}%  |  Critical threshold: {THRESHOLDS['cpu']['critical']}%",
                alert_key="cpu_critical"
            )
        elif cpu_usage > THRESHOLDS["cpu"]["warning"]:
            send_alert(
                WARNING,
                f"CPU usage at {cpu_usage}%",
                f"[{timestamp}] CPU usage has exceeded the warning threshold.\n"
                f"Current: {cpu_usage}%  |  Warning threshold: {THRESHOLDS['cpu']['warning']}%",
                alert_key="cpu_warning"
            )

    # RAM
    if isinstance(ram_info[0], (int, float)) and ram_info[0] > 0:
        ram_percent = round((ram_info[1] / ram_info[0]) * 100, 1)
        if ram_percent > THRESHOLDS["ram"]["critical"]:
            send_alert(
                CRITICAL,
                f"RAM usage at {ram_percent}%",
                f"[{timestamp}] RAM usage has exceeded the critical threshold.\n"
                f"Used: {ram_info[1]}GB / {ram_info[0]}GB ({ram_percent}%)"
                f"  |  Critical threshold: {THRESHOLDS['ram']['critical']}%",
                alert_key="ram_critical"
            )
        elif ram_percent > THRESHOLDS["ram"]["warning"]:
            send_alert(
                WARNING,
                f"RAM usage at {ram_percent}%",
                f"[{timestamp}] RAM usage has exceeded the warning threshold.\n"
                f"Used: {ram_info[1]}GB / {ram_info[0]}GB ({ram_percent}%)"
                f"  |  Warning threshold: {THRESHOLDS['ram']['warning']}%",
                alert_key="ram_warning"
            )

    # Storage (per partition) 
    for p in storage_list:
        pct = p["percent_used"]
        mp  = p["mountpoint"]
        # Sanitise mountpoint for use as a dict key (e.g. "/" or "C:\")
        mp_key = mp.replace("\\", "_").replace("/", "_").strip("_") or "root"
        if pct > THRESHOLDS["storage"]["critical"]:
            send_alert(
                CRITICAL,
                f"Disk {mp} at {pct}%",
                f"[{timestamp}] Disk usage on '{mp}' has exceeded the critical threshold.\n"
                f"Used: {p['used_storage']}GB / {p['total_storage']}GB ({pct}%)"
                f"  |  Critical threshold: {THRESHOLDS['storage']['critical']}%",
                alert_key=f"storage_{mp_key}_critical"
            )
        elif pct > THRESHOLDS["storage"]["warning"]:
            send_alert(
                WARNING,
                f"Disk {mp} at {pct}%",
                f"[{timestamp}] Disk usage on '{mp}' has exceeded the warning threshold.\n"
                f"Used: {p['used_storage']}GB / {p['total_storage']}GB ({pct}%)"
                f"  |  Warning threshold: {THRESHOLDS['storage']['warning']}%",
                alert_key=f"storage_{mp_key}_warning"
            )

    #  Network spike (consecutive checks required)
    # A single high reading could just be a burst (e.g. a cloud backup starting).
    # We only alert if the speed stays above the threshold for NETWORK_SPIKE_CONSECUTIVE
    # checks in a row, which filters out brief legitimate bursts.
    spike = THRESHOLDS["network"]["spike_mb"]

    for direction, speed in (("upload", net_upload), ("download", net_download)):
        if isinstance(speed, (int, float)) and speed > spike:
            _net_spike_count[direction] += 1
            if _net_spike_count[direction] >= NETWORK_SPIKE_CONSECUTIVE:
                send_alert(
                    WARNING,
                    f"Sustained network {direction} spike: {speed} MB/s",
                    f"[{timestamp}] {direction.capitalize()} speed has stayed above {spike} MB/s "
                    f"for {_net_spike_count[direction]} consecutive checks.\n"
                    f"Current: {speed} MB/s",
                    alert_key=f"network_{direction}_spike"
                )
        else:
            # Speed dropped back below threshold — reset the counter
            _net_spike_count[direction] = 0


def setup_logging():
    """Set up logging to a file next to this script."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, 'system.log')

        logging.getLogger().handlers = []
        logging.basicConfig(
            filename=file_path,
            level=logging.INFO,
            format='%(message)s'
        )
        return True
    except Exception as e:
        print(f"[WARNING] Could not set up log file: {e}. Logging to console only.")
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        return False


def check_cpu():
    """Check CPU usage, core count, and max frequency."""
    try:
        psutil.cpu_percent(interval=None)
        time.sleep(1)
        cpu_usage = psutil.cpu_percent(interval=None)
    except Exception as e:
        print(f"[ERROR] Could not read CPU usage: {e}")
        cpu_usage = "N/A"

    try:
        physical_cores = psutil.cpu_count(logical=False)
        logical_cores = psutil.cpu_count(logical=True)
    except Exception as e:
        print(f"[ERROR] Could not read CPU core count: {e}")
        physical_cores = "N/A"
        logical_cores = "N/A"

    try:
        freqs = psutil.cpu_freq()
        max_speed = freqs.max if freqs else "N/A"
    except Exception as e:
        print(f"[ERROR] Could not read CPU frequency: {e}")
        max_speed = "N/A"

    return cpu_usage, physical_cores, logical_cores, max_speed


def check_ram():
    """Check total and used RAM in GB."""
    try:
        ram_info = psutil.virtual_memory()
        total_ram = round(ram_info.total / (1024 ** 3), 2)
        used_ram = round(ram_info.used / (1024 ** 3), 2)
        return total_ram, used_ram
    except Exception as e:
        print(f"[ERROR] Could not read RAM info: {e}")
        return "N/A", "N/A"


def check_network():
    """
    Track network usage using two snapshots 1 second apart.

    psutil.net_io_counters() returns CUMULATIVE bytes since boot — not per second.
    To get meaningful speed (MB/s), we subtract two readings taken 1s apart.
    We also return the total sent/received since boot for the log.
    """
    try:
        snapshot1 = psutil.net_io_counters()
        time.sleep(1)
        snapshot2 = psutil.net_io_counters()

        # Speed = difference between the two snapshots (bytes per second → MB/s)
        upload_speed   = round((snapshot2.bytes_sent - snapshot1.bytes_sent) / (1024 ** 2), 4)
        download_speed = round((snapshot2.bytes_recv - snapshot1.bytes_recv) / (1024 ** 2), 4)

        # Total since boot
        total_sent = round(snapshot2.bytes_sent / (1024 ** 2), 2)
        total_recv = round(snapshot2.bytes_recv / (1024 ** 2), 2)

        return upload_speed, download_speed, total_sent, total_recv

    except Exception as e:
        print(f"[ERROR] Could not read network stats: {e}")
        return "N/A", "N/A", "N/A", "N/A"


def check_storage():
    """Check total and used disk storage across all mounted partitions."""
    partitions_data = []

    try:
        partitions = psutil.disk_partitions(all=False)  # all=False skips CD-ROM/empty drives
    except Exception as e:
        print(f"[ERROR] Could not list disk partitions: {e}")
        return partitions_data

    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            partitions_data.append({
                "mountpoint":    partition.mountpoint,
                "device":        partition.device,
                "fstype":        partition.fstype,
                "total_storage": round(usage.total / (1024 ** 3), 2),
                "used_storage":  round(usage.used  / (1024 ** 3), 2),
                "percent_used":  usage.percent,
            })
        except PermissionError:
            # Common on Windows for system-reserved partitions
            print(f"[WARNING] Permission denied for partition '{partition.mountpoint}'. Skipping.")
        except FileNotFoundError:
            print(f"[WARNING] Partition mountpoint '{partition.mountpoint}' not found. Skipping.")
        except Exception as e:
            print(f"[ERROR] Could not read storage for '{partition.mountpoint}': {e}")

    return partitions_data


def main():
    setup_logging()

    print("System monitor started. Press Ctrl+C to stop.\n")

    while True:
        try:
            CPU = check_cpu()
            RAM = check_ram()
            NET = check_network()
            STORAGE = check_storage()

            info = {
                "TimeStamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "CPU usage":           str(CPU[0]) + "%",
                "Physical cores":      str(CPU[1]),
                "Logical cores":       str(CPU[2]),
                "MAX speed of CPU":    str(CPU[3]) + "MHz",
                "Total RAM":           str(RAM[0]) + "GB",
                "Used RAM":            str(RAM[1]) + "GB",
                "Upload speed":        str(NET[0]) + " MB/s",
                "Download speed":      str(NET[1]) + " MB/s",
                "Total sent (boot)":   str(NET[2]) + " MB",
                "Total recv (boot)":   str(NET[3]) + " MB",
            }

            # Add one entry per discovered partition
            for p in STORAGE:
                label = p["mountpoint"]
                info[f"[{label}] Total"]   = f"{p['total_storage']}GB"
                info[f"[{label}] Used"]    = f"{p['used_storage']}GB"
                info[f"[{label}] % Used"]  = f"{p['percent_used']}%"
                info[f"[{label}] FS type"] = p["fstype"]

            log_string = ", ".join([f"{key}: {val}" for key, val in info.items()])
            print(info)
            logging.info(log_string)

            # Check thresholds and send alert emails if anything looks wrong
            evaluate_alerts(CPU[0], RAM, STORAGE, NET[0], NET[1])

        except Exception as e:
            # Catch any unexpected error in one loop iteration so the monitor keeps running
            print(f"[ERROR] Unexpected error during data collection: {e}")

        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nMonitor stopped by user.")
            break


main()
