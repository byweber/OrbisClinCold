"""7 modelos SQLAlchemy do OrbisClin Cold."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Setor(Base):
    __tablename__ = "setores"
    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    nome:       Mapped[str]           = mapped_column(String(120), unique=True, nullable=False)
    descricao:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active:  Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=_now, nullable=True)

    equipamentos: Mapped[list[Equipamento]] = relationship("Equipamento", back_populates="setor", lazy="select")
    usuarios:     Mapped[list[Usuario]]     = relationship("Usuario",     back_populates="setor", lazy="select")


class Equipamento(Base):
    __tablename__ = "equipamentos"
    id:                Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    setor_id:          Mapped[int]            = mapped_column(Integer, ForeignKey("setores.id", ondelete="RESTRICT"), nullable=False, index=True)
    nome:              Mapped[str]            = mapped_column(String(120), nullable=False)
    tipo:              Mapped[str]            = mapped_column(String(40),  nullable=False)
    patrimonio:        Mapped[Optional[str]]  = mapped_column(String(60),  nullable=True)
    fabricante:        Mapped[Optional[str]]  = mapped_column(String(120), nullable=True)
    modelo:            Mapped[Optional[str]]  = mapped_column(String(120), nullable=True)
    temp_min:          Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    temp_max:          Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    umid_min:          Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    umid_max:          Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    is_active:         Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    motivo_inativacao: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at:        Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at:        Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=_now, nullable=True)

    setor:    Mapped[Setor]          = relationship("Setor", back_populates="equipamentos")
    sensores: Mapped[list[Sensor]]   = relationship("Sensor",  back_populates="equipamento", lazy="select")
    alertas:  Mapped[list[Alerta]]   = relationship("Alerta",  back_populates="equipamento", lazy="select")
    __table_args__ = (Index("ix_equip_setor_active", "setor_id", "is_active"),)


class Sensor(Base):
    __tablename__ = "sensores"
    id:             Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    equipamento_id: Mapped[int]            = mapped_column(Integer, ForeignKey("equipamentos.id", ondelete="RESTRICT"), nullable=False, index=True)
    nome:           Mapped[Optional[str]]  = mapped_column(String(80),  nullable=True)
    protocolo:      Mapped[str]            = mapped_column(String(20),  nullable=False)
    endereco:       Mapped[str]            = mapped_column(String(255), nullable=False)
    config_json:    Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active:      Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    ultimo_sinal:   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=_now, nullable=True)

    equipamento: Mapped[Equipamento]  = relationship("Equipamento", back_populates="sensores")
    leituras:    Mapped[list[Leitura]]= relationship("Leitura", back_populates="sensor", lazy="select")
    alertas:     Mapped[list[Alerta]] = relationship("Alerta",  back_populates="sensor", lazy="select")


class Leitura(Base):
    __tablename__ = "leituras"
    id:          Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    sensor_id:   Mapped[int]            = mapped_column(Integer, ForeignKey("sensores.id", ondelete="CASCADE"), nullable=False)
    temperatura: Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    umidade:     Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    timestamp:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    sensor: Mapped[Sensor] = relationship("Sensor", back_populates="leituras")
    __table_args__ = (Index("ix_leitura_sensor_ts", "sensor_id", "timestamp"),)


class Alerta(Base):
    __tablename__ = "alertas"
    id:                       Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    sensor_id:                Mapped[int]            = mapped_column(Integer, ForeignKey("sensores.id", ondelete="CASCADE"), nullable=False, index=True)
    equipamento_id:           Mapped[int]            = mapped_column(Integer, ForeignKey("equipamentos.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo:                     Mapped[str]            = mapped_column(String(20), nullable=False)
    valor_registrado:         Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    valor_limite:             Mapped[Optional[float]]= mapped_column(Float, nullable=True)
    inicio_at:                Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    fim_at:                   Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reconhecido_por:          Mapped[Optional[str]]  = mapped_column(String(80), nullable=True)
    reconhecido_at:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    nivel_escalonamento:      Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    proxima_escalonamento_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    sensor:      Mapped[Sensor]      = relationship("Sensor",      back_populates="alertas")
    equipamento: Mapped[Equipamento] = relationship("Equipamento", back_populates="alertas")
    __table_args__ = (Index("ix_alerta_sensor_tipo_ativo", "sensor_id", "tipo", "fim_at"),)


class Usuario(Base):
    __tablename__ = "usuarios"
    id:                   Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    username:             Mapped[str]            = mapped_column(String(80),  unique=True, nullable=False, index=True)
    hashed_password:      Mapped[str]            = mapped_column(String(255), nullable=False)
    nome_completo:        Mapped[Optional[str]]  = mapped_column(String(150), nullable=True)
    email:                Mapped[Optional[str]]  = mapped_column(String(200), nullable=True)
    role:                 Mapped[str]            = mapped_column(String(20),  nullable=False, default="VIEWER")
    setor_id:             Mapped[Optional[int]]  = mapped_column(Integer, ForeignKey("setores.id", ondelete="SET NULL"), nullable=True)
    must_change_password: Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    is_active:            Mapped[bool]           = mapped_column(Boolean, default=True, nullable=False)
    totp_enabled:         Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    totp_secret:          Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    created_at:           Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=_now, nullable=True)
    last_login:           Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    setor: Mapped[Optional[Setor]] = relationship("Setor", back_populates="usuarios")


class AuditLog(Base):
    """APPEND-ONLY — nunca atualizar ou deletar."""
    __tablename__ = "audit_logs"
    id:         Mapped[int]            = mapped_column(Integer, primary_key=True, index=True)
    username:   Mapped[str]            = mapped_column(String(80),  nullable=False)
    action:     Mapped[str]            = mapped_column(String(50),  nullable=False)
    target:     Mapped[Optional[str]]  = mapped_column(String(120), nullable=True)
    details:    Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]]  = mapped_column(String(45),  nullable=True)
    created_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    __table_args__ = (
        Index("ix_audit_username_ts", "username", "created_at"),
        Index("ix_audit_action_ts",   "action",   "created_at"),
    )
