# app/routers/dashboard.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload
from app.core.database import get_db
from app.core.models import Setor, Equipamento, Sensor, Leitura, Alerta, Usuario
from app.core.security import get_current_active_user
from sqlalchemy import func

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    setores = db.query(Setor).options(
        selectinload(Setor.equipamentos).selectinload(Equipamento.sensores)
    ).all()
    alertas_ativos = db.query(func.count(Alerta.id)).filter(Alerta.resolvido == False).scalar()
    total_setores = len(setores)
    total_equipamentos = sum(len(s.equipamentos) for s in setores)
    total_sensores = sum(len(e.sensores) for s in setores for e in s.equipamentos)
    ultimas_leituras = {}
    for setor in setores:
        for equip in setor.equipamentos:
            for sensor in equip.sensores:
                ultima = db.query(Leitura).filter(Leitura.sensor_id == sensor.id).order_by(Leitura.timestamp.desc()).first()
                ultimas_leituras[sensor.id] = ultima
    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "current_user": current_user,
            "setores": setores,
            "alertas_ativos": alertas_ativos,
            "total_setores": total_setores,
            "total_equipamentos": total_equipamentos,
            "total_sensores": total_sensores,
            "ultimas_leituras": ultimas_leituras,
        }
    )