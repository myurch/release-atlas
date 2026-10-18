"""Saved workspaces with a shared active selection and global revision checks."""
from __future__ import annotations

from contextlib import contextmanager
import re
import secrets
import sqlite3
from pathlib import Path

from .models import MAX_REVISION, Audit, Workspace, now


class Conflict(Exception):
    pass


def database_authorizer(bootstrap=False):
    """Runtime SQL capabilities, independent of HTTP/model input validation."""
    def authorize(operation, table, column, database, origin):
        # Atlas never uses triggers, views, attached databases or schema-supplied code.
        if origin is not None or database not in (None, 'main'):
            return sqlite3.SQLITE_DENY
        if bootstrap:
            return sqlite3.SQLITE_OK  # Only fixed startup migrations use this connection.
        if operation in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_TRANSACTION):
            return sqlite3.SQLITE_OK
        if operation == sqlite3.SQLITE_FUNCTION and column in {'json_extract','json_array_length','count'}:
            return sqlite3.SQLITE_OK
        if operation in (sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE) and table in {'workspace','saved_workspaces'}:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return authorize


class Store:
    LIMIT = 30

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection(_bootstrap=True) as db:
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

    @contextmanager
    def connection(self, *, _bootstrap=False):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
            db.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
            db.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
            db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 10_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 16)
            db.set_authorizer(database_authorizer(_bootstrap))
            with db:
                yield db
        finally:
            db.close()

    def read(self) -> Workspace:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM workspace WHERE id=1').fetchone()
        return Workspace.model_validate_json(row[0])

    def snapshot(self):
        with self.connection() as db:
            db.execute('BEGIN')
            payload, active = db.execute('SELECT payload,active_id FROM workspace WHERE id=1').fetchone()
            rows = db.execute("SELECT id,json_extract(payload,'$.title'),json_array_length(payload,'$.sources'),json_array_length(payload,'$.claims'),updated_at FROM saved_workspaces ORDER BY updated_at DESC,id").fetchall()
        catalog = []
        for identifier, title, sources, claims, updated in rows:
            catalog.append({'id':identifier,'title':title,'sources':sources,'claims':claims,'updated_at':updated})
        return {'workspace':Workspace.model_validate_json(payload).model_dump(),'active_id':active,'workspaces':catalog}

    @staticmethod
    def checked(db, expected):
        if type(expected) is not int or not 0 <= expected < MAX_REVISION:
            raise ValueError('Invalid workspace revision')
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
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('Invalid workspace identifier')
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
