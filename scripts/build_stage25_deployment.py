"""Assemble one exact-source, hash-pinned installer bundle for the S25 runner."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"
ZIP = OUT / "CryptoSniper-Stage25-v0.24.0rc2.zip"
INSTALLER = OUT / "cryptosniper-stage25-run.sh"
SOURCE_INSTALLER = "scripts/cryptosniper-stage24-rebuild-run.sh"
MAPPING_SOURCE = ".github/workflows/release-stage24-rebuild.yml"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    pin = git("rev-parse", "HEAD")
    if pin != os.environ["GITHUB_SHA"]:
        raise SystemExit("Checkout does not match the workflow SHA.")
    OUT.mkdir(exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", "--prefix=CryptoSniper/", "-o", str(ZIP), pin],
        cwd=ROOT,
        check=True,
    )
    archive_hash = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    mapping_text = git("show", f"{pin}:{MAPPING_SOURCE}")
    blob_paths = dict(re.findall(r"'(__BLOB_[A-Z0-9_]+__)': blob\('([^']+)'\)", mapping_text))
    if len(blob_paths) < 40:
        raise SystemExit("Incomplete trusted-blob mapping in release workflow.")
    substitutions = {
        "__SOURCE_COMMIT__": pin,
        "__STAGE24_ARCHIVE_SHA256__": archive_hash,
        **{key: git("rev-parse", f"{pin}:{path}") for key, path in blob_paths.items()},
    }
    installer = git("show", f"{pin}:{SOURCE_INSTALLER}")
    for token, value in substitutions.items():
        if token not in installer:
            raise SystemExit(f"Installer missing expected token: {token}")
        installer = installer.replace(token, value)
    if re.search(r"__[A-Z0-9_]+__", installer):
        raise SystemExit("Unresolved installer token.")
    INSTALLER.write_text(installer + "\n")
    INSTALLER.chmod(0o700)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ZIP, INSTALLER)}
    (OUT / "SHA256SUMS.txt").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in hashes.items())
    )
    (OUT / "manifest.json").write_text(
        json.dumps({"source_commit": pin, "sha256": hashes}, sort_keys=True, indent=2) + "\n"
    )
    print(f"Prepared exact-source deployment bundle for {pin}")


if __name__ == "__main__":
    main()
