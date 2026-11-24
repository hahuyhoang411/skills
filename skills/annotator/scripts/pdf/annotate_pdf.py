#!/usr/bin/env python3
"""Build an annotated, color-coded reading copy of a paper PDF.

Usage:
  python annotate_pdf.py paper.pdf annotations.json out.pdf --passes passes.json [--extract-dir DIR] [--font FILE] [--allow-missing] [--skip-gates]

What it produces
  * Reading-map cover pages (verdict, legend, top issues, must-read, per-page digest, cross-links)
  * Every original page kept (text stays selectable) with a wide right-hand margin panel:
      - native highlight / underline / squiggle annotations (hover shows the note in any viewer)
      - numbered brackets + connector lines + color-coded note cards, like handwritten margin notes
      - clickable citation markers -> jump to the reference entry
      - clickable cross-links between related passages ("link the dots")
  * A citation index at the end (which reference is cited on which pages)
Input schema: see references/pdf-annotation-schema.md (worked example: assets/example_pdf_annotations.json)
"""
import json, os, re, sys, datetime
from pathlib import Path
import pymupdf

# ---------------------------------------------------------------- constants
TYPES = {  # key: (rgb, vi label, en label, vi description, en description, rank for overflow priority)
 "MUST_READ": ((1.00, 0.58, 0.00), "ĐỌC KỸ",   "READ CLOSELY", "Đoạn quan trọng nhất, phải đọc kỹ", "Most important passage; read closely", 9),
 "CLAIM":     ((0.20, 0.45, 0.95), "LUẬN ĐIỂM", "CLAIM",        "Tác giả khẳng định / đóng góp chính", "Author's claim or contribution", 7),
 "EVIDENCE":  ((0.15, 0.68, 0.33), "BẰNG CHỨNG","EVIDENCE",     "Dữ liệu/hình/số liệu hỗ trợ luận điểm", "Data/figure/number supporting a claim", 6),
 "CONCERN":   ((0.90, 0.15, 0.15), "NGHI NGẠI", "CONCERN",      "Bằng chứng yếu, nói quá, thiếu đối chứng", "Weak evidence, overclaim, missing control", 10),
 "ERROR":     ((0.75, 0.10, 0.60), "LỖI",       "ERROR",        "Sai sót, mâu thuẫn, số liệu không khớp", "Mistake, inconsistency, mismatch", 10),
 "METHOD":    ((0.50, 0.32, 0.85), "PHƯƠNG PHÁP","METHOD",      "Chi tiết thiết kế/phương pháp đáng chú ý", "Design/method detail worth noting", 5),
 "GAP":       ((0.95, 0.80, 0.05), "KHOẢNG TRỐNG","GAP",        "Khoảng trống nghiên cứu / hạn chế được nêu", "Research gap or stated limitation", 7),
 "CITE":      ((0.05, 0.65, 0.68), "TRÍCH DẪN",  "CITATION",    "Tài liệu tham khảo đáng theo dõi / lạc đề", "Reference worth following up / off-topic", 6),
 "QUESTION":  ((0.95, 0.40, 0.65), "CÂU HỎI",    "QUESTION",    "Câu hỏi cần tự trả lời hoặc hỏi tác giả", "Question to answer or ask the authors", 8),
 "SKIP":      ((0.55, 0.55, 0.58), "CÓ THỂ BỎ QUA","SKIM/SKIP", "Đọc lướt được", "Safe to skim", 1),
}
STR = {
 "vi": dict(cover="BẢN ĐỒ ĐỌC", pass1="Lượt 1 – Có đáng đọc tiếp không?", legend="Chú giải màu", top="Cần chú ý nhất",
            must="Đoạn phải đọc kỹ", digest="Tóm tắt từng trang", cites="Trích dẫn đáng theo dõi",
            links="Các điểm nối với nhau", unanch="Chưa định vị được trong PDF (kiểm tra lại trích dẫn)",
            pg="tr.", ps="L", page="Trang", over="Ghi chú tràn từ trang", citeidx="Chỉ mục trích dẫn",
            cited_on="trích ở", stats="Thống kê", plan="Kế hoạch đọc", ref="Tài liệu",
            five=dict(category="Loại bài", context="Bối cảnh", correctness="Giả định có hợp lý?", contributions="Đóng góp", clarity="Độ rõ ràng"),
            verdict="Kết luận nhanh", extra_page="(ghi chú ở trang phụ)", back="từ", to="tới"),
 "en": dict(cover="READING MAP", pass1="Pass 1 – Worth reading further?", legend="Color legend", top="Needs attention first",
            must="Must read closely", digest="Page-by-page digest", cites="References worth following",
            links="Connected passages", unanch="Could not locate in PDF (check the quote)",
            pg="p.", ps="P", page="Page", over="Notes overflowing from page", citeidx="Citation index",
            cited_on="cited on", stats="Stats", plan="Reading plan", ref="Ref",
            five=dict(category="Category", context="Context", correctness="Assumptions valid?", contributions="Contributions", clarity="Clarity"),
            verdict="Quick verdict", extra_page="(note on overflow page)", back="from", to="to"),
}
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                   "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                   "C:\\Windows\\Fonts\\arial.ttf"]
BOLD_CANDIDATES = [p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace("arial.ttf", "arialbd.ttf") for p in FONT_CANDIDATES]
INK = (0.12, 0.12, 0.14)

def pale(c, k=0.88): return tuple(1 - (1 - x) * (1 - k) for x in c)
def dark(c, k=0.72): return tuple(x * k for x in c)
def norm(t): return re.sub(r"[^\w]", "", t.lower())

# ---------------------------------------------------------------- fonts / text helpers
class Fonts:
    def __init__(self, reg, bold):
        self.reg_path, self.bold_path = reg, bold
        self.reg, self.bold = pymupdf.Font(fontfile=reg), pymupdf.Font(fontfile=bold)
    def install(self, page):
        page.insert_font(fontname="UR", fontfile=self.reg_path)
        page.insert_font(fontname="UB", fontfile=self.bold_path)
    def w(self, text, size, bold=False): return (self.bold if bold else self.reg).text_length(text, fontsize=size)
    def wrap(self, text, size, maxw, bold=False):
        out = []
        for para in str(text).split("\n"):
            line = ""
            for word in para.split(" "):
                trial = (line + " " + word).strip() if line else word
                if self.w(trial, size, bold) <= maxw or not line: line = trial
                else: out.append(line); line = word
            out.append(line)
        return out

def find_font(user_font):
    reg = user_font or next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if not reg: sys.exit("No Unicode TTF font found (needed for Vietnamese). Pass --font /path/to/font.ttf")
    bold = next((p for p in BOLD_CANDIDATES if os.path.exists(p)), reg) if not user_font else reg
    return Fonts(reg, bold)

# ---------------------------------------------------------------- quote anchoring
def word_match(page, quote):
    words = page.get_text("words")
    toks = [norm(w[4]) for w in words]
    qt = [norm(t) for t in quote.split() if norm(t)]
    best = (0, None, None)
    for qs in range(0, max(1, len(qt) - 2)):
        for i in range(len(toks)):
            if toks[i] != qt[qs]: continue
            n = 0
            while i + n < len(toks) and qs + n < len(qt) and toks[i + n] == qt[qs + n]: n += 1
            if n > best[0]: best = (n, i, qs)
        if best[0] >= len(qt) - qs: break
    n, i, _ = best
    if n < min(3, len(qt)): return []
    grp = {}
    for w in words[i:i + n]: grp.setdefault((w[5], w[6]), []).append(pymupdf.Rect(w[:4]))
    rects = []
    for rs in grp.values():
        r = rs[0]
        for x in rs[1:]: r |= x
        rects.append(r)
    return rects

def locate(page, quote, occ=0):
    q = " ".join(quote.split())
    for v in (q, q.replace("fi", "\ufb01").replace("fl", "\ufb02"), q[:90], " ".join(q.split()[:8])):
        if not v: continue
        hits = page.search_for(v)
        if hits:
            return [hits[occ]] if (len(v) < 25 and len(hits) > occ) else hits
    return word_match(page, q)

# ---------------------------------------------------------------- reading-map writer
class Flow:
    def __init__(self, doc, fonts, S, start_index, dry=False):
        self.doc, self.f, self.S, self.dry = doc, fonts, S, dry
        self.idx, self.page, self.y, self.W, self.H, self.m = start_index, None, 0, 595, 842, 44
        self.pages = 0; self.newpage()
    def newpage(self):
        self.page = self.doc.new_page(pno=self.idx + self.pages, width=self.W, height=self.H); self.pages += 1
        self.f.install(self.page); self.y = self.m
    def need(self, h):
        if self.y + h > self.H - self.m: self.newpage()
    def text(self, txt, size=9, color=INK, bold=False, indent=0, link=None, gap=3):
        lines = self.f.wrap(txt, size, self.W - 2 * self.m - indent, bold)
        for ln in lines:
            self.need(size + 3)
            if not self.dry:
                self.page.insert_text((self.m + indent, self.y + size), ln, fontname="UB" if bold else "UR", fontsize=size, color=color)
                if link:
                    r = pymupdf.Rect(self.m + indent, self.y, self.m + indent + self.f.w(ln, size, bold), self.y + size + 3)
                    self.page.insert_link({"kind": pymupdf.LINK_GOTO, "from": r, "page": link[0], "to": pymupdf.Point(0, max(0, link[1] - 30))})
            self.y += size + 2.5
        self.y += gap
    def chip(self, color, label, desc):
        self.need(14)
        if not self.dry:
            self.page.draw_rect(pymupdf.Rect(self.m, self.y, self.m + 104, self.y + 11), color=color, fill=color)
            self.page.insert_text((self.m + 3, self.y + 8.2), label, fontname="UB", fontsize=6.5, color=(1, 1, 1))
            self.page.insert_text((self.m + 112, self.y + 8.2), desc, fontname="UR", fontsize=8, color=INK)
        self.y += 15

# ---------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    if len(args) < 3: sys.exit(__doc__)
    src_path, ann_path, out_path = args[:3]
    spec = json.load(open(ann_path))

    # gates: three-pass record + note substance (scripts/gates.py). Unknown note types are errors, not silently remapped.
    bad_types = sorted({str(a.get("type", "MUST_READ")).upper() for a in spec.get("annotations", [])} - set(TYPES))
    if bad_types:
        sys.exit(f"ERROR: unsupported annotation type(s) {bad_types}. Allowed: {sorted(TYPES)} (references/pdf-annotation-schema.md)")
    if "--skip-gates" not in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import gates
        if not opt("--passes"):
            sys.exit("ERROR: --passes passes.json is required: record the three passes, evidence ledger and figure inspections first (references/gates.md)")
        anns_ = spec.get("annotations", [])
        high = [a.get("key") for a in anns_ if a.get("priority") == "high"]
        e1, w1 = gates.validate_passes(json.load(open(opt("--passes"))), None, [k for k in high if k], require_figure_key=True)
        if any(k is None for k in high):
            e1.append("every priority:'high' annotation needs a 'key' so the evidence ledger can reference it")
        e2, w2 = gates.lint_notes(anns_)
        gates.report(e1 + e2, w1 + w2)
        if e1 or e2:
            sys.exit(1)
    lang = spec.get("lang", "en"); S = STR.get(lang, STR["vi"]); tl = 1 if lang == "vi" else 2; td = 3 if lang == "vi" else 4
    fonts = find_font(opt("--font"))
    reviewer = spec.get("reviewer", "Annotator")
    src = pymupdf.open(src_path); N = len(src)

    # coverage check: every page must have a review entry (forces page-by-page reading)
    reviewed = {p["page"]: p for p in spec.get("pages", [])}
    missing = [i for i in range(1, N + 1) if i not in reviewed]
    if missing and "--allow-missing" not in sys.argv:
        sys.exit(f"ERROR: no page summary for pages {missing}. Read every page (incl. appendix/supplement) and add a 'pages' entry for each.")

    # ---- anchor annotations
    anns, warn = [], []
    for k, a in enumerate(spec.get("annotations", [])):
        a = dict(a); a["_i"] = k; a["type"] = a.get("type", "MUST_READ").upper()
        if a["type"] not in TYPES: warn.append(f"unknown type {a['type']} (ann {k}) -> MUST_READ"); a["type"] = "MUST_READ"
        pg = src[a["page"] - 1]
        rects = locate(pg, a["quote"], a.get("occurrence", 0)) if a.get("quote") else []
        if not rects and a.get("bbox"): rects = [pymupdf.Rect(a["bbox"])]
        a["rects"] = rects
        if not rects: warn.append(f"p.{a['page']} could not anchor: {a.get('quote','')[:60]!r}")
        a["y0"] = min((r.y0 for r in rects), default=40); a["y1"] = max((r.y1 for r in rects), default=48)
        anns.append(a)
    # reference notes -> CITE annotations anchored on the reference entry
    refs = {}
    ed = opt("--extract-dir")
    if ed and os.path.exists(f"{ed}/references.json"): refs = {int(k): v for k, v in json.load(open(f"{ed}/references.json")).items()}
    for num, note in (spec.get("ref_notes") or {}).items():
        r = refs.get(int(num))
        if not r: warn.append(f"ref_notes {num}: reference not found in references.json"); continue
        pg = src[r["page"] - 1]; rects = locate(pg, r["text"][:60]) or [pymupdf.Rect(40, r["y"], 400, r["y"] + 10)]
        anns.append({"page": r["page"], "type": "CITE", "note": f"[{num}] {note}", "rects": rects, "_i": 10_000 + int(num),
                     "y0": min(x.y0 for x in rects), "y1": max(x.y1 for x in rects), "pass": 3, "ref_note": int(num)})
    anns.sort(key=lambda a: (a["page"], a["y0"], a["_i"]))
    for n, a in enumerate(anns, 1): a["n"] = n
    by_key = {a["key"]: a for a in anns if a.get("key")}

    # ---- output doc: content pages
    out = pymupdf.open()
    content_idx = {}
    page_cards = {}
    for a in anns: page_cards.setdefault(a["page"], []).append(a)
    overflow_of = {}
    legend_h = 30
    for pno in range(1, N + 1):
        sp = src[pno - 1]; W, H = sp.rect.width, sp.rect.height; M = max(300, 0.56 * W)
        pg = out.new_page(width=W + M, height=H); content_idx[pno] = len(out) - 1; fonts.install(pg)
        pg.show_pdf_page(pymupdf.Rect(0, 0, W, H), src, pno - 1)
        cards = page_cards.get(pno, [])
        right = max([b[2] for b in sp.get_text("blocks")] + [W * 0.8]); xr0 = min(right + 4, W - 8)
        # native annotations + brackets (with lane assignment)
        lanes = []
        for a in sorted(cards, key=lambda a: a["y0"]):
            col = TYPES[a["type"]][0]
            if a["rects"]:
                quads = [r.quad for r in a["rects"]]
                kind = a["type"]
                if kind == "ERROR": an = pg.add_squiggly_annot(quads=quads)
                elif kind == "CITE": an = pg.add_underline_annot(quads=quads)
                else: an = pg.add_highlight_annot(quads=quads)
                an.set_colors(stroke=col); an.set_opacity(0.22 if kind == "SKIP" else 0.38 if kind != "CITE" else 0.9)
                an.set_info(title=f"{reviewer} · {TYPES[kind][tl]}", content=a.get("note", "")); an.update()
            lane = next((i for i, e in enumerate(lanes) if e < a["y0"] - 1), None)
            if lane is None: lanes.append(0); lane = len(lanes) - 1
            lanes[lane] = a["y1"]; a["lane"] = lane
            x = xr0 + lane * 13
            if a["rects"]:
                pg.draw_polyline([(x - 3, a["y0"]), (x, a["y0"]), (x, a["y1"]), (x - 3, a["y1"])], color=col, width=1.1)
            a["bx"], a["by"] = x, (a["y0"] + a["y1"]) / 2
        # card layout
        top = 8
        summ = reviewed.get(pno, {}).get("summary", "")
        x0, cw = W + 12, M - 20
        def layout(size):
            items = []
            for a in sorted(cards, key=lambda a: a["y0"]):
                lines = fonts.wrap(a.get("note", ""), size, cw - 14)
                extra = []
                for lk in a.get("links", []) or []:
                    t = by_key.get(lk) if isinstance(lk, str) else None
                    if t: extra.append((f"→ #{t['n']} ({S['pg']}{t['page']}) {t.get('title') or TYPES[t['type']][tl]}", t))
                for b in [x for x in anns if a.get("key") and a["key"] in (x.get("links") or [])]:
                    extra.append((f"← #{b['n']} ({S['pg']}{b['page']}) {b.get('title') or TYPES[b['type']][tl]}", b))
                for rn in a.get("refs", []) or []:
                    r = refs.get(int(rn)); extra.append((f"→ [{rn}] {S['pg']}{r['page']}" if r else f"→ [{rn}]", ("ref", r)))
                elines = []
                for t, tgt in extra:
                    for j, ln in enumerate(fonts.wrap(t, size - 0.5, cw - 14)): elines.append((ln, tgt if j == 0 else None))
                h = 5 + (size + 3.5) + len(lines) * (size + 2) + (len(elines) * (size + 1.5) + 2 if elines else 0) + 5
                items.append(dict(a=a, lines=lines, elines=elines, h=h))
            return items
        summ_h = 0
        avail_bottom = H - legend_h - 6
        used = None
        for size in (8, 7.5, 7, 6.5, 6):
            sl = [f"{S['page']} {pno}"] + (fonts.wrap(summ, size, cw - 10) if summ else [])
            summ_h = len(sl) * (size + 2) + 8
            items = layout(size); gap = 4
            # forward pass
            y = top + summ_h + 4
            for it in items:
                it["y"] = max(it["a"]["y0"] - 2, y); y = it["y"] + it["h"] + gap
            # backward pass if overflow bottom
            if items and items[-1]["y"] + items[-1]["h"] > avail_bottom:
                yb = avail_bottom
                for it in reversed(items):
                    it["y"] = min(it["y"], yb - it["h"]); yb = it["y"] - gap
                if items[0]["y"] < top + summ_h + 4: continue
            used = (size, items, sl); break
        dropped = []
        if used is None:  # too many notes: demote lowest-priority ones to an overflow page
            size = 6.5; sl = [f"{S['page']} {pno}"] + fonts.wrap(summ, size, cw - 10); summ_h = len(sl) * (size + 2) + 8
            items = layout(size)
            items.sort(key=lambda it: (-(it["a"].get("priority") == "high"), -TYPES[it["a"]["type"]][5]))
            keep = []
            for it in items:
                if sum(k["h"] + 4 for k in keep) + it["h"] + summ_h + 12 < avail_bottom - top: keep.append(it)
                else: dropped.append(it)
            keep.sort(key=lambda it: it["a"]["y0"]); y = top + summ_h + 4
            for it in keep: it["y"] = max(it["a"]["y0"] - 2, y); y = it["y"] + it["h"] + 4
            yb = avail_bottom
            for it in reversed(keep):
                it["y"] = min(it["y"], yb - it["h"]); yb = it["y"] - 4
            used = (size, keep, sl)
        size, items, sl = used
        # draw summary strip
        pg.draw_rect(pymupdf.Rect(x0 - 4, top, W + M - 8, top + summ_h), color=(0.7, 0.7, 0.72), fill=(0.94, 0.94, 0.95), width=0.5)
        for j, ln in enumerate(sl): pg.insert_text((x0, top + 7 + size + j * (size + 2) - 5), ln, fontname="UB" if j == 0 else "UR", fontsize=size, color=(0.25, 0.25, 0.3))
        # draw cards
        def draw_card(pg, it, xx, ww, size, link_pages):
            a = it["a"]; col = TYPES[a["type"]][0]; yy = it["y"]
            r = pymupdf.Rect(xx - 4, yy, xx + ww, yy + it["h"])
            pg.draw_rect(r, color=col, fill=pale(col), width=1.6 if a.get("priority") == "high" else 0.6)
            pg.draw_rect(pymupdf.Rect(r.x0, r.y0, r.x0 + 3.5, r.y1), color=col, fill=col)
            star = " ★" if a.get("priority") == "high" else ""
            head = f"#{a['n']}  {a.get('title') or TYPES[a['type']][tl]}  ·  {S['ps']}{a.get('pass', 2)}{star}"
            ty = yy + 5 + size
            pg.draw_circle((xx + 5, ty - size * 0.35), 0.1, color=col)
            pg.insert_text((xx + 4, ty), head, fontname="UB", fontsize=size, color=tuple(c * 0.75 for c in col))
            ty += 3.5
            for ln in it["lines"]:
                ty += size + 2; pg.insert_text((xx + 4, ty), ln, fontname="UR", fontsize=size, color=INK)
            for ln, tgt in it["elines"]:
                ty += size + 1.5
                pg.insert_text((xx + 4, ty), ln, fontname="UR", fontsize=size - 0.5, color=(0.1, 0.25, 0.75))
                if tgt is not None:
                    lr = pymupdf.Rect(xx + 4, ty - size, xx + ww - 4, ty + 2)
                    if isinstance(tgt, tuple):  # reference link, filled later by index
                        if tgt[1]: link_pages.append((pno_out, lr, tgt[1]["page"], tgt[1]["y"]))
                    else: link_pages.append((pno_out, lr, tgt["page"], tgt["y0"]))
            # connector + number badge
            if a["rects"]:
                bx, by = a["bx"], a["by"]
                pg.draw_line((bx, by), (xx - 4, yy + 9), color=col, width=0.6)
                pg.draw_circle((bx + 7, by), 4.6, color=col, fill=col)
                nn = str(a["n"]); pg.insert_text((bx + 7 - fonts.w(nn, 5, True) / 2, by + 1.8), nn, fontname="UB", fontsize=5, color=(1, 1, 1))
        pno_out = content_idx[pno]; link_pages = overflow_of.setdefault("links", [])
        for it in items: draw_card(pg, it, x0, cw, size, link_pages)
        for it in dropped:  # stub badge only
            a = it["a"]; col = TYPES[a["type"]][0]
            if a["rects"]:
                pg.draw_circle((a["bx"] + 7, a["by"]), 4.6, color=col, fill=col)
                nn = str(a["n"]); pg.insert_text((a["bx"] + 7 - fonts.w(nn, 5, True) / 2, a["by"] + 1.8), nn, fontname="UB", fontsize=5, color=(1, 1, 1))
        if dropped:
            op = out.new_page(width=W + M, height=H); fonts.install(op)
            op.insert_text((x0, 24), f"{S['over']} {pno}", fontname="UB", fontsize=9, color=INK)
            yy = 34
            for it in sorted(dropped, key=lambda it: it["a"]["y0"]):
                it2 = dict(it); it2["h"] = it["h"] + 6; it2["y"] = yy; it2["a"] = dict(it["a"], rects=[])
                pno_out_save = pno_out; pno_out = len(out) - 1
                draw_card(op, it2, x0, cw, size, link_pages); pno_out = pno_out_save
                yy += it2["h"] + 4
            pg.insert_text((x0, avail_bottom - 2), f"+{len(dropped)} {S['extra_page']}", fontname="UR", fontsize=6.5, color=(0.5, 0.1, 0.1))
        # legend strip
        lx, ly = x0, H - legend_h
        for i, (k, v) in enumerate(TYPES.items()):
            cx = lx + (i % 5) * (cw / 5); cy = ly + (i // 5) * 13
            pg.draw_rect(pymupdf.Rect(cx, cy, cx + 7, cy + 7), color=v[0], fill=v[0])
            pg.insert_text((cx + 10, cy + 6.4), v[tl], fontname="UR", fontsize=5.6, color=INK)
        # clickable citation markers
        if ed and refs and os.path.exists(f"{ed}/pages.json"):
            pj = json.load(open(f"{ed}/pages.json"))["pages"][pno - 1]
            for c in pj["citations"]:
                toks = [t for t in re.split(r"\s*,\s*", c["text"].strip()) if t]
                r = pymupdf.Rect(c["bbox"]); nt = max(1, len(toks))
                for j, t in enumerate(toks):
                    m = re.match(r"(\d+)", t)
                    if not m or int(m.group(1)) not in refs: continue
                    tr = pymupdf.Rect(r.x0 + j * r.width / nt, r.y0, r.x0 + (j + 1) * r.width / nt, r.y1)
                    ref = refs[int(m.group(1))]
                    link_pages.append((content_idx[pno], tr, ref["page"], ref["y"]))
                    pg.draw_line((tr.x0, tr.y1 + 0.4), (tr.x1, tr.y1 + 0.4), color=TYPES["CITE"][0], width=0.7)
                    overflow_of.setdefault("cited", {}).setdefault(int(m.group(1)), set()).add(pno)

    # ---- citation index pages + cover
    cited = overflow_of.get("cited", {})
    links = overflow_of.get("links", [])
    def count_by(t): return sum(1 for a in anns if a["type"] == t)
    def build_cover(doc, offset, dry):
        f = Flow(doc, fonts, S, 0, dry)
        tgt = lambda a: (content_idx[a["page"]] + offset, a["y0"])
        f.text(f"{S['cover']}  ·  {reviewer}", 8, (0.45, 0.45, 0.5), True, gap=1)
        f.text(spec.get("paper", {}).get("title", os.path.basename(src_path)), 15, INK, True, gap=2)
        f.text(f"{N} {'trang' if lang == 'vi' else ('page' if N == 1 else 'pages')} · {len(anns)} notes · {datetime.date.today().isoformat()}", 8, (0.4, 0.4, 0.45), gap=8)
        p1 = spec.get("pass1", {})
        if p1:
            f.text(S["pass1"], 11, INK, True)
            if p1.get("verdict"): f.text(f"{S['verdict']}: {p1['verdict']}", 9, (0.55, 0.1, 0.1), True, gap=4)
            for k, lab in S["five"].items():
                if p1.get(k): f.text(f"{lab}: {p1[k]}", 8.5, indent=6, gap=1.5)
            if p1.get("read_plan"): f.text(f"{S['plan']}: {p1['read_plan']}", 8.5, (0.1, 0.25, 0.6), True, gap=6)
        f.text(S["legend"], 11, INK, True)
        for k, v in TYPES.items(): f.chip(v[0], f"{v[tl]}  ({count_by(k)})", v[td])
        f.y += 4
        tops = [a for a in anns if a.get("priority") == "high" or a["type"] in ("CONCERN", "ERROR")]
        if tops:
            f.text(S["top"], 11, INK, True)
            for a in tops[:25]:
                f.text(f"#{a['n']}  {S['pg']}{a['page']}  [{TYPES[a['type']][tl]}]  {(a.get('title') or a.get('note',''))[:150]}", 8.5, dark(TYPES[a["type"]][0]), link=tgt(a), gap=1.5)
            f.y += 4
        mr = [a for a in anns if a["type"] == "MUST_READ"]
        if mr:
            f.text(S["must"], 11, INK, True)
            for a in mr[:25]: f.text(f"#{a['n']}  {S['pg']}{a['page']}  {a.get('title') or a.get('note','')[:140]}", 8.5, link=tgt(a), gap=1.5)
            f.y += 4
        cn = [a for a in anns if a["type"] == "CITE"]
        if cn:
            f.text(S["cites"], 11, INK, True)
            for a in cn[:25]: f.text(f"#{a['n']}  {S['pg']}{a['page']}  {a.get('note','')[:150]}", 8.5, dark(TYPES["CITE"][0]), link=tgt(a), gap=1.5)
            f.y += 4
        conn = [(a, by_key[lk]) for a in anns for lk in (a.get("links") or []) if lk in by_key]
        if conn:
            f.text(S["links"], 11, INK, True)
            for a, b in conn: f.text(f"#{a['n']} ({S['pg']}{a['page']}) → #{b['n']} ({S['pg']}{b['page']})   {(a.get('title') or '')} ↔ {(b.get('title') or TYPES[b['type']][tl])}", 8.5, link=tgt(a), gap=1.5)
            f.y += 4
        f.text(S["digest"], 11, INK, True)
        for pno in range(1, N + 1):
            c = page_cards.get(pno, []); cs = f"{len(c)} notes" + (f" · ⚠{sum(1 for a in c if a['type'] in ('CONCERN','ERROR'))}" if any(a['type'] in ('CONCERN','ERROR') for a in c) else "")
            f.text(f"{S['pg']}{pno}  {reviewed.get(pno,{}).get('summary','—')}   [{cs}]", 8, link=(content_idx[pno] + offset, 0), gap=1.2)
        if warn:
            f.y += 6; f.text(S["unanch"], 10, (0.7, 0.1, 0.1), True)
            for w in warn: f.text(w, 8, (0.7, 0.1, 0.1), gap=1)
        return f.pages
    tmp = pymupdf.open(); ncov = build_cover(tmp, 0, True); tmp.close()
    # citation index page(s) appended
    if cited:
        f = Flow(out, fonts, S, len(out), False)
        f.text(S["citeidx"], 12, INK, True)
        for num in sorted(cited):
            pages_ = sorted(cited[num]); r = refs.get(num, {"text": "?", "page": 1, "y": 0})
            f.text(f"[{num}] {r['text'][:140]}", 8, INK, link=(r["page"] - 1, r["y"]), gap=0.5)
            f.text(f"     {S['cited_on']}: " + ", ".join(f"{S['pg']}{p}" for p in pages_), 7.5, (0.1, 0.25, 0.75), link=(content_idx[pages_[0]], 0), gap=3)
    # cover inserted at the front
    build_cover(out, ncov, False)
    # resolve deferred links (indices shift by ncov)
    for (pidx, rect, tpage, ty) in links:
        tp = tpage - 1 if tpage <= N else tpage
        out[pidx + ncov].insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": content_idx.get(tpage, tp) + ncov, "to": pymupdf.Point(0, max(0, ty - 30))})
    out.set_metadata({"title": "Annotated: " + spec.get("paper", {}).get("title", ""), "author": reviewer})
    out.save(out_path, garbage=3, deflate=True)
    print(f"saved {out_path} | {N} source pages (+{ncov} cover) | {len(anns)} notes | {len(cited)} cited refs linked")
    for w in warn: print("WARN:", w)

if __name__ == "__main__":
    main()
