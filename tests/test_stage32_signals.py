import pytest
from apps.signals.parsing import assess
from apps.signals.quality import parser_quality_report
from django.urls import reverse


def test_stage32_labeled_smart_paste_quality_is_reproducible():
    report = parser_quality_report()
    assert report["corpus_version"] == "stage32-v1"
    assert report["samples"] >= 6
    assert report["accuracy_percent"] == 100
    assert report["meaning"] == "field_extraction_quality_not_profit_probability"


def test_stage32_confidence_and_validation_are_separate():
    result = assess(
        {
            "pair": "BTC/USDT",
            "side": "long",
            "entry": "100",
            "entry_range": None,
            "stop_loss": "90",
            "all_targets": ["110"],
            "execution_targets": ["110"],
            "extra_targets": [],
            "futures_mentioned": True,
        }
    )
    assert result["confidence_band"] == "high"
    assert result["validation"]["blocked"] is True
    assert result["validation"]["complete"] is False


@pytest.mark.django_db
def test_stage32_quality_endpoint_is_private(client, django_user_model):
    assert client.get(reverse("api-smart-paste-quality")).status_code in {302, 401, 403}
    client.force_login(django_user_model.objects.create_user(username="s32-quality"))
    payload = client.get(reverse("api-smart-paste-quality"))
    assert payload.status_code == 200
    assert payload.json()["quality"]["accuracy_percent"] == 100
