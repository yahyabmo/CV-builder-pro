"""Le .tex d'un CV cloné (mise en page ancrée, version 2).

Chaque unité inchangée est posée mot à mot, à sa place exacte : chaque mot à son bord
gauche d'origine, ramené à sa largeur d'origine (à 15 % près) si la police de l'appli
n'a pas tout à fait les mêmes largeurs. Une unité modifiée coule dans sa boîte, avec son
style ; ce qu'elle gagne ou perd en hauteur décale ce qui suit dans sa colonne (un
registre par colonne). Les éléments ajoutés reprennent le modèle de leurs voisins ; les
éléments retirés libèrent leur place.

Tout est en « bp », l'unité des PDF. Tout texte du contenu passe par ``escape`` ou
``rich`` ; les repères ``%@`` disent quel champ un clic sur l'aperçu ouvre.
"""

import statistics
from dataclasses import dataclass, field

from app import fonts
from app.latex.escape import escape, escape_url, rich
from app.latex.render import mark
from app.models.content import CVContent
from app.services.clone import fields as F
from app.services.clone.plan import AnchoredLayout, Glyph, Ink, Paint, Part, Unit

LANES = "abcdefgh"


def bp(value: float) -> str:
    return f"{value:.3f}bp"


def _color(hex_: str | None) -> str:
    return f"c{(hex_ or '000000').upper()}"


def current(content: CVContent, path: str) -> str | None:
    """Le texte d'un champ maintenant ; None s'il n'existe plus (élément retiré, rubrique
    masquée)."""
    bits = path.split(".")
    if bits[0] not in ("name", "headline", "summary", "contact"):
        section = next((s for s in content.sections if s.id == bits[0]), None)
        if section is None or not section.visible:
            return None
    value = F.get(content, path)
    if value is not None and not value.strip() and bits[0] not in ("name", "headline", "summary"):
        return None
    if value is not None and not value.strip():
        return None
    return value


def _remap(path: str, item: int) -> str:
    bits = path.split(".")
    bits[1] = str(item)
    return ".".join(bits)


@dataclass
class _Band:
    """Des unités posées sur une même ligne de base, dans une même colonne."""

    units: list[Unit]
    # Les unités ajoutées (copie d'un modèle) : leur chemin réécrit, leur écart.
    virtual: bool = False
    gap: float = 0.0
    paths: dict[int, dict[str, str]] = field(default_factory=dict)
    bullets: dict[int, int] = field(default_factory=dict)

    @property
    def lanes(self) -> list[int]:
        return sorted({n for u in self.units for n in u.lanes})

    @property
    def y(self) -> float:
        return min(u.y for u in self.units)

    @property
    def end(self) -> float:
        return max(u.y + u.end for u in self.units)


class Writer:
    def __init__(self, layout: AnchoredLayout, content: CVContent, photo: str | None) -> None:
        self.layout = layout
        self.content = content
        self.photo = photo
        self.colors: set[str] = set()
        self.fonts: set[str] = set()
        self.used_inks: set[int] = set()
        self.lanes = max((len(p) for p in layout.lanes), default=1) or 1

    # ─── Encres ───
    def color(self, hex_: str | None) -> str:
        self.colors.add((hex_ or "000000").upper())
        return _color(hex_)

    def ink(self, index: int) -> str:
        self.used_inks.add(index)
        ink = self.layout.inks[index] if index < len(self.layout.inks) else None
        if ink is not None:
            self.fonts.add(ink.font)
            self.colors.add(ink.color.upper())
        return f"\\cvi{_name(index)}"

    def ink_macro(self, index: int, ink: Ink) -> str:
        parts = [
            f"\\cvf{ink.font}",
            f"\\fontsize{{{bp(ink.size)}}}{{{bp(ink.size * 1.2)}}}\\selectfont",
            f"\\color{{{_color(ink.color)}}}",
        ]
        if ink.bold:
            parts.append("\\bfseries")
        if ink.italic:
            parts.append("\\itshape")
        if ink.tracking:
            spacing = ink.tracking / max(ink.size, 1) * 100
            parts.append(f"\\addfontfeatures{{LetterSpace={spacing:.1f}}}")
        return f"\\newcommand\\cvi{_name(index)}{{{''.join(parts)}}}"

    # ─── Formes ───
    def paint(self, p: Paint) -> str:
        if p.shade and p.fill and p.kind in ("rect", "path"):
            return self.gradient(p)
        opts = []
        if p.fill:
            opts.append(f"fill={self.color(p.fill)}")
        if p.stroke:
            opts.append(f"draw={self.color(p.stroke)}, line width={bp(max(p.width, 0.2))}")
        if not opts:
            return ""
        if p.even_odd:
            opts.append("even odd rule")
        style = ", ".join(opts)
        x0, y0, x1, y1 = p.box
        if p.kind == "path" and p.path:
            return f"\\path[{style}] {p.path};"
        if p.kind == "ellipse":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
            return f"\\path[{style}] ({cx:.3f},{cy:.3f}) ellipse ({rx:.3f} and {ry:.3f});"
        if p.kind == "line" and not p.fill:
            color = self.color(p.stroke)
            if x1 - x0 >= y1 - y0:
                y = (y0 + y1) / 2
                ends = f"({x0:.3f},{y:.3f}) -- ({x1:.3f},{y:.3f})"
            else:
                x = (x0 + x1) / 2
                ends = f"({x:.3f},{y0:.3f}) -- ({x:.3f},{y1:.3f})"
            return f"\\draw[{color}, line width={bp(max(p.width, 0.2))}] {ends};"
        corners = f", rounded corners={bp(p.radius)}" if p.radius else ""
        return f"\\path[{style}{corners}] ({x0:.3f},{y0:.3f}) rectangle ({x1:.3f},{y1:.3f});"

    def gradient(self, p: Paint) -> str:
        """Un dégradé en fines bandes de couleur, découpées à la forme (les dégradés de TikZ
        ne passent pas dans le fond de page sous XeTeX)."""
        way, *colors = p.shade or ["h"]
        x0, y0, x1, y1 = p.box
        shape = (
            p.path
            if p.kind == "path" and p.path
            else (f"({x0:.3f},{y0:.3f}) rectangle ({x1:.3f},{y1:.3f})")
        )
        n = len(colors)
        strips = []
        for i, color in enumerate(colors):
            name = self.color(color)
            if way == "h":
                a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n + 0.3
                strips.append(f"\\fill[{name}] ({a:.3f},{y0:.3f}) rectangle ({b:.3f},{y1:.3f});")
            else:
                a, b = y0 + (y1 - y0) * i / n, y0 + (y1 - y0) * (i + 1) / n + 0.3
                strips.append(f"\\fill[{name}] ({x0:.3f},{a:.3f}) rectangle ({x1:.3f},{b:.3f});")
        return f"\\begin{{scope}}\\clip {shape};{''.join(strips)}\\end{{scope}}"

    def picture(self, file: str, box, shape: str) -> str:
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        rect = f"({x0:.3f},{y0:.3f}) rectangle ({x1:.3f},{y1:.3f})"
        clip = {
            "circle": f"\\clip ({(x0 + x1) / 2:.3f},{(y0 + y1) / 2:.3f}) "
            f"ellipse ({w / 2:.3f} and {h / 2:.3f});",
            "rounded": f"\\clip[rounded corners={bp(min(w, h) / 8)}] {rect};",
            "square": "",
        }.get(shape, "")
        image = f"\\includegraphics[width={bp(w)},height={bp(h)}]{{{file}}}"
        return (
            f"\\begin{{scope}}{clip}\\node[anchor=north west, inner sep=0] "
            f"at ({x0:.3f},{y0:.3f}) {{{image}}};\\end{{scope}}"
        )

    def background(self, page: int) -> str:
        lines = [self.paint(p) for p in self.layout.paints if p.page == page and p.unit is None]
        lines += [
            self.picture(pic.file, pic.box, pic.shape)
            for pic in self.layout.pictures
            if pic.page == page and pic.unit is None
        ]
        photo = self.layout.photo
        if photo and self.photo and photo.page == page:
            lines.append(self.picture(self.photo, photo.box, photo.shape))
        body = "\n".join(line for line in lines if line)
        if not body:
            return ""
        return (
            "\\AddToShipoutPictureBG*{\\AtPageUpperLeft{"
            "\\begin{tikzpicture}[overlay, x=1bp, y=-1bp]\n" + body + "\n\\end{tikzpicture}}}"
        )

    def attached(self, unit: Unit, exact: bool) -> str:
        """Les formes et images qui suivent une unité, décalées comme elle (``\\cvy`` est sa
        ligne de base d'aujourd'hui)."""
        lines = [
            self.paint(p)
            for p in self.layout.paints
            if p.unit == unit.id and (exact or not p.exact)
        ]
        lines += [
            self.picture(pic.file, pic.box, pic.shape)
            for pic in self.layout.pictures
            if pic.unit == unit.id and (exact or not pic.exact)
        ]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        return (
            f"\\begin{{textblock*}}{{\\paperwidth}}(0pt,\\dimexpr\\cvy-{bp(unit.y)}\\relax)"
            "\\noindent\\smash{\\rlap{"
            "\\begin{tikzpicture}[overlay, x=1bp, y=-1bp]" + "".join(lines) + "\\end{tikzpicture}}}"
            "\\end{textblock*}"
        )

    # ─── Le texte ───
    def word(self, g: Glyph) -> str:
        text = "{" + self.ink(g.i) + " " + escape(g.t) + "}"
        if g.u:
            text = f"\\href{{{escape_url(g.u)}}}{{{text}}}"
        lift = f"\\raisebox{{{bp(-g.dy)}}}" if abs(g.dy) > 0.05 else ""
        return f"\\cvw{{{bp(g.x)}}}{{{bp(g.w)}}}{{{lift}{{{text}}}}}"

    def exact(self, unit: Unit) -> str:
        out = []
        for row in unit.rows:
            if not row.words:
                continue
            y = f"\\dimexpr\\cvy+{bp(row.y)}\\relax"
            out.append(f"\\cvline{{{y}}}{{{''.join(self.word(g) for g in row.words)}}}")
        return "\n".join(out)

    def field_text(self, part: Part, text: str) -> str:
        ink = self.layout.inks[part.ink] if part.ink < len(self.layout.inks) else None
        body = rich(text)
        if ink is not None and ink.upper:
            body = f"\\MakeUppercase{{{body}}}"
        url = part.url
        if part.path and part.path.startswith("contact.") and part.path.count(".") == 1:
            items = F.contacts(self.content)
            i = int(part.path.split(".")[1])
            if i < len(items) and items[i].url:
                url = items[i].url
        if url:
            body = f"\\href{{{escape_url(url)}}}{{{body}}}"
        return "{" + self.ink(part.ink) + " " + body + "}"

    def parts_text(self, unit: Unit, paths: dict[str, str]) -> str:
        """Le texte d'une unité qui coule : ses champs d'aujourd'hui et ses textes fixes."""
        pieces: list[tuple[str, bool]] = []  # (latex, est un champ)
        for part in unit.parts:
            if part.path is None:
                pieces.append(("{" + self.ink(part.ink) + " " + escape(part.text) + "}", False))
                continue
            path = paths.get(part.path, part.path)
            text = current(self.content, path)
            if text is None:
                pieces.append(("", True))
                continue
            pieces.append((self.field_text(part, text), True))
        # Un séparateur dont un voisin a disparu (un champ vidé) part avec lui.
        out = []
        for n, (latex, is_field) in enumerate(pieces):
            if not is_field:
                before = [t for t, f in pieces[:n] if f]
                after = [t for t, f in pieces[n + 1 :] if f]
                if not before and not after:
                    continue
                if before and not before[-1]:
                    continue
                if after and not after[0]:
                    continue
            out.append(latex)
        return "".join(out)

    def list_text(self, unit: Unit, items: list[int]) -> str:
        """Une liste écrite à la suite : le modèle du premier élément, pour chacun."""
        first = unit.items[0]
        template: list[Part] = []
        prefix: list[Part] = []
        suffix: list[Part] = []
        state = "prefix"
        for part in unit.parts:
            index = int(part.path.split(".")[1]) if part.path else None
            if state == "prefix":
                if index == first:
                    state = "template"
                    template.append(part)
                else:
                    prefix.append(part)
            elif state == "template":
                if index is None or index == first:
                    template.append(part)
                else:
                    state = "rest"
            if state == "rest":
                break
        # Le séparateur qui suit le premier élément n'est pas dans son modèle.
        while template and template[-1].path is None:
            template.pop()
        last_items = [int(p.path.split(".")[1]) for p in unit.parts if p.path]
        tail = False
        for part in unit.parts:
            if part.path and int(part.path.split(".")[1]) == max(last_items):
                tail = True
                suffix = []
            elif tail and part.path is None:
                suffix.append(part)
        joiner = (
            "{"
            + self.ink(template[0].ink if template else self.layout.body)
            + " "
            + escape(unit.joiner)
            + "}"
        )
        rendered = []
        for n in items:
            paths = {p.path: _remap(p.path, n) for p in template if p.path}
            text = self.parts_text(Unit(**{**unit.model_dump(), "parts": template}), paths)
            if text:
                rendered.append(text)
        head = "".join(
            "{" + self.ink(p.ink) + " " + escape(p.text) + "}" for p in prefix if p.path is None
        )
        tail_text = "".join("{" + self.ink(p.ink) + " " + escape(p.text) + "}" for p in suffix)
        return head + joiner.join(rendered) + tail_text

    def reflow(self, unit: Unit, text: str) -> str:
        """Le texte qui coule dans la boîte de l'unité ; ``\\cvn`` reçoit son nombre de lignes."""
        lead = {"left": "\\raggedright", "right": "\\raggedleft", "center": "\\centering"}[
            unit.align
        ]
        main = next((p.ink for p in unit.parts if p.path), unit.parts[0].ink if unit.parts else 0)
        indent = f"\\hspace*{{{bp(unit.indent)}}}" if unit.indent else ""
        marker = ""
        if unit.marker is not None:
            marker = (
                f"\\cvline{{\\cvy}}{{{self.word(unit.marker.model_copy(update={'w': 0.0}))}}}\n"
            )
        width = max(unit.x1 - unit.x0, 10)
        body = (
            f"{self.ink(main)}\\setlength\\baselineskip{{{bp(unit.leading)}}}"
            f"\\setlength\\lineskiplimit{{-\\maxdimen}}{lead}\\noindent{indent}"
            f"\\rule{{0pt}}{{{bp(unit.ascent)}}}{text}\\par\\xdef\\cvn{{\\the\\prevgraf}}"
        )
        return (
            marker
            + f"\\cvpar{{{bp(unit.x0)}}}{{\\cvy}}{{{bp(width)}}}{{{bp(unit.ascent)}}}{{{body}}}"
        )

    # ─── L'ordre des unités, avec les ajouts et les retraits ───
    def state(self, unit: Unit, band: _Band) -> tuple[str, str]:
        """« exact », « reflow » (avec le texte) ou « removed »."""
        paths = band.paths.get(unit.id, {})
        if unit.role == "list" and len(unit.items) >= 2:
            section = next((s for s in self.content.sections if s.id == unit.section), None)
            if section is None or not section.visible:
                return "removed", ""
            plan = self.layout.sections.get(unit.section or "")
            last = self._last_list_unit(unit.section or "")
            wanted = [
                n for n in range(min(unit.items), max(unit.items) + 1) if n < len(section.items)
            ]
            if plan is not None and last == unit.id:
                wanted += list(range(len(plan.items), len(section.items)))
            if not wanted:
                return "removed", ""
            unchanged = wanted == list(range(min(unit.items), max(unit.items) + 1)) and all(
                current(self.content, p) == text for p, text in unit.original.items()
            )
            if unchanged and not band.virtual:
                return "exact", ""
            return "reflow", self.list_text(unit, wanted)
        values = {p: current(self.content, paths.get(p, p)) for p in unit.original}
        if not unit.original:
            return ("removed", "") if band.virtual else ("exact", "")
        if all(v is None for v in values.values()):
            return "removed", ""
        if not band.virtual and all(values[p] == unit.original[p] for p in unit.original):
            return "exact", ""
        return "reflow", self.parts_text(unit, paths)

    def _last_list_unit(self, section_id: str) -> int | None:
        found = [
            u for u in self.layout.units if u.section == section_id and u.role == "list" and u.items
        ]
        if not found:
            return None
        return max(found, key=lambda u: (u.page, u.y, u.x0)).id

    def bands(self, page: int) -> list[_Band]:
        """Les unités d'une page groupées par ligne de base et colonne, de haut en bas ;
        les éléments ajoutés suivent leur modèle."""
        units = sorted((u for u in self.layout.units if u.page == page), key=lambda u: (u.y, u.x0))
        bands: list[_Band] = []
        for u in units:
            for band in bands:
                # Une même ligne : même colonne, ou même rubrique (une date dans sa marge).
                coupled = set(band.lanes) & set(u.lanes) or (
                    u.section is not None and any(v.section == u.section for v in band.units)
                )
                if abs(band.y - u.y) < 1.5 and coupled:
                    band.units.append(u)
                    break
            else:
                bands.append(_Band([u]))
        bands.sort(key=lambda b: (b.y, min(u.x0 for u in b.units)))
        return self._with_additions(bands, page)

    def _with_additions(self, bands: list[_Band], page: int) -> list[_Band]:
        out: list[_Band] = []
        anchors: dict[int, list[_Band]] = {}  # id d'une unité → bandes ajoutées après elle
        for s in self.content.sections:
            plan = self.layout.sections.get(s.id)
            if plan is None or not s.visible:
                continue
            originals = len(plan.items)
            # Des puces ajoutées à une entrée existante.
            for n, item in enumerate(s.items[:originals]):
                bullets = getattr(item, "bullets", None) or []
                known = plan.items[n].bullets
                template_id = known[-1] if known else self._any_bullet(s.id)
                if template_id is None or len(bullets) <= len(known):
                    continue
                template = self.layout.unit(template_id)
                anchor = (known or plan.items[n].units or [template_id])[-1]
                if self.layout.unit(anchor).page != page:
                    continue
                for k in range(len(known), len(bullets)):
                    band = _Band([template], virtual=True, gap=self._bullet_gap(template))
                    band.paths[template.id] = {
                        p: f"{s.id}.{n}.bullets.{k}" for p in template.original
                    }
                    anchors.setdefault(anchor, []).append(band)
            # Des entrées ajoutées à une rubrique (expériences, formations, projets).
            if s.kind in ("experience", "education", "projects") and len(s.items) > originals > 0:
                model = plan.items[-1]
                units = [self.layout.unit(i) for i in model.units + model.bullets]
                if not units or units[0].page != page:
                    continue
                anchor = max(units, key=lambda u: u.y + u.end).id
                for n in range(originals, len(s.items)):
                    item = s.items[n]
                    model_bullets = [self.layout.unit(i) for i in model.bullets]
                    rows = [self.layout.unit(i) for i in model.units]
                    grouped: list[list[Unit]] = []
                    for u in sorted(rows, key=lambda u: (u.y, u.x0)):
                        if grouped and abs(grouped[-1][0].y - u.y) < 1.5:
                            grouped[-1].append(u)
                        else:
                            grouped.append([u])
                    first = True
                    previous_end = None
                    for group in grouped:
                        top = min(u.y for u in group)
                        if first:
                            gap = min(u.gap for u in group)
                        else:
                            gap = top - previous_end
                        band = _Band(group, virtual=True, gap=gap)
                        for u in group:
                            band.paths[u.id] = {p: _remap(p, n) for p in u.original}
                        anchors.setdefault(anchor, []).append(band)
                        previous_end = max(u.y + u.end for u in group)
                        first = False
                    bullet_model = model_bullets[-1] if model_bullets else None
                    for k in range(len(getattr(item, "bullets", []) or [])):
                        if bullet_model is None:
                            break
                        gap = model_bullets[0].gap if k == 0 else self._bullet_gap(bullet_model)
                        band = _Band([bullet_model], virtual=True, gap=gap)
                        band.paths[bullet_model.id] = {
                            p: f"{s.id}.{n}.bullets.{k}" for p in bullet_model.original
                        }
                        anchors.setdefault(anchor, []).append(band)
            # Des lignes ajoutées à une liste (une compétence, une langue) : une ligne de plus.
            if (
                s.kind in ("skills", "languages", "grid", "bullets")
                and len(s.items) > originals > 0
            ):
                last = plan.items[-1].units
                if not last:
                    continue
                model = self.layout.unit(last[-1])
                if model.items and len(model.items) >= 2:
                    continue  # une liste à la suite : la dernière unité les reçoit
                if model.page != page:
                    continue
                for n in range(originals, len(s.items)):
                    band = _Band([model], virtual=True, gap=self._list_gap(s.id, model))
                    band.paths[model.id] = {p: _remap(p, n) for p in model.original}
                    anchors.setdefault(model.id, []).append(band)
        for band in bands:
            out.append(band)
            for u in band.units:
                out += anchors.pop(u.id, [])
        return out

    def _any_bullet(self, section_id: str) -> int | None:
        plan = self.layout.sections.get(section_id)
        if plan is None:
            return None
        for item in plan.items:
            if item.bullets:
                return item.bullets[-1]
        found = [u.id for u in self.layout.units if u.role == "bullet"]
        return found[-1] if found else None

    def _bullet_gap(self, unit: Unit) -> float:
        gaps = [
            u.gap
            for u in self.layout.units
            if u.role == "bullet" and u.section == unit.section and u.bullet
        ]
        return statistics.median(gaps) if gaps else unit.leading

    def _list_gap(self, section_id: str, unit: Unit) -> float:
        plan = self.layout.sections[section_id]
        gaps = [self.layout.unit(item.units[0]).gap for item in plan.items[1:] if item.units]
        return statistics.median(gaps) if gaps else unit.leading

    # ─── Une page ───
    def page(self, number: int) -> str:
        out = [self.background(number)]
        out.append("".join(f"\\global\\cvs{LANES[n]}=0pt" for n in range(self.lanes)))
        out.append("\\global\\cvlowest=0pt")
        # La dernière ligne de base d'origine posée dans chaque colonne.
        last_end: dict[int, float] = {}
        for band in self.bands(number):
            lanes = [n for n in band.lanes if n < self.lanes] or [0]
            out.append(f"\\global\\cvd=\\cvs{LANES[lanes[0]]}")
            for n in lanes[1:]:
                out.append(f"\\ifdim\\cvs{LANES[n]}>\\cvd\\global\\cvd=\\cvs{LANES[n]}\\fi")
            if band.virtual:
                # Un élément ajouté : sous la dernière ligne posée de sa colonne.
                base = max((last_end.get(n, 0.0) for n in lanes), default=0.0)
                y_band = base + band.gap
            else:
                y_band = band.y
            states = [(u, *self.state(u, band)) for u in band.units]
            rendered = [(u, st, t) for u, st, t in states if st != "removed"]
            if not rendered:
                if not band.virtual:
                    for n in lanes:
                        before = last_end.get(n)
                        drop = (
                            band.end - before
                            if before is not None
                            else (band.end - band.y + min(u.leading for u in band.units))
                        )
                        out.append(f"\\global\\advance\\cvs{LANES[n]} by -{bp(drop)}")
                        last_end[n] = band.end
                continue
            out.append("\\global\\cvbandend=-\\maxdimen")
            top = min(u.y for u in band.units)
            for u, st, text in rendered:
                y = y_band + (u.y - top if band.virtual else u.y - band.y)
                out.append(mark(*u.mark.split()) if u.mark != "none" else mark("none"))
                out.append(f"\\global\\cvy=\\dimexpr{bp(y)}+\\cvd\\relax")
                out.append(self.attached(u, st == "exact" and not band.virtual))
                if st == "exact":
                    out.append(self.exact(u))
                    out.append(f"\\global\\cvend=\\dimexpr\\cvy+{bp(u.end)}\\relax")
                else:
                    out.append(self.reflow(u, text))
                    out.append(f"\\global\\cvend=\\dimexpr\\cvy+{bp(u.leading)}*(\\cvn-1)\\relax")
                out.append("\\ifdim\\cvend>\\cvbandend\\global\\cvbandend=\\cvend\\fi")
                out.append("\\ifdim\\cvend>\\cvlowest\\global\\cvlowest=\\cvend\\fi")
            if band.virtual:
                base = max((last_end.get(n, 0.0) for n in lanes), default=0.0)
                for n in lanes:
                    out.append(f"\\global\\cvs{LANES[n]}=\\dimexpr\\cvbandend-{bp(base)}\\relax")
            else:
                for n in lanes:
                    out.append(
                        f"\\global\\cvs{LANES[n]}=\\dimexpr\\cvbandend-{bp(band.end)}\\relax"
                    )
                    last_end[n] = band.end
        out += self.free_links(number)
        out.append(self.overflow(number))
        return "\n".join(line for line in out if line)

    def overflow(self, number: int) -> str:
        """Un texte qui descend sous la marge du bas d'origine : signalé comme un dépassement
        de LaTeX (« Overfull \\vbox »), que l'appli sait déjà lire."""
        size = self.layout.pages[number - 1]
        units = [u for u in self.layout.units if u.page == number]
        lowest = max((u.y + u.end for u in units), default=size.height)
        limit = size.height - max(14.0, 0.5 * (size.height - lowest))
        return (
            f"\\ifdim\\cvlowest>{bp(limit)}\\typeout{{Overfull \\string\\vbox\\space"
            f"(\\the\\dimexpr\\cvlowest-{bp(limit)}\\relax\\space too high)}}\\fi"
        )

    def free_links(self, page: int) -> list[str]:
        out = []
        for link in self.layout.links:
            if link.page != page:
                continue
            x0, y0, x1, y1 = link.box
            out.append(
                f"\\cvline{{\\dimexpr{bp(y1)}\\relax}}{{\\hskip{bp(x0)}\\href{{{escape_url(link.url)}}}"
                f"{{\\color{{white}}\\rule{{0pt}}{{{bp(y1 - y0)}}}\\hspace*{{{bp(x1 - x0)}}}}}}}"
            )
        return out

    def additions(self) -> str:
        """Les rubriques ajoutées après le clonage : sous la dernière unité de la page 1,
        dans le style courant."""
        plans = self.layout.sections
        new = [s for s in self.content.sections if s.visible and s.id not in plans]
        if not new:
            return ""
        page_units = [u for u in self.layout.units if u.page == len(self.layout.pages)]
        if not page_units:
            return ""
        lowest = max(page_units, key=lambda u: u.y + u.end)
        lane = lowest.lanes[0] if lowest.lanes else 0
        column = [u for u in page_units if lane in u.lanes]
        x0 = min(u.x0 for u in column)
        x1 = max(u.x1 for u in column)
        title_ink = self.layout.title_ink if self.layout.title_ink is not None else self.layout.body
        body_ink = self.layout.body
        size = self.layout.inks[body_ink].size if self.layout.inks else 10
        out = []
        y = lowest.y + lowest.end
        for s in new:
            texts: list[str] = []
            for _path, text, _sid in F.paths(self.content):
                if _sid == s.id and not _path.endswith(".title"):
                    texts.append(text)
            title_unit = Unit(
                id=-1, page=lowest.page, y=0, x0=x0, x1=x1, leading=size * 1.3,
                ascent=size, parts=[Part(path=f"{s.id}.title", ink=title_ink)],
                mark=f"section {s.id}", lanes=lowest.lanes,
            )  # fmt: skip
            out.append(mark("section", s.id))
            y += size * 2.2
            out.append(f"\\global\\cvy=\\dimexpr{bp(y)}+\\cvs{LANES[lane]}\\relax")
            out.append(self.reflow(title_unit, self.parts_text(title_unit, {})))
            out.append(
                f"\\global\\advance\\cvs{LANES[lane]} by \\dimexpr{bp(size * 1.3)}*\\cvn\\relax"
            )
            for n, text in enumerate(texts):
                body_unit = Unit(
                    id=-1, page=lowest.page, y=0, x0=x0, x1=x1, leading=size * 1.25, ascent=size,
                    parts=[Part(text="", ink=body_ink)], lanes=lowest.lanes,
                )  # fmt: skip
                out.append(mark("item", s.id, n))
                y += size * 0.4
                out.append(f"\\global\\cvy=\\dimexpr{bp(y)}+\\cvs{LANES[lane]}\\relax")
                latex = "{" + self.ink(body_ink) + " " + rich(text) + "}"
                out.append(self.reflow(body_unit, latex))
                step = bp(size * 1.25)
                out.append(f"\\global\\advance\\cvs{LANES[lane]} by \\dimexpr{step}*\\cvn\\relax")
        return "\n".join(out)

    def document(self) -> str:
        pages = []
        for n in range(1, len(self.layout.pages) + 1):
            body = self.page(n)
            if n == len(self.layout.pages):
                body += "\n" + self.additions()
            pages.append(body + "\n" + mark("none") + "\n\\null")
        content = "\n\\clearpage\n".join(pages)
        font_lines = []
        for font_id in sorted(self.fonts):
            family = fonts.get(font_id)
            font_lines.append(
                f"\\newfontfamily\\cvf{font_id}{{{family.prefix}}}"
                f"[Path={family.folder.as_posix()}/, Extension=.ttf, "
                "UprightFont=*-Regular, BoldFont=*-Bold, ItalicFont=*-Italic, "
                "BoldItalicFont=*-BoldItalic, Numbers=Proportional, Ligatures={TeX, CommonOff}]"
            )
        inks = "\n".join(
            self.ink_macro(i, self.layout.inks[i])
            for i in sorted(self.used_inks)
            if i < len(self.layout.inks)
        )
        colors = "\n".join(
            f"\\definecolor{{{_color(c)}}}{{HTML}}{{{c}}}" for c in sorted(self.colors)
        )
        size = self.layout.pages[0]
        registers = "".join(f"\\newdimen\\cvs{LANES[n]}" for n in range(self.lanes))
        geometry = f"paperwidth={bp(size.width)},paperheight={bp(size.height)},margin=0pt"
        return f"""% CV cloné de son PDF d'origine, généré par CV Builder.
% Modifier content.json plutôt que ce fichier.
\\documentclass{{article}}
\\usepackage[{geometry}]{{geometry}}
\\usepackage{{fontspec}}
\\XeTeXgenerateactualtext=1
\\usepackage{{xcolor,graphicx,tikz,eso-pic}}
\\usepackage[absolute]{{textpos}}
\\usepackage[hidelinks]{{hyperref}}
\\setlength{{\\TPHorizModule}}{{1bp}}\\setlength{{\\TPVertModule}}{{1bp}}\\textblockorigin{{0pt}}{{0pt}}
\\pagestyle{{empty}}\\setlength{{\\parindent}}{{0pt}}\\setlength{{\\parskip}}{{0pt}}
\\hfuzz=\\maxdimen\\hbadness=10000\\vfuzz=\\maxdimen\\vbadness=10000
\\hyphenpenalty=10000\\exhyphenpenalty=10000\\setlength{{\\emergencystretch}}{{2em}}
{chr(10).join(font_lines)}
{colors}
{inks}
\\newdimen\\cvy\\newdimen\\cvd\\newdimen\\cvend\\newdimen\\cvbandend\\newdimen\\cvlowest{registers}
\\def\\cvn{{1}}
\\newsavebox\\cvbox
% Un mot ramené à sa largeur d'origine (de 60 à 130 %) : une police aux largeurs voisines
% ne fait ni chevaucher ni s'écarter les mots.
\\newcommand\\cvfit[2]{{\\sbox\\cvbox{{#2}}%
\\ifdim\\wd\\cvbox>0.5pt\\edef\\cvr{{\\fpeval{{#1/\\the\\wd\\cvbox}}}}%
\\ifdim\\cvr pt>1.3pt\\usebox\\cvbox
\\else\\ifdim\\cvr pt<0.6pt\\usebox\\cvbox
\\else\\scalebox{{\\cvr}}[1]{{\\usebox\\cvbox}}\\fi\\fi
\\else\\usebox\\cvbox\\fi}}
% Une ligne posée sur sa ligne de base ; un mot à son bord gauche ; un paragraphe qui coule.
\\newcommand\\cvline[2]{{\\begin{{textblock*}}{{\\paperwidth}}(0pt,#1)\\noindent\\smash{{\\rlap{{#2}}}}\\end{{textblock*}}}}
\\newcommand\\cvw[3]{{\\rlap{{\\hskip#1\\cvfit{{#2}}{{#3}}}}}}
\\newcommand\\cvpar[5]{{\\begin{{textblock*}}{{#3}}(#1,\\dimexpr#2-#4\\relax)#5\\end{{textblock*}}}}
\\begin{{document}}
{content}
\\end{{document}}
"""


def _name(index: int) -> str:
    """Un nom de commande fait de lettres : 0 → « a », 27 → « bb »."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    out = ""
    n = index
    while True:
        out = letters[n % 26] + out
        n = n // 26 - 1
        if n < 0:
            return out


def render(layout: AnchoredLayout, content: CVContent, photo: str | None = None) -> str:
    writer = Writer(layout, content, photo)
    # Le corps d'abord : il note les polices, encres et couleurs dont le préambule a besoin.
    writer.document()
    return writer.document()
