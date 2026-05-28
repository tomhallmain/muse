"""
Verify the muse_library.db initializes, seeds, and migrates correctly.
Run from the workspace root: python scripts/verify_db.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_connection, list_to_delim, delim_to_list

print("Opening DB connection (this seeds on first run)...")
conn = get_connection()
print("DB connection OK")
print()

# Meta flags
print("── db_meta ──────────────────────────────")
for key in ("seeded", "gzip_mb_migrated", "gzip_lfm_migrated"):
    row = conn.execute("SELECT value FROM db_meta WHERE key=?", (key,)).fetchone()
    print(f"  {key}: {row[0] if row else 'NOT SET'}")
print()

# Row counts
print("── Table row counts ─────────────────────")
tables = (
    "composers",
    "artists",
    "forms",
    "genres",
    "instruments",
    "blacklist",
    "blacklist_music",
    "directories",
    "media_tracks",
    "lfm_scopes",
    "lfm_tracks",
    "mb_recordings",
)
for table in tables:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {n}")
print()

# Spot-check blacklist
print("── Sample blacklist patterns ────────────")
rows = conn.execute("SELECT pattern FROM blacklist LIMIT 5").fetchall()
if rows:
    for r in rows:
        print(f"  {r['pattern']}")
else:
    print("  (empty — blacklist seeding may not yet be implemented)")
print()

# Spot-check forms
print("── Sample forms ─────────────────────────")
rows = conn.execute("SELECT name, transliterations FROM forms LIMIT 5").fetchall()
for r in rows:
    print(f"  {r['name']!r:30s}  transliterations: {r['transliterations'][:60]}")
print()

# Spot-check genres
print("── Sample genres ────────────────────────")
rows = conn.execute("SELECT name, transliterations FROM genres LIMIT 5").fetchall()
for r in rows:
    print(f"  {r['name']!r:30s}  transliterations: {r['transliterations'][:60]}")
print()

# Spot-check instruments
print("── Sample instruments ───────────────────")
rows = conn.execute("SELECT name FROM instruments LIMIT 5").fetchall()
for r in rows:
    print(f"  {r['name']}")
print()

# Spot-check composers
print("── Sample composers ─────────────────────")
rows = conn.execute(
    "SELECT name, start_date, end_date, indicators FROM composers LIMIT 5"
).fetchall()
for r in rows:
    inds = delim_to_list(r["indicators"])
    print(f"  {r['name']!r:40s}  {r['start_date']}–{r['end_date']}  indicators: {inds[:2]}")
print()

# Spot-check artists
print("── Sample artists ───────────────────────")
rows = conn.execute("SELECT id, name, genres FROM artists LIMIT 5").fetchall()
for r in rows:
    print(f"  id={r['id']}  {r['name']!r:35s}  genres: {r['genres'][:50]}")
print()

# Spot-check directories cache
print("── Sample directories ───────────────────")
rows = conn.execute("SELECT path, scanned_at FROM directories LIMIT 5").fetchall()
if rows:
    for r in rows:
        print(f"  {r['path'][:70]}  scanned_at={r['scanned_at']:.0f}")
else:
    print("  (empty — populated when store_caches() runs)")
print()

# Spot-check media_tracks cache
print("── Sample media_tracks ──────────────────")
rows = conn.execute(
    "SELECT filepath, title, artist, album FROM media_tracks LIMIT 5"
).fetchall()
if rows:
    for r in rows:
        print(f"  {r['title']!r:35s}  {r['artist']!r:25s}  {r['album']!r}")
else:
    print("  (empty — populated when store_caches() runs)")
print()

# Verify reference data modules load from DB
print("── Module load checks ───────────────────")
try:
    from library_data.form import forms_data
    print(f"  forms_data: {len(forms_data.get_form_names())} forms loaded")
except Exception as e:
    print(f"  forms_data ERROR: {e}")

try:
    from library_data.genre import genre_data
    print(f"  genre_data: {len(genre_data.get_genre_names())} genres loaded")
except Exception as e:
    print(f"  genre_data ERROR: {e}")

try:
    from library_data.instrument import instruments_data
    print(f"  instruments_data: {len(instruments_data.get_instrument_names())} instruments loaded")
except Exception as e:
    print(f"  instruments_data ERROR: {e}")

try:
    from library_data.artist import artists_data
    print(f"  artists_data: {len(artists_data.get_artist_names())} artists loaded")
except Exception as e:
    print(f"  artists_data ERROR: {e}")

print()

# Verify cache classes
print("── Cache class checks ───────────────────")
try:
    from extensions.musicbrainz_api import get_mb_cache
    mb = get_mb_cache()
    print(f"  MusicBrainzCache.size: {mb.size}")
    # Round-trip a record
    test_mbid = "__verify_test__"
    mb.set(test_mbid, {
        "mb_title": "Test Title",
        "mb_artist": "Test Artist",
        "mb_genres": ["Classical", "Baroque"],
        "composer": ["J.S. Bach"],
        "lyricist": [],
        "arranger": [],
        "orchestrator": [],
        "writer": [],
    })
    mb.save()
    rec = mb.get(test_mbid)
    assert rec is not None, "get() returned None"
    assert rec["mb_title"] == "Test Title"
    assert rec["mb_genres"] == ["Classical", "Baroque"]
    assert rec["composer"] == ["J.S. Bach"]
    assert test_mbid in mb
    # Clean up
    conn.execute("DELETE FROM mb_recordings WHERE mbid=?", (test_mbid,))
    conn.commit()
    print("  MusicBrainzCache round-trip: OK")
except Exception as e:
    print(f"  MusicBrainzCache ERROR: {e}")

try:
    from extensions.lastfm_api import get_lastfm_cache
    lfm = get_lastfm_cache()
    # Round-trip a scope
    test_user = "__verify_test_user__"
    tracks = [
        {"name": "Song A", "artist": "Artist X", "playcount": 10, "album": "Album 1", "mbid": "abc", "rank": 1},
        {"name": "Song B", "artist": "Artist Y", "playcount": 5,  "album": None,      "mbid": "",    "rank": 2},
    ]
    lfm.set_scope(test_user, "tracks", tracks)
    result = lfm.get_scope(test_user, "tracks")
    assert result is not None, "get_scope returned None"
    assert len(result) == 2
    assert result[0]["name"] == "Song A"
    assert result[0]["artist"] == "Artist X"
    fa = lfm.fetched_at(test_user, "tracks")
    assert fa is not None and fa > 0
    # None for unfetched scope
    assert lfm.get_scope(test_user, "albums") is None
    # Clean up
    conn.execute("DELETE FROM lfm_scopes WHERE username=?", (test_user,))
    conn.execute("DELETE FROM lfm_tracks WHERE username=?", (test_user,))
    conn.commit()
    print("  LastFmLibraryCache round-trip: OK")
except Exception as e:
    print(f"  LastFmLibraryCache ERROR: {e}")

print()
print("Verification complete.")
