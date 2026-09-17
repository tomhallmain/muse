"""Content gates shared by every social source: Reddit, Bluesky and Mastodon.

An item is anything carrying these attributes:

    title       the text that may be spoken
    source      the community or instance it came from
    score       an engagement count
    age_hours   how old it is
    sensitive   the platform's own sensitive/NSFW flag
    restricted  quarantined, non-public, or otherwise limited by the platform
    filter_text everything the blacklist should run over

Rejections are whole-item: a social post is one short unit written by a
stranger, so there is no surrounding context to fall back on if part of it is
objectionable.
"""

import datetime
from typing import List, Optional

from library_data.blacklist import Blacklist
from utils.globals import BlacklistItemType
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class SocialSourceUnusable(Exception):
    """Raised when a filtered result set is not fit to speak from.

    Deliberately not a WebConnectionException: that one makes the DJ apologize
    for a network problem out loud, which would be untrue here and would draw
    attention to the filtering. This fails the topic quietly and rotation moves
    on.
    """


def iso_age_hours(timestamp) -> float:
    """Hours since an ISO 8601 timestamp.

    An unreadable or absent one reads as infinitely old, so the age gate drops
    the item rather than letting it through unchecked.
    """
    if not timestamp:
        return float("inf")
    try:
        stamp = datetime.datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        logger.warning(f"Unreadable timestamp: {timestamp}")
        return float("inf")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (now - stamp).total_seconds() / 3600.0)


def source_is_blacklisted(name: str) -> bool:
    """Whether a community or instance name is itself blacklisted.

    Checked as a CHANNEL, the type the extension downloader already uses for
    video channels, so a name blacklisted once is blacklisted everywhere.
    """
    if not name:
        return False
    items = Blacklist.find_blacklisted_items(name, item_type=BlacklistItemType.CHANNEL)
    if items:
        logger.info(f"Social source blacklisted: {name} ({list(items.keys())})")
        return True
    return False


def _metadata_rejection(item, min_score: int, max_age_hours: float) -> Optional[str]:
    """Why the platform's own metadata disqualifies an item, or None.

    Runs before any text matching: these flags are authoritative and free.
    """
    if item.sensitive:
        return "flagged sensitive"
    if item.restricted:
        return "not public"
    if item.score < min_score:
        return f"score {item.score} below {min_score}"
    if item.age_hours > max_age_hours:
        return f"{item.age_hours:.0f}h old, over {max_age_hours}h"
    if not item.title.strip():
        return "no text"
    return None


def _blacklist_rejection(item) -> Optional[str]:
    tags = list(Blacklist.find_blacklisted_items(item.filter_text).keys())
    return f"blacklisted: {tags}" if tags else None


def filter_items(
    items: List,
    *,
    min_score: int,
    max_age_hours: float,
    min_surviving: int,
    max_rejection_ratio: float,
) -> List:
    """Items fit to hand to the LLM.

    Raises SocialSourceUnusable when too few survive, or when too large a share
    of the set was rejected. The second condition matters because keyword
    matching catches named subjects rather than themes: a set where a large
    share tripped the blacklist likely holds more items on those themes that
    happen not to name them.
    """
    if not items:
        raise SocialSourceUnusable("No items were returned")

    kept = []
    for item in items:
        reason = _metadata_rejection(item, min_score, max_age_hours) or _blacklist_rejection(item)
        if reason is None:
            kept.append(item)
        else:
            logger.info(f"Social item rejected ({reason}): {item.title[:80]}")

    rejected = len(items) - len(kept)
    ratio = rejected / len(items)
    logger.info(f"Social filter kept {len(kept)} of {len(items)} items ({ratio:.0%} rejected)")

    if len(kept) < min_surviving:
        raise SocialSourceUnusable(
            f"Only {len(kept)} of {len(items)} items survived filtering, need {min_surviving}"
        )
    if ratio > max_rejection_ratio:
        raise SocialSourceUnusable(
            f"{ratio:.0%} of {len(items)} items were rejected, over the {max_rejection_ratio:.0%} "
            f"limit -- the survivors are a biased remnant"
        )
    return kept


def assemble_payload(header: str, items: List, total: int = -1) -> str:
    """Render the filtered items for the LLM prompt.

    Each item's own __str__ decides what is exposed; nothing here adds fields,
    so authors, URLs and comment text stay out by construction.
    """
    out = header.rstrip() + "\n"
    for counter, item in enumerate(items):
        if total > -1 and counter >= total:
            break
        out += f"{item}\n"
    return out
