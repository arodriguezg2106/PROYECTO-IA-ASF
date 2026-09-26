"""Cliente mínimo para una instancia local de LanguageTool.

No usa el servicio público y no añade dependencias de ejecución. El transporte
se limita deliberadamente a loopback para evitar que una CRF salga del equipo.
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class LanguageToolDescriptor:
    provider: str = "language_tool"
    status: str = "experimental"
    capabilities: tuple[str, ...] = ("spelling", "grammar", "style")


class LanguageToolProvider:
    """Consulta LanguageTool por HTTP, exclusivamente en la máquina local."""

    descriptor = LanguageToolDescriptor()

    def __init__(self, base_url: str, language: str = "es", timeout_seconds: float = 10.0):
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
            raise ValueError("LanguageTool sólo puede configurarse mediante HTTP en loopback.")
        self.endpoint = base_url.rstrip("/")
        if not self.endpoint.endswith("/check"):
            self.endpoint += "/check"
        self.language = language
        self.timeout_seconds = timeout_seconds

    def check(self, text: str, *, rule_ids: tuple[str, ...] = ()) -> list[dict]:
        fields = {"language": self.language, "text": text}
        if rule_ids:
            fields.update({"enabledRules": ",".join(rule_ids), "enabledOnly": "true"})
        request = Request(
            self.endpoint,
            data=urlencode(fields).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("language_tool_unavailable") from exc
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise RuntimeError("language_tool_invalid_response")
        return [match for match in matches if isinstance(match, dict)]


def _cacheable_match(match: dict) -> dict:
    rule=match.get("rule") or {}; category=rule.get("category") or {}
    return {
        "offset":int(match.get("offset") or 0), "length":int(match.get("length") or 0),
        "message":str(match.get("message") or ""), "shortMessage":str(match.get("shortMessage") or ""),
        "replacements":[{"value":str(item.get("value") or "")} for item in
                        (match.get("replacements") or []) if isinstance(item,dict)],
        "rule":{"id":str(rule.get("id") or "UNKNOWN"),
                "description":str(rule.get("description") or ""),
                "issueType":str(rule.get("issueType") or ""),
                "category":{"id":str(category.get("id") or ""),"name":str(category.get("name") or "")}},
    }


class CachedLanguageToolProvider:
    """Caché por hash que nunca almacena el texto consultado ni su contexto."""

    descriptor = LanguageToolDescriptor()

    def __init__(self, provider: LanguageToolProvider, path: str | Path, *, namespace: str):
        self.provider=provider; self.path=Path(path); self.namespace=namespace
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS checks (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        self.connection.commit(); self.hits=0; self.misses=0

    @property
    def stats(self):
        return {"hits":self.hits,"misses":self.misses,"path":str(self.path),
                "stores_raw_text":False,"namespace":self.namespace}

    def check(self, text: str, *, rule_ids: tuple[str, ...] = ()) -> list[dict]:
        material=json.dumps({"namespace":self.namespace,"endpoint":self.provider.endpoint,
                             "language":self.provider.language,"rules":sorted(rule_ids),
                             "text_sha256":hashlib.sha256(text.encode()).hexdigest()},sort_keys=True)
        key=hashlib.sha256(material.encode()).hexdigest()
        row=self.connection.execute("SELECT payload FROM checks WHERE cache_key=?",(key,)).fetchone()
        if row:
            self.hits+=1; return json.loads(row[0])
        self.misses+=1
        matches=[_cacheable_match(match) for match in self.provider.check(text,rule_ids=rule_ids)]
        self.connection.execute("INSERT OR REPLACE INTO checks VALUES (?,?,?)",
                                (key,json.dumps(matches,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        self.connection.commit()
        return matches
