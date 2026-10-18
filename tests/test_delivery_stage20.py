from django.test import override_settings


@override_settings(
    RELEASE_VERSION="0.20.0rc1",
    SOURCE_REVISION="delivery-test",
    DEPLOYMENT_ENVIRONMENT="staging",
)
def test_base_delivery_contract_is_honest(client, django_user_model):
    owner = django_user_model.objects.create_user(username="delivery20")
    client.force_login(owner)
    response = client.get("/api/v1/acceptance/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release"] == "0.20.0rc1"
    assert payload["paper_only"] is True
    assert payload["real_order_writes"] is False
    assert payload["accepted_inputs"] == ["manual", "smart_paste"]
    assert payload["deferred"] == {
        "telegram": "stage21",
        "channel_templates": "stage21",
        "channel_ai": "stage21",
        "real_binance_writes": "disabled_not_verified",
    }


def test_delivery_contract_requires_login(client):
    response = client.get("/api/v1/acceptance/")
    assert response.status_code in {302, 401, 403}


def test_stage20_liveness_and_service_worker_version(client):
    assert client.get("/health/live/").json()["stage"] == "S20"
    worker = client.get("/service-worker.js").content.decode()
    assert "cryptosniper-static-v20" in worker
