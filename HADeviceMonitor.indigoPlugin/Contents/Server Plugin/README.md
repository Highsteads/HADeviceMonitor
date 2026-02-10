# HA Device Monitor Plugin

**Version:** 1.3.0
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
- When a **new problem** is found, a single line is logged per problem and one notification is sent (if enabled)
- If the **same problems persist** on the next check, nothing is logged or notified again
- When a device **recovers**, a single line is logged to confirm
- **Manual checks** (Run Check Now) always show the full box-drawing report regardless

This means you can safely run checks hourly or daily without filling your log or getting repeated notifications about the same issue.

## Indigo Variables

The plugin automatically creates and updates three variables in the **HA_Device_Monitor** folder:

| Variable | Description |
|----------|-------------|
| `ha_monitor_problem_count` | Current number of problem devices (use in triggers!) |
| `ha_monitor_device_count` | Total number of monitored HA Agent devices |
| `ha_monitor_last_check` | Timestamp of the last check cycle |

Use `ha_monitor_problem_count` in Indigo triggers to automate responses — e.g. turn on a warning LED, change a control page icon, or send additional alerts.

## Persistence Across Restarts

Known problems are saved to disk automatically. When the plugin restarts (or Indigo reboots), it restores the previous state — so you won't get false re-alerts for problems that were already known before the restart.

## Exclude List

Some entities are permanently unavailable by design (e.g. button entities, or devices you know are offline seasonally). Add their entity IDs to the exclude list in the config to skip them during checks. Supports comma-separated values.

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
2. Restores known problems from the previous session (no false re-alerts after restart)
3. Based on the schedule mode, waits for the next check window (or waits for a manual trigger)
4. Calls the HA REST API `/api/states` endpoint to get all entities (response time is tracked)
5. Skips any entities in the exclude list
6. Iterates all enabled HA Agent devices in Indigo and runs the four validation checks
7. Updates Indigo variables with the current status
8. **New problems only:** logged once as a single line per problem, with optional Pushover and/or Email notification
9. **Known problems:** suppressed on subsequent checks (no repeated alerts)
10. **Recoveries:** logged once when a previously-flagged device becomes healthy
11. **All OK:** nothing logged during scheduled checks (silent operation)

## Configuration

Access via **Plugins > HA Device Monitor > Configure...**

| Setting | Default | Description |
|---------|---------|-------------|
| Check schedule | Continuous | When to run checks: continuous, manual, hourly, daily, or weekly |
| Run at hour | 06:00 | Hour to run (shown for daily and weekly modes) |
| Run on day | Monday | Day of week to run (shown for weekly mode only) |
| Stale threshold | 2880 minutes (48h) | How old `last_updated` can be before flagging (0 = disable) |
| Exclude entity IDs | (empty) | Comma-separated entity IDs to skip during checks |
| Pushover alerts | Disabled | Send a single Pushover notification when new problems are found |
| Email+ alerts | Disabled | Send an email when new problems are found (requires Email+ SMTP account) |
| Email recipient | (empty) | Email address to send alerts to (shown when Email+ is enabled) |
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
- **Email+ plugin** (optional) — needed only if Email alerts are enabled (requires an SMTP account configured in Email+)
- **No additional Python dependencies** — uses only stdlib (`urllib`, `json`, `ssl`, `locale`, `time`)

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "HA Agent plugin is not installed or not enabled" | HA Agent plugin disabled or missing | Enable the Home Assistant Agent plugin |
| "No HA access token found" | Token not configured in HA Agent | Add a long-lived access token in HA Agent config |
| "HA API connection error" | Can't reach Home Assistant | Check HA is running and accessible from this machine |
| "HA API HTTP error 401" | Token is invalid or expired | Generate a new long-lived access token in HA |
| Many stale alerts | Threshold too low for infrequently-updating entities | Increase the stale threshold, add to exclude list, or set to 0 to disable |
| "No SMTP account found" | Email+ has no SMTP server configured | Create an SMTP account in Email+ plugin |

## Notes

- The plugin waits 30 seconds after startup before responding to schedule checks, giving the HA Agent time to establish its WebSocket connection
- Disabled Indigo devices are skipped
- Excluded entities are skipped before counting (they don't appear in totals)
- The `ha_generic` device type skips the domain check since generic devices can map to any HA domain
- Known problems persist across plugin/server restarts via a JSON state file
- Changing the schedule in config resets the schedule tracker, so the next eligible time slot will fire
- The thread checks every 30 seconds whether a scheduled run is due (very lightweight — no API calls until a check actually runs)
- The report header shows the HA connection URL and API response time for quick health verification

## Changelog

### v1.3.0
- **Indigo variables:** Creates `ha_monitor_problem_count`, `ha_monitor_device_count`, and `ha_monitor_last_check` in the HA_Device_Monitor folder — use in triggers and control pages
- **Persistence:** Known problems saved to disk and restored on restart — no false re-alerts after plugin/server restart
- **Email+ notifications:** New option to send alerts via Email+ plugin alongside or instead of Pushover
- **Exclude list:** Skip specific entity IDs from checks (comma-separated in config) — useful for entities that are permanently unavailable by design
- **Connection health:** Report header now shows HA URL and API response time in milliseconds

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
