"""Paper trading policy management, no live-mode controls."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import PaperRiskPolicy


class PaperRiskPolicyForm(forms.ModelForm):
    class Meta:
        model = PaperRiskPolicy
        fields = ("max_active_trades", "max_capital_per_trade", "max_total_allocated")
        labels = {
            "max_active_trades": "سقف معاملات فعال",
            "max_capital_per_trade": "حداکثر سرمایه هر معامله (USDT)",
            "max_total_allocated": "حداکثر سرمایه تخصیص‌یافته (USDT)",
        }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def paper_risk(request):
    policy, _ = PaperRiskPolicy.objects.get_or_create(owner=request.user)
    form = PaperRiskPolicyForm(request.POST or None, instance=policy)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        if updated.max_capital_per_trade > updated.max_total_allocated:
            form.add_error("max_capital_per_trade", "سقف یک معامله نباید از سقف کل بیشتر باشد.")
        else:
            updated.save()
            messages.success(request, "سقف‌های Paper ذخیره شد؛ اجرای واقعی همچنان غیرفعال است.")
            return redirect("paper-risk")
    return render(request, "trading/risk.html", {"form": form, "nav": "paper"})
