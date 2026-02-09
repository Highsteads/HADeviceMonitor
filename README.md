# HA Device Monitor for Indigo

A plugin for [Indigo Domotics](https://www.indigodomo.com/) that monitors the health of all devices created by the **Home Assistant Agent** plugin. It catches problems that the HA Agent plugin itself silently ignores.

## The Problem

The Home Assistant Agent plugin stores a Home Assistant entity ID (e.g. `climate.bedroom_trv`) in each Indigo device's address field. If that entity is deleted, renamed, or goes offline in Home Assistant, the HA Agent plugin logs a debug-level message and the Indigo device **silently stops updating** - retaining stale state values with no visible warning.

**HA Device Monitor** fills that gap with four validation checks run on a configurable schedule.

## Features

- **Entity Exists** - Detects entities deleted or renamed in Home Assistant
- **Entity Available** - Detects entities in `unavailable` or `unknown` state
- **Domain Match** - Detects entity domain mismatches (e.g. a climate device pointing to a sensor entity)
- **Freshness** - Detects entities that haven't updated within a configurable threshold
- **Zero Configuration** - Reads HA connection details directly from the HA Agent plugin (no duplicate setup)
- **Flexible Scheduling** - Manual, hourly, daily, or weekly check cycles
- **On-Demand Checks** - Run a check anytime from the plugin menu
- **Smart Alerts** - Batched Pushover notifications (optional), with suppression of known problems
- **Recovery Tracking** - Logs when previously-flagged devices become healthy again
- **Locale-Aware** - Date/time formatting automatically adapts to your system locale
- **Formatted Reports** - Professional box-drawing formatted output in the Indigo log

## Requirements

- **Indigo 2025.1** or later
- **Home Assistant Agent plugin** - installed, enabled, and configured with a valid long-lived access token
- **Pushover plugin** (optional) - only needed if you want push notifications

No additional Python dependencies required - uses only the Python standard library.

## Installation

1. Download `HADeviceMonitor.indigoPlugin` from the [latest release](../../releases/latest)
2. Double-click the downloaded file - Indigo will offer to install it
3. Enable the plugin when prompted

That's it! The plugin automatically reads your HA connection details from the Home Assistant Agent plugin.

## Configuration

Access via **Plugins > HA Device Monitor > Configure...**

| Setting | Default | Description |
|---------|---------|-------------|
| Check schedule | Manual only | When to run checks: manual, hourly, daily, or weekly |
| Run at hour | 06:00 | Hour to run (for daily and weekly modes) |
| Run on day | Monday | Day of week (for weekly mode) |
| Stale threshold | 2880 min (48h) | How old `last_updated` can be before flagging (0 = disable) |
| Pushover alerts | Disabled | Send a batched Pushover notification for new problems |
| Log level | Informational | Controls verbosity of log output |

## Plugin Menu

Access via **Plugins > HA Device Monitor**

| Menu Item | Description |
|-----------|-------------|
| **Run Check Now** | Trigger a check immediately regardless of schedule |
| **Plugin Documentation...** | Opens the full documentation |
| **Configure...** | Opens the configuration dialog |

## Example Log Output

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                   HA DEVICE MONITOR REPORT                                   ║
║                                    09/02/2026 14:30:00                                       ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║ [!!] PROBLEMS: 94/112 OK, 18 issue(s)                                                       ║
║ Stale threshold: 2880m (48h)                                                                 ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║ [X] MISSING ENTITIES (8)                                                                     ║
╟──────────────────────────────────────────────────────────────────────────────────────────────╢
║ Bathroom Basin Spacial Learning    button.z_bathroom_basin_motion_sensor_identify             ║
║ HA BlueIris Plug                   switch.blueiris_power_switch_outlet                       ║
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
| ha_generic | *(any - domain check skipped)* |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "HA Agent plugin is not installed or not enabled" | Enable the Home Assistant Agent plugin |
| "No HA access token found" | Add a long-lived access token in HA Agent config |
| "HA API connection error" | Check HA is running and accessible |
| "HA API HTTP error 401" | Generate a new long-lived access token in HA |
| Many stale alerts | Increase stale threshold or set to 0 to disable |

## How It Works

1. On startup, reads HA connection details (address, port, SSL, token) from the HA Agent plugin's preferences file
2. Waits for the configured schedule (or a manual trigger)
3. Calls the HA REST API `/api/states` endpoint
4. Validates every enabled HA Agent device against the four checks
5. Logs a formatted report with categorised results
6. Sends a single batched Pushover notification for any **new** problems (if enabled)
7. Tracks recoveries when previously-flagged devices become healthy

## Contributing

Issues and pull requests are welcome! Please open an issue first to discuss any significant changes.

## Licence

This project is licensed under the MIT Licence - see the [LICENSE](LICENSE) file for details.

## Credits

**Author:** CliveS

Built with assistance from Claude (Anthropic).
