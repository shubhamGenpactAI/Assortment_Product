"""
settings.py — Consolidated .env loader shared by db.py, agent_llm.py and
llm_service.py (previously three byte-identical private copies).
"""
import os
from pathlib import Path

# Project root = Assortment/  (config/ -> Backend/ -> Assortment/, three levels up)
_ROOT = Path(__file__).resolve().parent.parent.parent


def load_env() -> None:
    """Load .env into os.environ; only sets keys not already present."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val
