"""Adapter Modbus TCP — HF5111B (RS485→Ethernet). endereco: "IP:502"."""
from __future__ import annotations
import logging
from typing import Optional
from app.core.adapters.base import LeituraRaw, SensorAdapter

logger = logging.getLogger(__name__)


class ModbusAdapter(SensorAdapter):

    def _host_port(self) -> tuple[str, int]:
        p = self.endereco.rsplit(":", 1)
        return p[0], int(p[1]) if len(p) > 1 else 502

    def read(self) -> LeituraRaw:
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError:
            return LeituraRaw(None, None, False, "pymodbus não instalado")

        host, port   = self._host_port()
        slave_id     = self.config.get("slave_id",   1)
        reg_temp     = self.config.get("reg_temp",  16)
        reg_umid     = self.config.get("reg_umid")
        temp_scale   = self.config.get("temp_scale", 0.1)
        umid_scale   = self.config.get("umid_scale", 0.1)

        client = ModbusTcpClient(host=host, port=port, timeout=3)
        try:
            if not client.connect():
                return LeituraRaw(None, None, False, f"Sem conexão em {host}:{port}")
            res = client.read_holding_registers(address=reg_temp, count=1, slave=slave_id)
            if res.isError():
                return LeituraRaw(None, None, False, f"Erro reg_temp={reg_temp}: {res}")
            temperatura = res.registers[0] * temp_scale
            umidade: Optional[float] = None
            if reg_umid is not None:
                ru = client.read_holding_registers(address=reg_umid, count=1, slave=slave_id)
                if not ru.isError():
                    umidade = ru.registers[0] * umid_scale
            return LeituraRaw(temperatura=temperatura, umidade=umidade, sucesso=True)
        except Exception as exc:
            return LeituraRaw(None, None, False, str(exc))
        finally:
            client.close()

    def test_connection(self) -> tuple[bool, str]:
        r = self.read()
        if r.sucesso:
            msg = f"Modbus OK | temp={r.temperatura:.1f}°C"
            if r.umidade is not None:
                msg += f" | umid={r.umidade:.1f}%"
            return True, msg
        return False, r.erro or "Falha"
