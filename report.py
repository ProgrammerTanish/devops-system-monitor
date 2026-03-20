"""
report.py — Historical analysis of system_monitor logs.

Usage:
    python report.py                  # Full report (all time)
    python report.py --hours 1        # Last 1 hour only
    python report.py --today          # Today's data only
    python report.py --log /path/to/system.log  # Custom log path
"""

import os
import re
import argparse
from datetime import datetime, timedelta


# Log parsing

def parse_line(line: str) -> dict | None:
    """
    Parse one log line into a dict of typed values.

    Log format (written by system_monitor.py):
        TimeStamp: 2024-01-15 10:00:05, CPU usage: 78%, Used RAM: 7GB, ...

    Returns None if the line is malformed or is an ALERT log entry.
    """
    line = line.strip()
    if not line or line.startswith("ALERT"):
        return None

    record = {}
    # Split on ", " but only when followed by a known key pattern (word chars + space + word)
    # This avoids splitting on commas inside values like mountpoints
    parts = re.split(r",\s*(?=[A-Za-z\[\(])", line)

    for part in parts:
        if ": " not in part:
            continue
        key, _, raw_val = part.partition(": ")
        key     = key.strip()
        raw_val = raw_val.strip()

        # Strip units and cast to float where possible
        # Handles: "78%", "7GB", "0.0012 MB/s", "500MHz", "2024-01-15 10:00:05"
        numeric_match = re.match(r"^(-?\d+\.?\d*)", raw_val)
        if key == "TimeStamp":
            try:
                record[key] = datetime.strptime(raw_val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None                 # Unparseable timestamp → skip line
        elif numeric_match:
            record[key] = float(numeric_match.group(1))
        else:
            record[key] = raw_val          # Keep as string (e.g. fstype, N/A)

    return record if "TimeStamp" in record else None


def load_log(log_path: str, since: datetime | None = None) -> list[dict]:
    """
    Read and parse the log file, optionally filtering to entries after `since`.
    Skips unreadable lines silently so one bad line doesn't abort the whole report.
    """
    if not os.path.exists(log_path):
        print(f"[ERROR] Log file not found: {log_path}")
        return []

    records = []
    skipped = 0

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            record = parse_line(line)
            if record is None:
                skipped += 1
                continue
            if since and record["TimeStamp"] < since:
                continue
            records.append(record)

    if skipped:
        print(f"[INFO] Skipped {skipped} unreadable/alert lines in log.\n")

    return records


# Analysis helpers

def extract_numeric(records: list[dict], key: str) -> list[float]:
    """Pull all numeric values for a given key, skipping N/A entries."""
    return [
        r[key] for r in records
        if key in r and isinstance(r[key], float)
    ]


def safe_avg(values: list[float]) -> str:
    return f"{sum(values) / len(values):.1f}" if values else "N/A"

def safe_max(values: list[float]) -> str:
    return f"{max(values):.1f}" if values else "N/A"

def safe_min(values: list[float]) -> str:
    return f"{min(values):.1f}" if values else "N/A"

def count_above(values: list[float], threshold: float) -> int:
    return sum(1 for v in values if v > threshold)

def find_partition_keys(records: list[dict]) -> list[str]:
    """Find all unique partition mountpoints that appear in the log."""
    keys = set()
    for r in records:
        for k in r:
            if k.startswith("[") and k.endswith("] % Used"):
                # Extract just the mountpoint label, e.g. "[/] % Used" → "/"
                keys.add(k[1:k.index("]")])
    return sorted(keys)


#  Report sections 
def print_header(label: str, record_count: int, time_range: str):
    print()
    print("=" * 52)
    print("           SYSTEM MONITOR — LOG REPORT")
    print("=" * 52)
    print(f"  Period   : {time_range}")
    print(f"  Records  : {record_count}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 52)


def report_cpu(records: list[dict]):
    values = extract_numeric(records, "CPU usage")
    if not values:
        print("\n[ CPU ] No data found.")
        return

    print("\n[ CPU ]")
    print(f"  Average usage   : {safe_avg(values)}%")
    print(f"  Peak usage      : {safe_max(values)}%")
    print(f"  Lowest usage    : {safe_min(values)}%")
    print(f"  Crossed  90%    : {count_above(values, 90)} time(s)  ← critical threshold")
    print(f"  Crossed  70%    : {count_above(values, 70)} time(s)  ← warning threshold")


def report_ram(records: list[dict]):
    used   = extract_numeric(records, "Used RAM")
    total  = extract_numeric(records, "Total RAM")

    if not used:
        print("\n[ RAM ] No data found.")
        return

    # Calculate percent used per record where both values are available
    pct_values = []
    for r in records:
        u = r.get("Used RAM")
        t = r.get("Total RAM")
        if isinstance(u, float) and isinstance(t, float) and t > 0:
            pct_values.append(round(u / t * 100, 1))

    print("\n[ RAM ]")
    print(f"  Average used    : {safe_avg(used)} GB")
    print(f"  Peak used       : {safe_max(used)} GB")
    if total:
        print(f"  Total installed : {safe_max(total)} GB")
    if pct_values:
        print(f"  Average % used  : {safe_avg(pct_values)}%")
        print(f"  Peak % used     : {safe_max(pct_values)}%")
        print(f"  Crossed  90%    : {count_above(pct_values, 90)} time(s)  ← critical threshold")
        print(f"  Crossed  80%    : {count_above(pct_values, 80)} time(s)  ← warning threshold")


def report_network(records: list[dict]):
    upload   = extract_numeric(records, "Upload speed")
    download = extract_numeric(records, "Download speed")

    if not upload and not download:
        print("\n[ NETWORK ] No data found.")
        return

    print("\n[ NETWORK ]")
    if upload:
        print(f"  Avg upload      : {safe_avg(upload)} MB/s")
        print(f"  Peak upload     : {safe_max(upload)} MB/s")
        print(f"  Spikes >50 MB/s : {count_above(upload, 50)} time(s)  (upload)")
    if download:
        print(f"  Avg download    : {safe_avg(download)} MB/s")
        print(f"  Peak download   : {safe_max(download)} MB/s")
        print(f"  Spikes >50 MB/s : {count_above(download, 50)} time(s)  (download)")


def report_storage(records: list[dict]):
    partitions = find_partition_keys(records)

    if not partitions:
        print("\n[ STORAGE ] No partition data found.")
        return

    print("\n[ STORAGE ]")
    for mp in partitions:
        pct_key  = f"[{mp}] % Used"
        used_key = f"[{mp}] Used"
        tot_key  = f"[{mp}] Total"

        pct    = extract_numeric(records, pct_key)
        used   = extract_numeric(records, used_key)
        total  = extract_numeric(records, tot_key)

        print(f"\n  Partition: {mp}")
        if total:
            print(f"    Total size      : {safe_max(total)} GB")
        if used:
            print(f"    Average used    : {safe_avg(used)} GB")
            print(f"    Peak used       : {safe_max(used)} GB")
        if pct:
            print(f"    Average % used  : {safe_avg(pct)}%")
            print(f"    Peak % used     : {safe_max(pct)}%")
            print(f"    Crossed  90%    : {count_above(pct, 90)} time(s)  ← critical threshold")
            print(f"    Crossed  85%    : {count_above(pct, 85)} time(s)  ← warning threshold")


def report_timeline(records: list[dict]):
    """Show the top 5 worst CPU moments for quick incident review."""
    scored = [
        (r["TimeStamp"], r.get("CPU usage"), r.get("Used RAM"))
        for r in records
        if isinstance(r.get("CPU usage"), float)
    ]
    if not scored:
        return

    top5 = sorted(scored, key=lambda x: x[1], reverse=True)[:5]

    print("\n[ TOP 5 HIGHEST CPU MOMENTS ]")
    print(f"  {'Timestamp':<22}  {'CPU':>6}  {'RAM Used':>10}")
    print(f"  {'-'*22}  {'-'*6}  {'-'*10}")
    for ts, cpu, ram in top5:
        ram_str = f"{ram} GB" if isinstance(ram, float) else "N/A"
        print(f"  {ts.strftime('%Y-%m-%d %H:%M:%S'):<22}  {cpu:>5.1f}%  {ram_str:>10}")


# Entry point

def main():
    parser = argparse.ArgumentParser(
        description="Analyse system_monitor.py log files and print a summary report."
    )
    parser.add_argument(
        "--log",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "system.log"),
        help="Path to the log file (default: system.log next to this script)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--hours",
        type=float,
        metavar="N",
        help="Only analyse the last N hours of data"
    )
    group.add_argument(
        "--today",
        action="store_true",
        help="Only analyse data from today (midnight onwards)"
    )
    args = parser.parse_args()

    # Determine the time filter
    since = None
    if args.hours:
        since = datetime.now() - timedelta(hours=args.hours)
        time_range = f"Last {args.hours} hour(s)"
    elif args.today:
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        time_range = f"Today ({since.strftime('%Y-%m-%d')})"
    else:
        time_range = "All time"

    records = load_log(args.log, since=since)

    if not records:
        print("No records found for the selected time range. Is the log file populated?")
        return

    # Determine actual range of data in the log
    timestamps = [r["TimeStamp"] for r in records]
    actual_range = (
        f"{min(timestamps).strftime('%Y-%m-%d %H:%M:%S')} → "
        f"{max(timestamps).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print_header(time_range, len(records), actual_range)
    report_cpu(records)
    report_ram(records)
    report_network(records)
    report_storage(records)
    report_timeline(records)

    print("\n" + "=" * 52)
    print()


main()
