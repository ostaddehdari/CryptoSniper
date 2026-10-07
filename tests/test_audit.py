import json

import pytest
from apps.accounts.audit import record_audit
from apps.accounts.models import AuditLog
from django.core.exceptions import ValidationError
from django.urls import reverse


@pytest.mark.django_db
def test_audit_log_is_append_only_and_redacts_sensitive_metadata(django_user_model, rf):
    user = django_user_model.objects.create_user(username="audit-user")
    request = rf.get("/", REMOTE_ADDR="203.0.113.9")
    request.user = user
    event = record_audit(
        "security.checked",
        request=request,
        user=user,
        metadata={
            "password": "plain-secret",
            "details": "token=another-secret acceptable=value",
            "nested": {"api_key": "key-secret"},
        },
    )
    encoded = json.dumps(event.metadata)
    assert "plain-secret" not in encoded
    assert "another-secret" not in encoded
    assert "key-secret" not in encoded
    assert "203.0.113.9" not in event.ip_hash
    assert len(event.ip_hash) == 64
    event.event_type = "security.changed"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        AuditLog.objects.filter(pk=event.pk).update(event_type="security.changed")
    with pytest.raises(ValidationError):
        AuditLog.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_audit_ui_is_owner_scoped_and_masks_ip(client, django_user_model, rf):
    owner = django_user_model.objects.create_user(username="audit-owner", password="safe-password")
    other = django_user_model.objects.create_user(username="audit-other")
    request = rf.get("/", REMOTE_ADDR="198.51.100.7")
    record_audit("profile.updated", request=request, user=owner, metadata={"fields": ["theme"]})
    record_audit("private.other_event", request=request, user=other)
    client.force_login(owner)
    response = client.get(reverse("audit-events"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "profile.updated" in body
    assert "private.other_event" not in body
    assert "198.51.100.7" not in body


@pytest.mark.django_db
def test_sensitive_account_actions_create_audit_events(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="audited-actions", email="before@example.test", password="safe-password"
    )
    client.force_login(user)
    response = client.post(
        reverse("profile"),
        {
            "display_name": "Audited",
            "email": "after@example.test",
            "timezone": "Asia/Tehran",
            "base_currency": "USDT",
            "theme": "dark",
        },
    )
    assert response.status_code == 302
    event = AuditLog.objects.get(owner=user, event_type="profile.updated")
    assert set(event.metadata["fields"]) == {"display_name", "email", "theme"}
    assert "after@example.test" not in json.dumps(event.metadata)
