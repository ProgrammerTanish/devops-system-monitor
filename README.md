# 🖥️ System Monitor

A lightweight, production-style Python system monitor that continuously tracks CPU, RAM, network, and disk usage — and alerts you by email when something goes wrong.

Built as a two-script system the way real DevOps tools work:

| Script | Role |
|---|---|
| `system_monitor.py` | Runs continuously, collects data every 5 seconds, writes to `system.log` |
| `report.py` | Run on-demand to analyse the log and print a historical summary |

---

## Features

- **CPU monitoring** — usage %, core count, max frequency
- **RAM monitoring** — total and used GB, calculated usage %
- **Disk monitoring** — auto-detects all partitions on any OS (Windows, Linux, macOS)
- **Network monitoring** — real-time upload/download speed in MB/s using two-snapshot delta
- **Email alerts** — WARNING and CRITICAL levels with 30-minute cooldown to prevent inbox flooding
- **Alert storm protection** — cooldown system + consecutive-check filter for network spikes
- **Non-blocking alerts** — emails send in a background thread so the monitor never pauses
- **Historical reports** — analyse the last hour, today, or all time from the log file
- **Cross-platform** — works on Linux, macOS, and Windows

---

## Requirements

- Python 3.10 or higher
- [`psutil`](https://pypi.org/project/psutil/) library

Install the dependency:

```bash
pip install psutil
```

---

## Project Structure

```
your-project/
│
├── system_monitor.py   # Continuous data collector
├── report.py           # Log analyser and report generator
└── system.log          # Created automatically when monitor runs
```

---

## Quick Start

**Step 1 — Clone or download the files**

```bash
git clone https://github.com/your-username/system-monitor.git
cd system-monitor
```

**Step 2 — Install dependencies**

```bash
pip install psutil
```

**Step 3 — (Optional) Configure email alerts**

Open `system_monitor.py` and fill in the email config at the top of the file. See the [Email Alert Setup](#email-alert-setup) section below for detailed instructions.

**Step 4 — Run the monitor**

```bash
python system_monitor.py
```

You will see output like this every 5 seconds:

```
System monitor started. Press Ctrl+C to stop.

{'TimeStamp': '2024-01-15 10:00:05', 'CPU usage': '45.2%', 'Used RAM': '6.1GB', ...}
{'TimeStamp': '2024-01-15 10:00:12', 'CPU usage': '78.4%', 'Used RAM': '6.3GB', ...}
```

Press `Ctrl+C` to stop cleanly.

**Step 5 — Run a report whenever you want**

```bash
python report.py              # Full summary of all logged data
python report.py --hours 1    # Only the last 1 hour
python report.py --today      # Only since midnight today
python report.py --hours 0.5  # Last 30 minutes
```

Example report output:

```
====================================================
           SYSTEM MONITOR — LOG REPORT
====================================================
  Period   : 2024-01-15 09:00:05 → 2024-01-15 10:00:05
  Records  : 720
  Generated: 2024-01-15 10:01:00
====================================================

[ CPU ]
  Average usage   : 52.3%
  Peak usage      : 94.1%
  Lowest usage    : 18.7%
  Crossed  90%    : 4 time(s)  ← critical threshold
  Crossed  70%    : 31 time(s) ← warning threshold

[ RAM ]
  Average used    : 6.8 GB
  Peak used       : 11.2 GB
  Total installed : 16.0 GB
  Average % used  : 42.5%
  Peak % used     : 70.0%

[ NETWORK ]
  Avg upload      : 2.1 MB/s
  Peak upload     : 45.3 MB/s
  Avg download    : 18.4 MB/s
  Peak download   : 61.2 MB/s
  Spikes >50 MB/s : 3 time(s)  (download)

[ STORAGE ]
  Partition: /
    Total size      : 500.0 GB
    Average used    : 312.0 GB
    Peak % used     : 62.4%

[ TOP 5 HIGHEST CPU MOMENTS ]
  Timestamp                CPU      RAM Used
  ----------------------  ------  ----------
  2024-01-15 09:47:32     94.1%     9.80 GB
  ...
====================================================
```

---

## Email Alert Setup

This is the most important configuration step. If you skip it, the monitor still works — it just won't send emails.

### Step 1 — Find the config block

Open `system_monitor.py`. Near the top of the file, you will find this block:

```python
# ─── Email config ──────────────────────────────────────────────────────────────
EMAIL_SENDER   = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECEIVER = "alert_receiver@gmail.com"
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
```

Replace the placeholder values with your real details.

---

### Step 2 — Get a Gmail App Password

> ⚠️ **Do not use your real Gmail password.** Gmail requires App Passwords for third-party scripts. Using your real password will fail and is a security risk.

1. Go to your Google Account: [myaccount.google.com](https://myaccount.google.com)
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google", click **2-Step Verification** and make sure it is turned on (App Passwords require 2FA to be enabled)
4. Go back to Security and search for **App Passwords** (or go directly to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords))
5. Click **Create a new app password**
6. Give it a name like `System Monitor` and click **Create**
7. Google will show you a **16-character password** like `abcd efgh ijkl mnop`
8. Copy it (without the spaces) and paste it as your `EMAIL_PASSWORD`

Your config should then look like this:

```python
EMAIL_SENDER   = "yourname@gmail.com"
EMAIL_PASSWORD = "abcdefghijklmnop"       # 16-char App Password, no spaces
EMAIL_RECEIVER = "yourname@gmail.com"     # Can be the same address or a different one
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
```

> 💡 `EMAIL_SENDER` and `EMAIL_RECEIVER` can be the same address if you want to email yourself.

---

### Step 3 — Understand the alert thresholds

Just below the email config, you will find the thresholds block:

```python
THRESHOLDS = {
    "cpu":     {"warning": 70,  "critical": 90},
    "ram":     {"warning": 80,  "critical": 90},
    "storage": {"warning": 85,  "critical": 90},
    "network": {"spike_mb": 50},
}
```

This is the only place you need to edit to change when alerts fire.

#### How the two levels work

| Level | Meaning | When to use |
|---|---|---|
| `warning` | Something is elevated — worth knowing about | Non-urgent, investigation needed |
| `critical` | Something is seriously wrong — act now | Immediate attention required |

Both levels send separate emails. If CPU is at 95%, you get a **CRITICAL** email. If it drops to 75%, the **CRITICAL** clears and you would get a **WARNING** email instead on the next check.

#### Customising each metric

**CPU** — values are a percentage (0–100):
```python
"cpu": {"warning": 70, "critical": 90}
```
- Change `70` if your machine normally runs hot (e.g. a build server) — set it to `80`
- Change `90` if you want earlier notice — set it to `85`

**RAM** — values are a percentage of total installed RAM:
```python
"ram": {"warning": 80, "critical": 90}
```
- On a machine with 8 GB RAM, `warning: 80` means alert when 6.4 GB is in use
- On a machine with 64 GB RAM, `warning: 80` means alert when 51.2 GB is in use
- The script calculates the percentage automatically from the GB values it reads

**Storage** — values are a percentage of each partition's total size:
```python
"storage": {"warning": 85, "critical": 90}
```
- Applied independently per partition — if you have `/` and `/data`, each is checked separately
- A full `/data` disk will alert even if `/` is fine

**Network** — value is MB/s, not a percentage:
```python
"network": {"spike_mb": 50}
```
- An alert fires only if the speed stays above `50 MB/s` for **3 consecutive checks** (~21 seconds)
- This avoids false alarms from a brief cloud sync or video stream buffering
- On a slow connection (e.g. 10 MB/s max), lower this to `8` or `10`
- On a fast server with a 1 Gbps link, raise this to `200` or `500`

#### Example: tighter thresholds for a production server

```python
THRESHOLDS = {
    "cpu":     {"warning": 60,  "critical": 80},
    "ram":     {"warning": 70,  "critical": 85},
    "storage": {"warning": 75,  "critical": 85},
    "network": {"spike_mb": 100},
}
```

#### Example: relaxed thresholds for a developer laptop

```python
THRESHOLDS = {
    "cpu":     {"warning": 85,  "critical": 95},
    "ram":     {"warning": 85,  "critical": 95},
    "storage": {"warning": 90,  "critical": 95},
    "network": {"spike_mb": 20},
}
```

---

### Step 4 — Understand alert cooldown

If your CPU stays at 95% for two hours, you do not want 1,440 emails. The cooldown system prevents this.

```python
ALERT_COOLDOWN_SECONDS = 1800  # 30 minutes
```

This means: once an alert fires for a given metric, that same alert cannot fire again for 30 minutes. The cooldown is tracked per metric and per level independently — so a `cpu_warning` cooldown does not block a `cpu_critical` alert.

To change the cooldown, find this line near the top of `system_monitor.py` and edit the number:

```python
ALERT_COOLDOWN_SECONDS = 3600  # 1 hour — for less noisy environments
ALERT_COOLDOWN_SECONDS = 900   # 15 minutes — for faster re-alerting
```

---

### Using a different email provider

The script defaults to Gmail. To use a different provider, change `SMTP_HOST` and `SMTP_PORT`:

| Provider | SMTP Host | Port |
|---|---|---|
| Gmail | `smtp.gmail.com` | `587` |
| Outlook / Hotmail | `smtp.office365.com` | `587` |
| Yahoo Mail | `smtp.mail.yahoo.com` | `587` |
| Zoho Mail | `smtp.zoho.com` | `587` |
| Custom / self-hosted | your mail server address | usually `587` or `465` |

---

## How the Log File Works

`system_monitor.py` writes one line to `system.log` every 5 seconds. Each line looks like:

```
TimeStamp: 2024-01-15 10:00:05, CPU usage: 45.2%, Physical cores: 8, Logical cores: 16, MAX speed of CPU: 3600MHz, Total RAM: 16.0GB, Used RAM: 6.1GB, Upload speed: 0.0021 MB/s, Download speed: 1.2340 MB/s, Total sent (boot): 450.0 MB, Total recv (boot): 1200.0 MB, [/] Total: 500GB, [/] Used: 312GB, [/] % Used: 62.4%, [/] FS type: ext4
```

`report.py` reads this file and parses each line. Any lines it cannot parse (including alert log entries) are skipped silently. The log file is never deleted or rotated by these scripts — it grows indefinitely. For long-running deployments you may want to set up log rotation using the OS (e.g. `logrotate` on Linux).

---

## Running Continuously in the Background

### Linux / macOS — using nohup

```bash
nohup python system_monitor.py > /dev/null 2>&1 &
echo $! > monitor.pid   # Save the process ID so you can stop it later
```

To stop it:
```bash
kill $(cat monitor.pid)
```

### Linux — using systemd (recommended for servers)

Create `/etc/systemd/system/system-monitor.service`:

```ini
[Unit]
Description=Python System Monitor
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/system_monitor.py
Restart=always
User=your-username

[Install]
WantedBy=multi-user.target
```

Then enable and start it:
```bash
sudo systemctl enable system-monitor
sudo systemctl start system-monitor
sudo systemctl status system-monitor
```

### Windows — using Task Scheduler

1. Open Task Scheduler
2. Create a new task set to trigger **At startup**
3. Action: `python C:\path\to\system_monitor.py`
4. Check **Run whether user is logged on or not**

---

## Troubleshooting

**"Email authentication failed"**
— You used your real Gmail password instead of an App Password. Re-read [Step 2](#step-2--get-a-gmail-app-password) above.

**"Could not connect to SMTP server"**
— Your firewall or ISP may be blocking outbound port 587. Try from a different network or check firewall rules.

**"Log file not found" when running report.py**
— Run `system_monitor.py` first to generate `system.log`. Make sure both scripts are in the same folder, or pass the log path explicitly: `python report.py --log /path/to/system.log`

**CPU frequency shows N/A**
— Normal on some Linux VMs and cloud instances (like AWS EC2) where the hypervisor does not expose CPU frequency data. All other metrics still work.

**Disk usage shows N/A for some partitions on Windows**
— Normal for system-reserved partitions (like the EFI partition) that deny read access without admin privileges. Run the script as Administrator to resolve.

---

## Concepts Used

This project was built to demonstrate real DevOps and Python patterns:

- **Separation of concerns** — one script collects, one script analyses. This is how tools like Prometheus + Grafana work at scale.
- **Structured logging** — consistent key-value format that a parser can reliably read back
- **Cooldown / debounce** — alert state tracking to prevent notification floods
- **Background threads** — non-blocking I/O so a slow SMTP server never pauses monitoring
- **Consecutive-check filtering** — avoids false positives from momentary spikes
- **Cross-platform paths** — `psutil.disk_partitions()` instead of hardcoded `/` or `C:\`
- **Graceful degradation** — every `check_*` function returns `"N/A"` on failure so one broken metric never kills the whole loop

---

## License

MIT — free to use, modify, and distribute.
