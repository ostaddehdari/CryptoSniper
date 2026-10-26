"""Loaded explicitly by the isolated test Celery worker; never imported by production."""

from stage31_contract_provider import install_contract_provider

install_contract_provider()
