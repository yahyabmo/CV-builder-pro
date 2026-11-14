"""La police de l'appli pour chaque police du PDF (lecture d'un scan, style repéré).

1. La même, si l'appli l'a déjà (dossier fonts/ ou polices déjà téléchargées).
1 bis. La même, installée sur la machine (fontconfig), en fichiers statiques.
2. La même, téléchargée de Google Fonts (familles libres : Montserrat, Poppins, Roboto…),
   en fichiers séparés par style (XeTeX gère mal les polices variables).
3. Une police aux mêmes largeurs de lettres : les lignes se coupent aux mêmes endroits
   (Arial → Arimo, Times → Tinos, Calibri → Carlito, Cambria → Caladea…).
4. Sinon, la plus proche parmi celles de l'appli.
"""

import json
import re
import shutil
import subprocess
import threading
import unicodedata
from pathlib import Path

import httpx

from app import fonts, paths
from app.services.cv_style import match_font

Badge = str  # « identique », « mêmes largeurs », « proche »

# Polices du système ou payantes → leur équivalent libre aux mêmes largeurs.
METRIC = {
    "arial": "Arimo",
    "arialmt": "Arimo",
    "helvetica": "Arimo",
    "helveticaneue": "Arimo",
    "liberationsans": "Arimo",
    "timesnewroman": "Tinos",
    "timesnewromanps": "Tinos",
    "times": "Tinos",
    "liberationserif": "Tinos",
    "calibri": "Carlito",
    "cambria": "Caladea",
    "couriernew": "Cousine",
    "courier": "Cousine",
    "liberationmono": "Cousine",
    "georgia": "Gelasio",
    "segoeui": "Selawik",
}
# Des noms de PDF qui ne sont pas ceux de Google Fonts.
ALIASES = {
    "ptsans": "PT Sans",
    "ptserif": "PT Serif",
    "opensans": "Open Sans",
    "sourcesanspro": "Source Sans 3",
}

CSS = "https://fonts.googleapis.com/css2"
# Sans navigateur moderne, Google répond par des fichiers TrueType (ni WOFF ni EOT).
OLD_BROWSER = "Wget/1.21"
STYLES = (("Regular", 0, 400), ("Bold", 0, 700), ("Italic", 1, 400), ("BoldItalic", 1, 700))
_lock = threading.Lock()


def _key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def _font_id(name: str) -> str:
    return re.sub(r"[^A-Za-z]", "", name) or "Police"


def _spaced(name: str) -> str:
    """« OpenSans » → « Open Sans » (le nom des familles chez Google)."""
    if _key(name) in ALIASES:
        return ALIASES[_key(name)]
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", " ", name).strip()


def known(name: str) -> str | None:
    available = {_key(f.id): f.id for f in fonts.families().values()}
    available.update({_key(f.name): f.id for f in fonts.families().values()})
    return available.get(_key(name))


def download(name: str, timeout: float = 20) -> str | None:
    """La famille ``name`` de Google Fonts, en quatre fichiers ; son identifiant, ou None."""
    family = _spaced(name)
    font_id = _font_id(family)
    folder = paths.EXTRA_FONTS_DIR / font_id
    with _lock:
        if known(font_id):
            return known(font_id)
        params = {"family": f"{family}:ital,wght@0,400;0,700;1,400;1,700"}
        try:
            with httpx.Client(timeout=timeout, headers={"user-agent": OLD_BROWSER}) as client:
                css = client.get(CSS, params=params)
                if css.status_code == 400:
                    # Pas d'italique ou de gras : on prend ce qui existe.
                    css = client.get(CSS, params={"family": family})
                if css.status_code != 200:
                    return None
                faces = re.findall(
                    r"font-style:\s*(\w+);\s*font-weight:\s*(\d+);.*?src:\s*url\(([^)]+)\)",
                    css.text,
                    re.S,
                )
                if not faces:
                    return None
                files: dict[tuple[int, int], bytes] = {}
                for style, weight, url in faces:
                    answer = client.get(url)
                    if answer.status_code == 200 and answer.content[:4] in (
                        b"\x00\x01\x00\x00",
                        b"true",
                        b"OTTO",
                    ):
                        files[(int(style == "italic"), int(weight))] = answer.content
        except httpx.HTTPError:
            return None
        if not files:
            return None
        regular = files.get((0, 400)) or next(iter(files.values()))
        folder.mkdir(parents=True, exist_ok=True)
        for suffix, italic, weight in STYLES:
            data = (
                files.get((italic, weight))
                or files.get((0, weight))
                or files.get((italic, 400))
                or regular
            )
            (folder / f"{font_id}-{suffix}.ttf").write_bytes(data)
        (folder / "font.json").write_text(
            json.dumps(
                {
                    "name": family,
                    "category": "sans",
                    "prefix": font_id,
                    "license": "OFL-1.1",
                    "source": "Google Fonts",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return known(font_id)


def _match(name: str, style: str) -> tuple[str, str, str] | None:
    """Famille, style et fichier que fontconfig donne pour ``name`` dans ce style."""
    if shutil.which("fc-match") is None:
        return None
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{family}|%{style}|%{file}", f"{name}:style={style}"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = out.split("|")
    if len(parts) != 3:
        return None
    family = parts[0].split(",")[0]
    return family, parts[1], parts[2]


def system(name: str) -> str | None:
    """La famille ``name`` installée sur la machine, recopiée en quatre fichiers statiques
    (une police variable, mal gérée par XeTeX, est laissée de côté)."""
    regular = _match(name, "Regular")
    if regular is None or _key(regular[0]) != _key(name):
        return None
    family = regular[0]
    font_id = _font_id(family)
    with _lock:
        if known(font_id):
            return known(font_id)
        files = {}
        for suffix, style in (
            ("Regular", "Regular"),
            ("Bold", "Bold"),
            ("Italic", "Italic"),
            ("BoldItalic", "Bold Italic"),
        ):
            found = _match(family, style)
            if found is None or _key(found[0]) != _key(family):
                found = regular
            path = found[2]
            if "[" in path or not path.lower().endswith((".ttf", ".otf")):
                return None
            files[suffix] = path
        folder = paths.EXTRA_FONTS_DIR / font_id
        folder.mkdir(parents=True, exist_ok=True)
        for suffix, path in files.items():
            shutil.copyfile(path, folder / f"{font_id}-{suffix}.ttf")
        (folder / "font.json").write_text(
            json.dumps(
                {"name": family, "category": "sans", "prefix": font_id, "source": "système"},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return known(font_id)


# Les polices de TeX Live (Latin Modern) : leurs fichiers OpenType, trouvés par kpsewhich.
TEX_FONTS = {
    "lmroman": "lmroman10",
    "lmsans": "lmsans10",
    "lmmono": "lmmono10",
    "lmromancaps": "lmromancaps10",
}


def texlive(name: str) -> str | None:
    """Latin Modern (les CV faits en LaTeX), recopié de TeX Live en quatre fichiers."""
    stem = TEX_FONTS.get(_key(name))
    if stem is None or shutil.which("kpsewhich") is None:
        return None
    font_id = _font_id(name)
    with _lock:
        manifest = paths.EXTRA_FONTS_DIR / font_id / "font.json"
        current = known(font_id)
        if current and manifest.is_file() and json.loads(manifest.read_text()).get("version") == 2:
            return current
        files = {}
        for suffix, style in (
            ("Regular", "regular"),
            ("Bold", "bold"),
            ("Italic", "italic"),
            ("BoldItalic", "bolditalic"),
        ):
            fallbacks = (f"{stem}-{style}.otf", f"{stem}-oblique.otf", f"{stem}-regular.otf")
            for candidate in fallbacks if "italic" in style else fallbacks[::2]:
                try:
                    found = subprocess.run(
                        ["kpsewhich", candidate], capture_output=True, text=True, timeout=10
                    ).stdout.strip()
                except (OSError, subprocess.TimeoutExpired):
                    found = ""
                if found:
                    files[suffix] = found
                    break
        if len(files) < 4:
            return None
        folder = paths.EXTRA_FONTS_DIR / font_id
        folder.mkdir(parents=True, exist_ok=True)
        # Pas de gras dans la famille (les petites capitales de Latin Modern) : le maigre,
        # renommé en gras, que fontspec épaissit (« FakeBold »).
        fake = files["Bold"] == files["Regular"]
        for suffix, path in files.items():
            # Un OpenType sous le nom attendu (.ttf) : XeTeX et Pillow lisent son contenu.
            target = folder / f"{font_id}-{suffix}.ttf"
            shutil.copyfile(path, target)
            if fake and "Bold" in suffix:
                _rename(target, f"{font_id}-{suffix}")
        (folder / "font.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "category": "serif",
                    "prefix": font_id,
                    "source": "TeX Live",
                    "version": 2,
                    "fake_bold": fake,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return known(font_id)


def _rename(file: Path, postscript: str) -> None:
    """Le nom PostScript d'une police (ce que le PDF montre) : « …-Bold » pour un gras épaissi."""
    from fontTools.ttLib import TTFont

    font = TTFont(str(file))
    for record in font["name"].names:
        if record.nameID in (4, 6):
            record.string = postscript
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames = [postscript]
        cff.topDictIndex[0].FullName = postscript
    font.save(str(file))


def fake_bold(font_id: str) -> bool:
    """La famille n'a pas de vrai gras : son gras est le maigre, à épaissir."""
    try:
        family = fonts.get(font_id)
    except fonts.UnknownFont:
        return False
    manifest = family.folder / "font.json"
    return manifest.is_file() and bool(json.loads(manifest.read_text()).get("fake_bold"))


def resolve(name: str, online: bool = True) -> tuple[str, Badge]:
    """L'identifiant de police de l'appli pour la famille ``name`` du PDF, et son badge."""
    found = known(name) or texlive(name) or system(name)
    if found:
        return found, "identique"
    metric = METRIC.get(_key(name))
    if metric:
        found = known(metric) or (download(metric) if online else None)
        if found:
            return found, "mêmes largeurs"
    if online:
        found = download(name)
        if found:
            return found, "identique"
    return match_font(name)[0], "proche"
