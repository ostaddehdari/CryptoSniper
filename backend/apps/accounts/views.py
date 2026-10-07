from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import ProfileForm


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
