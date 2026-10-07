import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_profile_is_self_scoped_and_updates_normalized_fields(client, django_user_model):
    owner = django_user_model.objects.create_user(
        username="owner-profile", email="owner@example.test", password="safe-password"
    )
    other = django_user_model.objects.create_user(
        username="other-profile", email="other@example.test", display_name="Private name"
    )
    client.force_login(owner)
    response = client.get(reverse("profile"))
    assert response.status_code == 200
    assert "Private name" not in response.content.decode()
    response = client.post(
        reverse("profile"),
        {
            "display_name": "معامله‌گر آرام",
            "email": "NEW@EXAMPLE.TEST",
            "timezone": "Asia/Tehran",
            "base_currency": "USDT",
            "theme": "light",
        },
    )
    assert response.status_code == 302
    owner.refresh_from_db()
    other.refresh_from_db()
    assert owner.email == "new@example.test"
    assert owner.display_name == "معامله‌گر آرام"
    assert other.display_name == "Private name"


@pytest.mark.django_db
def test_profile_rejects_duplicate_email_and_invalid_timezone(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="profile-user", email="one@example.test", password="safe-password"
    )
    django_user_model.objects.create_user(username="existing", email="used@example.test")
    client.force_login(user)
    response = client.post(
        reverse("profile"),
        {
            "display_name": "Name",
            "email": "USED@example.test",
            "timezone": "Not/AZone",
            "base_currency": "USDT",
            "theme": "light",
        },
    )
    assert response.status_code == 200
    assert "این ایمیل قبلاً ثبت شده است" in response.content.decode()


def test_profile_requires_authentication(client):
    assert client.get(reverse("profile")).status_code == 302
