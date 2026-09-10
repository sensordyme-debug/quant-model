"""Load API keys from live/secrets.env (gitignored) into a dict / os.environ.

    from secrets import keys
    k = keys()                  # {"ALPACA_API_KEY": ..., ...}
    keys(export=True)           # also sets os.environ so client libraries pick them up

Never print or log the values. Keys the file does not contain are simply absent.
"""
from __future__ import annotations

import os
from pathlib import Path

SECRETS = Path(__file__).resolve().parents[1] / "live" / "secrets.env"


def keys(export: bool = False) -> dict[str, str]:
    out: dict[str, str] = {}
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "THETADATA_API_KEY", "FMP_API_KEY",
              "POLYGON_API_KEY", "FINNHUB_API_KEY", "NASDAQ_DATA_LINK_API_KEY", "TELEGRAM_BOT_TOKEN"):
        if k in os.environ and k not in out:
            out[k] = os.environ[k]
    if export:
        for k, v in out.items():
            os.environ.setdefault(k, v)
    return out


def require(*names: str) -> dict[str, str]:
    k = keys()
    missing = [n for n in names if not k.get(n)]
    if missing:
        raise SystemExit(f"missing API keys in {SECRETS}: {missing}")
    return k
