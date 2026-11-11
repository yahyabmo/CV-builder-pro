"""Le .tex d'un CV cloné : sa mise en page (``CloneLayout``) et son contenu.

Les formes fixes sont dessinées sous la page (eso-pic + TikZ), chaque cadre est posé à
sa place (textpos) et le contenu y coule avec les encres et les écarts mesurés. Tout est
en « bp », l'unité des PDF (1/72 de pouce), pour retrouver les mêmes nombres.
Tout texte du contenu passe par ``escape`` ou ``rich``.
"""

from app import fonts
from app.latex.escape import escape, escape_url, rich
from app.latex.render import mark
from app.models.content import CVContent, Section
from app.services.clone.model import Block, Bullet, CloneLayout, Frame, Ink, Look, Paint, Row

PHOTO = "photo.jpg"


def bp(value: float) -> str:
    return f"{value:.2f}bp"


def _color(hex_: str | None) -> str:
    return f"c{(hex_ or '000000').upper()}"


class Writer:
    def __init__(self, layout: CloneLayout, content: CVContent, photo: str | None) -> None:
        self.layout = layout
        self.content = content
        self.photo = photo
        self.colors: set[str] = set()
        self.fonts: set[str] = set()

    # ─── Encres ───
    def color(self, hex_: str | None) -> str:
        name = _color(hex_)
        self.colors.add((hex_ or "000000").upper())
        return name

    def ink(self, ink: Ink | None, latex: str, par: bool = False) -> str:
        """Le texte dans son encre ; ``par`` : le paragraphe se termine dedans (interligne)."""
        if ink is None:
            return latex + ("\\par" if par else "")
        self.fonts.add(ink.font)
        parts = [
            f"\\cvf{ink.font}",
            f"\\fontsize{{{bp(ink.size)}}}{{{bp(ink.leading)}}}\\selectfont",
            f"\\color{{{self.color(ink.color)}}}",
        ]
        if ink.bold:
            parts.append("\\bfseries")
        if ink.italic:
            parts.append("\\itshape")
        if ink.tracking:
            parts.append(f"\\addfontfeatures{{LetterSpace={ink.tracking:.1f}}}")
        body = f"\\MakeUppercase{{{latex}}}" if ink.upper and not ink.small else latex
        return "{" + "".join(parts) + " " + body + ("\\par" if par else "") + "}"

    # ─── Formes fixes ───
    def paint(self, p: Paint) -> str:
        opts = []
        if p.fill:
            opts.append(f"fill={self.color(p.fill)}")
        if p.stroke:
            opts.append(f"draw={self.color(p.stroke)}, line width={bp(max(p.width, 0.2))}")
        if not opts:
            return ""
        style = ", ".join(opts)
        if p.kind == "ellipse":
            cx, cy = (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2
            rx, ry = (p.x1 - p.x0) / 2, (p.y1 - p.y0) / 2
            return f"\\path[{style}] ({cx:.2f},{cy:.2f}) ellipse ({rx:.2f} and {ry:.2f});"
        if p.kind == "line":
            color = self.color(p.stroke or p.fill)
            if p.x1 - p.x0 >= p.y1 - p.y0:
                y = (p.y0 + p.y1) / 2
                width = bp(max(p.width, p.y1 - p.y0, 0.2))
                ends = f"({p.x0:.2f},{y:.2f}) -- ({p.x1:.2f},{y:.2f})"
            else:
                x = (p.x0 + p.x1) / 2
                width = bp(max(p.width, p.x1 - p.x0, 0.2))
                ends = f"({x:.2f},{p.y0:.2f}) -- ({x:.2f},{p.y1:.2f})"
            return f"\\draw[{color}, line width={width}] {ends};"
        corners = f", rounded corners={bp(p.radius)}" if p.radius else ""
        return (
            f"\\path[{style}{corners}] ({p.x0:.2f},{p.y0:.2f}) rectangle ({p.x1:.2f},{p.y1:.2f});"
        )

    def background(self) -> str:
        lines = [self.paint(p) for p in self.layout.paints]
        photo = self.layout.photo
        if photo and self.photo:
            x0, y0, x1, y1 = photo.x, photo.y, photo.x + photo.w, photo.y + photo.h
            box = f"({x0:.2f},{y0:.2f}) rectangle ({x1:.2f},{y1:.2f})"
            clip = {
                "circle": f"\\clip ({(x0 + x1) / 2:.2f},{(y0 + y1) / 2:.2f}) "
                f"ellipse ({photo.w / 2:.2f} and {photo.h / 2:.2f});",
                "rounded": f"\\clip[rounded corners={bp(min(photo.w, photo.h) / 8)}] {box};",
                "square": f"\\clip {box};",
            }[photo.shape]
            image = f"\\includegraphics[width={bp(photo.w)},height={bp(photo.h)}]{{{self.photo}}}"
            lines.append(
                f"\\begin{{scope}}{clip}\\node[anchor=north west, inner sep=0] "
                f"at ({x0:.2f},{y0:.2f}) {{{image}}};\\end{{scope}}"
            )
        body = "\n".join(line for line in lines if line)
        if not body:
            return ""
        return (
            "\\AddToShipoutPictureBG*{\\AtPageUpperLeft{"
            "\\begin{tikzpicture}[overlay, x=1bp, y=-1bp]\n" + body + "\n\\end{tikzpicture}}}"
        )

    # ─── Blocs ───
    @staticmethod
    def align(align: str) -> str:
        return {"left": "\\raggedright", "center": "\\centering", "right": "\\raggedleft"}[align]

    def gap(self, value: float) -> str:
        return f"\\vspace*{{{bp(value)}}}" if abs(value) > 0.01 else ""

    def block(self, frame: Frame, block: Block, first: bool) -> str:
        h = self.content.header
        out = [] if first else [self.gap(block.gap)]
        lead = self.align(block.align)
        if block.kind in ("name", "headline", "summary"):
            out.append(mark("header"))
            out.append(
                "{" + lead + self.ink(block.ink, rich(getattr(h, block.kind)), par=True) + "}"
            )
        elif block.kind == "label":
            out.append(mark("none"))
            out.append("{" + lead + self.ink(block.ink, escape(block.text), par=True) + "}")
        elif block.kind == "contacts":
            items = [item for line in h.contact_lines for item in line]
            groups = block.lines or [list(range(len(items)))]
            placed = {i for g in groups for i in g}
            groups = [g for g in groups if g] + (
                [[i for i in range(len(items)) if i not in placed]]
                if len(placed) < len(items)
                else []
            )
            for number, g in enumerate(groups):
                parts = (
                    [rich(h.headline)]
                    if block.with_headline and number == 0 and h.headline.strip()
                    else []
                )
                for i in g:
                    if i >= len(items):
                        continue
                    item = items[i]
                    text = escape(item.text)
                    if item.bold:
                        text = f"\\textbf{{{text}}}"
                    if item.label:
                        text = f"\\textbf{{{escape(item.label)} :}} {text}"
                    if item.url:
                        text = f"\\href{{{escape_url(item.url)}}}{{{text}}}"
                    parts.append(text)
                out.append(mark("contact", number))
                out.append(
                    "{" + lead + self.ink(block.ink, escape(block.sep).join(parts), par=True) + "}"
                )
        elif block.kind == "section":
            section = next((s for s in self.content.sections if s.id == block.ref), None)
            look = self.layout.look(block.ref)
            if section is not None and look is not None and section.visible:
                out.append(mark("section", section.id))
                out.append(self.section(section, look, frame))
        return "\n".join(x for x in out if x)

    @staticmethod
    def small_caps(text: str, ink: Ink) -> str:
        """Petites capitales imitées : l'initiale de chaque mot en grand, le reste en petit."""
        small = f"\\fontsize{{{bp(ink.small)}}}{{{bp(ink.leading)}}}\\selectfont "
        words = []
        for word in text.split(" "):
            if not word:
                continue
            words.append(
                escape(word[0].upper())
                + ("{" + small + escape(word[1:].upper()) + "}" if len(word) > 1 else "")
            )
        return " ".join(words)

    def title_text(self, section: Section, look: Look) -> str:
        if look.title is not None and look.title.small:
            return self.small_caps(section.title, look.title)
        return escape(section.title)

    def title(self, section: Section, look: Look, frame_width: float) -> str:
        if look.title_mode != "above" or look.title is None:
            return ""
        text = self.title_text(section, look)
        deco = look.deco
        lead = self.align(look.title_align)
        if deco.kind == "band":
            # Le bandeau à sa hauteur exacte, le titre posé sur sa ligne de base.
            width = deco.width or frame_width
            self.colors.add(deco.color.upper())
            corners = f", rounded corners={bp(deco.radius)}" if deco.radius else ""
            top, bottom = -deco.above, deco.height - deco.above
            left, right = deco.offset, deco.offset + width
            return (
                "\\noindent\\begin{tikzpicture}[baseline=0pt, x=1bp, y=-1bp]"
                f"\\fill[{_color(deco.color)}{corners}] ({left:.2f},{top:.2f}) "
                f"rectangle ({right:.2f},{bottom:.2f});"
                f"\\node[anchor=base west, inner sep=0] at ({left + deco.gap:.2f},0) "
                f"{{{self.ink(look.title, text)}}};"
                "\\end{tikzpicture}\\par" + self.gap(look.after_title)
            )
        indent = (
            f"\\hspace*{{{bp(look.title_indent)}}}"
            if look.title_indent and look.title_align == "left"
            else ""
        )
        line = "{" + lead + self.ink(look.title, "\\noindent " + indent + text, par=True) + "}"
        if deco.kind == "rule":
            width = bp(deco.width) if deco.width else "\\linewidth"
            self.colors.add(deco.color.upper())
            place = "\\centering" if deco.align == "center" else "\\raggedright"
            rule = f"\\rule{{{width}}}{{{bp(deco.thickness)}}}"
            line += (
                f"\\nointerlineskip\\vspace{{{bp(deco.gap)}}}"
                f"{{{place}{{\\color{{{_color(deco.color)}}}{rule}}}\\par}}"
            )
        return line + self.gap(look.after_title)

    def gutter(self, section: Section, look: Look) -> str:
        if look.title_mode != "gutter" or look.title is None:
            return ""
        width = max(look.gutter - 8, 20)
        title = self.ink(look.title, self.title_text(section, look))
        box = f"\\parbox[t]{{{bp(width)}}}{{\\raggedleft {title}}}"
        return f"\\llap{{{box}\\hspace{{{bp(look.gutter - width)}}}}}"

    def bullet_mark(self, b: Bullet, ink: Ink | None) -> str:
        if b.kind == "dot":
            r = b.size / 2
            dot = f"\\tikz[baseline=0pt]\\fill[{self.color(b.color)}] (0,0) circle ({bp(r)});"
            return (
                f"\\llap{{\\raisebox{{{bp(b.raise_)}}}{{{dot}}}"
                f"\\hspace{{{bp(max(b.offset - r, 0))}}}}}"
            )
        if b.kind == "char":
            space = max(b.offset - (ink.size * 0.5 if ink else 4), 1)
            return f"\\llap{{{self.ink(ink, escape(b.char))}\\hspace{{{bp(space)}}}}}"
        return ""

    def bullets(
        self, items: list[str], look: Look, ink: Ink | None, where: tuple[str, int] | None = None
    ) -> str:
        """Des puces ; ``where`` (rubrique, entrée) : leurs repères pour le clic sur l'aperçu."""
        b = look.bullet
        out = []
        for n, text in enumerate(items):
            sign = self.bullet_mark(b, ink)
            body = self.ink(ink, rich(text), par=True)
            gap = self.gap(look.bullet_space) if n else ""
            if where is not None:
                out.append(mark("bullet", where[0], where[1], n))
            elif look.mode != "flow":
                out.append(mark("item", look.id, n))
            out.append(f"{gap}{{\\leftskip={bp(b.indent)}\\noindent {sign}{body}}}")
        return "\n".join(out)

    def row(self, row: Row, values: dict[str, str], look: Look, gutter: str) -> str:
        def field(name: str) -> str:
            value = values.get(name, "")
            return self.ink(look.inks.get(name), rich(value)) if value.strip() else ""

        left = [x for x in (field(n) for n in row.left) if x]
        right = [x for x in (field(n) for n in row.right) if x]
        if not left and not right:
            return ""
        main = look.inks.get(row.left[0] if row.left else row.right[0])
        sep = escape(row.sep)
        line = gutter + sep.join(left) + ("\\hfill " + " ".join(right) if right else "")
        return self.ink(main, "\\noindent " + line, par=True)

    def entries(self, section: Section, look: Look) -> str:
        rows = look.rows or [Row(left=["title"]), Row(left=["place"], right=["dates"])]
        named = {n for r in rows for n in r.left + r.right}
        out = []
        for n, it in enumerate(section.items):
            values = {
                "title": it.title,
                "tag": getattr(it, "tag", ""),
                "place": getattr(it, "place", ""),
                "dates": getattr(it, "dates", None) or getattr(it, "date", ""),
            }
            parts = ([self.gap(look.item_gap)] if n else []) + [mark("item", section.id, n)]
            gutter = self.gutter(section, look) if n == 0 else ""
            for r in rows:
                line = self.row(r, values, look, gutter)
                if line:
                    if not gutter and parts and look.row_gap and len(parts) > (1 if n else 0):
                        parts.append(self.gap(look.row_gap))
                    parts.append(line)
                    gutter = ""
            for extra in ("title", "tag", "place", "dates"):
                if extra not in named and values[extra].strip():
                    parts.append(
                        self.ink(
                            look.inks.get(extra) or look.inks.get("place"),
                            rich(values[extra]),
                            par=True,
                        )
                    )
            description = getattr(it, "description", "")
            if description.strip():
                parts.append(
                    self.ink(
                        look.inks.get("description") or look.inks.get("bullets"),
                        rich(description),
                        par=True,
                    )
                )
            bullets = getattr(it, "bullets", [])
            if bullets:
                parts.append(self.gap(look.bullet_gap))
                parts.append(
                    self.bullets(
                        bullets,
                        look,
                        look.inks.get("bullets") or look.inks.get("description"),
                        (section.id, n),
                    )
                )
            out.append("\n".join(p for p in parts if p))
        return "\n".join(out)

    def pairs(self, section: Section, look: Look) -> str:
        """Compétences et langues : libellé et texte."""
        if section.kind == "skills":
            pairs = [(it.label, it.text) for it in section.items]
        else:
            pairs = [(it.name, it.level) for it in section.items]
        label_ink, text_ink = (
            look.inks.get("label"),
            look.inks.get("text") or look.inks.get("label"),
        )
        out = []
        if look.mode == "tags" and look.chip:
            chip = look.chip
            words = [
                w.strip()
                for _, t in pairs
                for w in t.replace(";", ",").rstrip(".").split(",")
                if w.strip()
            ]
            opts = []
            if chip.fill:
                opts.append(f"fill={self.color(chip.fill)}")
            if chip.stroke:
                opts.append(f"draw={self.color(chip.stroke)}, line width={bp(chip.width)}")
            style = ", ".join(
                opts
                + [
                    f"rounded corners={bp(chip.radius)}",
                    f"inner xsep={bp(chip.pad_x)}",
                    f"inner ysep={bp(chip.pad_y)}",
                ]
            )
            nodes = [
                f"\\tikz[baseline=(t.base)]\\node[{style}] (t) {{{self.ink(text_ink, escape(w))}}};"
                for w in words
            ]
            return self.gutter(section, look) + self.ink(
                text_ink, "\\noindent " + f"\\hspace{{{bp(chip.gap)}}}".join(nodes), par=True
            )
        if look.mode == "flow":
            parts = [
                (
                    self.ink(label_ink, rich(label))
                    + escape(look.sep)
                    + self.ink(text_ink, rich(text))
                    + escape(look.suffix)
                )
                if text.strip()
                else self.ink(label_ink, rich(label))
                for label, text in pairs
            ]
            return self.ink(
                text_ink,
                "\\noindent " + self.gutter(section, look) + escape(look.joiner).join(parts),
                par=True,
            )
        for n, (label, text) in enumerate(pairs):
            out.append(mark("item", section.id, n))
            gap = self.gap(look.item_gap) if n else ""
            gutter = self.gutter(section, look) if n == 0 else ""
            if look.mode == "inline":
                body = (
                    self.ink(label_ink, rich(label)) + escape(look.sep) if label.strip() else ""
                ) + self.ink(text_ink, rich(text))
                out.append(gap + self.ink(text_ink, "\\noindent " + gutter + body, par=True))
            elif look.mode == "stacked":
                out.append(
                    gap
                    + self.ink(label_ink, "\\noindent " + gutter + rich(label), par=True)
                    + self.ink(text_ink, rich(text), par=True)
                )
            elif look.mode == "label":
                out.append(
                    gap
                    + self.ink(label_ink, "\\noindent " + gutter + rich(label or text), par=True)
                )
            else:
                out.append(
                    gap + self.ink(text_ink, "\\noindent " + gutter + rich(text or label), par=True)
                )
        return "\n".join(out)

    def lines(self, section: Section, look: Look) -> str:
        texts = [it.text for it in section.items] if section.kind == "grid" else list(section.items)
        ink = look.inks.get("text")
        if look.mode == "flow":
            return self.ink(
                ink,
                "\\noindent "
                + self.gutter(section, look)
                + escape(look.joiner).join(rich(t) for t in texts),
                par=True,
            )
        if look.bullet.kind != "none":
            return self.gutter(section, look) + self.bullets(texts, look, ink)
        if section.kind == "grid" and look.columns > 1:
            cells = [
                f"\\makebox[\\dimexpr\\linewidth/{look.columns}\\relax][l]{{{rich(t)}}}"
                for t in texts
            ]
            rows = [
                "".join(cells[i : i + look.columns]) for i in range(0, len(cells), look.columns)
            ]
            return "\n".join(
                (self.gap(look.item_gap) if n else "") + self.ink(ink, "\\noindent " + r, par=True)
                for n, r in enumerate(rows)
            )
        return "\n".join(
            mark("item", section.id, n)
            + "\n"
            + (self.gap(look.item_gap) if n else "")
            + self.ink(
                ink,
                "\\noindent " + (self.gutter(section, look) if n == 0 else "") + rich(t),
                par=True,
            )
            for n, t in enumerate(texts)
        )

    def section(self, section: Section, look: Look, frame: Frame) -> str:
        head = self.title(section, look, frame.w)
        if section.kind in ("experience", "education", "projects"):
            body = self.entries(section, look)
        elif section.kind in ("skills", "languages"):
            body = self.pairs(section, look)
        else:
            body = self.lines(section, look)
        return head + "\n" + body

    def frame(self, frame: Frame) -> str:
        blocks = "\n".join(self.block(frame, b, n == 0) for n, b in enumerate(frame.blocks))
        return (
            f"\\begin{{textblock}}{{{frame.w:.2f}}}({frame.x:.2f},{frame.y:.2f})\n"
            "\\setlength{\\parindent}{0pt}\\setlength{\\parskip}{0pt}\\raggedright\n"
            f"{blocks}\n{mark('none')}\n\\end{{textblock}}"
        )

    def document(self) -> str:
        frames = "\n\n".join(self.frame(f) for f in self.layout.frames)
        background = self.background()
        font_lines = []
        for font_id in sorted(self.fonts):
            family = fonts.get(font_id)
            font_lines.append(
                f"\\newfontfamily\\cvf{font_id}{{{family.prefix}}}"
                f"[Path={family.folder.as_posix()}/, Extension=.ttf, "
                "UprightFont=*-Regular, BoldFont=*-Bold, ItalicFont=*-Italic, "
                "BoldItalicFont=*-BoldItalic, Numbers=Proportional, Ligatures={TeX, CommonOff}]"
            )
        colors = "\n".join(
            f"\\definecolor{{{_color(c)}}}{{HTML}}{{{c}}}" for c in sorted(self.colors)
        )
        page = f"paperwidth={bp(self.layout.width)},paperheight={bp(self.layout.height)},margin=0pt"
        return f"""% CV cloné de son PDF d'origine, généré par CV Builder.
% Modifier content.json plutôt que ce fichier.
\\documentclass{{article}}
\\usepackage[{page}]{{geometry}}
\\usepackage{{fontspec}}
\\XeTeXgenerateactualtext=1
\\usepackage{{xcolor,graphicx,tikz,eso-pic}}
\\usepackage[absolute]{{textpos}}
\\usepackage[hidelinks]{{hyperref}}
\\setlength{{\\TPHorizModule}}{{1bp}}\\setlength{{\\TPVertModule}}{{1bp}}
\\pagestyle{{empty}}\\setlength{{\\parindent}}{{0pt}}\\setlength{{\\parskip}}{{0pt}}
\\setlength{{\\emergencystretch}}{{1em}}
{chr(10).join(font_lines)}
{colors}
\\begin{{document}}
{background}
{frames}
\\null
\\end{{document}}
"""


def render(layout: CloneLayout, content: CVContent, photo: str | None = PHOTO) -> str:
    writer = Writer(layout, content, photo)
    # Le corps d'abord : il note les polices et couleurs dont le préambule a besoin.
    writer.document()
    return writer.document()
