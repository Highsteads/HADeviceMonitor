# HA Device Monitor Plugin

**Version:** 1.1.0
**Author:** CliveS and Claude Opus 4
**Requires:** Indigo 2025.1+, Home Assistant Agent plugin

## What It Does

This plugin monitors all Indigo devices created by the Home Assistant Agent plugin, validating that each device's associated HA entity is healthy. It catches problems that the HA Agent plugin itself silently ignores.

## Why You Need It

The HA Agent plugin stores a Home Assistant entity_id (e.g. `climate.bedroom_trv`) in each Indigo device's address field. If that entity is deleted, renamed, or goes offline in Home Assistant, the HA Agent plugin logs a debug-level message and the Indigo device silently stops updating — retaining stale state values with no visible warning. This plugin fills that gap.

## Four Validation Checks

Each check cycle queries the Home Assistant REST API and validates every HA Agent device:

| Check | What It Detects |
|-------|----------------|
| **Exists** | Entity has been deleted or renamed in HA |
| **Available** | Entity is in `unavailable` or `unknown` state (integration/device offline) |
| **Domain Match** | Entity domain doesn't match the Indigo device type (e.g. a climate device pointing to a sensor entity) |
| **Freshness** | Entity's `last_updated` timestamp exceeds the configured threshold (integration may be frozen) |

## Schedule Options

The plugin supports four scheduling modes, configured via **Plugins > HA Device Monitor > Configure...**

| Mode | Description |
|------|-------------|
| **Manual only** (default) | No automatic checks. Use **Plugins > HA Device Monitor > Run Check Now** to trigger a check on demand |
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
6. New problems are logged as WARNINGs and optionally sent as a single batched Pushover notification
7. Known problems are suppressed (no repeated alerts on subsequent checks)
8. Recoveries are logged when a previously-flagged device becomes healthy
9. A summary line is logged each cycle (e.g. `HA Device Monitor: 24/26 devices OK, 2 problem(s)`)

## Configuration

Access via **Plugins > HA Device Monitor > Configure...**

| Setting | Default | Description |
|---------|---------|-------------|
| Check schedule | Manual only | When to run checks: manual, hourly, daily, or weekly |
| Run at hour | 06:00 | Hour to run (shown for daily and weekly modes) |
| Run on day | Monday | Day of week to run (shown for weekly mode only) |
| Stale threshold | 2880 minutes (48h) | How old `last_updated` can be before flagging (0 = disable) |
| Pushover alerts | Disabled | Send a single batched Pushover notification for new problems each cycle |
| Log level | Informational | Controls verbosity of log output |

## Plugin Menu

Access via **Plugins > HA Device Monitor**

| Menu Item | Description |
|-----------|-------------|
| **Run Check Now** | Immediately triggers a validation check regardless of schedule |
| **Plugin Documentation...** | Opens this README file |
| **Configure...** | Opens the plugin configuration dialog |

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
- **No additional Python dependencies** — uses only stdlib (`urllib`, `json`, `ssl`)

## Log Messages

**Schedule info (on startup and config change):**
```
Schedule: Manual only - use Plugins > HA Device Monitor > Run Check Now
Schedule: Daily at 06:00
Schedule: Weekly on Monday at 06:00
```

**Manual trigger:**
```
Check requested from menu
Running manual check...
```

**Problems (WARNING level):**
```
PROBLEM: 'Bedroom TRV' references 'climate.bedroom_trv' which does not exist in HA
PROBLEM: 'Kitchen Sensor' entity 'sensor.kitchen_temp' is 'unavailable' in HA
PROBLEM: 'Lounge Light' entity 'sensor.lounge' has domain 'sensor' but expected 'light'
PROBLEM: 'Garden Sensor' entity 'sensor.garden_temp' last updated 3000 minutes ago (threshold: 2880m)
```

**Recoveries (INFO level):**
```
RECOVERED: climate.bedroom_trv (missing) - previously reported: ...
```

**Summary (each cycle):**
```
HA Device Monitor: 24/26 devices OK, 2 problem(s)
HA Device Monitor: 26/26 devices OK
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "HA Agent plugin is not installed or not enabled" | HA Agent plugin disabled or missing | Enable the Home Assistant Agent plugin |
| "No HA access token found" | Token not configured in HA Agent | Add a long-lived access token in HA Agent config |
| "HA API connection error" | Can't reach Home Assistant | Check HA is running and accessible from this machine |
| "HA API HTTP error 401" | Token is invalid or expired | Generate a new long-lived access token in HA |
| Many stale alerts | Threshold too low for infrequently-updating entities | Increase the stale threshold or set to 0 to disable |
| No Configure... menu item | PluginConfig.xml in wrong location | Must be in `Contents/Server Plugin/` not `Contents/` |

## Notes

- The plugin waits 30 seconds after startup before responding to schedule checks, giving the HA Agent time to establish its WebSocket connection
- Disabled Indigo devices are skipped
- The `ha_generic` device type skips the domain check since generic devices can map to any HA domain
- Alert suppression is reset when the plugin restarts
- Changing the schedule in config resets the schedule tracker, so the next eligible time slot will fire
- The thread checks every 30 seconds whether a scheduled run is due (very lightweight — no API calls until a check actually runs)

## Changelog

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
