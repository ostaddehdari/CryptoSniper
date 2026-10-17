from datetime import timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone


class ReportFilter(forms.Form):
    period = forms.ChoiceField(choices=[("day", "روزانه"), ("week", "هفتگی"), ("month", "ماهانه")])
    group = forms.ChoiceField(
        choices=[
            ("total", "مجموع"),
            ("coin", "ارز"),
            ("exchange", "صرافی"),
            ("source", "منبع"),
        ]
    )
    date_from = forms.DateField(label="از تاریخ", required=False)
    date_to = forms.DateField(label="تا تاریخ", required=False)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.now().astimezone(ZoneInfo(user.timezone)).date()
        self.fields["date_from"].initial = today - timedelta(days=30)
        self.fields["date_to"].initial = today
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        data = super().clean()
        start, end = data.get("date_from"), data.get("date_to")
        if start and end and start > end:
            raise forms.ValidationError("تاریخ شروع نباید بعد از تاریخ پایان باشد.")
        if start and end and (end - start).days > 3660:
            raise forms.ValidationError("بازه گزارش حداکثر ده سال است.")
        return data
