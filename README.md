# HA Device Monitor for Indigo

A plugin for [Indigo Domotics](https://www.indigodomo.com/) that monitors the health of all devices created by the **Home Assistant Agent** plugin. It catches problems that the HA Agent plugin itself silently ignores.

## The Problem

The Home Assistant Agent plugin stores a Home Assistant entity ID (e.g. `climate.bedroom_trv`) in each Indigo device's address field. If that entity is deleted, renamed, or goes offline in Home Assistant, the HA Agent plugin logs a debug-level message and the Indigo device **silently stops updating** — retaining stale state values with no visible warning.

**HA Device Monitor** fills that gap with four validation checks run on a configurable schedule.

## Features

- **Entity Exists** — Detects entities deleted or renamed in Home Assistant
- **Entity Available** — Detects entities in `unavailable` or `unknown` state
- **Domain Match** — Detects entity domain mismatches (e.g. a climate device pointing to a sensor entity)
- **Freshness** — Detects entities that haven't updated within a configurable threshold
- **Zero Configuration** — Reads HA connection details directly from the HA Agent plugin (no duplicate setup)
- **Flexible Scheduling** — Continuous, manual, hourly, daily, or weekly check cycles
- **On-Demand Checks** — Run a check anytime from the plugin menu
- **Continuous Monitoring** — Default mode checks every 30 seconds, completely silent unless problems found
- **Silent Operation** — Scheduled checks produce no log output unless something changes
- **One-Off Alerts** — Problems are logged and notified once only; no repeated alerts for known issues
- **Recovery Tracking** — Logs when previously-flagged devices become healthy again
- **Indigo Variables** — Creates variables for problem count, device count, and last check time — use in triggers!
- **Persistence** — Known problems survive plugin/server restarts — no false re-alerts
- **Exclude List** — Skip specific entity IDs that are permanently unavailable by design
- **Email+ Support** — Send alerts via Email+ plugin alongside or instead of Pushover
- **Connection Health** — Report shows HA URL and API response time for quick diagnostics
- **Locale-Aware** — Date/time formatting automatically adapts to your system locale (UK, US, European, Asian)
- **Formatted Reports** — Professional box-drawing formatted output in the Indigo log

## Smart Logging — No Spam

The plugin is designed to stay quiet and only speak up when something changes:

| Scenario | Log Output | Notification |
|----------|-----------|--------------|
| Scheduled check, all OK | Nothing | No |
| New problem found | Single line per problem (once) | One Pushover/Email |
| Same problems persist on next check | Nothing | No |
| Device recovers | Single line per recovery (once) | No |
| Manual "Run Check Now" | Full box-drawing report (always) | Only if new problems |

This means you can safely run checks continuously or hourly without filling your log or getting repeated notifications about the same issue.

## Indigo Variables

The plugin automatically creates and updates three variables in the **HA_Device_Monitor** folder:

| Variable | Description |
|----------|-------------|
| `ha_monitor_problem_count` | Current number of problem devices (use in triggers!) |
| `ha_monitor_device_count` | Total number of monitored HA Agent devices |
| `ha_monitor_last_check` | Timestamp of the last check cycle |

## Requirements

- **Indigo 2025.1** or later
- **Home Assistant Agent plugin** — installed, enabled, and configured with a valid long-lived access token
- **Pushover plugin** (optional) — only needed if you want push notifications
- **Email+ plugin** (optional) — only needed if you want email notifications (requires an SMTP account)

No additional Python dependencies required — uses only the Python standard library.

## Installation

1. Download `HADeviceMonitor.indigoPlugin.zip` from the [latest release](../../releases/latest)
2. Unzip and double-click `HADeviceMonitor.indigoPlugin`
3. Indigo will offer to install it — enable when prompted

That's it! The plugin automatically reads your HA connection details from the Home Assistant Agent plugin.

## Configuration

Access via **Plugins > HA Device Monitor > Configure...**

| Setting | Default | Description |
|---------|---------|-------------|
| Check schedule | Continuous | When to run checks: continuous (every 30s), manual, hourly, daily, or weekly |
| Run at hour | 06:00 | Hour to run (for daily and weekly modes) |
| Run on day | Monday | Day of week (for weekly mode) |
| Stale threshold | 2880 min (48h) | How old `last_updated` can be before flagging (0 = disable) |
| Exclude entity IDs | (empty) | Comma-separated entity IDs to skip during checks |
| Pushover alerts | Disabled | Send a one-off Pushover notification when new problems are found |
| Email+ alerts | Disabled | Send an email when new problems are found |
| Email recipient | (empty) | Email address to send alerts to (shown when Email+ is enabled) |
| Log level | Informational | Controls verbosity of log output |

## Plugin Menu

Access via **Plugins > HA Device Monitor**

| Menu Item | Description |
|-----------|-------------|
| **Run Check Now** | Trigger a check immediately — always shows the full report |
| **Plugin Documentation...** | Opens the full documentation |
| **Configure...** | Opens the configuration dialog |

## Example Log Output

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                   HA DEVICE MONITOR REPORT                                 ║
║                                    09/02/2026 14:30:00                                     ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║ HA: http://homeassistant.local:8123  (API response: 142ms)                                 ║
║ [!!] PROBLEMS: 94/112 OK, 18 issue(s)                                                     ║
║ Stale threshold: 2880m (48h)                                                               ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║ [X] MISSING ENTITIES (8)                                                                   ║
╟──────────────────────────────────────────────────────────────────────────────────────────────╢
║ Bathroom Basin Spacial Learning      button.z_bathroom_basin_motion_sensor_identify         ║
║ HA BlueIris Plug                     switch.blueiris_power_switch_outlet                   ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

## Device Type Mapping

| HA Agent Device Type | Expected HA Domain |
|---------------------|-------------------|
| HAclimate | climate |
| HAdimmerType | light |
| HAswitchType | switch |
| HAbinarySensorType | binary_sensor |
| HAsensor | sensor |
| ha_cover | cover |
| ha_lock | lock |
| ha_fan | fan |
| ha_media_player | media_player |
| ha_generic | *(any — domain check skipped)* |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "HA Agent plugin is not installed or not enabled" | Enable the Home Assistant Agent plugin |
| "No HA access token found" | Add a long-lived access token in HA Agent config |
| "HA API connection error" | Check HA is running and accessible |
| "HA API HTTP error 401" | Generate a new long-lived access token in HA |
| Many stale alerts | Increase stale threshold, add to exclude list, or set to 0 to disable |
| "No SMTP account found" | Create an SMTP account in Email+ plugin |

## How It Works

1. On startup, reads HA connection details (address, port, SSL, token) from the HA Agent plugin's preferences file
2. Restores known problems from the previous session (no false re-alerts after restart)
3. Waits for the configured schedule (or a manual trigger)
4. Calls the HA REST API `/api/states` endpoint (with response time tracking)
5. Skips any entities in the exclude list
6. Validates every enabled HA Agent device against the four checks
7. Updates Indigo variables with current status
8. **New problems:** logs a single line per problem and sends one notification (if enabled)
9. **Known problems:** stays silent on subsequent checks
10. **Recoveries:** logs once when previously-flagged devices become healthy

## Contributing

Issues and pull requests are welcome! Please open an issue first to discuss any significant changes.

## Licence

This project is licensed under the MIT Licence — see the [LICENSE](LICENSE) file for details.

## Credits

**Author:** CliveS

Built with assistance from Claude (Anthropic).
