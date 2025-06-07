#!/usr/bin/env python3
"""
network_monitor_web.py

- Background thread: monitors gateway & internet reachability every CHECK_INTERVAL seconds.
  Each check is logged (to file) and appended to an in‐memory history list.

- Flask web server: serves an HTML page at `/` showing:
    • Current status (UP / GATEWAY_DOWN / INTERNET_DOWN)
    • Summary statistics (total checks, gateway-down count, internet-down count, uptime %)
    • Table of recent checks (timestamp, gateway_reachable, internet_reachable, state)

Usage:
    cd network_monitor_web/
    python3 network_monitor_web.py

Then open a browser to http://<SERVER_IP>:5000/
"""

import subprocess
import logging
import threading
import time
import datetime

from flask import Flask, render_template

# ── CONFIGURATION ────────────────────────────────────────────────────────────────

# 1) Gateway/router IP on your LAN
GATEWAY_IP = "192.168.0.1"

# 2) External host to ping (Google DNS is reliable)
INTERNET_HOST = "8.8.8.8"

# 3) Check interval, in seconds
CHECK_INTERVAL = 30

# 4) Log file (each run will append)
LOG_FILE = "network_monitor_web.log"
LOG_LEVEL = logging.INFO

# 5) E‑mail alerts (optional). Defaults to disabled.
EMAIL_ENABLED = False
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USERNAME = "your_username@example.com"
SMTP_PASSWORD = "your_password"
EMAIL_FROM = "network-monitor@example.com"
EMAIL_TO = "your_recipient@example.com"
EMAIL_SUBJECT = "Network Monitor Alert"

# ── END CONFIGURATION ──────────────────────────────────────────────────────────


# ─── GLOBAL DATA ────────────────────────────────────────────────────────────────
#
# We keep:
#   1) history: a list of recent check‐results (dict)
#   2) history_lock: to guard concurrent access
#   3) last_state: last known state string
#
history = []
history_lock = threading.Lock()
last_state = None

# Maximum number of entries to keep in memory (for display). Adjust as you like.
MAX_HISTORY_ENTRIES = 500

# ─── LOGGER SETUP ────────────────────────────────────────────────────────────────
logger = logging.getLogger("NetworkMonitorWeb")
logger.setLevel(LOG_LEVEL)

# File handler
fh = logging.FileHandler(LOG_FILE)
fh.setLevel(LOG_LEVEL)
formatter = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console (stdout) handler
ch = logging.StreamHandler()
ch.setLevel(LOG_LEVEL)
ch.setFormatter(formatter)
logger.addHandler(ch)


def ping_host(host: str, timeout: int = 2) -> bool:
    """
    Ping `host` once. Return True if we get a reply (exit code 0), False otherwise.
    Uses Linux/macOS arguments: `ping -c 1 -W timeout host`.
    On Windows, you’d replace with: ["ping", "-n", "1", "-w", str(timeout*1000), host].
    """
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return (result.returncode == 0)
    except Exception as e:
        logger.error(f"ping_host exception for {host}: {e}")
        return False


def send_email_alert(subject: str, body: str):
    """If EMAIL_ENABLED is True, send a plaintext e‑mail with the given subject/body."""
    if not EMAIL_ENABLED:
        return

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        logger.info("Email alert sent.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def monitor_loop():
    """
    Background thread that:
      - Pings GATEWAY_IP; if unreachable, state="GATEWAY_DOWN"
      - Else pings INTERNET_HOST; if unreachable, state="INTERNET_DOWN"
      - Else state="UP"
    Records every check into `history` and logs transitions.
    """
    global last_state

    logger.info("Monitor thread starting.")
    while True:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1) Ping the gateway/router
        gateway_ok = ping_host(GATEWAY_IP)

        if not gateway_ok:
            current_state = "GATEWAY_DOWN"
            logger.warning(f"[{now}] Gateway ({GATEWAY_IP}) is NOT reachable.")
        else:
            # 2) Gateway is OK → ping external host
            internet_ok = ping_host(INTERNET_HOST)
            if not internet_ok:
                current_state = "INTERNET_DOWN"
                logger.warning(f"[{now}] Internet is NOT reachable (gateway OK).")
            else:
                current_state = "UP"
                logger.info(f"[{now}] All good: gateway & internet reachable.")

        # Record this check in history
        entry = {
            "timestamp": now,
            "gateway_reachable": gateway_ok,
            "internet_reachable": (gateway_ok and internet_ok),
            "state": current_state
        }
        with history_lock:
            history.append(entry)
            # Trim if too large
            if len(history) > MAX_HISTORY_ENTRIES:
                history.pop(0)

        # If state changed (transition), send alert
        if current_state != last_state:
            if current_state == "GATEWAY_DOWN":
                msg = f"[{now}] ALERT: Router/Gateway ({GATEWAY_IP}) is DOWN."
                logger.error(msg)
                send_email_alert(EMAIL_SUBJECT, msg)

            elif current_state == "INTERNET_DOWN":
                msg = (f"[{now}] ALERT: Internet is DOWN "
                       f"(router OK, but cannot reach {INTERNET_HOST}).")
                logger.error(msg)
                send_email_alert(EMAIL_SUBJECT, msg)

            elif current_state == "UP":
                if last_state in ("GATEWAY_DOWN", "INTERNET_DOWN"):
                    msg = f"[{now}] INFO: Connectivity RESTORED (state: UP)."
                    logger.info(msg)
                    send_email_alert(EMAIL_SUBJECT, msg)

            last_state = current_state

        time.sleep(CHECK_INTERVAL)


# ─── FLASK APP SETUP ──────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    """
    Render the dashboard:
      • current_state
      • total_checks
      • gateway_down_count
      • internet_down_count
      • uptime_percent
      • recent entries (up to MAX_HISTORY_ENTRIES)
    """
    with history_lock:
        hist_copy = list(history)

    total_checks = len(hist_copy)
    gateway_down_count = sum(1 for e in hist_copy if e["state"] == "GATEWAY_DOWN")
    internet_down_count = sum(1 for e in hist_copy if e["state"] == "INTERNET_DOWN")
    up_count = sum(1 for e in hist_copy if e["state"] == "UP")

    # Avoid division by zero
    uptime_percent = (up_count / total_checks * 100) if total_checks > 0 else 0.0

    # Latest state (if history empty, show "Unknown")
    current_state = hist_copy[-1]["state"] if hist_copy else "Unknown"

    return render_template(
        "index.html",
        current_state=current_state,
        total_checks=total_checks,
        gateway_down_count=gateway_down_count,
        internet_down_count=internet_down_count,
        uptime_percent=round(uptime_percent, 2),
        recent_checks=hist_copy[::-1]  # reverse chronological
    )


def start_monitor_thread():
    """Spawn `monitor_loop` in a daemon thread so Flask can run concurrently."""
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    # Start monitoring in background
    start_monitor_thread()

    # Launch Flask server, listening on all interfaces (0.0.0.0) port 5000
    logger.info("Starting Flask server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)
