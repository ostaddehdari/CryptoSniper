# S25 production transition from the historical Stage34 branch

The Stage34 label on production is a historical release name from a diverged branch. It does not mark S26–S31 in the current deployment-center plan as complete. Current execution order is S25, S26–S30, then S31.

## Observed baseline (2026-11-28 UTC)

- Source repository current S25 baseline before this document: `d2f47a193c0bf06e479b88c3436d8257e3619238`.
- Installed production source: `7ce55a59b07519ba84a948058fd4ee84942ba414`; Nginx route marker is `# Managed by CryptoSniper Stage34 installer`.
- The branches diverged after `8c0352ddb5b5cd8639208dbd95b2e790a0746104`. The historical branch contains extra applied migrations in accounts, exchanges, marketdata, operations and tradeplans. The migration ledger also contains names from an earlier parallel branch.
- [Read-only schema inventory](https://github.com/ostaddehdari/deployment-center/actions/runs/46109867386) and [gate inventory](https://github.com/ostaddehdari/deployment-center/actions/runs/46110298660): database ~30 MB; web/PostgreSQL/trailing services active; `LIVE_TRADING_ENABLED=true`, one exchange account has `trading_enabled=true`, no unsettled live orders or unfinished managed positions were recorded at the instant of inspection. These counts are time-dependent and must be checked again at cutover.
- [Initial S25 deployment attempt](https://github.com/ostaddehdari/deployment-center/actions/runs/46108550300) completed exact-source checks and encrypted pre-upgrade backup, then stopped at the unmanaged Nginx marker guard before replacing the app or route.
- [Initial isolated schema rehearsal](https://github.com/ostaddehdari/deployment-center/actions/runs/46110202920): a local PostgreSQL custom dump was restored into a disposable database on the same host, exact S25 source was tested with a separate database URL, Django `check` passed, `migrate --plan` had no pending operations, `migrate --noinput` succeeded, and the temporary database was dropped. No production database migration or app replacement occurred. This establishes schema boot compatibility only; it is not an end-to-end UI, live trading or rollback acceptance test.

- [Isolated UI and rollback-code rehearsal](https://github.com/ostaddehdari/deployment-center/actions/runs/46110689430): copied exchange-account trading was disabled and Live flags were false; S25 Django check, migrate plan/apply, static collection and HTTPS login/app responses passed. The historical Stage34 code also passed Django check and had no pending migrations against that disposable copy. This is a code/schema rollback check, not a production service rollback.
- [Real encrypted-backup restore](https://github.com/ostaddehdari/deployment-center/actions/runs/46110858371): the latest daily AES-GCM archive was authenticated against its manifest, decrypted locally on the server, restored into a disposable database, and its migration-ledger count matched production. The temporary database and plaintext were removed. Neither archive nor data left the server.

## Safe transition gate

1. Freeze the target commit after incorporating this decision and pass exact-source CI. Keep the existing S25 deploy workflow blocked until the steps below are tested.
2. Test the S25 web app and essential Paper flows against an isolated restored database with network-isolated credentials and Live gates explicitly off. Reconcile the extra historical schema fields and records without deleting them.
3. Implement a narrow installer transition from the exact installed Stage34 SHA and Nginx marker. Verify the original route hash, backup the app, route and database, and fail closed if any observed source, marker or environment differs. Never bypass the guard by editing the live marker manually.
4. At cutover, set `LIVE_TRADING_ENABLED=false` and disable per-account trading through the product's controlled path; recheck provider-side orders and local unsettled orders/managed positions. A zero count in this document is not proof that no new orders have appeared.
5. Deploy through deployment-center and confirm exact installed SHA, all services, public and local readiness, login, Paper path, and rollback to the preserved Stage34 app and route. Keep Live off after rollback or S25 cutover until provider-specific acceptance is completed.
6. If the isolated UI or rollback checks fail, leave production on Stage34, preserve its data and record the blocker. Do not delete Stage34-only migration records or database objects as a shortcut.

This document is a transition decision record, not an authorization to trade or a claim that S25 is installed.
