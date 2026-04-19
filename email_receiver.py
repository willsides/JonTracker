"""
Polls a Gmail inbox for photo attachments sent from the field.
Setup: create a dedicated Gmail, enable 2-Step Verification,
generate an App Password at myaccount.google.com/apppasswords.
The person in the field emails photos to that address.
"""

import email
import imaplib
import logging
import os
import threading
import time
from datetime import datetime, timezone
from email.header import decode_header

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

    os.makedirs(config.PHOTOS_DIR, exist_ok=True)

    # Prefix with timestamp so slideshow can sort by receipt order
    ts = received_dt.strftime("%Y%m%d_%H%M%S")
    base, extension = os.path.splitext(filename)
    dest = os.path.join(config.PHOTOS_DIR, f"{ts}_{base}{extension}")

    # Avoid overwriting if two attachments arrive in the same second
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(config.PHOTOS_DIR, f"{ts}_{base}_{counter}{extension}")
        counter += 1

    data = part.get_payload(decode=True)
    if not data:
        return None

    with open(dest, "wb") as f:
        f.write(data)

    logger.info("Saved photo: %s (%d bytes)", os.path.basename(dest), len(data))
    return dest


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

        # Search for unseen messages
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            logger.warning("IMAP search failed: %s", status)
            return

        uids = data[0].split()
        if not uids:
            logger.debug("No new messages")
            return

        logger.info("Found %d new message(s)", len(uids))
        saved_any = False

        for uid in uids:
            if uid in _processed_uids:
                continue

            status, msg_data = mail.fetch(uid, "(RFC822)")
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


def start_poller():
    """Start the background email polling thread."""
    def _loop():
        logger.info("Email poller started (interval: %ds)", config.EMAIL_POLL_INTERVAL)
        while True:
            _poll_inbox()
            time.sleep(config.EMAIL_POLL_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True, name="email-poller")
    t.start()
    return t
