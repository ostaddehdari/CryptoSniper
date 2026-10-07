import re
from datetime import timedelta

import pytest
from apps.accounts.models import PasswordResetRequest, UserSession
from django.core import mail
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
def test_password_reset_is_generic_one_time_and_revokes_sessions(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="reset-user", email="reset@example.test", password="old-secure-password"
    )
    signed_in = client.__class__()
    signed_in.force_login(user)
    signed_in.get(reverse("dashboard"), HTTP_USER_AGENT="Test browser")
    old_key = signed_in.session.session_key
    assert UserSession.objects.filter(owner=user, session_key=old_key).exists()

    response = client.post(reverse("password-reset"), {"email": "RESET@example.test"})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    token = re.search(r"/auth/password-reset/([^/]+)/", mail.outbox[0].body).group(1)
    response = client.post(
        reverse("password-reset-confirm", args=[token]),
        {
            "password": "a-new-strong-password-2026",
            "password_confirm": "a-new-strong-password-2026",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("password-reset-complete")
    user.refresh_from_db()
    assert user.check_password("a-new-strong-password-2026")
    assert not signed_in.get(reverse("dashboard")).wsgi_request.user.is_authenticated
    assert client.get(reverse("password-reset-confirm", args=[token])).status_code == 400


@pytest.mark.django_db
def test_password_reset_expiry_and_unknown_email_are_indistinguishable(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="expired-user", email="expired@example.test"
    )
    client.post(reverse("password-reset"), {"email": user.email})
    reset = PasswordResetRequest.objects.get(owner=user)
    reset.expires_at = timezone.now() - timedelta(seconds=1)
    reset.save(update_fields=("expires_at",))
    token = re.search(r"/auth/password-reset/([^/]+)/", mail.outbox[0].body).group(1)
    assert client.get(reverse("password-reset-confirm", args=[token])).status_code == 400
    mail.outbox.clear()
    response = client.post(reverse("password-reset"), {"email": "absent@example.test"})
    assert response.status_code == 302
    assert response.url == reverse("password-reset-sent")
    assert mail.outbox == []


@pytest.mark.django_db
def test_user_can_revoke_only_their_own_session(client, django_user_model):
    owner = django_user_model.objects.create_user(
        username="session-owner", password="safe-password"
    )
    other = django_user_model.objects.create_user(username="session-other")
    other_session = UserSession.objects.create(
        owner=other,
        session_key="other-key",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    client.force_login(owner)
    client.get(reverse("sessions"))
    assert client.post(reverse("revoke-session", args=[other_session.pk])).status_code == 404
    own = UserSession.objects.get(owner=owner)
    response = client.post(reverse("revoke-session", args=[own.pk]))
    assert response.status_code == 302
    assert not client.get(reverse("dashboard")).wsgi_request.user.is_authenticated
