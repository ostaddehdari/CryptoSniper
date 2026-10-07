from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .forms import (
    PasswordResetRequestForm,
    ProfileForm,
    SetNewPasswordForm,
    SignInForm,
)
from .models import PasswordResetRequest, UserSession
from .services import (
    issue_password_reset,
    revoke_all_user_sessions,
    revoke_user_session,
    token_digest,
)


class SignInView(LoginView):
    template_name = "registration/login.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات حساب شما ذخیره شد.")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"form": form, "nav": "settings"})


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        issue_password_reset(request, form.cleaned_data["email"])
        return redirect("password-reset-sent")
    return render(request, "registration/password_reset_request.html", {"form": form})


@never_cache
def password_reset_sent(request):
    return render(request, "registration/password_reset_sent.html")


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def password_reset_confirm(request, token):
    reset = (
        PasswordResetRequest.objects.select_related("owner")
        .filter(token_digest=token_digest(token))
        .first()
    )
    if not reset or not reset.is_usable:
        return render(request, "registration/password_reset_invalid.html", status=400)
    form = SetNewPasswordForm(reset.owner, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = (
                PasswordResetRequest.objects.select_for_update()
                .select_related("owner")
                .get(pk=reset.pk)
            )
            if not locked.is_usable:
                raise Http404
            locked.owner.set_password(form.cleaned_data["password"])
            locked.owner.save(update_fields=("password",))
            locked.used_at = timezone.now()
            locked.save(update_fields=("used_at",))
            revoke_all_user_sessions(locked.owner)
        return redirect("password-reset-complete")
    return render(request, "registration/password_reset_confirm.html", {"form": form})


@never_cache
def password_reset_complete(request):
    return render(request, "registration/password_reset_complete.html")


@login_required
@never_cache
@require_http_methods(["GET"])
def sessions(request):
    active = UserSession.objects.for_user(request.user).order_by("-last_seen_at")
    return render(
        request,
        "accounts/sessions.html",
        {"sessions": active, "current_key": request.session.session_key, "nav": "settings"},
    )


@login_required
@require_http_methods(["POST"])
def revoke_session(request, session_id):
    session = get_object_or_404(UserSession.objects.for_user(request.user), pk=session_id)
    is_current = session.session_key == request.session.session_key
    revoke_user_session(session)
    if is_current:
        logout(request)
        return redirect("login")
    messages.success(request, "نشست انتخاب‌شده بسته شد.")
    return redirect("sessions")


@login_required
@require_http_methods(["POST"])
def sign_out(request):
    key = request.session.session_key
    tracked = UserSession.objects.filter(owner=request.user, session_key=key).first()
    if tracked:
        revoke_user_session(tracked)
    logout(request)
    return redirect("login")
