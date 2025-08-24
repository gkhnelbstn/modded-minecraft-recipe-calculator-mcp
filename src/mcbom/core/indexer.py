"""Item indexer for fast /items search.

Builds a per-instance SQLite index of all item ids discovered from recipes
and tags. Provides query helpers that prefer FTS5 when available and
fallback to LIKE search otherwise.

All code is in English per project rules. Docstrings include Args/Returns.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from contextlib import closing
from typing import Iterable, List, Tuple

from mcbom.core.parser import load_recipes, load_tags


def _safe_hash(text: str) -> str:
    """Return a short stable sha1 hash of the input string."""
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:12]


def _out_dir() -> str:
    """Ensure and return the output directory path.

    Priority:
    1) MCBOM_INDEX_DIR if set
    2) /app/out if it exists (persisted via docker bind mount)
    3) /tmp/mcbom-index inside container (reliable writable path)
    4) ./.index next to the current working directory
    """
    base = os.environ.get("MCBOM_INDEX_DIR")
    if not base:
        if os.path.isdir("/app/out"):
            base = "/app/out"
        elif os.path.isdir("/"):
            base = "/tmp/mcbom-index"
        else:
            base = os.path.join(os.getcwd(), ".index")
    os.makedirs(base, exist_ok=True)
    return base


def get_index_path(base_path: str) -> str:
    """Compute the SQLite index file path for a given instance base path.

    Args:
        base_path: Absolute or container-relative instance path.
    Returns:
        Path to the index file.
    """
    base_abs = os.path.abspath(base_path)
    h = _safe_hash(base_abs)
    return os.path.join(_out_dir(), f"items_index_{h}.sqlite")


def humanize(item_id: str) -> str:
    """Convert a fully-qualified item id into a human-readable name.

    Args:
        item_id: e.g., "minecraft:oak_log".
    Returns:
        Human-friendly title-cased name.
    """
    if ":" in item_id:
        name = item_id.split(":", 1)[1]
    else:
        name = item_id
    return name.replace("_", " ").title()


def collect_items(base_path: str) -> List[Tuple[str, str, str]]:
    """Collect unique item ids from recipes outputs and tag values.

    Args:
        base_path: Instance path to scan (datapacks and mod JARs).
    Returns:
        List of tuples (id, name, ns) without duplicates.
    """
    recipes = load_recipes(base_path)
    tags = load_tags(base_path)

    items_set = set(recipes.keys())
    for vals in tags.values():
        for v in vals:
            if isinstance(v, str) and not v.startswith("#"):
                items_set.add(v)

    out: List[Tuple[str, str, str]] = []
    for iid in items_set:
        ns = iid.split(":", 1)[0] if ":" in iid else "minecraft"
        out.append((iid, humanize(iid), ns))
    return out


def _create_schema(con: sqlite3.Connection) -> bool:
    """Create tables and indexes. Try to create FTS5; return whether FTS is available."""
    cur = con.cursor()
    # Pragmas for speed; avoid WAL on some host mounts (can cause disk I/O error)
    cur.execute("PRAGMA journal_mode=DELETE;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ns TEXT NOT NULL,
            search_text TEXT NOT NULL
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_ns ON items(ns);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_search ON items(search_text);")

    fts_ok = True
    try:
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
            USING fts5(name, id, tokenize='porter');
            """
        )
    except sqlite3.OperationalError:
        # FTS not compiled in this SQLite build
        fts_ok = False
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    con.commit()
    return fts_ok


def build_index(base_path: str, refresh: bool = False) -> str:
    """Build or refresh the SQLite index for the given instance path.

    Args:
        base_path: Instance path that contains datapacks/mod JARs.
        refresh: If True, always rebuild the index.
    Returns:
        Path to the SQLite index file.
    """
    db_path = get_index_path(base_path)
    need_rebuild = refresh or not os.path.exists(db_path)

    with closing(sqlite3.connect(db_path)) as con:
        fts_ok = _create_schema(con)
        if not need_rebuild:
            # Heuristic: if item count exists, skip rebuild
            cnt = con.execute("SELECT COUNT(1) FROM items").fetchone()[0]
            if cnt > 0:
                return db_path
            # else fallthrough to rebuild
        # Rebuild
        con.execute("DELETE FROM items;")
        if fts_ok:
            con.execute("DELETE FROM items_fts;")
        items = collect_items(base_path)
        with con:
            con.executemany(
                "INSERT OR REPLACE INTO items(id, name, ns, search_text) VALUES (?, ?, ?, ?)",
                ((iid, name, ns, f"{iid.lower()} {name.lower()}") for iid, name, ns in items),
            )
            if fts_ok:
                con.executemany(
                    "INSERT INTO items_fts(name, id) VALUES (?, ?)",
                    ((name, iid) for iid, name, _ in items),
                )
            # Meta
            con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("built_at", str(int(time.time()))),
            )
            con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("source_path", os.path.abspath(base_path)),
            )
    return db_path


def ensure_index(base_path: str, refresh: bool = False) -> str:
    """Ensure index exists; build if necessary.

    Args:
        base_path: Instance path.
        refresh: Force rebuild if True.
    Returns:
        DB path.
    """
    return build_index(base_path, refresh=refresh)


def query_items(base_path: str, q: str | None, limit: int = 50, refresh: bool = False) -> List[dict]:
    """Query items from the index with optional search string.

    Args:
        base_path: Instance path.
        q: Optional query text. If empty/None, returns top items sorted by name.
        limit: Max rows to return.
        refresh: Whether to force rebuild before query.
    Returns:
        List of dicts with keys: id, name.
    """
    db_path = ensure_index(base_path, refresh=refresh)
    with closing(sqlite3.connect(db_path)) as con:
        con.row_factory = sqlite3.Row
        # Check if FTS exists
        fts_exists = (
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='items_fts'"
            ).fetchone()
            is not None
        )
        if not q:
            rows = con.execute(
                "SELECT id, name FROM items ORDER BY name LIMIT ?", (limit,)
            ).fetchall()
            return [{"id": r["id"], "name": r["name"]} for r in rows]
        q = q.strip()
        if fts_exists:
            # Prefix match across tokens via FTS; combine terms with AND
            terms = [t for t in q.split() if t]
            fts_q = " AND ".join(f"{t}*" for t in terms) if terms else q
            sql = (
                "SELECT i.id, i.name FROM items i "
                "JOIN items_fts ON items_fts.id = i.id "
                "WHERE items_fts MATCH ? ORDER BY i.name LIMIT ?"
            )
            rows = con.execute(sql, (fts_q, limit)).fetchall()
            return [{"id": r["id"], "name": r["name"]} for r in rows]
        # Fallback: substring search on precomputed search_text
        patt = f"%{q.lower()}%"
        rows = con.execute(
            "SELECT id, name FROM items WHERE search_text LIKE ? ORDER BY name LIMIT ?",
            (patt, limit),
        ).fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]
