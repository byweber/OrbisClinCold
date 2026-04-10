# app/core/models.py
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    nome_completo = Column(String(150), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="VIEWER")
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    setores = relationship("Setor", back_populates="responsavel")
    alertas_resolvidos = relationship("Alerta", back_populates="usuario")
    logs_audit = relationship("AuditLog", back_populates="usuario")

class Setor(Base):
    __tablename__ = "setores"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    descricao = Column(Text)
    localizacao = Column(String(100))
    responsavel_id = Column(Integer, ForeignKey("usuarios.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    responsavel = relationship("Usuario", back_populates="setores")
    equipamentos = relationship("Equipamento", back_populates="setor", cascade="all, delete-orphan")

class Equipamento(Base):
    __tablename__ = "equipamentos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    modelo = Column(String(50))
    fabricante = Column(String(50))
    numero_serie = Column(String(50))
    setor_id = Column(Integer, ForeignKey("setores.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    setor = relationship("Setor", back_populates="equipamentos")
    sensores = relationship("Sensor", back_populates="equipamento", cascade="all, delete-orphan")

class Sensor(Base):
    __tablename__ = "sensores"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)
    unidade = Column(String(10))
    endereco = Column(String(255))
    protocolo = Column(String(20))
    equipamento_id = Column(Integer, ForeignKey("equipamentos.id"))
    alerta_min = Column(Float, nullable=True)
    alerta_max = Column(Float, nullable=True)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipamento = relationship("Equipamento", back_populates="sensores")
    leituras = relationship("Leitura", back_populates="sensor", cascade="all, delete-orphan")
    alertas = relationship("Alerta", back_populates="sensor", cascade="all, delete-orphan")

class Leitura(Base):
    __tablename__ = "leituras"
    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensores.id"))
    valor = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    sensor = relationship("Sensor", back_populates="leituras")

class Alerta(Base):
    __tablename__ = "alertas"
    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensores.id"))
    tipo = Column(String(50))
    valor = Column(Float)
    limite = Column(Float)
    mensagem = Column(String(255))
    timestamp = Column(DateTime, default=datetime.utcnow)
    resolvido = Column(Boolean, default=False)
    resolvido_em = Column(DateTime, nullable=True)
    resolvido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    sensor = relationship("Sensor", back_populates="alertas")
    usuario = relationship("Usuario", back_populates="alertas_resolvidos")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    acao = Column(String(50))
    entidade = Column(String(50))
    entidade_id = Column(Integer, nullable=True)
    detalhes = Column(Text)
    ip_address = Column(String(45))
    timestamp = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="logs_audit")