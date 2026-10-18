"""Canonical signal ingress, including the final-stage Telegram boundary."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SignalSource(models.Model):
    class Method(models.TextChoices):
        MANUAL = "manual", "ورود دستی"
        SMART_PASTE = "smart_paste", "چسباندن هوشمند"
        TELEGRAM = "telegram", "تلگرام"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signal_sources"
    )
    name = models.CharField(max_length=80)
    method = models.CharField(max_length=16, choices=Method.choices)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("method", "name", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "method", "name"), name="signal_source_owner_method_name_unique"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.method})"

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "نام منبع لازم است."})


class RawSignal(models.Model):
    """Immutable original input. New versions are append-only RawSignalRevision rows."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="raw_signals"
    )
    source = models.ForeignKey(SignalSource, on_delete=models.CASCADE, related_name="inputs")
    original_text = models.TextField()
    original_payload = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    external_id = models.CharField(max_length=160, blank=True)
    received_version = models.CharField(max_length=24, default="v1")
    revision_number = models.PositiveIntegerField(default=1)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "source", "checksum"),
                name="rawsignal_owner_source_checksum_unique",
            ),
            models.UniqueConstraint(
                fields=("owner", "source", "external_id"),
                condition=~models.Q(external_id=""),
                name="rawsignal_owner_source_external_unique",
            ),
        ]
        indexes = [models.Index(fields=("owner", "received_at"))]

    def __str__(self):
        return f"Raw #{self.pk} · {self.source_id} · r{self.revision_number}"


class RawSignalRevision(models.Model):
    raw_signal = models.ForeignKey(RawSignal, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    text = models.TextField()
    payload = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    received_version = models.CharField(max_length=24, default="v1")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("version",)
        constraints = [
            models.UniqueConstraint(
                fields=("raw_signal", "version"), name="rawsignal_revision_unique"
            ),
        ]

    def __str__(self):
        return f"Raw #{self.raw_signal_id} revision {self.version}"


class Signal(models.Model):
    """One entry, at most three executable targets; trade execution is a later stage."""

    class Status(models.TextChoices):
        NEW = "new", "جدید"
        PARSED = "parsed", "ساختارمند"
        NEEDS_REVIEW = "needs_review", "نیازمند بررسی"
        APPROVED = "approved", "تأییدشده"
        REJECTED = "rejected", "ردشده"
        EXECUTED = "executed", "اجراشده"
        FAILED = "failed", "ناموفق"

    class Side(models.TextChoices):
        LONG = "long", "Long"
        SHORT = "short", "Short"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inbox_signals"
    )
    source = models.ForeignKey(SignalSource, on_delete=models.CASCADE, related_name="signals")
    raw_signal = models.OneToOneField(
        RawSignal, on_delete=models.CASCADE, related_name="structured_signal"
    )
    exchange_account = models.ForeignKey(
        "exchanges.UserExchangeAccount", on_delete=models.CASCADE, null=True, blank=True
    )
    market = models.ForeignKey(
        "exchanges.ExchangeMarket", on_delete=models.PROTECT, null=True, blank=True
    )
    side = models.CharField(max_length=8, choices=Side.choices, blank=True)
    entry_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    technical_confidence = models.PositiveSmallIntegerField(default=0)
    parser_version = models.CharField(max_length=40, default="manual-v1")
    parsed_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    review_reason = models.CharField(max_length=500, blank=True)
    revision = models.PositiveIntegerField(default=1)
    approved_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("owner", "status", "created_at")),
            models.Index(fields=("owner", "source", "created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(technical_confidence__lte=100), name="signal_confidence_lte_100"
            ),
        ]

    def __str__(self):
        return f"Signal #{self.pk} · {self.status}"

    def clean(self):
        super().clean()
        if self.source_id and self.owner_id and self.source.owner_id != self.owner_id:
            raise ValidationError("منبع سیگنال متعلق به این کاربر نیست.")
        if self.raw_signal_id and self.owner_id:
            if (
                self.raw_signal.owner_id != self.owner_id
                or self.raw_signal.source_id != self.source_id
            ):
                raise ValidationError("ورودی اصلی سیگنال با کاربر یا منبع هم‌خوان نیست.")
        if self.market_id and self.exchange_account_id:
            if self.market.exchange_id != self.exchange_account.exchange_id:
                raise ValidationError("بازار متعلق به این اتصال نیست.")
            if self.exchange_account.owner_id != self.owner_id:
                raise ValidationError("حساب صرافی متعلق به کاربر دیگری است.")


class SignalTarget(models.Model):
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="targets")
    position = models.PositiveSmallIntegerField()
    price = models.DecimalField(max_digits=32, decimal_places=16)
    share_percent = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(
                fields=("signal", "position"), name="signal_target_position_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1) & models.Q(position__lte=3),
                name="signal_target_position_range",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="signal_target_positive_price"
            ),
            models.CheckConstraint(
                condition=models.Q(share_percent__gt=0) & models.Q(share_percent__lte=100),
                name="signal_target_share_range",
            ),
        ]

    def __str__(self):
        return f"Signal {self.signal_id} TP{self.position}"


class SignalRevision(models.Model):
    """Historical structured snapshots; never updated after creation."""

    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="history")
    revision = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    reason = models.CharField(max_length=500)
    snapshot = models.JSONField(default=dict)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("revision",)
        constraints = [
            models.UniqueConstraint(fields=("signal", "revision"), name="signal_revision_unique")
        ]

    def __str__(self):
        return f"Signal {self.signal_id} revision {self.revision}"


class TelegramAccount(models.Model):
    """Encrypted Telethon session and API identity; plaintext never reaches logs/UI."""

    class Status(models.TextChoices):
        DISCONNECTED = "disconnected", "قطع"
        AWAITING_CODE = "awaiting_code", "منتظر کد"
        AWAITING_PASSWORD = "awaiting_password", "منتظر رمز دومرحله‌ای"
        CONNECTED = "connected", "متصل"
        ERROR = "error", "خطا"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_account"
    )
    label = models.CharField(max_length=80, default="Telegram")
    phone_hint = models.CharField(max_length=32, blank=True)
    credential_key_version = models.PositiveIntegerField(default=1)
    credentials_encrypted = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DISCONNECTED)
    last_error = models.CharField(max_length=80, blank=True)
    verification_sent_at = models.DateTimeField(null=True, blank=True)
    verification_expires_at = models.DateTimeField(null=True, blank=True)
    verification_resend_at = models.DateTimeField(null=True, blank=True)
    verification_attempts = models.PositiveSmallIntegerField(default=0)
    connected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.owner_id}:{self.label}"


class TelegramChannel(models.Model):
    class ParseMode(models.TextChoices):
        TEMPLATE = "template", "قالب"
        AI = "ai", "هوش مصنوعی"
        HYBRID = "hybrid", "ترکیبی"

    class Automation(models.TextChoices):
        MANUAL = "manual", "دستی"
        SEMI_AUTO = "semi_auto", "نیمه‌خودکار"
        FULL_AUTO = "full_auto", "تمام‌خودکار Paper"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_channels"
    )
    account = models.ForeignKey(TelegramAccount, on_delete=models.CASCADE, related_name="channels")
    source = models.OneToOneField(
        SignalSource, on_delete=models.CASCADE, related_name="telegram_channel"
    )
    peer_id = models.BigIntegerField()
    username = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=160)
    parse_mode = models.CharField(
        max_length=12, choices=ParseMode.choices, default=ParseMode.TEMPLATE
    )
    template = models.JSONField(default=dict, blank=True)
    automation = models.CharField(
        max_length=12, choices=Automation.choices, default=Automation.MANUAL
    )
    enabled = models.BooleanField(default=True)
    last_message_id = models.BigIntegerField(default=0)
    live_message_id = models.BigIntegerField(default=0)
    max_catchup = models.PositiveSmallIntegerField(default=100)
    min_confidence = models.PositiveSmallIntegerField(default=80)
    paper_capital = models.DecimalField(max_digits=32, decimal_places=16, default=Decimal("100"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "peer_id"), name="telegram_channel_owner_peer_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(max_catchup__gte=1) & models.Q(max_catchup__lte=500),
                name="telegram_channel_catchup_range",
            ),
            models.CheckConstraint(
                condition=models.Q(min_confidence__lte=100),
                name="telegram_channel_confidence_lte_100",
            ),
            models.CheckConstraint(
                condition=models.Q(paper_capital__gt=0),
                name="telegram_channel_capital_positive",
            ),
        ]

    def __str__(self):
        return self.title


class TelegramChannelTemplate(models.Model):
    class MessageKind(models.TextChoices):
        SIGNAL = "signal", "سیگنال"
        UPDATE = "update", "به‌روزرسانی"
        CANCEL = "cancel", "لغو"
        RESULT = "result", "نتیجه"
        NOISE = "noise", "غیرسیگنال"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.ForeignKey(TelegramChannel, on_delete=models.CASCADE, related_name="templates")
    name = models.CharField(max_length=80)
    version = models.PositiveIntegerField(default=1)
    priority = models.PositiveSmallIntegerField(default=100)
    message_kind = models.CharField(
        max_length=12, choices=MessageKind.choices, default=MessageKind.SIGNAL
    )
    definition = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("priority", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("channel", "name", "version"),
                name="telegram_template_channel_name_version_unique",
            )
        ]

    def __str__(self):
        return f"{self.channel_id}:{self.name}:v{self.version}"


class TelegramMessage(models.Model):
    """Durable cursor/dedup record; raw/edit history lives in RawSignal revisions."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.ForeignKey(TelegramChannel, on_delete=models.CASCADE, related_name="messages")
    message_id = models.BigIntegerField()
    revision = models.PositiveIntegerField(default=1)
    text_checksum = models.CharField(max_length=64)
    message_kind = models.CharField(
        max_length=12,
        choices=TelegramChannelTemplate.MessageKind.choices,
        default=TelegramChannelTemplate.MessageKind.SIGNAL,
    )
    matched_template = models.ForeignKey(
        TelegramChannelTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    raw_signal = models.ForeignKey(
        RawSignal, on_delete=models.SET_NULL, null=True, blank=True, related_name="telegram_events"
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("channel", "message_id")
        constraints = [
            models.UniqueConstraint(
                fields=("channel", "message_id"), name="telegram_message_channel_id_unique"
            )
        ]

    def __str__(self):
        return f"{self.channel_id}:{self.message_id}:r{self.revision}"


class TelegramBackfillJob(models.Model):
    """Resumable archive import bounded by the latest message seen when the job starts."""

    class Status(models.TextChoices):
        PENDING = "pending", "در صف"
        RUNNING = "running", "در حال دریافت"
        PAUSED = "paused", "متوقف"
        COMPLETED = "completed", "کامل"
        FAILED = "failed", "ناموفق"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.ForeignKey(
        TelegramChannel, on_delete=models.CASCADE, related_name="backfill_jobs"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    upper_message_id = models.BigIntegerField(default=0)
    cursor_message_id = models.BigIntegerField(default=0)
    scanned_messages = models.PositiveBigIntegerField(default=0)
    imported_messages = models.PositiveBigIntegerField(default=0)
    skipped_messages = models.PositiveBigIntegerField(default=0)
    batch_size = models.PositiveSmallIntegerField(default=100)
    last_error = models.CharField(max_length=80, blank=True)
    retry_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(batch_size__gte=20) & models.Q(batch_size__lte=500),
                name="telegram_backfill_batch_range",
            )
        ]

    def __str__(self):
        return f"{self.channel_id}:{self.status}:{self.cursor_message_id}"


class SignalAIAnalysis(models.Model):
    class Status(models.TextChoices):
        COMPLETE = "complete", "کامل"
        INVALID = "invalid", "نامعتبر"
        ERROR = "error", "خطا"

    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="ai_analyses")
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=40, default="telegram-signal-v1")
    input_hash = models.CharField(max_length=64)
    output = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices)
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("signal", "input_hash", "prompt_version"),
                name="signal_ai_analysis_input_unique",
            )
        ]

    def __str__(self):
        return f"Signal {self.signal_id} · {self.model} · {self.status}"


class SignalOutcome(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "منتظر داده"
        NO_DATA = "no_data", "بدون داده"
        NOT_TRIGGERED = "not_triggered", "ورود فعال نشد"
        OPEN = "open", "فعال"
        TARGET = "target", "هدف محقق شد"
        STOPPED = "stopped", "حد ضرر"
        AMBIGUOUS = "ambiguous", "مبهم"
        EXPIRED = "expired", "منقضی"

    signal = models.OneToOneField(Signal, on_delete=models.CASCADE, related_name="outcome")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=32, default="binance_public")
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8, default="1h")
    entry_hit_at = models.DateTimeField(null=True, blank=True)
    stop_hit_at = models.DateTimeField(null=True, blank=True)
    targets_hit = models.PositiveSmallIntegerField(default=0)
    last_target_price = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    evaluated_from = models.DateTimeField()
    evaluated_until = models.DateTimeField(null=True, blank=True)
    policy_version = models.CharField(max_length=32, default="ohlc-conservative-v1")
    evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-evaluated_from",)
        indexes = [models.Index(fields=("owner", "status", "evaluated_from"))]

    def __str__(self):
        return f"{self.signal_id}:{self.status}:{self.targets_hit}"
