"""« Tout télécharger » : toutes les données de la personne dans un zip.

En ligne, son dossier (``data/users/<e-mail>``) ; en local, ``data/``. Les fichiers de
compilation (dossiers ``build/``), refaits à la demande, n'y sont pas.
"""

import tempfile
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.paths import user_root

router = APIRouter(prefix="/api/export", tags=["export"])

SKIPPED = {"build", "users"}
# Les clés d'API chiffrées de la personne : elles restent sur le serveur.
SKIPPED_FILES = {"cles.json"}


def build_zip(root: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        if not root.is_dir():
            return
        for file in sorted(root.rglob("*")):
            relative = file.relative_to(root)
            if (
                file.is_symlink()
                or not file.is_file()
                or SKIPPED & set(relative.parts)
                or file.name in SKIPPED_FILES
            ):
                continue
            archive.write(file, Path("cv-builder-pro") / relative)


@router.get("")
def export() -> FileResponse:
    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    target = Path(handle.name)
    build_zip(user_root(), target)
    return FileResponse(
        target,
        media_type="application/zip",
        filename=f"cv-builder-pro-{date.today().isoformat()}.zip",
        background=BackgroundTask(target.unlink, missing_ok=True),
    )
