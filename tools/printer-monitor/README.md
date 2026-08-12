# Printer Supply Monitor

Watches supply levels on the shop's **HP Latex 360** and **HP LaserJet 4100**, keeps a
running count of the spares on the shelf, and pops up a window plus sends an email when
anything drops below a level you set.

No third-party packages — plain Python 3.9+ and the standard library, so it installs on a
locked-down shop PC without a pip mirror or admin rights.

## What it watches

Everything the printer reports over SNMP (the standard Printer MIB, RFC 3805). Nothing is
hardcoded per model — whatever the printer exposes is what gets monitored:

| | Latex 360 | LaserJet 4100 |
|---|---|---|
| Ink / toner | 6 colours + optimizer, in ml and % | black toner, in % |
| Printheads | life remaining per printhead | — |
| Maintenance | maintenance cartridge (counts *up* as it fills) | maintenance kit / fuser, in impressions |
| Media | substrate roll + loaded media name | all trays, sheets and % |
| Status | idle / printing / warming up, front-panel message | same, plus low-toner and jam flags |
| Counters | lifetime page count | lifetime page count |
| Errors | the printer's own alert table (jams, doors, service due) | same |

Waste receptacles are handled correctly: the Latex's maintenance cartridge reports how
**full** it is, so the app inverts it and always shows *life remaining*. A threshold of
15% means the same thing for every supply on both machines.

## Setup

### 1. Turn on SNMP at each printer

Browse to the printer's IP address in a web browser and enable read-only SNMP:

- **Latex 360** — Internal Print Server / embedded web server → Networking → SNMP.
- **LaserJet 4100** — the JetDirect page → Networking → SNMP. Older firmware only speaks
  SNMPv1; the app detects that and switches itself over.

Note the community string (it's usually `public`).

### 2. Install

```bash
cd tools/printer-monitor
pip install -e .          # optional — gives you the `printer-monitor` command
```

Or skip installing and run it in place with `python -m printer_monitor`.

### 3. Point it at the printers

Open the window (`python -m printer_monitor`, or double-click `run-monitor.bat` on
Windows), go to **Settings → Printers**, enter each IP, and press **Test connection**.
That confirms it can talk to the printer, reports how many supplies it found, and fixes
the SNMP version automatically if it was wrong. Press **Save settings**.

From a terminal instead:

```bash
printer-monitor add-printer "HP Latex 360"   192.168.1.50 --profile hp_latex
printer-monitor add-printer "HP LaserJet 4100" 192.168.1.51 --profile hp_laserjet
printer-monitor check          # poll once and print every level
```

## The four tabs

**Printer levels** — a bar per supply per printer, colour-coded green/amber/red with a
dashed line showing where the alert fires. Also shows the capacity (`775 ml`), how many
spares you have on the shelf, and once there's a couple of weeks of history, an estimate
like *~9 days at current use*.

**Supply list** — the shelf inventory, with a **+** and **−** button on every row. Set a
*reorder at* number per item and the row turns amber (`ORDER`) or red (`OUT`) when you hit
it. Double-click a row for its movement history. **Load starter list** fills in the usual
consumables for both printers; polling a printer also adds whatever supplies it reports,
linked to the live level. **Export CSV** gives you something to send a supplier.

**Alert history** — every alert that has fired, newest first.

**Settings** — printers, alert levels, and popup/email options.

## Alert levels

Set in **Settings → Alert levels**:

| Setting | Default | Meaning |
|---|---|---|
| Low warning | 20% | first alert, amber |
| Critical | 8% | urgent alert, red |
| Paper / media | 10% | tray or roll low |
| Check every | 300s | how often to poll |
| Repeat alerts after | 12h | how long before it nags again about the same thing |
| Keep history for | 180 days | trimmed automatically |

**Per-supply overrides** let one cartridge behave differently — a colour you burn through
on big wraps might warn at 40%, while the maintenance cartridge can wait until 10%.

Repeat behaviour is deliberately quiet: each supply alerts once, then stays silent until
either the repeat window passes or it gets *worse* (a warning escalating to critical always
gets through). Once you replace the cartridge it re-arms itself, with a 5% margin so a
cartridge hovering right at the trip point doesn't flip-flop.

## Email

**Settings → Popup & email**. Fill in the SMTP server, from address and recipients
(comma-separated), then press **Send test email**. Gmail and Microsoft 365 accounts with
two-factor authentication need an **app password**, not the normal account password.

The config file is written owner-only (mode 600). To keep the password off disk entirely,
leave the box empty and set an environment variable instead:

```bash
export PRINTER_MONITOR_SMTP_PASSWORD='app-password-here'    # Windows: setx
```

Alert emails arrive with a coloured level bar per item, critical items first, and a note
about whether you have a spare on hand.

## Running it unattended

**Windows** — put a shortcut to `start-hidden.vbs` in the Startup folder (press Win+R,
type `shell:startup`, drop the shortcut in). It launches with no console window.

**Headless / no screen** — `printer-monitor monitor` runs the loop in the foreground with
email alerts only. As a systemd service:

```ini
[Unit]
Description=Printer supply monitor
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 -m printer_monitor monitor
Environment=PRINTER_MONITOR_SMTP_PASSWORD=app-password-here
Restart=always
User=printermon

[Install]
WantedBy=multi-user.target
```

## Command line

```bash
printer-monitor                  # open the window
printer-monitor check            # poll once, print all levels, exit
printer-monitor check --notify   # ...and fire alerts for anything low
printer-monitor monitor          # headless polling loop
printer-monitor discover 192.168.1.50 --raw   # dump every supply OID a printer reports
printer-monitor stock            # print the supply list
printer-monitor stock --add "Cyan ink cartridge (HP 831, 775 ml)" --printer latex360 --plus 2
printer-monitor stock --csv      # export
printer-monitor test-email
printer-monitor paths            # where config.json and the database live
```

`check` exits non-zero if any printer is unreachable, so it works in a scheduled task.

## Where things are stored

`printer-monitor paths` prints the exact locations:

- **Windows** — `%APPDATA%\PrinterMonitor\`
- **macOS** — `~/Library/Application Support/PrinterMonitor/`
- **Linux** — `~/.config/printer-monitor/`

`config.json` holds the settings; `monitor.db` (SQLite) holds level history, the supply
list and the alert log. Override with `--config` / `--db`, or the
`PRINTER_MONITOR_CONFIG`, `PRINTER_MONITOR_DB` and `PRINTER_MONITOR_HOME` environment
variables.

## Troubleshooting

**"No SNMP reply"** — check the IP, that SNMP is enabled on the printer, and the community
string. Both printers must be reachable from this PC; try `ping` first. Some firewalls
block outbound UDP 161.

**Supplies show "Unknown" or "Some remaining"** — that's the printer, not the app. HP
firmware reports `-3` ("some remaining") for a cartridge it can't measure precisely,
usually a brand-new or third-party one. Those can't be alerted on numerically; the shelf
count is your backstop. `printer-monitor discover <ip> --raw` shows exactly what the
printer is sending.

**Levels look wrong on the maintenance cartridge** — it's a receptacle that fills up. The
app shows life *remaining*, so 18% means nearly full and nearly due.

**No popup appears** — popups need a desktop session. Under `monitor` on a headless box,
use email.

## Testing

```bash
cd tools/printer-monitor
pip install -e ".[dev]"
python -m pytest
```

206 tests. The suite includes a small in-process SNMP agent
(`tests/fake_agent.py`) serving canned MIBs shaped like both real printers
(`tests/mibs.py`), so polling, v1-vs-v2c fallback, retries, level maths, alerting and the
CLI are all exercised over a real UDP socket rather than mocks. The GUI modules are
imported against a stub tkinter, so they're checked even on machines without it.
