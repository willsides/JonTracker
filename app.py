"""
JonTracker — web server for real-time GPS tracking and photo slideshows.
  - Left: Leaflet.js map with latest Garmin inReach GPS location
  - Right: Slideshow of photos received via email
"""

import logging
import os

from flask import Flask, jsonify, render_template, send_from_directory, send_file, abort, request

import config
import elevation
import email_receiver
import garmin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


# ---------------------------------------------------------------------------
# API routes (consumed by the kiosk page via fetch())
# ---------------------------------------------------------------------------

@app.route("/api/location")
def api_location():
    """Return the latest GPS location from the Garmin inReach."""
    return jsonify(garmin.get_location())


@app.route("/api/photos")
def api_photos():
    """Return a list of photo filenames sorted newest-first."""
    try:
        photos = sorted(
            [
                f for f in os.listdir(config.PHOTOS_DIR)
                if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS
            ],
            reverse=True,  # newest first (filenames are timestamp-prefixed)
        )
    except OSError:
        photos = []

    return jsonify({
        "photos": photos,
        "count": len(photos),
        "slideshow_interval": config.SLIDESHOW_INTERVAL,
    })


@app.route("/photos/<path:filename>")
def serve_photo(filename):
    """Serve a photo from the photos directory."""
    return send_from_directory(config.PHOTOS_DIR, filename)


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """Inject a test GPS fix. Only accessible from localhost."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "localhost only"}), 403
    body = request.get_json(silent=True) or {}
    try:
        lat = float(request.form.get("lat") or body.get("lat"))
        lon = float(request.form.get("lon") or body.get("lon"))
        msg = request.form.get("message") or body.get("message")
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon required"}), 400
    garmin.simulate_location(lat, lon, msg)
    return jsonify({"ok": True, "lat": lat, "lon": lon})


@app.route("/api/pct-trail")
def api_pct_trail():
    """Serve the PCT GeoJSON trail file if present."""
    if not os.path.exists(config.PCT_GEOJSON):
        return jsonify(None)
    return send_file(config.PCT_GEOJSON, mimetype="application/geo+json")


@app.route("/api/elevation-profile")
def api_elevation_profile():
    """Return the downsampled PCT elevation profile for the chart."""
    profile = elevation.get_profile(config.PCT_GEOJSON)
    return jsonify(profile)


# ---------------------------------------------------------------------------
# Main display page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        slideshow_interval=config.SLIDESHOW_INTERVAL,
        stadia_api_key=config.STADIA_API_KEY,
        has_pct=os.path.exists(config.PCT_GEOJSON),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(config.PHOTOS_DIR, exist_ok=True)

    # Start background pollers
    garmin.start_poller()
    email_receiver.start_poller()

    logger.info("Starting JonTracker on %s:%d", config.FLASK_HOST, config.FLASK_PORT)
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False, use_reloader=False)
