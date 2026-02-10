#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# HA Device Monitor - Validates Home Assistant Agent devices against HA entities
# Author: CliveS and Claude Opus 4
# Version: 1.3.0
####################

import indigo
import locale
import logging
import json
import os
import ssl
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


HA_AGENT_PLUGIN_ID = "no.homeassistant.plugin"
EMAIL_PLUGIN_ID = "com.indigodomo.email"
VARIABLE_FOLDER_NAME = "HA_Device_Monitor"
STATE_FILE_NAME = "known_problems.json"

# Maps HA Agent deviceTypeId to expected HA entity domain
DEVICE_TYPE_TO_DOMAIN = {
    "HAclimate":          "climate",
    "HAdimmerType":       "light",
    "HAswitchType":       "switch",
    "HAbinarySensorType": "binary_sensor",
    "HAsensor":           "sensor",
    "ha_cover":           "cover",
    "ha_lock":            "lock",
    "ha_fan":             "fan",
    "ha_media_player":    "media_player",
    # ha_generic intentionally omitted - any domain is valid
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super().__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter(
            '%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.plugin_file_handler.setFormatter(pfmt)

        self.logLevel = int(pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.plugin_file_handler.setLevel(self.logLevel)

        self.pluginPrefs = pluginPrefs
        self.known_problems = {}   # entity_id -> {"type": str, "since": str}
        self.ha_base_url = None
        self.ha_token = None
        self.run_check_requested = False
        self.last_scheduled_run = None  # Track when we last ran to avoid double-firing
        self.last_api_response_ms = None  # Track HA API response time
        self.date_fmt = self._detect_date_format()
        self.state_file_path = self._get_state_file_path()

    # -------------------------------------------------------------------------
    # State persistence
    # -------------------------------------------------------------------------

    def _get_state_file_path(self):
        """Get path for the state persistence file in the plugin's preferences directory."""
        prefs_dir = os.path.join(
            indigo.server.getInstallFolderPath(),
            "Preferences", "Plugins"
        )
        return os.path.join(prefs_dir, f"com.clives.indigoplugin.hadevicemonitor.{STATE_FILE_NAME}")

    def _save_known_problems(self):
        """Save known problems to disk for persistence across restarts."""
        try:
            with open(self.state_file_path, "w") as f:
                json.dump(self.known_problems, f, indent=2)
            self.logger.debug(f"Saved {len(self.known_problems)} known problem(s) to disk")
        except Exception:
            self.logger.exception("Failed to save known problems to disk")

    def _load_known_problems(self):
        """Load known problems from disk (if any exist from a previous session)."""
        if not os.path.exists(self.state_file_path):
            self.logger.debug("No previous state file found - starting fresh")
            return

        try:
            with open(self.state_file_path, "r") as f:
                self.known_problems = json.load(f)
            count = len(self.known_problems)
            if count > 0:
                self.logger.info(f"Restored {count} known problem(s) from previous session (no false re-alerts)")
            else:
                self.logger.debug("Previous state file was empty")
        except Exception:
            self.logger.exception("Failed to load previous state - starting fresh")
            self.known_problems = {}

    # -------------------------------------------------------------------------
    # Indigo variable management
    # -------------------------------------------------------------------------

    def _get_or_create_variable_folder(self):
        """Get or create the HA_Device_Monitor variable folder."""
        try:
            for folder in indigo.variables.folders:
                if folder.name == VARIABLE_FOLDER_NAME:
                    return folder.id
            new_folder = indigo.variables.folder.create(VARIABLE_FOLDER_NAME)
            self.logger.info(f"Created variable folder: {VARIABLE_FOLDER_NAME}")
            return new_folder.id
        except Exception:
            self.logger.exception("Failed to create variable folder")
            return None

    def _update_variable(self, name, value):
        """Create or update an Indigo variable in the HA_Device_Monitor folder."""
        try:
            str_value = str(value)
            if name in indigo.variables:
                indigo.variable.updateValue(name, str_value)
            else:
                folder_id = self._get_or_create_variable_folder()
                if folder_id is not None:
                    indigo.variable.create(name, str_value, folder=folder_id)
                    self.logger.info(f"Created variable: {name} = {str_value}")
                else:
                    indigo.variable.create(name, str_value)
                    self.logger.info(f"Created variable: {name} = {str_value} (no folder)")
        except Exception:
            self.logger.exception(f"Failed to update variable {name}")

    def _update_status_variables(self, total, problems):
        """Update Indigo variables with current status."""
        self._update_variable("ha_monitor_problem_count", problems)
        self._update_variable("ha_monitor_device_count", total)
        self._update_variable("ha_monitor_last_check", self._format_timestamp())

    # -------------------------------------------------------------------------
    # Exclude list
    # -------------------------------------------------------------------------

    def _get_exclude_list(self):
        """Parse the exclude list from plugin preferences.

        Returns a set of entity_id strings to skip during checks.
        The user can enter entity IDs separated by commas, semicolons, or newlines.
        """
        raw = self.pluginPrefs.get("excludeEntities", "").strip()
        if not raw:
            return set()

        excludes = set()
        # Split on commas, semicolons, or newlines
        for item in raw.replace(";", ",").replace("\n", ",").split(","):
            entity_id = item.strip()
            if entity_id:
                excludes.add(entity_id)
        return excludes

    # -------------------------------------------------------------------------
    # Locale-aware date/time formatting
    # -------------------------------------------------------------------------

    @staticmethod
    def _detect_date_format():
        """Detect the system locale and return an appropriate strftime format string.

        Tries Python locale, then macOS AppleLocale, then defaults to ISO format.
        Common mappings:
            en_GB, de_DE, fr_FR, etc. -> dd/mm/yyyy HH:MM:SS
            en_US, en_CA, ja_JP, etc. -> mm/dd/yyyy HH:MM:SS  (or ISO)
        """
        locale_id = ""

        # Try 1: Python locale module
        try:
            loc = locale.getdefaultlocale()
            if loc and loc[0]:
                locale_id = loc[0]  # e.g. "en_GB", "de_DE"
        except Exception:
            pass

        # Try 2: macOS AppleLocale (more reliable on macOS)
        if not locale_id:
            try:
                result = subprocess.run(
                    ["defaults", "read", "NSGlobalDomain", "AppleLocale"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    locale_id = result.stdout.strip()  # e.g. "en_GB"
            except Exception:
                pass

        locale_id = locale_id.lower()

        # Date-Month-Year countries (most of Europe, UK, Australia, etc.)
        dmy_locales = (
            "en_gb", "en_au", "en_nz", "en_ie", "en_za", "en_in",
            "de_", "fr_", "es_", "it_", "pt_", "nl_", "pl_", "cs_",
            "da_", "sv_", "no_", "fi_", "ru_", "uk_", "el_", "tr_",
            "ro_", "hu_", "bg_", "hr_", "sk_", "sl_", "lt_", "lv_",
            "et_", "is_", "ga_", "cy_",
        )

        # Year-Month-Day countries (Japan, China, Korea, etc.)
        ymd_locales = (
            "ja_", "zh_", "ko_", "hu_",
        )

        for prefix in dmy_locales:
            if locale_id.startswith(prefix):
                return "%d/%m/%Y %H:%M:%S"

        for prefix in ymd_locales:
            if locale_id.startswith(prefix):
                return "%Y-%m-%d %H:%M:%S"

        # Default: US-style mm/dd/yyyy for en_US, ISO for anything else
        if locale_id.startswith("en_us"):
            return "%m/%d/%Y %H:%M:%S"

        # Fallback to ISO 8601
        return "%Y-%m-%d %H:%M:%S"

    def _format_timestamp(self, dt=None):
        """Format a datetime using the detected locale format."""
        if dt is None:
            dt = datetime.now()
        return dt.strftime(self.date_fmt)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def startup(self):
        self.logger.debug("startup called")
        self.logger.info(f"Date format: {self._format_timestamp()} (locale detected)")
        self._read_ha_agent_config()
        self._load_known_problems()
        self._log_schedule_info()

    def shutdown(self):
        self.logger.debug("shutdown called")
        self._save_known_problems()

    def runConcurrentThread(self):
        try:
            # Brief pause on startup to let HA Agent connect first
            self.sleep(30)

            while True:
                # Check for manual trigger (always show full report)
                if self.run_check_requested:
                    self.run_check_requested = False
                    self.logger.info("Running manual check...")
                    try:
                        self._run_check_cycle(manual=True)
                    except Exception:
                        self.logger.exception("Error during manual check cycle")

                # Check if scheduled run is due (respects silent mode)
                elif self._is_check_due():
                    try:
                        self._run_check_cycle(manual=False)
                    except Exception:
                        self.logger.exception("Error during scheduled check cycle")

                # Sleep 30 seconds between schedule checks (lightweight)
                self.sleep(30)

        except self.StopThread:
            self._save_known_problems()

    # -------------------------------------------------------------------------
    # Schedule Logic
    # -------------------------------------------------------------------------

    def _is_check_due(self):
        """Determine if a scheduled check should run now."""
        mode = self.pluginPrefs.get("scheduleMode", "continuous")

        if mode == "manual":
            return False

        # Continuous mode: run every loop cycle (every 30 seconds)
        if mode == "continuous":
            return True

        now = datetime.now()
        current_hour = now.hour
        current_day = now.weekday()  # 0=Monday, 6=Sunday

        # Create a key for "this time slot" to avoid running multiple times
        # within the same eligible period
        if mode == "hourly":
            slot_key = f"{now.date()}-{current_hour}"
        elif mode == "daily":
            target_hour = int(self.pluginPrefs.get("scheduleHour", "06"))
            if current_hour != target_hour:
                return False
            slot_key = f"{now.date()}-{target_hour}"
        elif mode == "weekly":
            target_hour = int(self.pluginPrefs.get("scheduleHour", "06"))
            target_day = int(self.pluginPrefs.get("scheduleDay", "0"))
            if current_day != target_day or current_hour != target_hour:
                return False
            slot_key = f"{now.date()}-{target_hour}"
        else:
            return False

        # Only run once per slot
        if self.last_scheduled_run == slot_key:
            return False

        self.last_scheduled_run = slot_key
        self.logger.info(f"Scheduled check triggered ({mode})")
        return True

    def _log_schedule_info(self):
        """Log the current schedule configuration."""
        mode = self.pluginPrefs.get("scheduleMode", "continuous")

        if mode == "continuous":
            self.logger.info("Schedule: Continuous (every 30 seconds, silent unless problems found)")
        elif mode == "manual":
            self.logger.info("Schedule: Manual only - use Plugins > HA Device Monitor > Run Check Now")
        elif mode == "hourly":
            self.logger.info("Schedule: Every hour (on the hour)")
        elif mode == "daily":
            hour = self.pluginPrefs.get("scheduleHour", "06")
            self.logger.info(f"Schedule: Daily at {hour}:00")
        elif mode == "weekly":
            hour = self.pluginPrefs.get("scheduleHour", "06")
            day_idx = int(self.pluginPrefs.get("scheduleDay", "0"))
            day_name = DAY_NAMES[day_idx] if 0 <= day_idx <= 6 else "Monday"
            self.logger.info(f"Schedule: Weekly on {day_name} at {hour}:00")

    # -------------------------------------------------------------------------
    # Menu Items
    # -------------------------------------------------------------------------

    def run_check_now(self):
        """Triggered from Plugins > HA Device Monitor > Run Check Now."""
        self.logger.info("Check requested from menu")
        self.run_check_requested = True

    def show_readme(self):
        readme_path = os.path.join(
            indigo.server.getInstallFolderPath(),
            "Plugins", "HADeviceMonitor.indigoPlugin",
            "Contents", "Server Plugin", "README.md"
        )
        subprocess.Popen(["/usr/bin/open", readme_path])

    # -------------------------------------------------------------------------
    # Config UI
    # -------------------------------------------------------------------------

    def validatePrefsConfigUi(self, valuesDict):
        errorMsgDict = indigo.Dict()

        try:
            threshold = int(valuesDict.get("staleThreshold", 2880))
            if threshold < 0:
                errorMsgDict["staleThreshold"] = "Cannot be negative"
        except ValueError:
            errorMsgDict["staleThreshold"] = "Must be a number"

        if len(errorMsgDict) > 0:
            return False, valuesDict, errorMsgDict
        return True, valuesDict

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.logLevel = int(valuesDict.get("logLevel", logging.INFO))
            self.indigo_log_handler.setLevel(self.logLevel)
            self.plugin_file_handler.setLevel(self.logLevel)
            self.pluginPrefs = valuesDict
            self._read_ha_agent_config()

            stale_mins = int(valuesDict.get("staleThreshold", 2880))
            stale_display = f"{stale_mins}m ({stale_mins // 60}h)" if stale_mins > 0 else "disabled"
            self.logger.info(f"Config updated - stale threshold: {stale_display}")

            exclude_count = len(self._get_exclude_list())
            if exclude_count > 0:
                self.logger.info(f"Exclude list: {exclude_count} entity/entities will be skipped")

            # Reset schedule tracking so next eligible slot fires
            self.last_scheduled_run = None
            self._log_schedule_info()

    # -------------------------------------------------------------------------
    # HA Agent Config Reader
    # -------------------------------------------------------------------------

    def _read_ha_agent_config(self):
        try:
            # Check the HA Agent plugin is installed and enabled
            ha_plugin = indigo.server.getPlugin(HA_AGENT_PLUGIN_ID)
            if not ha_plugin or not ha_plugin.isEnabled():
                self.logger.error("Home Assistant Agent plugin is not installed or not enabled")
                self.ha_base_url = None
                self.ha_token = None
                return False

            # Read HA Agent preferences from its .indiPref file on disk
            prefs_path = os.path.join(
                indigo.server.getInstallFolderPath(),
                "Preferences", "Plugins",
                f"{HA_AGENT_PLUGIN_ID}.indiPref"
            )

            if not os.path.exists(prefs_path):
                self.logger.error(f"HA Agent preferences file not found: {prefs_path}")
                self.ha_base_url = None
                self.ha_token = None
                return False

            tree = ET.parse(prefs_path)
            root = tree.getroot()

            ha_prefs = {}
            for elem in root:
                val = elem.text or ""
                if elem.get("type") == "bool":
                    val = val.lower() == "true"
                ha_prefs[elem.tag] = val

            address = ha_prefs.get("address", "localhost")
            port = ha_prefs.get("port", "8123")
            use_ssl = ha_prefs.get("use_ssl", False)
            self.ha_token = ha_prefs.get("haToken", "")

            if not self.ha_token:
                self.logger.error("No HA access token found in Home Assistant Agent config")
                self.ha_base_url = None
                return False

            scheme = "https" if use_ssl else "http"
            self.ha_base_url = f"{scheme}://{address}:{port}"
            self.logger.info(f"Using HA Agent connection: {self.ha_base_url}")
            return True

        except Exception:
            self.logger.exception("Failed to read Home Assistant Agent config")
            self.ha_base_url = None
            self.ha_token = None
            return False

    # -------------------------------------------------------------------------
    # HA REST API
    # -------------------------------------------------------------------------

    def _fetch_ha_entities(self):
        if not self.ha_base_url or not self.ha_token:
            if not self._read_ha_agent_config():
                return None

        url = f"{self.ha_base_url}/api/states"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json"
        })

        # Allow self-signed certs
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.last_api_response_ms = int((time.time() - start_time) * 1000)

            entities = {}
            for entity in data:
                entities[entity["entity_id"]] = entity
            self.logger.debug(f"Fetched {len(entities)} entities from Home Assistant ({self.last_api_response_ms}ms)")
            return entities

        except urllib.error.HTTPError as e:
            self.last_api_response_ms = None
            self.logger.error(f"HA API HTTP error {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            self.last_api_response_ms = None
            self.logger.error(f"HA API connection error: {e.reason}")
            return None
        except Exception:
            self.last_api_response_ms = None
            self.logger.exception("Failed to fetch HA entities")
            return None

    # -------------------------------------------------------------------------
    # Main Check Cycle
    # -------------------------------------------------------------------------

    def _run_check_cycle(self, manual=False):
        entities = self._fetch_ha_entities()
        if entities is None:
            self.logger.warning("Skipping check cycle - could not fetch HA entities")
            return

        stale_threshold = int(self.pluginPrefs.get("staleThreshold", 2880))
        exclude_list = self._get_exclude_list()
        now = datetime.now(timezone.utc)
        total = 0
        problems = 0
        excluded = 0
        new_problems = []
        current_problem_ids = set()

        # Collect results by category for the report
        missing_devices = []
        unavailable_devices = []
        domain_mismatch_devices = []
        stale_devices = []
        recovered_devices = []

        for dev in indigo.devices:
            if dev.pluginId != HA_AGENT_PLUGIN_ID:
                continue
            if not dev.enabled:
                continue

            entity_id = dev.address

            # Check exclude list before counting
            if entity_id and entity_id in exclude_list:
                excluded += 1
                continue

            total += 1

            if not entity_id:
                key = f"device:{dev.id}"
                is_new = self._record_problem(key, "no_address")
                if is_new:
                    new_problems.append(f"{dev.name}: no entity_id")
                missing_devices.append({"name": dev.name, "entity": "(none)", "detail": "No entity_id configured"})
                problems += 1
                current_problem_ids.add(key)
                continue

            # --- Check 1: Entity exists ---
            if entity_id not in entities:
                is_new = self._record_problem(entity_id, "missing")
                if is_new:
                    new_problems.append(f"{dev.name}: missing in HA")
                missing_devices.append({"name": dev.name, "entity": entity_id, "detail": "Not found in HA"})
                problems += 1
                current_problem_ids.add(entity_id)
                continue

            ha_entity = entities[entity_id]

            # --- Check 2: Entity available ---
            state = ha_entity.get("state", "")
            if state in ("unavailable", "unknown"):
                is_new = self._record_problem(entity_id, "unavailable")
                if is_new:
                    new_problems.append(f"{dev.name}: {state}")
                unavailable_devices.append({"name": dev.name, "entity": entity_id, "detail": state})
                problems += 1
                current_problem_ids.add(entity_id)
                continue

            # --- Check 3: Domain matches device type ---
            entity_domain = entity_id.split(".")[0]
            expected_domain = DEVICE_TYPE_TO_DOMAIN.get(dev.deviceTypeId)
            if expected_domain and entity_domain != expected_domain:
                is_new = self._record_problem(entity_id, "domain_mismatch")
                if is_new:
                    new_problems.append(f"{dev.name}: domain mismatch")
                domain_mismatch_devices.append({
                    "name": dev.name, "entity": entity_id,
                    "detail": f"Expected '{expected_domain}', got '{entity_domain}'"
                })
                problems += 1
                current_problem_ids.add(entity_id)

            # --- Check 4: Freshness ---
            if stale_threshold > 0:
                last_updated_str = ha_entity.get("last_updated", "")
                if last_updated_str:
                    try:
                        last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                        age_minutes = (now - last_updated).total_seconds() / 60.0
                        if age_minutes > stale_threshold:
                            is_new = self._record_problem(entity_id, "stale")
                            if is_new:
                                new_problems.append(f"{dev.name}: stale ({int(age_minutes)}m)")
                            stale_devices.append({
                                "name": dev.name, "entity": entity_id,
                                "detail": self._format_age(age_minutes)
                            })
                            problems += 1
                            current_problem_ids.add(entity_id)
                    except (ValueError, TypeError):
                        self.logger.debug(f"Could not parse last_updated for {entity_id}: {last_updated_str}")

        # Check for recoveries
        recovered = set(self.known_problems.keys()) - current_problem_ids
        for entity_id in recovered:
            info = self.known_problems.pop(entity_id)
            recovered_devices.append({"entity": entity_id, "type": info["type"]})

        # Update Indigo variables
        self._update_status_variables(total, problems)

        # Save state to disk whenever problems change
        has_news = len(new_problems) > 0 or len(recovered_devices) > 0
        if has_news:
            self._save_known_problems()

        if manual:
            # Manual check: always show the full report
            self._log_report(
                total, problems,
                missing_devices, unavailable_devices,
                domain_mismatch_devices, stale_devices,
                recovered_devices, stale_threshold, excluded
            )
        elif has_news:
            # Scheduled/continuous: only log the specific changes, not the full report
            for p in new_problems:
                self.logger.warning(f"NEW PROBLEM: {p}")
            for item in recovered_devices:
                self.logger.info(f"RECOVERED: {item['entity']} (was: {item['type']})")
        else:
            # Nothing new: stay silent
            self.logger.debug(
                f"Silent check complete: {total - problems}/{total} OK, "
                f"{problems} known issue(s), nothing new"
            )

        # Send notifications only for NEW problems (not repeated on subsequent checks)
        if new_problems:
            summary = f"{len(new_problems)} new problem(s):\n" + "\n".join(f"- {p}" for p in new_problems)
            if self.pluginPrefs.get("enablePushover", False):
                self._send_pushover("HA Device Monitor", summary)
            if self.pluginPrefs.get("enableEmail", False):
                self._send_email("HA Device Monitor Alert", summary)

    @staticmethod
    def _format_age(minutes):
        """Format age in minutes to a human-readable string."""
        if minutes < 60:
            return f"{int(minutes)}m"
        elif minutes < 1440:
            return f"{minutes / 60:.1f}h"
        else:
            return f"{minutes / 1440:.1f}d"

    def _log_report(self, total, problems, missing, unavailable, domain_mismatch, stale, recovered, stale_threshold, excluded=0):
        """Output a formatted report to the Indigo log using Unicode box-drawing characters."""
        ok_count = total - problems
        timestamp = self._format_timestamp()
        W = 88  # inner width (fits most entity IDs in full)

        # Box-drawing characters
        TL = "\u2554"   # ╔  top-left double
        TR = "\u2557"   # ╗  top-right double
        BL = "\u255A"   # ╚  bottom-left double
        BR = "\u255D"   # ╝  bottom-right double
        HD = "\u2550"   # ═  horizontal double
        VD = "\u2551"   # ║  vertical double
        HL = "\u2500"   # ─  horizontal light
        LT = "\u255F"   # ╟  left tee (double-vert, light-horiz)
        RT = "\u2562"   # ╢  right tee (double-vert, light-horiz)
        LS = "\u2560"   # ╠  left tee double
        RS = "\u2563"   # ╣  right tee double

        C1W = 36  # column 1 width (device name)

        def pad_row(text):
            """Pad or truncate text to exactly W characters."""
            if len(text) > W:
                text = text[:W]
            return f"{VD} {text:<{W}} {VD}"

        def section_hdr(text):
            return f"{LS}{HD * (W + 2)}{RS}\n{pad_row(text)}\n{LT}{HL * (W + 2)}{RT}"

        def data_row(col1, col2):
            col1 = col1[:C1W]
            max_c2 = W - C1W - 3  # 3 = spaces between columns
            col2 = col2[:max_c2]
            line = f"{col1:<{C1W}}   {col2}"
            return pad_row(line)

        lines = []
        lines.append("")
        lines.append(f"{TL}{HD * (W + 2)}{TR}")
        lines.append(f"{VD}{'HA DEVICE MONITOR REPORT':^{W + 2}}{VD}")
        lines.append(f"{VD}{timestamp:^{W + 2}}{VD}")
        lines.append(f"{LS}{HD * (W + 2)}{RS}")

        # Connection health
        if self.ha_base_url:
            conn_info = f"HA: {self.ha_base_url}"
            if self.last_api_response_ms is not None:
                conn_info += f"  (API response: {self.last_api_response_ms}ms)"
            lines.append(pad_row(conn_info))

        # Summary
        if problems == 0:
            status = f"[OK] ALL OK: {ok_count}/{total} devices healthy"
        else:
            status = f"[!!] PROBLEMS: {ok_count}/{total} OK, {problems} issue(s)"
        lines.append(pad_row(status))
        stale_display = f"{stale_threshold}m ({stale_threshold // 60}h)" if stale_threshold > 0 else "disabled"
        lines.append(pad_row(f"Stale threshold: {stale_display}"))
        if excluded > 0:
            lines.append(pad_row(f"Excluded: {excluded} entity/entities skipped"))

        if problems == 0 and not recovered:
            lines.append(pad_row(""))
            lines.append(pad_row("No issues detected."))
            lines.append(f"{BL}{HD * (W + 2)}{BR}")
            self.logger.info("\n".join(lines))
            return

        # Missing entities
        if missing:
            lines.append(section_hdr(f"[X] MISSING ENTITIES ({len(missing)})"))
            for item in sorted(missing, key=lambda x: x["name"]):
                lines.append(data_row(item["name"], item["entity"]))

        # Unavailable
        if unavailable:
            lines.append(section_hdr(f"[!] UNAVAILABLE ({len(unavailable)})"))
            for item in sorted(unavailable, key=lambda x: x["name"]):
                lines.append(data_row(item["name"], item["detail"]))

        # Domain mismatch
        if domain_mismatch:
            lines.append(section_hdr(f"[?] DOMAIN MISMATCH ({len(domain_mismatch)})"))
            for item in sorted(domain_mismatch, key=lambda x: x["name"]):
                lines.append(data_row(item["name"], item["detail"]))

        # Stale
        if stale:
            lines.append(section_hdr(f"[~] STALE ({len(stale)})"))
            for item in sorted(stale, key=lambda x: x["name"]):
                lines.append(data_row(item["name"], f"Last: {item['detail']}"))

        # Recovered
        if recovered:
            lines.append(section_hdr(f"[+] RECOVERED ({len(recovered)})"))
            for item in sorted(recovered, key=lambda x: x["entity"]):
                lines.append(data_row(item["entity"], f"was: {item['type']}"))

        # Footer
        lines.append(f"{BL}{HD * (W + 2)}{BR}")

        report = "\n".join(lines)
        if problems > 0:
            self.logger.warning(report)
        else:
            self.logger.info(report)

    # -------------------------------------------------------------------------
    # Problem Tracking & Alerting
    # -------------------------------------------------------------------------

    def _record_problem(self, entity_id, problem_type):
        """Record a problem. Returns True if this is a NEW problem, False if already known."""
        if entity_id in self.known_problems:
            return False

        self.known_problems[entity_id] = {
            "type": problem_type,
            "since": self._format_timestamp(),
        }
        return True

    def _send_pushover(self, title, message):
        try:
            pushover = indigo.server.getPlugin("io.thechad.indigoplugin.pushover")
            if pushover and pushover.isEnabled():
                pushover.executeAction("send", props={
                    "msgTitle": title,
                    "msgBody": message,
                    "msgPriority": 0,
                    "msgSound": "pushover"
                })
                self.logger.debug(f"Pushover sent: {message}")
            else:
                self.logger.debug("Pushover plugin not available")
        except Exception:
            self.logger.exception("Failed to send Pushover notification")

    def _send_email(self, subject, message):
        """Send an email notification via the Email+ plugin."""
        try:
            email_plugin = indigo.server.getPlugin(EMAIL_PLUGIN_ID)
            if not email_plugin or not email_plugin.isEnabled():
                self.logger.debug("Email+ plugin not available")
                return

            email_to = self.pluginPrefs.get("emailTo", "").strip()
            if not email_to:
                self.logger.warning("Email notifications enabled but no recipient address configured")
                return

            # Find the first SMTP device in the Email+ plugin
            smtp_device_id = None
            for dev in indigo.devices:
                if dev.pluginId == EMAIL_PLUGIN_ID and dev.deviceTypeId == "smtpAccount":
                    smtp_device_id = dev.id
                    break

            if smtp_device_id is None:
                self.logger.warning("Email notifications enabled but no SMTP account found in Email+ plugin")
                return

            email_plugin.executeAction("sendEmail", deviceId=smtp_device_id, props={
                "emailTo": email_to,
                "emailSubject": subject,
                "emailMessage": message,
                "emailFormat": "plain"
            })
            self.logger.debug(f"Email sent to {email_to}: {subject}")

        except Exception:
            self.logger.exception("Failed to send email notification")
