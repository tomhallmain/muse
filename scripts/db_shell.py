"""
Interactive shell for inspecting muse_library.db.
Run from the workspace root: python scripts/db_shell.py

The following are pre-bound in the REPL:
  conn            -- sqlite3.Connection (row_factory=sqlite3.Row)
  DB_PATH         -- pathlib.Path to the database file
  list_to_delim   -- join a list into a "; "-delimited string
  delim_to_list   -- split a "; "-delimited string into a list

Example queries:
  conn.execute("SELECT COUNT(*) FROM composers").fetchone()[0]
  conn.execute("SELECT name, genres FROM composers LIMIT 5").fetchall()
  [dict(r) for r in conn.execute("SELECT * FROM mb_recordings LIMIT 3")]
"""

import code
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_connection, DB_PATH, list_to_delim, delim_to_list

conn = get_connection()

banner = f"""
muse_library.db shell  ({DB_PATH})
─────────────────────────────────────────────────────────────────
  conn          sqlite3.Connection
  DB_PATH       {DB_PATH}
  list_to_delim / delim_to_list

Tables: {", ".join(
    r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
)}

Type Ctrl-D (or exit()) to quit.
─────────────────────────────────────────────────────────────────
"""

code.interact(banner=banner, local={
    "conn": conn,
    "DB_PATH": DB_PATH,
    "list_to_delim": list_to_delim,
    "delim_to_list": delim_to_list,
})
