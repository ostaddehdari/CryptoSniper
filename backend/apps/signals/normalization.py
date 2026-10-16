"""Stage07 deterministic, lossless-input normalization. NEVER write output over RawSignal."""
import re
import unicodedata

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ـ": ""})
SPACE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")
MULTI_SPACE = re.compile(r"[ \t]{2,}")


def normalize(raw: str) -> str:
    """Return a search-friendly copy; original incoming text is never changed."""
    if not isinstance(raw, str):
        raise TypeError("Signal text must be a string")
    text = unicodedata.normalize("NFKC", raw).translate(DIGITS).translate(ARABIC)
    text = SPACE.sub(" ", text).replace("\r\n", "\n").replace("\r", "\n")
    text = EMOJI.sub(" ", text)
    text = MULTI_SPACE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()
