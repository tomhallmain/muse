"""ICY metadata polling for internet radio streams.

ICY (SHOUTcast/Icecast) embeds StreamTitle updates in the audio byte stream.
This module opens a dedicated HTTP connection with ``Icy-MetaData: 1`` and
reads those updates without interfering with VLC's audio connection.
"""

import http.client
import re
import threading
from typing import Callable, Tuple
from urllib.parse import urlparse

from utils.logging_setup import get_logger

logger = get_logger(__name__)

_CHUNK_SIZE = 4096
_SOCKET_TIMEOUT = 10.0
_RECONNECT_BASE_DELAY = 2.0
_RECONNECT_MAX_DELAY = 60.0


def parse_stream_title(raw: str) -> Tuple[str, str]:
    """Parse an ICY StreamTitle string into ``(artist, title)``.

    Most stations broadcast ``"Artist - Title"``; some send only a title.
    Returns ``("", "")`` for blank or whitespace-only input.
    """
    raw = (raw or "").strip()
    if not raw:
        return ("", "")
    if " - " in raw:
        artist, _, title = raw.partition(" - ")
        return (artist.strip(), title.strip())
    return ("", raw)


def _read_exactly(resp, n: int, stop_event: threading.Event) -> bytes:
    """Read exactly *n* bytes from *resp*.

    Raises ``EOFError`` if the stream ends prematurely or *stop_event* fires.
    """
    buf = bytearray()
    while len(buf) < n:
        if stop_event.is_set():
            raise EOFError("stopped")
        want = min(n - len(buf), _CHUNK_SIZE)
        chunk = resp.read(want)
        if not chunk:
            raise EOFError("stream ended")
        buf.extend(chunk)
    return bytes(buf)


def _parse_metadata_block(data: bytes) -> str:
    """Extract the ``StreamTitle`` value from raw ICY metadata bytes."""
    text = data.decode("utf-8", errors="replace").rstrip("\x00")
    m = re.search(r"StreamTitle='([^']*)'", text)
    return m.group(1) if m else ""


def _make_connection(url: str):
    """Return ``(connection, path)`` for *url*, using HTTPS when appropriate."""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(host, timeout=_SOCKET_TIMEOUT)
    else:
        conn = http.client.HTTPConnection(host, timeout=_SOCKET_TIMEOUT)
    return conn, path


def poll_icy_metadata(
    url: str,
    stop_event: threading.Event,
    on_title_change: Callable[[str, str], None],
) -> None:
    """Poll ICY metadata on *url* until *stop_event* is set.

    Opens a second HTTP connection (separate from VLC's audio connection) and
    reads embedded ``StreamTitle`` updates.  Calls ``on_title_change(artist,
    title)`` whenever the title changes.  Reconnects automatically on error.
    Safe to run as a daemon thread.

    Returns immediately without raising if the station does not advertise an
    ``icy-metaint`` header (i.e. no ICY metadata support).
    """
    last_title: str = ""
    delay = _RECONNECT_BASE_DELAY

    while not stop_event.is_set():
        conn = None
        try:
            conn, path = _make_connection(url)
            conn.request(
                "GET",
                path,
                headers={
                    "Icy-MetaData": "1",
                    "User-Agent": "Muse/1.0",
                    "Connection": "close",
                },
            )
            resp = conn.getresponse()

            metaint_hdr = resp.getheader("icy-metaint")
            if not metaint_hdr:
                logger.debug(
                    "No icy-metaint header for %s; ICY metadata not supported", url
                )
                conn.close()
                return

            metaint = int(metaint_hdr)
            delay = _RECONNECT_BASE_DELAY  # reset backoff on successful connect

            while not stop_event.is_set():
                # Discard the audio payload between metadata blocks
                _read_exactly(resp, metaint, stop_event)
                if stop_event.is_set():
                    break

                length_byte = resp.read(1)
                if not length_byte:
                    raise EOFError("stream ended reading length byte")
                meta_len = length_byte[0] * 16

                raw_title = ""
                if meta_len:
                    meta_bytes = _read_exactly(resp, meta_len, stop_event)
                    raw_title = _parse_metadata_block(meta_bytes)

                if raw_title and raw_title != last_title:
                    last_title = raw_title
                    artist, title = parse_stream_title(raw_title)
                    try:
                        on_title_change(artist, title)
                    except Exception:
                        logger.exception("on_title_change callback raised")

        except EOFError as exc:
            if stop_event.is_set():
                break
            logger.debug("ICY stream ended (%s); reconnecting in %.0fs", exc, delay)
        except Exception as exc:
            if stop_event.is_set():
                break
            logger.warning(
                "ICY connection error (%s); reconnecting in %.0fs", exc, delay
            )
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        if not stop_event.is_set():
            stop_event.wait(delay)
            delay = min(delay * 2, _RECONNECT_MAX_DELAY)
