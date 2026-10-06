"""Single-workspace persistence with atomic optimistic concurrency."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Audit, Workspace, now


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO workspace VALUES (1,0,?)', (Workspace().model_dump_json(),))
            db.execute('PRAGMA user_version=1')

    def connection(self):
        return sqlite3.connect(self.path, timeout=5)

    def read(self) -> Workspace:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM workspace WHERE id=1').fetchone()
        return Workspace.model_validate_json(row[0])

    def save(self, state: Workspace, expected: int, actor: str, action: str) -> Workspace:
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision,payload FROM workspace WHERE id=1').fetchone()
            if current[0] != expected:
                raise Conflict('Another reviewer changed this workspace. Reload and retry your change.')
            state = state.model_copy(deep=True)
            state.revision = expected+1
            # Imports cannot rewrite the server's authenticated audit history.
            old = Workspace.model_validate_json(current[1])
            state.audit = (old.audit+[Audit(at=now(), by=actor, action=action, revision=state.revision)])[-200:]
            state = Workspace.model_validate(state.model_dump())
            db.execute('UPDATE workspace SET revision=?,payload=? WHERE id=1', (state.revision,state.model_dump_json()))
        return state
