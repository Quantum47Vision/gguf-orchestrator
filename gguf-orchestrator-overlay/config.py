"""
config.py — Loads config.yaml and exposes all settings as a typed object.
The PostgreSQL password is read from .env (never from config.yaml).
Import `cfg` anywhere in the project to access settings.
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")


def _load_raw() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD is missing. Copy .env.example to .env and set it."
        )
    raw["database"]["password"] = password
    return raw


def load_config():
    return _load_raw()


# ── Singleton config object ──────────────────────────────────
_raw = _load_raw()


class _Namespace:
    """Simple attribute-access wrapper around a dict."""
    def __init__(self, d: dict):
        for k, v in d.items():
            setattr(self, k, _Namespace(v) if isinstance(v, dict) else v)

    def get(self, key, default=None):
        return getattr(self, key, default)


cfg = _Namespace(_raw)


# ── Convenience helpers ──────────────────────────────────────

def db_url() -> str:
    """Sync psycopg2 connection string."""
    d = _raw["database"]
    return f"postgresql://{d['user']}:{d['password']}@{d['host']}:{d['port']}/{d['name']}"


def async_db_url() -> str:
    """Async asyncpg connection string."""
    return db_url()


def model_path(role: str) -> str:
    """Get the .gguf file path for a model role: 'router', 'brain', 'code'."""
    return _raw["models"][role]["path"]


def model_cfg(role: str) -> dict:
    """Get full model config dict for a role."""
    return _raw["models"][role]


def rag_cfg() -> dict:
    return _raw["rag"]


def server_cfg() -> dict:
    return _raw["server"]
