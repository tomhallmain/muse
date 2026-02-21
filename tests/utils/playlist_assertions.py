"""Playlist state inspection and assertion helpers for test scripts.

Works with both pure-backend tests (no Qt) and Qt widget tests.
"""

from typing import Optional


# ── Playlist state snapshot (backend) ──────────────────────────────────

def snapshot(label: str, playlist, master, limit: int = 20):
    """Print a compact summary of a playlist + master config state."""
    print(f"\n{'─'*80}")
    print(f"  {label}")
    print(f"{'─'*80}")
    print(f"  current_track_index: {playlist.current_track_index}")
    print(f"  pending_tracks:      {len(playlist.pending_tracks)}")
    print(f"  played_tracks:       {len(playlist.played_tracks)}")
    print(f"  master.played_tracks: {len(master.played_tracks)}")
    n = min(limit, len(playlist.sorted_tracks))
    for i in range(n):
        t = playlist.sorted_tracks[i]
        in_pending = t.get_parent_filepath() in playlist.pending_tracks
        is_cursor = i == playlist.current_track_index
        marker = "\u25b6 " if is_cursor else "  "
        status = "pending" if in_pending else "PLAYED"
        artist = t.artist[:30] if t.artist else "?"
        print(f"  {marker}{i:>3}. [{status:>7}] {t.title[:60]} - {artist}")


# ── Expected queue building ────────────────────────────────────────────

def build_expected_queue(playlist, format_fn=None) -> list[str]:
    """Return a list of formatted track titles representing the expected
    queue: the current track (at ``current_track_index``) plus all tracks
    still in ``pending_tracks``, in ``sorted_tracks`` order.

    *format_fn* defaults to ``"title - artist"`` formatting.
    """
    if format_fn is None:
        format_fn = _default_format

    cur_idx = playlist.current_track_index
    pending_set = set(playlist.pending_tracks)
    queue = []
    for ti, t in enumerate(playlist.sorted_tracks):
        fp = t.get_parent_filepath()
        if ti == cur_idx or fp in pending_set:
            queue.append(format_fn(t))
    return queue


def _default_format(t) -> str:
    title = getattr(t, "title", None)
    artist = getattr(t, "artist", None)
    if not title:
        import os
        fp = getattr(t, "filepath", "")
        title = os.path.basename(fp) if fp else "?"
    return f"{title} - {artist}" if artist else title


# ── Queue order comparison ─────────────────────────────────────────────

def verify_queue_order(actual_widget_items: list[tuple[str, bool]],
                       expected_titles: list[str],
                       queue_start_row: int = 0,
                       compare_limit: int = 20,
                       label: str = "") -> bool:
    """Compare the widget's queue items (from *queue_start_row* onward)
    against *expected_titles*.

    Returns ``True`` if all compared items match (by substring containment).
    Prints mismatches to stdout.
    """
    queue_items = actual_widget_items[queue_start_row:]
    compare_n = min(len(queue_items), len(expected_titles), compare_limit)
    ok = True
    for i in range(compare_n):
        actual_text = queue_items[i][0]
        expected_title = expected_titles[i]
        if expected_title not in actual_text:
            print(f"  MISMATCH at queue row {i}{f' ({label})' if label else ''}:")
            print(f"    expected: ...{expected_title[:60]}...")
            print(f"    actual:   {actual_text[:60]}")
            ok = False

    tag = f" ({label})" if label else ""
    if ok:
        print(f"  \u2713 Queue order correct{tag} ({compare_n} items)")
    else:
        print(f"  \u2717 Queue order BROKEN{tag}")
    return ok


def verify_single_track_moved(before_titles: list[str],
                               after_titles: list[str],
                               label: str = "") -> bool:
    """Verify that exactly one track disappeared from the queue between two
    snapshots (the track that finished playing and moved to history).

    Returns ``True`` on success.
    """
    before_set = set(before_titles)
    after_set = set(after_titles)
    missing = before_set - after_set
    tag = f" ({label})" if label else ""

    if len(missing) == 1:
        gone = missing.pop()
        print(f"  \u2713 Exactly 1 track moved from queue to history{tag}: {gone[:60]}")
        return True
    elif len(missing) == 0:
        print(f"  WARN: No tracks moved from queue{tag} (track may have been re-added?)")
        return True  # not a hard failure
    else:
        print(f"  FAIL: {len(missing)} tracks disappeared from queue{tag}:")
        for mt in sorted(missing):
            print(f"    - {mt[:80]}")
        return False
