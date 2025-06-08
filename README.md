# Netstatus

Netstatus is a lightweight network monitoring dashboard written in Python and Flask.
It periodically pings your local gateway and a remote host to determine if your
router or Internet connection is down.  Results are displayed on a simple web
page with statistics and a trends graph of recent ping times.

## Features

* Monitors both gateway reachability and Internet connectivity.
* Stores a history of checks in memory and logs to a file.
* Sends optional e‑mail alerts when connectivity changes.
* Web interface shows current state, summary statistics and a table of recent
  checks.
* Graph of ping latency that automatically scrolls to the newest data.

## Requirements

* Python 3.7+
* Flask

## Installation

1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Edit `network_monitor_web.py` to configure your gateway IP, the external
   host to ping and optional e‑mail settings.

## Usage

Run the monitor and web server:

```bash
python netstatus-project/network_monitor_web.py
```

Then open your browser to `http://localhost:5000/` (or replace `localhost` with
your server's address). The dashboard updates whenever the page is refreshed.

## License

This project is licensed under the terms of the MIT license. See
[`LICENSE`](LICENSE) for details.
