"""Encrypted PostgreSQL backups and isolated restore verification."""

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from django.conf import settings
from psycopg import sql

MAGIC = b"CSBK1\n"
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
RESTORE_NAME = re.compile(r"^cryptosniper_restore_[a-z0-9_]{1,40}$")


def _database():
    database = settings.DATABASES["default"]
    return {
        "name": database["NAME"],
        "user": database["USER"],
        "password": database["PASSWORD"],
        "host": database.get("HOST") or "127.0.0.1",
        "port": str(database.get("PORT") or "5432"),
    }


def _key(passphrase, salt):
    if len(passphrase) < 16:
        raise ValueError("Backup passphrase must contain at least 16 characters.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def encrypt_file(source, destination, passphrase):
    source, destination = Path(source), Path(destination)
    salt, nonce = os.urandom(16), os.urandom(12)
    header = json.dumps(
        {
            "created_at": datetime.now(UTC).isoformat(),
            "release": settings.RELEASE_VERSION,
            "source_revision": settings.SOURCE_REVISION,
            "salt": salt.hex(),
            "nonce": nonce.hex(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    plain_hash = hashlib.sha256()
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        outgoing.write(prefix)
        while chunk := incoming.read(CHUNK_SIZE):
            plain_hash.update(chunk)
            outgoing.write(encryptor.update(chunk))
        outgoing.write(encryptor.finalize())
        outgoing.write(encryptor.tag)
    destination.chmod(0o600)
    return plain_hash.hexdigest()


def decrypt_file(source, destination, passphrase):
    source, destination = Path(source), Path(destination)
    size = source.stat().st_size
    with source.open("rb") as incoming:
        if incoming.read(len(MAGIC)) != MAGIC:
            raise ValueError("Unsupported backup format.")
        header_length = struct.unpack(">I", incoming.read(4))[0]
        if not 2 <= header_length <= 4096:
            raise ValueError("Invalid backup header.")
        header_bytes = incoming.read(header_length)
        header = json.loads(header_bytes)
        ciphertext_start = len(MAGIC) + 4 + header_length
        ciphertext_length = size - ciphertext_start - TAG_SIZE
        if ciphertext_length < 1:
            raise ValueError("Encrypted backup is empty.")
        incoming.seek(size - TAG_SIZE)
        tag = incoming.read(TAG_SIZE)
        incoming.seek(ciphertext_start)
        prefix = MAGIC + struct.pack(">I", header_length) + header_bytes
        decryptor = Cipher(
            algorithms.AES(_key(passphrase, bytes.fromhex(header["salt"]))),
            modes.GCM(bytes.fromhex(header["nonce"]), tag),
        ).decryptor()
        decryptor.authenticate_additional_data(prefix)
        remaining = ciphertext_length
        try:
            with destination.open("xb") as outgoing:
                while remaining:
                    chunk = incoming.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ValueError("Truncated encrypted backup.")
                    remaining -= len(chunk)
                    outgoing.write(decryptor.update(chunk))
                outgoing.write(decryptor.finalize())
        except (InvalidTag, ValueError):
            destination.unlink(missing_ok=True)
            raise ValueError("Backup authentication failed.") from None
    destination.chmod(0o600)
    return header


def prune_backups(directory, *, keep_daily=14, keep_weekly=8):
    directory = Path(directory)
    removed = []
    for label, keep in (("daily", keep_daily), ("weekly", keep_weekly)):
        candidates = sorted(
            (
                path
                for path in directory.glob(f"cryptosniper-{label}-*.csbk")
                if path.is_file() and not path.is_symlink()
            ),
            reverse=True,
        )
        for path in candidates[keep:]:
            path.unlink()
            path.with_suffix(path.suffix + ".json").unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def create_backup(passphrase, *, weekly=False, runner=subprocess.run):
    output = Path(settings.HOSTING_BACKUP_DIR)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = "weekly" if weekly else "daily"
    final = output / f"cryptosniper-{label}-{timestamp}.csbk"
    database = _database()
    env = {**os.environ, "PGPASSWORD": str(database["password"])}
    with tempfile.TemporaryDirectory(prefix=".backup-", dir=output) as work:
        dump = Path(work) / "database.dump"
        runner(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--host",
                database["host"],
                "--port",
                database["port"],
                "--username",
                database["user"],
                "--file",
                str(dump),
                database["name"],
            ],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        plain_sha = encrypt_file(dump, final, passphrase)
    archive_sha = hashlib.file_digest(final.open("rb"), "sha256").hexdigest()
    manifest = {
        "archive": final.name,
        "archive_sha256": archive_sha,
        "plaintext_sha256": plain_sha,
        "encrypted": "AES-256-GCM+scrypt",
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
    }
    manifest_path = final.with_suffix(final.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    offsite = None
    if settings.HOSTING_BACKUP_OFFSITE_DIR:
        offsite_dir = Path(settings.HOSTING_BACKUP_OFFSITE_DIR)
        offsite_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for source in (final, manifest_path):
            temporary = offsite_dir / (source.name + ".part")
            shutil.copyfile(source, temporary)
            temporary.chmod(0o600)
            os.replace(temporary, offsite_dir / source.name)
        offsite = str(offsite_dir / final.name)
    prune_backups(output)
    return {**manifest, "path": str(final), "offsite_path": offsite}


def verify_restore(
    archive, passphrase, target_database, *, keep_database=False, runner=subprocess.run
):
    if not RESTORE_NAME.fullmatch(target_database):
        raise ValueError("Restore target must be a dedicated cryptosniper_restore_* database.")
    database = _database()
    if target_database == database["name"]:
        raise ValueError("Restore verification cannot target the production database.")
    connection_info = {
        "host": database["host"],
        "port": database["port"],
        "user": database["user"],
        "password": database["password"],
        "dbname": "postgres",
    }
    env = {**os.environ, "PGPASSWORD": str(database["password"])}
    with tempfile.TemporaryDirectory(prefix="cryptosniper-restore-") as work:
        dump = Path(work) / "database.dump"
        header = decrypt_file(archive, dump, passphrase)
        with psycopg.connect(**connection_info, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(target_database)
                )
            )
            admin.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(target_database)
                )
            )
        try:
            runner(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--host",
                    database["host"],
                    "--port",
                    database["port"],
                    "--username",
                    database["user"],
                    "--dbname",
                    target_database,
                    str(dump),
                ],
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            with psycopg.connect(**{**connection_info, "dbname": target_database}) as restored:
                migrations = restored.execute("SELECT count(*) FROM django_migrations").fetchone()[
                    0
                ]
                audit = restored.execute("SELECT count(*) FROM accounts_auditlog").fetchone()[0]
            return {"status": "verified", "migrations": migrations, "audit_rows": audit, **header}
        finally:
            if not keep_database:
                with psycopg.connect(**connection_info, autocommit=True) as admin:
                    admin.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(target_database)
                        )
                    )
