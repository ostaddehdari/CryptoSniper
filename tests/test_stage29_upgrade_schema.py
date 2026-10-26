from io import StringIO

import pytest
from apps.accounts.models import WalletConnection
from apps.core.management.commands.reconcile_react_schema import TARGETS
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

pytestmark = pytest.mark.django_db(transaction=True)
WALLET = TARGETS[0][:2]


def run_apply():
    call_command("reconcile_react_schema", apply=True, stdout=StringIO())


def test_preview_wallet_is_adopted_without_losing_rows(django_user_model):
    owner = django_user_model.objects.create_user(username="legacy-wallet")
    wallet = WalletConnection.objects.create(
        owner=owner, provider="evm_address", label="existing", address="test-address"
    )
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*WALLET)
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER INDEX accounts_wa_owner_i_e18d3d_idx RENAME TO old_preview_wallet_idx"
        )
    try:
        run_apply()
        run_apply()  # Resumed installations are idempotent.
        assert WALLET in recorder.applied_migrations()
        assert WalletConnection.objects.get(pk=wallet.pk).address == "test-address"
        with connection.cursor() as cursor:
            assert "accounts_wa_owner_i_e18d3d_idx" in connection.introspection.get_constraints(
                cursor, "accounts_walletconnection"
            )
    finally:
        recorder.record_applied(*WALLET)
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX IF EXISTS old_preview_wallet_idx")


def test_mismatching_existing_wallet_is_not_blindly_faked():
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*WALLET)
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE accounts_walletconnection ALTER COLUMN label TYPE varchar(79)")
    try:
        with pytest.raises(CommandError, match="Schema mismatch"):
            run_apply()
        assert WALLET not in recorder.applied_migrations()
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE accounts_walletconnection ALTER COLUMN label TYPE varchar(80)"
            )
        recorder.record_applied(*WALLET)


def test_dry_run_never_marks_migration_applied():
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*WALLET)
    try:
        call_command("reconcile_react_schema", stdout=StringIO())
        assert WALLET not in recorder.applied_migrations()
    finally:
        recorder.record_applied(*WALLET)


def test_partial_preview_diagnostics_are_completed_without_touching_existing_values():
    key = TARGETS[2][:2]
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*key)
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE exchanges_userexchangeaccount DROP COLUMN last_error_message")
    try:
        run_apply()
        assert key in recorder.applied_migrations()
        with connection.cursor() as cursor:
            cursor.execute("SELECT last_error_message FROM exchanges_userexchangeaccount LIMIT 1")
    finally:
        recorder.record_applied(*key)


def test_applied_schema_needs_no_changes():
    before = set(MigrationRecorder(connection).applied_migrations())
    run_apply()
    assert before == set(MigrationRecorder(connection).applied_migrations())


def test_missing_table_is_left_for_normal_migrate():
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*WALLET)
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE accounts_walletconnection RENAME TO wallet_fresh_probe")
    try:
        run_apply()
        assert WALLET not in recorder.applied_migrations()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE wallet_fresh_probe RENAME TO accounts_walletconnection")
        recorder.record_applied(*WALLET)
