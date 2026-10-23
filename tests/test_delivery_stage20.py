from django.test import override_settings


@override_settings(
    RELEASE_VERSION="0.23.0rc1",
    SOURCE_REVISION="delivery-test",
    DEPLOYMENT_ENVIRONMENT="staging",
)
def test_stage23_delivery_contract_is_honest(client, django_user_model):
    owner = django_user_model.objects.create_user(username="delivery23")
    client.force_login(owner)
    response = client.get("/api/v1/acceptance/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release"] == "0.23.0rc1"
    assert payload["paper_only"] is True
    assert payload["real_order_writes"] is False
    assert payload["accepted_inputs"] == ["manual", "smart_paste", "telegram_feature_gated"]
    assert payload["deferred"] == {
        "telegram_real_account_validation": "credentials_required",
        "telegram_full_archive_validation": "authorized_channel_required",
        "channel_ai_provider_validation": "provider_credentials_required",
        "provider_specific_historical_candles": "not_implemented_binance_public_only",
        "real_binance_writes": "disabled_not_verified",
        "five_exchange_live_validation": "credentials_required",
    }


def test_delivery_contract_requires_login(client):
    response = client.get("/api/v1/acceptance/")
    assert response.status_code in {302, 401, 403}


def test_stage23_liveness_and_service_worker_version(client):
    assert client.get("/health/live/").json()["stage"] == "S23"
    worker = client.get("/service-worker.js").content.decode()
    assert "cryptosniper-static-v23" in worker
