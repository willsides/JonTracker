"""
Polls a Gmail inbox for photo attachments sent from the field.
Setup: create a dedicated Gmail, enable 2-Step Verification,
generate an App Password at myaccount.google.com/apppasswords.
The person in the field emails photos to that address.
"""

import email
import imaplib
import io
import logging
import os
import threading
import time
from datetime import datetime, timezone
from email.header import decode_header

from PIL import Image, ImageOps

import config

logger = logging.getLogger(__name__)

_processed_uids = set()  # Track already-downloaded message UIDs


def _sanitize_filename(name):
    """Strip unsafe characters from an attachment filename."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return "".join(c if c in keep else "_" for c in name)


def _decode_header_value(value):
    """Decode a potentially encoded email header value."""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _exif_capture_date(data, ext):
    """Return the EXIF DateTimeOriginal from image bytes, or None if unavailable."""
    if ext.lower() not in ('.jpg', '.jpeg', '.webp', '.tiff'):
        return None
    try:
        exif = Image.open(io.BytesIO(data)).getexif()
        for tag_id in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            val = exif.get(tag_id)
            if val:
                return datetime.strptime(val, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _save_attachment(part, received_dt):
    """Save a single MIME attachment to the photos directory. Returns saved path or None."""
    filename = part.get_filename()
    if not filename:
        return None

    filename = _sanitize_filename(_decode_header_value(filename))
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        logger.debug("Skipping non-photo attachment: %s", filename)
        return None

    data = part.get_payload(decode=True)
    if not data:
        return None

    os.makedirs(config.PHOTOS_DIR, exist_ok=True)

    # Use EXIF capture date if available, fall back to email received date.
    # Marker E = EXIF date (shown to user), R = received date (sort only, not shown).
    exif_dt = _exif_capture_date(data, ext)
    photo_dt = exif_dt or received_dt
    marker = "E" if exif_dt else "R"
    ts = photo_dt.strftime("%Y%m%d_%H%M%S")
    base, extension = os.path.splitext(filename)
    dest = os.path.join(config.PHOTOS_DIR, f"{ts}_{marker}_{base}{extension}")

    # Skip if already saved (e.g. after a container restart scanning ALL mail)
    if os.path.exists(dest):
        logger.debug("Already saved, skipping: %s", os.path.basename(dest))
        return None

    # Avoid overwriting if two attachments share a name in the same second
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(config.PHOTOS_DIR, f"{ts}_{marker}_{base}_{counter}{extension}")
        counter += 1

    with open(dest, "wb") as f:
        f.write(data)

    logger.info("Saved photo: %s (%d bytes)", os.path.basename(dest), len(data))
    _generate_variants(dest)
    return dest


def _generate_variants(src_path):
    """Generate display and thumb JPEG variants for a saved photo."""
    basename = os.path.basename(src_path)
    base = os.path.splitext(basename)[0]

    display_dir = os.path.join(config.PHOTOS_DIR, "display")
    thumb_dir = os.path.join(config.PHOTOS_DIR, "thumb")
    os.makedirs(display_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)

    display_path = os.path.join(display_dir, base + ".jpg")
    thumb_path = os.path.join(thumb_dir, base + ".jpg")

    try:
        with Image.open(src_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")

            display_img = img.copy()
            display_img.thumbnail(
                (config.PHOTO_DISPLAY_MAX_WIDTH, config.PHOTO_DISPLAY_MAX_WIDTH),
                Image.LANCZOS,
            )
            display_img.save(display_path, "JPEG", quality=85, optimize=True)

            img.thumbnail(
                (config.PHOTO_THUMB_MAX_WIDTH, config.PHOTO_THUMB_MAX_WIDTH),
                Image.LANCZOS,
            )
            img.save(thumb_path, "JPEG", quality=80, optimize=True)

        logger.info("Generated variants for %s", basename)
    except Exception as e:
        logger.warning("Could not generate variants for %s: %s", basename, e)


def _prune_old_photos():
    """If we exceed MAX_PHOTOS, delete the oldest ones."""
    try:
        photos = sorted(
            [
                os.path.join(config.PHOTOS_DIR, f)
                for f in os.listdir(config.PHOTOS_DIR)
                if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS
            ]
        )
        while len(photos) > config.MAX_PHOTOS:
            oldest = photos.pop(0)
            os.remove(oldest)
            logger.info("Pruned old photo: %s", os.path.basename(oldest))
            base = os.path.splitext(os.path.basename(oldest))[0]
            for variant_dir in ("display", "thumb"):
                variant_path = os.path.join(config.PHOTOS_DIR, variant_dir, base + ".jpg")
                if os.path.exists(variant_path):
                    os.remove(variant_path)
    except OSError as e:
        logger.warning("Photo pruning error: %s", e)


def _poll_inbox():
    """Connect to IMAP, fetch unseen messages, save photo attachments."""
    if not config.EMAIL_ADDRESS or not config.EMAIL_APP_PASSWORD:
        logger.warning("Email credentials not configured — skipping poll")
        return

    try:
        mail = imaplib.IMAP4_SSL(config.EMAIL_IMAP_SERVER)
        mail.login(config.EMAIL_ADDRESS, config.EMAIL_APP_PASSWORD)
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        if status != "OK":
            logger.warning("IMAP search failed: %s", status)
            return

        uids = data[0].split()
        if not uids:
            logger.debug("No messages in inbox")
            return

        logger.info("Scanning %d message(s)", len(uids))
        saved_any = False

        for uid in uids:
            if uid in _processed_uids:
                continue

            status, msg_data = mail.fetch(uid, "(BODY.PEEK[])")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            # Determine received timestamp
            date_str = msg.get("Date", "")
            try:
                from email.utils import parsedate_to_datetime
                received_dt = parsedate_to_datetime(date_str)
            except Exception:
                received_dt = datetime.now(timezone.utc)

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue
                _save_attachment(part, received_dt)
                saved_any = True

            _processed_uids.add(uid)

        if saved_any:
            _prune_old_photos()

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error("IMAP error: %s", e)
    except OSError as e:
        logger.error("Network error during email poll: %s", e)


def _backfill_variants():
    """Generate variants for any existing photos that are missing them."""
    try:
        files = [
            f for f in os.listdir(config.PHOTOS_DIR)
            if os.path.splitext(f)[1].lower() in config.ALLOWED_EXTENSIONS
        ]
    except OSError:
        return
    missing = [
        f for f in files
        if not os.path.exists(
            os.path.join(config.PHOTOS_DIR, "display", os.path.splitext(f)[0] + ".jpg")
        )
    ]
    if missing:
        logger.info("Backfilling variants for %d photo(s)", len(missing))
    for f in missing:
        _generate_variants(os.path.join(config.PHOTOS_DIR, f))


def start_poller():
    """Start the background email polling thread."""
    def _loop():
        logger.info("Email poller started (interval: %ds)", config.EMAIL_POLL_INTERVAL)
        _backfill_variants()
        while True:
            _poll_inbox()
            time.sleep(config.EMAIL_POLL_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name="email-poller")
    t.start()
    return t
