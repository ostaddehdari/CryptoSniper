"""Small deterministic release gate; dependency CVEs are checked separately in CI."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "critical_private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "critical_aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "high_live_enabled": re.compile(r"^LIVE_TRADING_ENABLED\s*=\s*True\s*$", re.MULTILINE),
}
SKIP_PREFIXES = ("release-assets/",)


def tracked_files():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode(
        errors="surrogateescape"
    )
    return [
        ROOT / name for name in names.split("\0") if name and not name.startswith(SKIP_PREFIXES)
    ]


def scan():
    findings = []
    for path in tracked_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = str(path.relative_to(ROOT))
        for code, pattern in PATTERNS.items():
            if pattern.search(content):
                severity = code.split("_", 1)[0]
                findings.append({"severity": severity, "code": code, "path": relative})
    return findings


if __name__ == "__main__":
    result = scan()
    print(json.dumps({"findings": result}, sort_keys=True))
    if any(item["severity"] in {"critical", "high"} for item in result):
        raise SystemExit(1)
