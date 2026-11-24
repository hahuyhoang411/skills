#!/usr/bin/env python3
"""Extract a paper PDF into a page-by-page JSON that Claude reads in full.

Usage: python extract_pdf.py paper.pdf out_dir [--render]

Writes:
  out_dir/pages.json      per page: text blocks (with bbox), headings, captions, citation markers
  out_dir/references.json parsed reference list (number -> text, page, y)
  out_dir/page_NN.txt     plain text per page (easy to read in chunks)
  out_dir/png/page_NN.png (with --render) page images, for reading figures/gels/plots
"""
import json, re, sys, os
import pymupdf

def is_heading(line_text, size, body_size, bold):
    t = line_text.strip()
    if not t or len(t) > 120: return False
    if re.match(r"^(abstract|introduction|results?|discussion|conclusions?|methods?|materials and methods|"
                r"references|acknowledg|supplementary|appendix|data availability|author contributions|"
                r"competing interests|funding|background|summary|keywords?)\b", t, re.I): return True
    if re.match(r"^(\d+(\.\d+)*\.?|[A-Z]\.)\s+[A-Z]", t) and (bold or size > body_size + 0.5): return True
    return (bold and size >= body_size + 0.3 and len(t.split()) <= 14 and not t.endswith("."))

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pdf, out = sys.argv[1], sys.argv[2]
    render = "--render" in sys.argv
    os.makedirs(out, exist_ok=True)
    doc = pymupdf.open(pdf)

    # body font size = most common span size
    sizes = {}
    for p in doc:
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    k = round(s["size"], 1); sizes[k] = sizes.get(k, 0) + len(s["text"])
    body = max(sizes, key=sizes.get) if sizes else 10

    pages, ref_start = [], None
    for pno, p in enumerate(doc, 1):
        d = p.get_text("dict")
        blocks, headings, captions, cites = [], [], [], []
        for b in d["blocks"]:
            if b["type"] != 0: continue
            txt_lines = []
            for l in b["lines"]:
                lt = "".join(s["text"] for s in l["spans"])
                if not lt.strip(): continue
                txt_lines.append(lt)
                sz = max(s["size"] for s in l["spans"])
                bold = any("bold" in s["font"].lower() or (s["flags"] & 16) for s in l["spans"])
                if is_heading(lt, sz, body, bold):
                    headings.append({"text": lt.strip(), "bbox": [round(x,1) for x in l["bbox"]]})
                    if re.match(r"^(references|bibliography)\s*$", lt.strip(), re.I) and ref_start is None:
                        ref_start = (pno, l["bbox"][1])
                # superscript citation markers: smaller span right after body text, digits / ranges / commas
                for i, s in enumerate(l["spans"]):
                    if i and (s["flags"] & 1 or s["size"] < body - 1.5) and re.fullmatch(r"[\d,\u2013\-\s]+", s["text"].strip() or "x"):
                        cites.append({"text": s["text"].strip(), "bbox": [round(x,1) for x in s["bbox"]]})
            text = "\n".join(txt_lines)
            if not text.strip(): continue
            blocks.append({"bbox": [round(x,1) for x in b["bbox"]], "text": text})
            if re.match(r"^(fig(ure)?|table|extended data|supplementary)\.?\s*[\dS]+", text.strip(), re.I):
                captions.append({"text": text[:200].replace("\n", " "), "bbox": blocks[-1]["bbox"]})
        # bracket / author-year citations in plain text
        plain = p.get_text("text")
        for m in re.finditer(r"\[(\d+(?:[\u2013\-,\s]+\d+)*)\]", plain):
            hits = p.search_for(m.group(0))
            if hits: cites.append({"text": m.group(1), "bbox": [round(x,1) for x in hits[0]]})
        pages.append({"page": pno, "width": p.rect.width, "height": p.rect.height,
                      "n_images": len(p.get_images()), "headings": headings, "captions": captions,
                      "citations": cites, "blocks": blocks})
        open(f"{out}/page_{pno:02d}.txt", "w").write(p.get_text("text"))
        if render:
            os.makedirs(f"{out}/png", exist_ok=True)
            p.get_pixmap(dpi=110).save(f"{out}/png/page_{pno:02d}.png")

    # ---- reference list parsing ----
    refs = {}
    if ref_start:
        cur = None
        for pg in pages[ref_start[0]-1:]:
            for b in pg["blocks"]:
                if pg["page"] == ref_start[0] and b["bbox"][1] <= ref_start[1] + 1: continue
                for line in b["text"].split("\n"):
                    m = re.match(r"^\s*\[?(\d{1,3})[\].)]?\s+(\S.*)", line)
                    if m and (cur is None or cur < int(m.group(1)) <= cur + 10):
                        cur = int(m.group(1)); refs[cur] = {"num": cur, "page": pg["page"], "y": b["bbox"][1], "text": m.group(2)}
                    elif cur and cur in refs and not re.match(r"^(supplementary|acknowledg|author|competing|additional)", line, re.I):
                        refs[cur]["text"] += " " + line.strip()
    json.dump({"body_font_size": body, "n_pages": len(pages), "reference_section_starts": ref_start,
               "pages": pages}, open(f"{out}/pages.json", "w"), ensure_ascii=False, indent=1)
    json.dump(refs, open(f"{out}/references.json", "w"), ensure_ascii=False, indent=1)
    print(f"{len(pages)} pages | {sum(len(p['citations']) for p in pages)} citation markers | {len(refs)} references parsed")
    if not refs: print("WARNING: no numbered reference list parsed; link citations manually (author-year?)")

if __name__ == "__main__":
    main()
