"""Saved workspaces with a shared active selection and global revision checks."""
from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from .models import Audit, Workspace, now


class Conflict(Exception):
    pass


class Store:
    LIMIT = 30

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO workspace (id,revision,payload) VALUES (1,0,?)', (Workspace().model_dump_json(),))
            db.execute('CREATE TABLE IF NOT EXISTS saved_workspaces (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)')
            if 'active_id' not in {row[1] for row in db.execute('PRAGMA table_info(workspace)')}:
                db.execute('ALTER TABLE workspace ADD COLUMN active_id TEXT')
            row = db.execute('SELECT payload,active_id FROM workspace WHERE id=1').fetchone()
            if row[1] is None:
                identifier = secrets.token_hex(16)
                # Migration preserves the original payload, including reviews and audit.
                db.execute('INSERT INTO saved_workspaces VALUES (?,?,?)', (identifier,row[0],now()))
                db.execute('UPDATE workspace SET active_id=? WHERE id=1', (identifier,))
            db.execute('PRAGMA user_version=2')

    def connection(self):
        return sqlite3.connect(self.path, timeout=5)

    def read(self) -> Workspace:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM workspace WHERE id=1').fetchone()
        return Workspace.model_validate_json(row[0])

    def snapshot(self):
        with self.connection() as db:
            db.execute('BEGIN')
            payload, active = db.execute('SELECT payload,active_id FROM workspace WHERE id=1').fetchone()
            rows = db.execute('SELECT id,payload,updated_at FROM saved_workspaces ORDER BY updated_at DESC,id').fetchall()
        catalog = []
        for identifier, text, updated in rows:
            state = Workspace.model_validate_json(text)
            catalog.append({'id':identifier,'title':state.title,'sources':len(state.sources),'claims':len(state.claims),'updated_at':updated})
        return {'workspace':Workspace.model_validate_json(payload).model_dump(),'active_id':active,'workspaces':catalog}

    @staticmethod
    def checked(db, expected):
        row = db.execute('SELECT revision,payload,active_id FROM workspace WHERE id=1').fetchone()
        if row[0] != expected:
            raise Conflict('The shared workspace changed. Reload and retry; your input has been kept.')
        return row

    @staticmethod
    def write(db, state, expected, identifier, actor, action, history):
        state = state.model_copy(deep=True)
        state.revision = expected+1
        state.audit = (history+[Audit(at=now(), by=actor, action=action, revision=state.revision)])[-200:]
        state = Workspace.model_validate(state.model_dump())
        payload = state.model_dump_json()
        db.execute('INSERT INTO saved_workspaces VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at', (identifier,payload,now()))
        db.execute('UPDATE workspace SET revision=?,payload=?,active_id=? WHERE id=1', (state.revision,payload,identifier))
        return state

    def save(self, state: Workspace, expected: int, actor: str, action: str) -> Workspace:
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            _, payload, identifier = self.checked(db,expected)
            # Imports cannot rewrite authenticated audit history.
            return self.write(db,state,expected,identifier,actor,action,Workspace.model_validate_json(payload).audit)

    def create(self, state: Workspace, expected: int, actor: str, imported=False):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.checked(db,expected)
            if db.execute('SELECT COUNT(*) FROM saved_workspaces').fetchone()[0] >= self.LIMIT:
                raise ValueError('Workspace limit reached (30). Export a snapshot before using another Release Atlas data directory.')
            action = 'Imported saved analysis into a new workspace; embedded review names are unverified provenance' if imported else 'Created empty workspace'
            return self.write(db,state,expected,secrets.token_hex(16),actor,action,[])

    def switch(self, identifier: str, expected: int, actor: str):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            _, payload, active = self.checked(db,expected)
            if active == identifier:
                return Workspace.model_validate_json(payload)
            row = db.execute('SELECT payload FROM saved_workspaces WHERE id=?',(identifier,)).fetchone()
            if row is None:
                raise LookupError('Saved workspace not found')
            target = Workspace.model_validate_json(row[0])
            # Global revisions never rewind when an old workspace is selected.
            return self.write(db,target,expected,identifier,actor,'Switched to this saved workspace',target.audit)
