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


def template_matches(text, template):
    if not isinstance(template, dict):
        return False
    required = template.get("required_markers", [])
    excluded = template.get("exclude_markers", [])
    if not isinstance(required, list) or not isinstance(excluded, list):
        raise ValidationError("markerهای قالب باید فهرست باشند.")
    if len(required) > 10 or len(excluded) > 10:
        raise ValidationError("تعداد markerهای قالب بیش از حد است.")
    folded = text.casefold()
    required = [str(value).strip().casefold() for value in required]
    excluded = [str(value).strip().casefold() for value in excluded]
    if any(not value or len(value) > 80 for value in required + excluded):
        raise ValidationError("marker خالی یا بیش از حد طولانی است.")
    return all(value in folded for value in required) and not any(
        value in folded for value in excluded
    )


def select_channel_template(text, templates, fallback=None):
    """Return the first priority-ordered matching template and deterministic extraction."""

    for template in templates:
        definition = template.definition
        if not template_matches(text, definition):
            continue
        parsed = apply_channel_template(text, definition)
        return template, parsed
    if fallback:
        return None, apply_channel_template(text, fallback)
    return None, extract(text)


def complete_extraction(result):
    return bool(
        result.get("pair")
        and result.get("side")
        and result.get("entry")
        and result.get("stop_loss")
        and result.get("execution_targets")
        and not result.get("futures_mentioned")
    )
