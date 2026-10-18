"""Per-channel aliases layered over the deterministic local signal parser."""

import re

from django.core.exceptions import ValidationError

from .parser import extract

CANONICAL = {
    "entry": "ENTRY",
    "stop": "STOP LOSS",
    "target": "TARGET",
    "long": "LONG",
    "short": "SHORT",
    "leverage": "LEVERAGE",
}


def apply_channel_template(text, template):
    if not isinstance(template, dict):
        raise ValidationError("قالب کانال باید JSON object باشد.")
    aliases = template.get("aliases", {})
    if not isinstance(aliases, dict) or set(aliases) - set(CANONICAL):
        raise ValidationError("کلید alias قالب ناشناخته است.")
    normalized = text
    for key, values in aliases.items():
        if not isinstance(values, list) or len(values) > 20:
            raise ValidationError("هر alias باید فهرست محدود باشد.")
        for value in values:
            value = str(value).strip()
            if not value or len(value) > 40:
                raise ValidationError("طول alias قالب معتبر نیست.")
            normalized = re.sub(re.escape(value), CANONICAL[key], normalized, flags=re.I)
    result = extract(normalized)
    result["source_hint"] = "telegram_template"
    result["template_version"] = str(template.get("version", "1"))[:20]
    return result


def complete_extraction(result):
    return bool(
        result.get("pair")
        and result.get("side")
        and result.get("entry")
        and result.get("stop_loss")
        and result.get("execution_targets")
        and not result.get("futures_mentioned")
    )
