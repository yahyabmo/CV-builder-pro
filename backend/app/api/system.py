"""La vérification de la machine : LaTeX, ses paquets et les outils PDF."""

from fastapi import APIRouter

from app.services import machine

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/check")
def check() -> machine.Machine:
    return machine.check()
