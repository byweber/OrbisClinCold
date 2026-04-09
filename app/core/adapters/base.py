from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LeituraRaw:
    temperatura: Optional[float]
    umidade:     Optional[float]
    sucesso:     bool
    erro:        Optional[str] = None


class SensorAdapter(ABC):
    def __init__(self, endereco: str, config: dict):
        self.endereco = endereco
        self.config   = config or {}

    @abstractmethod
    def read(self) -> LeituraRaw: ...

    def test_connection(self) -> tuple[bool, str]:
        try:
            r = self.read()
            return (True, "Conexão OK") if r.sucesso else (False, r.erro or "Falha")
        except Exception as exc:
            return False, str(exc)


def get_adapter(protocolo: str, endereco: str, config: dict) -> SensorAdapter:
    from app.core.constants import Protocolo
    p = protocolo.upper()
    if p == Protocolo.MODBUS.value:
        from app.core.adapters.modbus import ModbusAdapter
        return ModbusAdapter(endereco, config)
    if p == Protocolo.MQTT.value:
        from app.core.adapters.mqtt import MqttAdapter
        return MqttAdapter(endereco, config)
    if p == Protocolo.HTTP.value:
        from app.core.adapters.http import HttpAdapter
        return HttpAdapter(endereco, config)
    raise ValueError(f"Protocolo não suportado: {protocolo}")
