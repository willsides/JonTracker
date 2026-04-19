import os
from dotenv import load_dotenv

load_dotenv()


def _get(key, default=""):
    """Read from a secret file if <KEY>_FILE is set, otherwise from env."""
    file_path = os.getenv(f"{key}_FILE")
    if file_path:
        try:
            with open(file_path) as f:
                return f.read().strip()
        except OSError:
            pass
    return os.getenv(key, default)


# Garmin MapShare
MAPSHARE_ID = _get("MAPSHARE_ID")
GARMIN_POLL_INTERVAL = int(os.getenv("GARMIN_POLL_INTERVAL", "300"))  # seconds

# Email (Gmail with App Password)
EMAIL_ADDRESS = _get("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = _get("EMAIL_APP_PASSWORD")
EMAIL_IMAP_SERVER = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")
EMAIL_POLL_INTERVAL = int(os.getenv("EMAIL_POLL_INTERVAL", "60"))  # seconds

# Photos
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "static", "photos")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp"}
MAX_PHOTOS = int(os.getenv("MAX_PHOTOS", "200"))

# Slideshow
SLIDESHOW_INTERVAL = int(os.getenv("SLIDESHOW_INTERVAL", "8"))  # seconds per photo

# Map
STADIA_API_KEY = _get("STADIA_API_KEY")
PCT_GEOJSON = os.path.join(os.path.dirname(__file__), "static", "pct.geojson")

# Flask
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
SECRET_KEY = _get("SECRET_KEY", "change-me-in-production")
