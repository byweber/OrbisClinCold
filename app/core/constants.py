"""Constantes do domínio OrbisClin Cold."""
from enum import Enum


class Role(str, Enum):
    ADMIN    = "ADMIN"
    OPERADOR = "OPERADOR"
    VIEWER   = "VIEWER"


class Protocolo(str, Enum):
    MODBUS = "MODBUS"
    MQTT   = "MQTT"
    HTTP   = "HTTP"


PROTOCOLOS = [p.value for p in Protocolo]


class TipoEquipamento(str, Enum):
    GELADEIRA   = "GELADEIRA"
    FREEZER     = "FREEZER"
    CAMARA_FRIA = "CAMARA_FRIA"
    ESTUFA      = "ESTUFA"
    INCUBADORA  = "INCUBADORA"
    BANHO_MARIA = "BANHO_MARIA"


TIPOS_EQUIPAMENTO = [t.value for t in TipoEquipamento]


class TipoAlerta(str, Enum):
    TEMP_ALTA  = "TEMP_ALTA"
    TEMP_BAIXA = "TEMP_BAIXA"
    UMID_ALTA  = "UMID_ALTA"
    UMID_BAIXA = "UMID_BAIXA"
    OFFLINE    = "OFFLINE"


class NivelEscalonamento(int, Enum):
    IMEDIATO = 0
    SEGUNDO  = 1
    GERENCIA = 2
    ADMIN    = 3


ESCALONAMENTO_MINUTOS = {
    NivelEscalonamento.IMEDIATO: 0,
    NivelEscalonamento.SEGUNDO:  5,
    NivelEscalonamento.GERENCIA: 15,
    NivelEscalonamento.ADMIN:    30,
}

# Ranges padrão RDC 430/2020 ANVISA
RANGES_PADRAO: dict[str, dict] = {
    TipoEquipamento.GELADEIRA.value:   {"temp_min":  2.0, "temp_max":  8.0, "umid_min": 40.0, "umid_max": 80.0},
    TipoEquipamento.FREEZER.value:     {"temp_min": -25.0,"temp_max": -15.0,"umid_min": None, "umid_max": None},
    TipoEquipamento.CAMARA_FRIA.value: {"temp_min":  2.0, "temp_max":  8.0, "umid_min": 40.0, "umid_max": 80.0},
    TipoEquipamento.ESTUFA.value:      {"temp_min": 35.0, "temp_max": 37.0, "umid_min": None, "umid_max": None},
    TipoEquipamento.INCUBADORA.value:  {"temp_min": 35.0, "temp_max": 37.5, "umid_min": 50.0, "umid_max": 95.0},
    TipoEquipamento.BANHO_MARIA.value: {"temp_min": 36.0, "temp_max": 38.0, "umid_min": None, "umid_max": None},
}

CONFIG_JSON_DEFAULTS: dict[str, dict] = {
    Protocolo.MODBUS.value: {"slave_id": 1, "reg_temp": 16, "reg_umid": 17, "temp_scale": 0.1, "umid_scale": 0.1},
    Protocolo.MQTT.value:   {"topic": "cold/setor/equipamento", "field_temp": "temperature", "field_umid": "humidity"},
    Protocolo.HTTP.value:   {"url": "http://sensor.local/api/data", "field_temp": "data.temp", "field_umid": "data.humidity"},
}


class AcaoAudit(str, Enum):
    LOGIN              = "LOGIN"
    LOGOUT             = "LOGOUT"
    CREATE             = "CREATE"
    UPDATE             = "UPDATE"
    DELETE             = "DELETE"
    DEACTIVATE         = "DEACTIVATE"
    ALERTA_RECONHECIDO = "ALERTA_RECONHECIDO"
    SENSOR_TEST        = "SENSOR_TEST"
    PASSWORD_CHANGE    = "PASSWORD_CHANGE"
    TOTP_ENABLE        = "TOTP_ENABLE"
    TOTP_DISABLE       = "TOTP_DISABLE"
    REPORT_GENERATE    = "REPORT_GENERATE"
    EXPORT_CSV         = "EXPORT_CSV"
