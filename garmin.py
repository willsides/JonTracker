"""
Polls the Garmin MapShare feed for the latest inReach GPS location.
MapShare is free with any inReach subscription — enable it in Garmin Explore app.
Feed URL: https://share.garmin.com/feed/Share/{MapShareIdentifier}
"""

import logging
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

import config

logger = logging.getLogger(__name__)

# Shared state — written by background thread, read by Flask routes
_state = {
    "lat": None,
    "lon": None,
    "timestamp": None,      # ISO8601 string from Garmin
    "message": None,        # Any text message sent from the device
    "last_checked": None,   # When we last polled
    "error": None,
}
_lock = threading.Lock()


def get_location():
    """Return a copy of the current location state (thread-safe)."""
    with _lock:
        return dict(_state)


def simulate_location(lat, lon, message=None):
    """Inject a simulated GPS fix directly into state (for testing)."""
    with _lock:
        _state["lat"] = lat
        _state["lon"] = lon
        _state["timestamp"] = datetime.now(timezone.utc).isoformat()
        _state["message"] = message
        _state["last_checked"] = datetime.now(timezone.utc).isoformat()
        _state["error"] = None
    logger.info("Simulated location set: %.6f, %.6f", lat, lon)


def _fetch_mapshare():
    """Fetch and parse the Garmin MapShare KML feed."""
    if not config.MAPSHARE_ID:
        logger.warning("MAPSHARE_ID not configured — skipping Garmin poll")
        return

    url = f"https://share.garmin.com/feed/Share/{config.MAPSHARE_ID}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        _parse_kml(resp.text)
        with _lock:
            _state["last_checked"] = datetime.now(timezone.utc).isoformat()
            _state["error"] = None
    except requests.RequestException as e:
        logger.error("Garmin MapShare fetch failed: %s", e)
        with _lock:
            _state["last_checked"] = datetime.now(timezone.utc).isoformat()
            _state["error"] = str(e)


def _parse_kml(kml_text):
    """
    Parse Garmin MapShare KML response.
    The feed returns Placemarks sorted newest-first; we take the first one.
    """
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as e:
        logger.error("KML parse error: %s", e)
        return

    # Garmin KML uses the standard KML namespace
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    # Collect all Placemarks with Point coordinates
    placemarks = root.findall(".//kml:Placemark", ns)
    if not placemarks:
        # Try without namespace (some Garmin feeds omit it)
        placemarks = root.findall(".//Placemark")

    best = None
    best_time = None

    for pm in placemarks:
        # Get coordinates
        coords_el = pm.find(".//kml:Point/kml:coordinates", ns)
        if coords_el is None:
            coords_el = pm.find(".//Point/coordinates")
        if coords_el is None or not coords_el.text:
            continue

        parts = coords_el.text.strip().split(",")
        if len(parts) < 2:
            continue

        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue

        # Get timestamp
        when_el = pm.find(".//kml:TimeStamp/kml:when", ns)
        if when_el is None:
            when_el = pm.find(".//TimeStamp/when")
        ts_str = when_el.text.strip() if when_el is not None and when_el.text else None

        ts = None
        if ts_str:
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y %H:%M:%S"):
                try:
                    ts = datetime.strptime(ts_str, fmt)
                    break
                except ValueError:
                    continue

        if best_time is None or (ts and ts > best_time):
            best = (lat, lon, ts_str, pm)
            best_time = ts

    if best:
        lat, lon, ts_str, best_pm = best

        message = None
        for data in best_pm.findall(".//kml:Data", ns) or best_pm.findall(".//Data"):
            name = data.get("name", "")
            if name.lower() in ("text", "message"):
                val = data.find("kml:value", ns)
                if val is None:
                    val = data.find("value")
                if val is not None and val.text:
                    message = val.text.strip()
                break

        with _lock:
            _state["lat"] = lat
            _state["lon"] = lon
            _state["timestamp"] = ts_str
            _state["message"] = message

        logger.info("Location updated: %.6f, %.6f @ %s", lat, lon, ts_str)
    else:
        logger.warning("No valid Placemarks found in MapShare feed")


def start_poller():
    """Start the background polling thread."""
    def _loop():
        logger.info("Garmin poller started (interval: %ds)", config.GARMIN_POLL_INTERVAL)
        while True:
            _fetch_mapshare()
            time.sleep(config.GARMIN_POLL_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name="garmin-poller")
    t.start()
    return t
