# HA Device Monitor Plugin

**Version:** 1.2.2
**Author:** CliveS
**Requires:** Indigo 2025.1+, Home Assistant Agent plugin

## What It Does

This plugin monitors all Indigo devices created by the Home Assistant Agent plugin, validating that each device's associated HA entity is healthy. 
It catches problems that the HA Agent plugin itself silently ignores.

## Why You Need It

The HA Agent plugin stores a Home Assistant entity_id (e.g. `climate.bedroom_trv`) in each Indigo device's address field. 
If that entity is deleted, renamed, or goes offline in Home Assistant, the HA Agent plugin logs a debug-level message and the Indigo device silently stops updating — retaining stale state values with no visible warning. This plugin fills that gap.

## Four Validation Checks

Each check cycle queries the Home Assistant REST API and validates every HA Agent device:

| Check | What It Detects |
|-------|----------------|
| **Exists** | Entity has been deleted or renamed in HA |
| **Available** | Entity is in `unavailable` or `unknown` state (integration/device offline) |
| **Domain Match** | Entity domain doesn't match the Indigo device type (e.g. a climate device pointing to a sensor entity) |
| **Freshness** | Entity's `last_updated` timestamp exceeds the configured threshold (integration may be frozen) |

## Smart Logging — No Spam

The plugin is designed to stay quiet and only speak up when something changes:

- **Scheduled checks** produce **no log output** when all devices are healthy
- When a **new problem** is found, the full report is logged **once** and one Pushover notification is sent (if enabled)
- If the **same problems persist** on the next check, nothing is logged or notified again
- When a device **recovers**, the report is logged once to confirm
- **Manual checks** (Run Check Now) always show the full report regardless

This means you can safely run checks hourly or daily without filling your log or getting repeated Pushover messages about the same issue.

## Schedule Options

The plugin supports five scheduling modes, configured via **Plugins > HA Device Monitor > Configure...**

| Mode | Description |
|------|-------------|
| **Continuous** (default) | Checks every 30 seconds in the background, completely silent unless a new problem is found |
| **Manual only** | No automatic checks. Use **Plugins > HA Device Monitor > Run Check Now** to trigger a check on demand |
| **Every hour** | Runs automatically once per hour, on the hour |
| **Daily** | Runs once per day at a configurable hour (e.g. 06:00) |
| **Weekly** | Runs once per week on a configurable day and hour (e.g. Monday at 06:00) |

You can always run **Run Check Now** from the plugin menu regardless of the schedule mode.

## How It Works

1. On startup, reads HA connection details (address, port, SSL, token) directly from the Home Assistant Agent plugin — no duplicate configuration needed
2. Based on the schedule mode, waits for the next check window (or waits for a manual trigger)
3. Calls the HA REST API `/api/states` endpoint to get all entities
4. Iterates all enabled HA Agent devices in Indigo
5. Runs the four validation checks on each device
6. **New problems only:** logged once as a WARNING with a formatted report, and optionally one Pushover notification
7. **Known problems:** suppressed on subsequent checks (no repeated alerts)
8. **Recoveries:** logged once when a previously-flagged device becomes healthy
9. **All OK:** nothing logged during scheduled checks (silent operation)

## Configuration

Access via **Plugins > HA Device Monitor > Configure...**

| Setting | Default | Description |
|---------|---------|-------------|
| Check schedule | Continuous | When to run checks: continuous, manual, hourly, daily, or weekly |
| Run at hour | 06:00 | Hour to run (shown for daily and weekly modes) |
| Run on day | Monday | Day of week to run (shown for weekly mode only) |
| Stale threshold | 2880 minutes (48h) | How old `last_updated` can be before flagging (0 = disable) |
| Pushover alerts | Disabled | Send a single Pushover notification when new problems are found (one-off, not repeated) |
| Log level | Informational | Controls verbosity of log output |

## Plugin Menu

Access via **Plugins > HA Device Monitor**

| Menu Item | Description |
|-----------|-------------|
| **Run Check Now** | Immediately triggers a validation check — always shows the full report |
| **Plugin Documentation...** | Opens this README file |
| **Configure...** | Opens the plugin configuration dialog |

## Locale-Aware Date Formatting

The plugin automatically detects your system locale and formats dates accordingly:

| Locale | Format |
|--------|--------|
| UK, Europe, Australia | dd/mm/yyyy HH:MM:SS |
| US | mm/dd/yyyy HH:MM:SS |
| Japan, China, Korea | yyyy-mm-dd HH:MM:SS |
| Other/Unknown | yyyy-mm-dd HH:MM:SS (ISO 8601) |

## Device Type Mapping

The plugin knows which HA domain each HA Agent device type expects:

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

## Requirements

- **Home Assistant Agent plugin** must be installed, enabled, and configured with a valid long-lived access token
- **Pushover plugin** (optional) — needed only if Pushover alerts are enabled
- **No additional Python dependencies** — uses only stdlib (`urllib`, `json`, `ssl`, `locale`)

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "HA Agent plugin is not installed or not enabled" | HA Agent plugin disabled or missing | Enable the Home Assistant Agent plugin |
| "No HA access token found" | Token not configured in HA Agent | Add a long-lived access token in HA Agent config |
| "HA API connection error" | Can't reach Home Assistant | Check HA is running and accessible from this machine |
| "HA API HTTP error 401" | Token is invalid or expired | Generate a new long-lived access token in HA |
| Many stale alerts | Threshold too low for infrequently-updating entities | Increase the stale threshold or set to 0 to disable |

## Notes

- The plugin waits 30 seconds after startup before responding to schedule checks, giving the HA Agent time to establish its WebSocket connection
- Disabled Indigo devices are skipped
- The `ha_generic` device type skips the domain check since generic devices can map to any HA domain
- Problem tracking is reset when the plugin restarts (all problems will be treated as new on the first check after restart)
- Changing the schedule in config resets the schedule tracker, so the next eligible time slot will fire
- The thread checks every 30 seconds whether a scheduled run is due (very lightweight — no API calls until a check actually runs)

## Changelog

### v1.2.2
- Added GithubInfo metadata to Info.plist for Indigo Plugin Store update checking
- Scheduled/continuous checks now log only individual NEW PROBLEM / RECOVERED lines (not full report)
- Full box-drawing report reserved for manual "Run Check Now" only

### v1.2.1
- Added continuous mode (default): checks every 30 seconds, completely silent unless problems found
- Near-instant detection of broken entity links

### v1.2.0
- Smart silent operation: scheduled checks produce no log output when all is well
- Problems logged and notified once only — no repeated alerts for known issues
- Recoveries logged once when devices return to healthy state
- Wider report format (88 characters) to show full entity IDs
- Locale-aware date/time formatting (UK, US, European, Asian formats)
- Replaced emoji markers with fixed-width ASCII for consistent report alignment

### v1.1.0
- Replaced fixed-interval polling with flexible scheduling: manual, hourly, daily, weekly
- Added "Run Check Now" menu item for on-demand checks
- Default mode is now "manual only" — no automatic checks unless configured
- Stale threshold default raised from 60 minutes to 2880 minutes (48 hours)
- Pushover default changed to disabled; sends single batched summary instead of per-problem
- Removed checkInterval config field (replaced by schedule mode)

### v1.0.0
- Initial release with four validation checks (exists, available, domain match, freshness)
- Pushover integration
- Alert suppression for known problems
- Recovery detection
