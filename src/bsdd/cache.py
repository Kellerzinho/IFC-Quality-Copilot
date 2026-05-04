"""Cache persistente simples para artefatos resolvidos do bSDD."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BSDDCacheStore:
    """Armazena cache em JSON por namespace, sem dependencia externa."""

    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self._data: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def get(self, namespace: str, key: str) -> Any | None:
        if not self.enabled:
            return None
        self._ensure_loaded()
        return self._data.get(namespace, {}).get(key)

    def set(self, namespace: str, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._ensure_loaded()
        self._data.setdefault(namespace, {})[key] = value
        self._flush()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            self._data = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}
            return
        self._data = payload if isinstance(payload, dict) else {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
