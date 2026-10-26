"""Adopt only verified, pre-existing React schema left by earlier preview installs."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

TARGETS = (
    ("accounts", "0007_walletconnection", "WalletConnection"),
    ("marketdata", "0003_favoriteasset", "FavoriteAsset"),
    ("exchanges", "0008_react_connection_diagnostics", "UserExchangeAccount"),
)
DIAGNOSTICS = ("last_error_at", "last_error_code", "last_error_message")


def columns(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull "
            "FROM pg_attribute a WHERE a.attrelid=to_regclass(%s) "
            "AND a.attnum>0 AND NOT a.attisdropped",
            [table],
        )
        return {
            name: (kind.replace("character varying", "varchar"), required)
            for name, kind, required in cursor.fetchall()
        }


def validate_fields(model, actual, fields):
    for field in fields:
        expected = (field.db_type(connection), not field.null)
        if actual.get(field.column) != expected:
            raise CommandError(f"Schema mismatch: {model._meta.db_table}.{field.column}; stopped.")


def validate_model(model, actual):
    table = model._meta.db_table
    fields = model._meta.local_fields
    if set(actual) != {field.column for field in fields}:
        raise CommandError(f"Unexpected columns in {table}; stopped without adopting migration.")
    validate_fields(model, actual, fields)
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
        cursor.execute("SELECT pg_get_serial_sequence(%s,%s)", [table, model._meta.pk.column])
        if cursor.fetchone()[0] is None:
            raise CommandError(f"Missing generated primary key in {table}.")
    values = list(constraints.values())
    if not any(c["primary_key"] and c["columns"] == [model._meta.pk.column] for c in values):
        raise CommandError(f"Primary key mismatch in {table}.")
    for field in fields:
        if field.remote_field and field.db_constraint:
            target = (field.target_field.model._meta.db_table, field.target_field.column)
            if not any(
                c.get("foreign_key") == target and c["columns"] == [field.column] for c in values
            ):
                raise CommandError(f"Foreign key mismatch in {table}.{field.column}.")
        if field.get_internal_type().startswith("Positive") and not any(
            c.get("check") and c["columns"] == [field.column] for c in values
        ):
            raise CommandError(f"Missing positive-value check in {table}.{field.column}.")
    for constraint in model._meta.constraints:
        expected = [model._meta.get_field(name).column for name in constraint.fields]
        if not any(c.get("unique") and c["columns"] == expected for c in values):
            raise CommandError(f"Unique constraint mismatch in {table}; stopped.")
        if constraint.name in constraints and constraints[constraint.name]["columns"] != expected:
            raise CommandError(f"Conflicting constraint name in {table}.")
    for index in model._meta.indexes:
        expected = [model._meta.get_field(name).column for name in index.fields]
        if index.name in constraints and constraints[index.name]["columns"] != expected:
            raise CommandError(f"Conflicting index name in {table}.")
    return constraints


class Command(BaseCommand):
    help = (
        "Verify legacy React tables/columns; --apply adopts matching schema without deleting data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL is required for schema reconciliation.")
        apply = options["apply"]
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [290029])
            executor = MigrationExecutor(connection)
            recorder = MigrationRecorder(connection)
            applied = set(recorder.applied_migrations())
            tables = set(connection.introspection.table_names())
            for app, name, model_name in TARGETS:
                key = (app, name)
                if key in applied:
                    continue
                state = executor.loader.project_state([key])
                model = state.apps.get_model(app, model_name)
                table = model._meta.db_table
                if table not in tables:
                    continue  # Fresh install: normal migrate creates it.
                actual = columns(table)
                diagnostic = app == "exchanges"
                if diagnostic:
                    present = [model._meta.get_field(n) for n in DIAGNOSTICS if n in actual]
                    if not present:
                        continue  # Normal migration adds all three columns.
                    validate_fields(model, actual, present)
                else:
                    constraints = validate_model(model, actual)
                parents = executor.loader.graph.node_map[key].parents
                if any(parent.key not in applied for parent in parents):
                    raise CommandError(f"Unapplied dependency for {app}.{name}; stopped.")
                self.stdout.write(f"VERIFIED: existing schema for {app}.{name}")
                if not apply:
                    continue
                with connection.schema_editor() as editor:
                    if diagnostic:
                        for field_name in DIAGNOSTICS:
                            if field_name not in actual:
                                editor.add_field(model, model._meta.get_field(field_name))
                    else:
                        # Preview builds used different index names. Preserve existing indexes;
                        # add canonical names so future migration state remains accurate.
                        for constraint in model._meta.constraints:
                            if constraint.name not in constraints:
                                editor.add_constraint(model, constraint)
                        for index in model._meta.indexes:
                            if index.name not in constraints:
                                editor.add_index(model, index)
                recorder.record_applied(app, name)
                applied.add(key)
                self.stdout.write(f"ADOPTED: {app}.{name}; existing rows preserved")
        self.stdout.write("REACT_SCHEMA_OK" if apply else "REACT_SCHEMA_CHECK_OK (no changes)")
