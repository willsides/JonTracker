"""
Computes and caches the PCT elevation profile from the trail GeoJSON.

Expects Z (elevation) coordinates in the GeoJSON. Most PCT data from the
PCTA or CalTopo exports includes these. If your GeoJSON has no Z values,
re-export from CalTopo, Gaia GPS, or gpx.studio with elevation data enabled.

Distance calculation handles MultiLineString correctly: each segment's
internal distance is summed, and inter-segment gaps > 2km are treated as
route breaks (distance is bridged without adding the gap).
"""

import json
import logging
import math
import os

logger = logging.getLogger(__name__)

_cache = None

MILES_PER_KM = 0.621371
FT_PER_M = 3.28084
MAX_INTER_SEGMENT_GAP_KM = 2.0  # gaps larger than this are skipped (not trail distance)
TARGET_POINTS = 4000


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_profile(geojson_path):
    """Return the elevation profile dict (cached after first load)."""
    global _cache
    if _cache is not None:
        return _cache
    if not os.path.exists(geojson_path):
        return None
    _cache = _compute(geojson_path)
    return _cache


def _compute(path):
    logger.info("Computing PCT elevation profile from %s", path)
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to read PCT GeoJSON: %s", e)
        return None

    # Collect segments — keep each LineString as its own list
    segments = []
    for feature in data.get("features", []):
        geom = feature.get("geometry", {})
        gtype = geom.get("type")
        if gtype == "LineString":
            coords = geom.get("coordinates", [])
            if coords:
                segments.append(coords)
        elif gtype == "MultiLineString":
            for seg in geom.get("coordinates", []):
                if seg:
                    segments.append(seg)

    if not segments:
        logger.warning("No LineString coordinates found in PCT GeoJSON")
        return {"has_elevation": False, "points": [], "total_miles": 0}

    # Use only the longest segment — for a continuous trail like the PCT,
    # the single longest LineString is the main route. All other segments
    # (alternates, connectors, lateral trails) are discarded to prevent
    # inflating the total mileage.
    segments = [max(segments, key=len)]
    logger.info(
        "Using longest segment: %d coordinates",
        len(segments[0]),
    )

    # Check if any Z values exist
    has_ele = any(len(c) >= 3 for seg in segments for c in seg)

    # Sort segments south-to-north by their starting latitude
    segments.sort(key=lambda seg: seg[0][1])

    # Build profile: accumulate distance within each segment.
    # Between segments, bridge small gaps (<= MAX_INTER_SEGMENT_GAP_KM) as
    # trail distance; treat larger gaps as route breaks (no distance added).
    full = []
    cum_km = 0.0
    prev_coord = None

    for seg in segments:
        for coord in seg:
            lon, lat = coord[0], coord[1]
            ele_m = coord[2] if has_ele and len(coord) >= 3 else 0

            if prev_coord is not None:
                prev_lat, prev_lon = prev_coord[1], prev_coord[0]
                gap = haversine_km(prev_lat, prev_lon, lat, lon)
                if gap <= MAX_INTER_SEGMENT_GAP_KM:
                    cum_km += gap
                # else: large jump between segments — don't add the gap to mileage

            full.append({
                "dist": cum_km * MILES_PER_KM,
                "ele": round(ele_m * FT_PER_M) if has_ele else 0,
                "lat": lat,
                "lon": lon,
            })
            prev_coord = coord

    if not full:
        return {"has_elevation": False, "points": [], "total_miles": 0}

    total_miles = full[-1]["dist"]

    # Downsample evenly to TARGET_POINTS
    stride = max(1, len(full) // TARGET_POINTS)
    points = full[::stride]
    if points[-1] is not full[-1]:
        points.append(full[-1])

    for p in points:
        p["dist"] = round(p["dist"], 2)

    logger.info(
        "Profile: %d source points → %d samples, %.0f total miles, elevation: %s",
        len(full), len(points), total_miles, "yes" if has_ele else "no",
    )

    return {
        "has_elevation": has_ele,
        "total_miles": round(total_miles, 1),
        "points": points,
    }
