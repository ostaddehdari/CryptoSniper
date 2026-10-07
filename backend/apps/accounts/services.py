import hashlib
import secrets
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import PasswordResetRequest, User, UserSession


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_password_reset(request, email):
    user = User.objects.filter(email__iexact=email, is_active=True, account_status="active").first()
    if not user:
        return
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    with transaction.atomic():
        PasswordResetRequest.objects.filter(
            owner=user, used_at__isnull=True, expires_at__gt=now
        ).update(used_at=now)
        PasswordResetRequest.objects.create(
            owner=user,
            token_digest=token_digest(token),
            expires_at=now + timedelta(minutes=30),
        )
    reset_url = request.build_absolute_uri(reverse("password-reset-confirm", args=[token]))
    send_mail(
        "بازیابی رمز CryptoSniper",
        "این پیوند تا ۳۰ دقیقه و فقط یک‌بار معتبر است:\n" + reset_url,
        None,
        [user.email],
    )


def revoke_user_session(session, *, at=None):
    at = at or timezone.now()
    if session.revoked_at is None:
        session.revoked_at = at
        session.save(update_fields=("revoked_at",))
    Session.objects.filter(session_key=session.session_key).delete()


def revoke_all_user_sessions(user):
    now = timezone.now()
    keys = list(
        UserSession.objects.for_user(user)
        .filter(revoked_at__isnull=True)
        .values_list("session_key", flat=True)
    )
    UserSession.objects.for_user(user).filter(revoked_at__isnull=True).update(revoked_at=now)
    Session.objects.filter(session_key__in=keys).delete()
