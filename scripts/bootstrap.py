"""Create a private development .env without printing or committing its secret."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    raise SystemExit(".env already exists; it has not been overwritten.")
text = (root / ".env.example").read_text()
password = secrets.token_urlsafe(24)
text = text.replace("DJANGO_SECRET_KEY=\n", "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(64) + "\n")
text = text.replace("CHANGE_ME", password)
text += "\nPOSTGRES_PASSWORD=" + password + "\n"
path.write_text(text)
path.chmod(0o600)
print("Private development .env created. Review host/port settings before starting services.")
