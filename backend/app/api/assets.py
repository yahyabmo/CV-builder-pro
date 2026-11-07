"""Routes des ressources de style : polices et thèmes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import fonts
from app.models.style import CVStyle
from app.storage import themes

router = APIRouter(prefix="/api", tags=["style"])


class FontOut(BaseModel):
    id: str
    name: str
    category: str


@router.get("/fonts")
def list_fonts() -> list[FontOut]:
    return [FontOut(id=f.id, name=f.name, category=f.category) for f in fonts.families().values()]


@router.get("/fonts/{font_id}/{style}")
def font_file(font_id: str, style: str) -> FileResponse:
    """Le fichier d'une police, pour l'aperçu des polices dans l'interface."""
    try:
        family = fonts.get(font_id)
    except fonts.UnknownFont:
        raise HTTPException(404, "Police inconnue") from None
    if style not in fonts.STYLES:
        raise HTTPException(404, "Style inconnu")
    return FileResponse(
        family.file(style), media_type="font/ttf", headers={"Cache-Control": "max-age=86400"}
    )


class ThemeOut(BaseModel):
    slug: str
    name: str
    style: CVStyle


class ThemeIn(BaseModel):
    name: str
    style: CVStyle


@router.get("/themes")
def list_themes() -> list[ThemeOut]:
    return [ThemeOut(slug=slug, name=t.name, style=t.style) for slug, t in themes.list_all()]


@router.post("/themes")
def create_theme(theme: ThemeIn) -> ThemeOut:
    if not theme.name.strip():
        raise HTTPException(422, "Donne un nom au thème.")
    slug, saved = themes.create(theme.name, theme.style)
    return ThemeOut(slug=slug, name=saved.name, style=saved.style)


@router.delete("/themes/{slug}")
def delete_theme(slug: str) -> dict[str, bool]:
    try:
        themes.delete(slug)
    except themes.UnknownTheme:
        raise HTTPException(404, "Thème introuvable") from None
    return {"deleted": True}
