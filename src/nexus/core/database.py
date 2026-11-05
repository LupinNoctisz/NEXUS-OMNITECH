"""Banco de dados local SQLite com migrações versionadas."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from .errors import BackupError, SchemaVersionError
from .util import sha256_file

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE technicians (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            role       TEXT NOT NULL CHECK (role IN ('viewer','technician','admin')),
            active     INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE devices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            uid        TEXT NOT NULL UNIQUE,
            kind       TEXT NOT NULL,
            source     TEXT NOT NULL,
            vendor     TEXT,
            model      TEXT,
            serial     TEXT,
            label      TEXT,
            connection TEXT NOT NULL DEFAULT 'unknown',
            first_seen TEXT NOT NULL,
            last_seen  TEXT NOT NULL,
            properties TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id  INTEGER NOT NULL REFERENCES devices(id),
            kind       TEXT NOT NULL,
            technician TEXT NOT NULL,
            status     TEXT NOT NULL CHECK (status IN ('open','completed','aborted')),
            started_at TEXT NOT NULL,
            ended_at   TEXT,
            summary    TEXT
        );
        CREATE TABLE modules (
            id                     TEXT PRIMARY KEY,
            version                TEXT NOT NULL,
            enabled                INTEGER NOT NULL DEFAULT 0,
            pinned_manifest_sha256 TEXT NOT NULL,
            registered_at          TEXT NOT NULL,
            registered_by          TEXT NOT NULL
        );
        CREATE TABLE operations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            technician TEXT NOT NULL,
            action     TEXT NOT NULL,
            target     TEXT,
            session_id INTEGER,
            details    TEXT NOT NULL DEFAULT '{}',
            outcome    TEXT NOT NULL,
            prev_hash  TEXT NOT NULL,
            hash       TEXT NOT NULL
        );
        CREATE INDEX idx_sessions_device ON sessions(device_id);
        CREATE INDEX idx_operations_session ON operations(session_id);
        """,
    ),
    (
        2,
        """
        ALTER TABLE technicians ADD COLUMN password_hash TEXT;
        ALTER TABLE technicians ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE technicians ADD COLUMN locked_until TEXT;
        """,
    ),
    (
        3,
        """
        CREATE INDEX idx_sessions_open ON sessions(id) WHERE status = 'open';
        CREATE INDEX idx_devices_connection ON devices(connection, last_seen);
        CREATE INDEX idx_devices_last_seen ON devices(last_seen);
        """,
    ),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


class Database:
    """Conexão SQLite única, protegida por lock, com transações aninháveis."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._depth = 0
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    # -- migrações ---------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"Este banco de dados é da versão {current} do esquema, mais nova que a suportada por este NEXUS "
                    f"({SCHEMA_VERSION}). Atualize o NEXUS; o banco não foi alterado.")
            if 0 < current < SCHEMA_VERSION and self.path != ":memory:":
                self._backup_before_migration(current)
            for version, sql in MIGRATIONS:
                if version <= current:
                    continue
                try:
                    self._conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
                except Exception:
                    if self._conn.in_transaction:
                        self._conn.execute("ROLLBACK")
                    raise

    def _backup_before_migration(self, current: int) -> None:
        """Cópia de segurança (verificada) do banco existente ANTES de migrá-lo para um esquema novo."""
        folder = Path(self.path).parent / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = folder / f"nexus-{stamp}-pre-migration-v{current}.db"
        counter = 1
        while target.exists():
            target = folder / f"nexus-{stamp}-pre-migration-v{current}-{counter}.db"
            counter += 1
        try:
            copy = sqlite3.connect(str(target))
            try:
                self._conn.backup(copy)
            finally:
                copy.close()
            check = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
            try:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("a cópia não passou na verificação de integridade")
            finally:
                check.close()
            digest = sha256_file(target)
            Path(str(target) + ".sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise BackupError(
                f"Não foi possível fazer o backup de segurança antes de atualizar o banco; nada foi alterado. ({exc})") from exc

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    # -- acesso ------------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            outermost = self._depth == 0
            if outermost:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self._conn
            except BaseException:
                self._depth -= 1
                if outermost:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outermost:
                    self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def backup_to(self, dest: Path) -> None:
        """Cópia consistente (API de backup do SQLite), segura com o banco em uso."""
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._conn.backup(target)
            finally:
                target.close()

    def restore_from(self, source_path: Path) -> None:
        """Substitui o conteúdo do banco em uso pelo de um backup (já validado)."""
        with self._lock:
            if self._depth:
                raise RuntimeError("restore_from não pode ocorrer dentro de uma transação")
            source = sqlite3.connect(str(source_path))
            try:
                source.backup(self._conn)
            finally:
                source.close()
            self._migrate()

    def integrity_check(self) -> bool:
        row = self.query_one("PRAGMA integrity_check")
        return bool(row) and row[0] == "ok"

    def close(self) -> None:
        with self._lock:
            self._conn.close()
