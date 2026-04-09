"""Adapter HTTP REST. config: {url, field_temp, field_umid, method, headers, auth_bearer}."""
from __future__ import annotations
import logging
from typing import Optional
from app.core.adapters.base import LeituraRaw, SensorAdapter

logger = logging.getLogger(__name__)


def _get(data: dict, path: str) -> Optional[float]:
    val = data
    for k in path.split("."):
        val = val.get(k) if isinstance(val, dict) else None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


class HttpAdapter(SensorAdapter):

    def read(self) -> LeituraRaw:
        try:
            import httpx
        except ImportError:
            return LeituraRaw(None, None, False, "httpx não instalado")

        url        = self.config.get("url", self.endereco)
        field_temp = self.config.get("field_temp", "temperature")
        field_umid = self.config.get("field_umid")
        method     = self.config.get("method", "GET").upper()
        headers    = dict(self.config.get("headers", {}))
        bearer     = self.config.get("auth_bearer")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        try:
            with httpx.Client(timeout=5) as client:
                resp = client.request(method, url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            temperatura = _get(data, field_temp)
            umidade     = _get(data, field_umid) if field_umid else None
            if temperatura is None:
                return LeituraRaw(None, None, False, f"Campo '{field_temp}' não encontrado")
            return LeituraRaw(temperatura=temperatura, umidade=umidade, sucesso=True)
        except Exception as exc:
            return LeituraRaw(None, None, False, str(exc))
