"""L'image de signature de la personne : déposée une fois, elle sert à toutes ses lettres."""

import asyncio

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import signature

router = APIRouter(prefix="/api/signature", tags=["signature"])


class SignatureOut(BaseModel):
    present: bool
    size: signature.Size
    # Change à chaque nouvelle image : l'aperçu la recharge.
    version: int | None


class SizeIn(BaseModel):
    size: signature.Size


def _state() -> SignatureOut:
    return SignatureOut(
        present=signature.exists(), size=signature.size(), version=signature.version()
    )


@router.get("")
def get_signature() -> SignatureOut:
    return _state()


@router.get("/image")
def get_image() -> FileResponse:
    if not signature.exists():
        raise HTTPException(404, "Pas d'image de signature.")
    return FileResponse(
        signature.path(), media_type="image/png", headers={"Cache-Control": "no-store"}
    )


@router.put("")
async def put_signature(file: UploadFile) -> SignatureOut:
    data = await file.read(signature.MAX_BYTES + 1)
    try:
        await asyncio.to_thread(signature.store, data)
    except signature.BadImage as error:
        raise HTTPException(422, str(error)) from None
    return _state()


@router.patch("")
def patch_signature(body: SizeIn) -> SignatureOut:
    signature.set_size(body.size)
    return _state()


@router.delete("")
def delete_signature() -> SignatureOut:
    signature.delete()
    return _state()
