"""Build the cumulative release from an exact Git commit and its freshly built React assets."""

import ast
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP_NAME = "CryptoSniper-Stage30-React-v0.30.0rc1-r1.zip"
INSTALLER = "cryptosniper-stage30-react-run.sh"
TAG = "stage30-react-v0.30.0rc1-deploy-r1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build():
    pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(["git", "archive", "--format=zip", pin], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        files = {
            info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()
        }
    for name in ("app.js", "app.css", "index.html"):
        path = "backend/static/react/" + name
        files[path] = (ROOT / path).read_bytes()
        if not files[path]:
            raise SystemExit("Missing built asset: " + path)
    out = ROOT / ".runtime" / "stage30-release"
    out.mkdir(parents=True, exist_ok=True)
    package = out / ZIP_NAME
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("CryptoSniper/" + name, date_time=(2026, 10, 26, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    template = files["scripts/" + INSTALLER].decode()
    match = re.search(r"trusted_blobs = (\{.*?\n\})", template, re.S)
    if not match:
        raise SystemExit("Installer source pin map is missing")
    replacements = {
        "__SOURCE_COMMIT__": pin,
        "__STAGE30_ARCHIVE_SHA256__": digest(package.read_bytes()),
        "__REACT_APP_JS_SHA256__": digest(files["backend/static/react/app.js"]),
        "__REACT_APP_CSS_SHA256__": digest(files["backend/static/react/app.css"]),
    }
    for path, token in ast.literal_eval(match[1]).items():
        data = files[path]
        replacements[token] = hashlib.sha1(
            f"blob {len(data)}\0".encode() + data, usedforsecurity=False
        ).hexdigest()
    for token, value in replacements.items():
        template = template.replace(token, value)
    if re.search(r"__[A-Z0-9_]+__", template):
        raise SystemExit("Unexpanded installer token")
    installer = out / INSTALLER
    installer.write_text(template)
    subprocess.run(["bash", "-n", str(installer)], check=True)
    checked = subprocess.check_output(
        ["bash", str(installer), "--check", str(package)], text=True, cwd=out
    )
    (out / "runlog.txt").write_text(f"SOURCE={pin}\nUI=approved React base\n" + checked)
    names = [ZIP_NAME, INSTALLER, "runlog.txt"]
    hashes = {name: digest((out / name).read_bytes()) for name in names}
    (out / "SHA256SUMS.txt").write_text("".join(f"{hashes[n]}  {n}\n" for n in names))
    (out / "release.json").write_text(
        json.dumps({"source": pin, "tag": TAG, "sha256": hashes}, indent=2) + "\n"
    )
    print(checked)
    print(json.dumps({"source": pin, "output": str(out), "sha256": hashes}, indent=2))


if __name__ == "__main__":
    build()
