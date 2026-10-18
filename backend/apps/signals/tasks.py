"""Celery discovery boundary for signal ingestion tasks."""

from .backfill import process_backfill_batch

__all__ = ["process_backfill_batch"]
