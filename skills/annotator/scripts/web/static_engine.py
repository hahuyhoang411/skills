"""Browserless ("static") engine for the web route. Stdlib + Pillow; PyMuPDF / rsvg-convert / cairosvg for SVG.

Used when Chromium cannot be launched (typical in ChatGPT's sandbox) so the web route still produces the full,
figure-aware annotated HTML instead of silently degrading. It mirrors scripts/web/js/common.js + extract.js:
same article root, same leaf blocks, same media list, same ids (p1.., f1..), so annotations.json written against
either engine anchors the same way in the overlay (overlay.js runs in the READER's browser when the file is opened).

What it cannot do (and the callers must say so): run page JavaScript, apply CSS (visibility/size filters are
approximated from attributes), screenshot canvas/iframe/video, make a PDF, or look at the finished page.
"""
import base64, html, io, mimetypes, re, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption", "pre", "td", "th", "dd", "dt", "summary"}
MEDIA = {"img", "video", "svg", "canvas", "iframe"}
SKIP_TEXT = {"script", "style", "noscript", "template", "math", "head", "title"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
CLOSES = {"p": {"p"}, "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "tr": {"tr", "td", "th"}, "td": {"td", "th"},
          "th": {"td", "th"}, "option": {"option"}}
NOISE_ANCESTORS = {"nav", "footer", "button"}
# HTML parsing rule: these start tags implicitly close an open <p> (browsers build a different tree than a naive stack parser)
CLOSE_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset", "figcaption", "figure", "footer", "form",
           "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "main", "menu", "nav", "ol", "p", "pre", "section", "table", "ul"}
SCOPE_STOP = {"td", "th", "table", "button", "caption", "template", "svg", "object", "marquee", "applet", "html", "body"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "start", "end", "tagtext")

    def __init__(self, tag, attrs=None, parent=None, start=0, tagtext=""):
        self.tag, self.attrs, self.parent = tag, dict(attrs or {}), parent
        self.children, self.start, self.end, self.tagtext = [], start, start, tagtext

    def iter(self):
        """Elements in document order (like querySelectorAll)."""
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent


class _Parser(HTMLParser):
    def __init__(self, src):
        super().__init__(convert_charrefs=True)
        self.src = src
        self.lines = [0]
        for m in re.finditer("\n", src):
            self.lines.append(m.end())
        self.root = Node("#root")
        self.cur = self.root

    def off(self):
        ln, col = self.getpos()
        return self.lines[ln - 1] + col

    def _close_p(self):
        n = self.cur
        while n is not None and n is not self.root and n.tag not in SCOPE_STOP:
            if n.tag == "p":
                self.cur = n.parent
                n.end = self.off()
                return
            n = n.parent

    def handle_starttag(self, tag, attrs):
        if tag in CLOSE_P:
            self._close_p()
        if tag in HEADINGS and self.cur.tag in HEADINGS:
            self.cur = self.cur.parent
        for closer in list(CLOSES.get(tag, ())):
            if self.cur.tag == closer:
                self.cur.end = self.off()
                self.cur = self.cur.parent
        raw = self.get_starttag_text() or ""
        n = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur, self.off(), raw)
        self.cur.children.append(n)
        n.end = n.start + len(raw)
        if tag not in VOID and not raw.rstrip().endswith("/>"):
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        n = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur, self.off(), raw)
        n.end = n.start + len(raw)
        self.cur.children.append(n)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is None or n is self.root:
            return
        gt = self.src.find(">", self.off())
        n.end = (gt + 1) if gt >= 0 else self.off()
        self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)

    def close(self):
        super().close()
        while self.cur is not self.root:
            self.cur.end = len(self.src)
            self.cur = self.cur.parent


def parse(src):
    p = _Parser(src)
    p.feed(src)
    p.close()
    return p.root


# ---------------------------------------------------------------- text helpers
def norm(s):
    return " ".join(s.split())


def _is_bg(n):
    """Element with an inline CSS background-image that is a leaf visual (mirrors common.js isBg)."""
    return (n.tag not in MEDIA and re.search(r"background-image\s*:[^;]*url\(", n.attrs.get("style") or "", re.I) is not None
            and not any(c.tag in BLOCK for c in n.iter()))


def _hidden(n):
    a = n.attrs
    st = (a.get("style") or "").replace(" ", "").lower()
    return "hidden" in a or "display:none" in st or "visibility:hidden" in st or a.get("type") == "hidden"


def _skipped(n):
    """True when text/media under n is not rendered (approximation of common.js SKIP + visible())."""
    for x in [n, *n.ancestors()]:
        if x.tag in SKIP_TEXT or _hidden(x):
            return True
        cls = (x.attrs.get("class") or "").split()
        if "katex" in cls or x.tag == "math":
            return True
    return False


def text_of(n):
    out = []

    def walk(e):
        for c in e.children:
            if isinstance(c, str):
                out.append(c)
            elif c.tag in SKIP_TEXT or "katex" in (c.attrs.get("class") or "").split():
                continue
            else:
                walk(c)
    walk(n)
    return norm("".join(out))


def _has_block_desc(n):
    return any(c.tag in BLOCK for c in n.iter())


def pick_root(body):
    def score(e):
        return sum(len(text_of_plain(p)) for p in ([e] if e.tag == "p" else []) + [x for x in e.iter() if x.tag == "p"])

    best, bs = None, 0
    for c in body.iter():
        if c.tag in ("article", "main") or c.attrs.get("role") == "main":
            s = score(c)
            if s > bs:
                best, bs = c, s
    total = score(body)
    if not (best and bs >= min(500, total * 0.5)):
        best = body
        while True:
            nxt = None
            for ch in best.children:
                if isinstance(ch, Node) and score(ch) >= 0.8 * total:
                    nxt = ch
                    break
            if nxt is None:
                break
            best = nxt
    return best


def text_of_plain(n):
    out = []

    def walk(e):
        for c in e.children:
            out.append(c) if isinstance(c, str) else walk(c)
    walk(n)
    return "".join(out)


# ---------------------------------------------------------------- figures
def _dim(v):
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(px)?\s*$", v or "")
    return int(float(m.group(1))) if m else None


def svg_to_png(svg_bytes, out_png, max_w=1100):
    """Rasterise an SVG with whatever is installed. Returns (ok, how_or_reason)."""
    if b"xmlns" not in svg_bytes[:400]:
        svg_bytes = svg_bytes.replace(b"<svg", b'<svg xmlns="http://www.w3.org/2000/svg"', 1)
    try:
        import pymupdf
        doc = pymupdf.open(stream=svg_bytes, filetype="svg")
        pg = doc[0]
        z = min(4.0, max(1.0, max_w / max(1.0, pg.rect.width)))
        pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False).save(str(out_png))
        return True, "pymupdf"
    except Exception as e:
        why = f"pymupdf: {str(e)[:60]}"
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_bytes, write_to=str(out_png), output_width=max_w, background_color="white")
        return True, "cairosvg"
    except Exception as e:
        why += f"; cairosvg: {str(e)[:40]}"
    import shutil, subprocess
    if shutil.which("rsvg-convert"):
        r = subprocess.run(["rsvg-convert", "-w", str(max_w), "-b", "white", "-o", str(out_png)], input=svg_bytes, capture_output=True)
        if r.returncode == 0 and Path(out_png).exists():
            return True, "rsvg-convert"
        why += "; rsvg-convert failed"
    return False, why


def svg_rasterizer_available():
    for mod in ("pymupdf", "cairosvg"):
        try:
            __import__(mod)
            return mod
        except Exception:
            pass
    import shutil
    return "rsvg-convert" if shutil.which("rsvg-convert") else ""


class UnsafePath(Exception):
    pass


def safe_local(src, base_dir, root):
    """Resolve a relative asset path from a saved page. Never leaves `root` (zip-slip / ../ / absolute paths)."""
    ref = urllib.parse.unquote(src.split("#")[0].split("?")[0])
    if ref.startswith("file:"):
        ref = urllib.parse.urlparse(ref).path
    p = (root / ref.lstrip("/")) if ref.startswith("/") else (base_dir / ref)
    p = p.resolve()
    root = root.resolve()
    if root != p and root not in p.parents:
        raise UnsafePath(f"path escapes the saved page folder: {src[:60]}")
    return p


def load_bytes(src, base_dir, base_url, root=None):
    """data: URI, local file inside the saved page folder, or http(s) (only when the sandbox has internet)."""
    if src.startswith("data:"):
        head, _, data = src.partition(",")
        raw = base64.b64decode(data) if ";base64" in head else urllib.parse.unquote_to_bytes(data)
        return raw, head[5:].split(";")[0]
    if re.match(r"^https?://", src) or src.startswith("//") or (base_url and base_url.startswith("http")):
        url = urllib.parse.urljoin(base_url or "", src)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(), r.headers.get_content_type()
    p = safe_local(src, base_dir, root or base_dir)
    return p.read_bytes(), mimetypes.guess_type(str(p))[0] or ""


def first_srcset(v):
    for part in (v or "").split(","):
        u = part.strip().split(" ")[0]
        if u:
            return u
    return ""


def _css_props(style):
    d = {}
    for part in (style or "").split(";"):
        k, _, v = part.partition(":")
        if k.strip():
            d[k.strip().lower()] = v.strip()
    return d


def bg_crop(im, style):
    """Emulate the visible part of a CSS background-image (cover/contain/auto + position) when the element's px size is
    given inline. Returns (image, note). Without a known box the full image is returned and the note says so."""
    from PIL import Image
    p = _css_props(style)
    W, H = _dim(p.get("width")), _dim(p.get("height"))
    if not (W and H):
        return im, "background image: full image shown; element size comes from CSS, so the page may crop it differently"
    size = p.get("background-size", "auto").split()[0] if p.get("background-size") else "auto"
    sw, sh = im.size
    if size == "cover":
        k = max(W / sw, H / sh)
    elif size == "contain":
        k = min(W / sw, H / sh)
    elif size == "auto":
        k = 1.0
    else:
        return im, f"background-size:{size} not emulated; full image shown"
    pos = (p.get("background-position") or "0% 0%").replace("center", "50%").replace("left", "0%").replace("right", "100%") \
        .replace("top", "0%").replace("bottom", "100%").split()
    pos = (pos + ["50%"])[:2]
    try:
        px, py = [float(v.rstrip("%")) / 100 for v in pos]
    except ValueError:
        px = py = 0.5
    nw, nh = max(1, round(sw * k)), max(1, round(sh * k))
    scaled = im.resize((nw, nh))
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    canvas.paste(scaled, (round((W - nw) * px), round((H - nh) * py)))
    return canvas, f"background-size:{size} cropped to the {W}x{H} element (repeat/clip emulation approximate)"


def pillow_png(raw, out_png):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im.seek(0)
    im.convert("RGBA").save(out_png)
    return im.size


# ---------------------------------------------------------------- extraction
def extract(src_html, out, base_dir, base_url, frames_k, gif_frames, root=None):
    """Returns (data, tagged_html_info). data matches extract.js output plus engine info."""
    tree = parse(src_html)
    body = next((n for n in tree.iter() if n.tag == "body"), tree)
    title_n = next((n for n in tree.iter() if n.tag == "title"), None)
    title = norm(text_of_plain(title_n)) if title_n else ""
    art = pick_root(body)

    figs, paras, order, inject = [], [], [], []
    pi = fi = 0
    media_idx = -1
    for el in art.iter():
        if el.tag in MEDIA or _is_bg(el):
            if any(a.tag in NOISE_ANCESTORS or a.tag == "svg" for a in el.ancestors()) or _skipped(el):
                continue
            # size filter approximated from attributes (common.js uses the rendered box)
            w, h = _dim(el.attrs.get("width")), _dim(el.attrs.get("height"))
            if el.tag == "svg" and not (w and h):
                vb = (el.attrs.get("viewbox") or "").replace(",", " ").split()
                if len(vb) == 4:
                    try:
                        w, h = w or int(float(vb[2])), h or int(float(vb[3]))
                    except ValueError:
                        pass
            if (w and w < 64) or (h and h < 64):
                continue
            media_idx += 1
            fi += 1
            fid = f"f{fi}"
            f = _figure(el, fid, media_idx, out, base_dir, base_url, src_html, frames_k, gif_frames, root)
            if f is None:           # decorative/tiny after loading
                fi -= 1
                media_idx -= 1
                continue
            fig = next((a for a in el.ancestors() if a.tag == "figure"), None)
            cap = next((c for c in fig.iter() if c.tag == "figcaption"), None) if fig else None
            f["caption"] = text_of(cap) if cap else ""
            figs.append(f)
            order.append(fid)
            inject.append((el, fid))
        elif el.tag in BLOCK:
            if _has_block_desc(el) or _skipped(el):
                continue
            t = text_of(el)
            if not t:
                continue
            pi += 1
            paras.append({"id": f"p{pi}", "tag": el.tag, "text": t})
            order.append(f"p{pi}")
    return {"title": title, "url": base_url, "paragraphs": paras, "figures": figs, "order": order}, inject


def _figure(el, fid, idx, out, base_dir, base_url, src_html, frames_k, gif_frames, root=None):
    png = out / "figures" / f"{fid}.png"
    f = {"id": fid, "index": idx, "kind": el.tag if el.tag != "iframe" else "embed", "src": "", "alt": "",
         "caption": "", "w": _dim(el.attrs.get("width")) or 0, "h": _dim(el.attrs.get("height")) or 0,
         "natural_w": 0, "natural_h": 0, "duration": None, "frames": [], "engine": "static"}
    f["tag_offset"] = el.start
    a = el.attrs
    f["alt"] = (a.get("alt") or a.get("aria-label") or a.get("title") or "").strip()
    try:
        if el.tag == "img" or _is_bg(el):
            f["kind"] = "img" if el.tag == "img" else "background"
            if el.tag == "img":
                src = a.get("src") or a.get("data-src") or first_srcset(a.get("srcset") or a.get("data-srcset"))
                pic = el.parent if el.parent is not None and el.parent.tag == "picture" else None
                if pic is not None:
                    srcs = [first_srcset(c.attrs.get("srcset")) for c in pic.children if isinstance(c, Node) and c.tag == "source"]
                    src = src or next((x for x in srcs if x), "")
                    f["render"] = "picture: <img> src used; <source> art-direction not evaluated"
            else:
                m = re.search(r"url\((['\"]?)(.*?)\1\)", a.get("style") or "")
                src = m.group(2) if m else ""
            if src.startswith("data:image/gif;base64,R0lGODlhAQABA"):       # 1x1 lazy placeholder
                src = a.get("data-src") or first_srcset(a.get("data-srcset")) or src
            f["src"] = src
            f["figure_container"] = next((x.tag for x in el.ancestors() if x.tag in ("figure", "picture")), "")
            if not src:
                f["error"] = "image did not load (no src)"
                return f
            try:
                raw, mime = load_bytes(src, base_dir, base_url, root)
            except Exception as e:
                f["error"] = f"image did not load ({e.__class__.__name__}: {str(e)[:60]})"
                return f
            if "svg" in mime or raw.lstrip()[:5] in (b"<?xml", b"<svg ") or raw.lstrip()[:4] == b"<svg":
                ok, how = svg_to_png(raw, png)
                if not ok:
                    (out / "figures" / f"{fid}.svg").write_bytes(raw)
                    f["error"] = f"svg could not be rasterised ({how}); source saved as figures/{fid}.svg, NOT viewable as an image"
                    return f
                from PIL import Image
                f["natural_w"], f["natural_h"] = Image.open(png).size
                f["render"] = f"svg rasterised with {how}; page CSS not applied"
            else:
                f["natural_w"], f["natural_h"] = pillow_png(raw, png)
                if f["kind"] == "background":
                    from PIL import Image
                    im2, note = bg_crop(Image.open(png).convert("RGBA"), a.get("style"))
                    im2.save(png)
                    f["render"] = note
                    f["natural_w"], f["natural_h"] = im2.size
                frs, animated = gif_frames(raw, str(out / "figures" / fid), frames_k)
                if animated:
                    f["kind"] = "animated"
                    f["frames"] = [dict(fr, file=f"figures/{fr['file']}") for fr in frs]
            if (f["natural_w"] < 64 or f["natural_h"] < 64) and not (f["w"] and f["h"]):
                png.unlink(missing_ok=True)
                return None                                      # tracking pixel / icon
            f["file"] = f"figures/{png.name}"
        elif el.tag == "svg":
            raw = src_html[el.start:el.end].encode("utf-8")
            ok, how = svg_to_png(raw, png)
            if not ok:
                (out / "figures" / f"{fid}.svg").write_bytes(raw)
                f["error"] = f"inline svg could not be rasterised ({how}); source saved as figures/{fid}.svg, NOT viewable as an image"
                return f
            from PIL import Image
            f["natural_w"], f["natural_h"] = Image.open(png).size
            f["render"] = f"inline svg rasterised with {how}; page CSS not applied, check against the caption/text"
            f["file"] = f"figures/{png.name}"
            (out / "figures" / f"{fid}.svg").write_bytes(raw)
        elif el.tag == "video":
            poster = a.get("poster")
            f["error"] = "video cannot be sampled without a browser" + ("; poster only" if poster else "")
            if poster:
                try:
                    raw, _ = load_bytes(poster, base_dir, base_url, root)
                    f["natural_w"], f["natural_h"] = pillow_png(raw, png)
                    f["file"] = f"figures/{png.name}"
                    f["error"] = "poster frame only: the video itself was not inspected"
                    f["frame_error"] = f["error"]
                except Exception:
                    pass
        elif el.tag == "canvas":
            f["error"] = "canvas is drawn by JavaScript: not inspectable without a browser"
        else:
            f["note"] = "embedded iframe: contents not inspectable"
            f["error"] = "iframe not captured without a browser"
    except Exception as e:
        f["error"] = f"figure extraction failed: {e.__class__.__name__}: {str(e)[:80]}"
    return f


# ---------------------------------------------------------------- output HTML
INLINE_MAX = 12_000_000


def _to_data_uri(src, base_dir, base_url, root=None):
    try:
        raw, mime = load_bytes(src, base_dir, base_url, root)
    except Exception:
        return None
    if len(raw) > INLINE_MAX:
        return None
    mime = mime or mimetypes.guess_type(src.split("?")[0])[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _inline_attr(tag_text, attr, base_dir, base_url, root):
    m = re.search(r'(\s%s\s*=\s*)("([^"]*)"|\'([^\']*)\')' % re.escape(attr), tag_text, re.I)
    if not m:
        return tag_text
    val = html.unescape(m.group(3) if m.group(3) is not None else m.group(4))
    if attr == "srcset":
        val = first_srcset(val)
    if not val or val.startswith(("data:", "#", "blob:")) or re.match(r"^(https?:)?//", val):
        return tag_text
    du = _to_data_uri(val, base_dir, base_url, root)
    return tag_text[:m.start()] + m.group(1) + '"' + du + '"' + tag_text[m.end():] if du else tag_text


def build_html(src_html, inject, base_dir, base_url, boot, root=None):
    """Original page + data-wa-id on each figure + EVERY local image/poster/stylesheet inlined (single self-contained file)
    + page scripts removed + overlay boot injected."""
    tree = parse(src_html)
    ids = {el.start: fid for el, fid in inject}
    edits = []                                           # (offset, remove_len, text)
    for el in tree.iter():
        tt = el.tagtext
        new = tt
        fid = ids.get(el.start)
        if el.tag == "img":
            new = _inline_attr(new, "src", base_dir, base_url, root)
            new = _inline_attr(new, "data-src", base_dir, base_url, root)
            if "srcset" in new.lower() and 'src="data:' in new:
                new = re.sub(r'\ssrcset\s*=\s*("[^"]*"|\'[^\']*\')', "", new, flags=re.I)
        elif el.tag == "source":
            new = _inline_attr(new, "srcset", base_dir, base_url, root)
            new = _inline_attr(new, "src", base_dir, base_url, root)
        elif el.tag == "video":
            new = _inline_attr(new, "poster", base_dir, base_url, root)
        if "background-image" in new.lower():
            def _bg(m):
                u = html.unescape(m.group(2))
                if not u or u.startswith("data:") or re.match(r"^(https?:)?//", u):
                    return m.group(0)
                du = _to_data_uri(u, base_dir, base_url, root)
                return "url(%s%s%s)" % (m.group(1), du, m.group(1)) if du else m.group(0)
            new = re.sub(r"url\((['\"]?)(.*?)\1\)", _bg, new)
        if fid:
            new = re.sub(r"^<(\w+)", r'<\1 data-wa-id="%s"' % fid, new, count=1)
        if new != tt:
            edits.append((el.start, len(tt), new))
        if el.tag == "link" and re.search(r"stylesheet", el.attrs.get("rel") or "", re.I):
            href = el.attrs.get("href") or ""
            if href and not href.startswith("data:") and not re.match(r"^(https?:)?//", href):
                try:
                    css = load_bytes(href, base_dir, base_url, root)[0].decode("utf-8", "replace")
                    edits.append((el.start, len(tt), "<style>" + css.replace("</style", "<\\/style") + "</style>"))
                except Exception:
                    pass
    out = src_html
    for off, ln, new in sorted(edits, key=lambda e: -e[0]):
        out = out[:off] + new + out[off + ln:]
    out = re.sub(r"<script\b[^>]*>.*?</script>", "", out, flags=re.S | re.I)
    if base_url.startswith("http") and not re.search(r"<base\b", out, re.I):
        out = re.sub(r"(<head[^>]*>)", r'\1<base href="%s">' % html.escape(base_url, quote=True), out, count=1, flags=re.I)
    return out.replace("</body>", boot + "</body>") if "</body>" in out else out + boot


def inject_for(src_html, figures):
    """Re-locate figure elements in the source by the offsets recorded at fetch time. Returns (inject, lost_ids)."""
    tree = parse(src_html)
    by = {n.start: n for n in tree.iter()}
    inject, lost = [], []
    for f in figures:
        n = by.get(f.get("tag_offset"))
        if n is None:
            lost.append(f["id"])
        else:
            inject.append((n, f["id"]))
    return inject, lost
