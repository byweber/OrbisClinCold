"""Adapter MQTT. config: {topic, field_temp, field_umid, broker_host, broker_port}."""
from __future__ import annotations
import json, logging, threading
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


class MqttAdapter(SensorAdapter):

    def read(self) -> LeituraRaw:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return LeituraRaw(None, None, False, "paho-mqtt não instalado")

        topic       = self.config.get("topic", "")
        field_temp  = self.config.get("field_temp", "temperature")
        field_umid  = self.config.get("field_umid")
        broker_host = self.config.get("broker_host", self.endereco)
        broker_port = int(self.config.get("broker_port", 1883))

        received: dict = {}
        ev = threading.Event()

        def on_message(_c, _u, msg):
            try:
                received["data"] = json.loads(msg.payload.decode())
            except Exception:
                received["raw"] = msg.payload.decode()
            ev.set()

        client = mqtt.Client()
        client.on_message = on_message
        try:
            client.connect(broker_host, broker_port, keepalive=10)
            client.subscribe(topic)
            client.loop_start()
            if not ev.wait(timeout=5):
                return LeituraRaw(None, None, False, f"Timeout em '{topic}'")
            data        = received.get("data", {})
            temperatura = _get(data, field_temp)
            umidade     = _get(data, field_umid) if field_umid else None
            if temperatura is None:
                return LeituraRaw(None, None, False, f"Campo '{field_temp}' não encontrado")
            return LeituraRaw(temperatura=temperatura, umidade=umidade, sucesso=True)
        except Exception as exc:
            return LeituraRaw(None, None, False, str(exc))
        finally:
            client.loop_stop()
            client.disconnect()
