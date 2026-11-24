#!/usr/bin/env python3
"""Acceptance tests.  python tests/run_tests.py
Chromium-free tests always run (no-browser is simulated by ANNOTATOR_ENGINE=static and by a missing playwright package).
Real-browser tests (overlay geometry, interaction, engine parity, system-Chromium discovery) are SKIPPED, never passed, without Chromium."""
import base64, io, json, os, re, shutil, subprocess, sys, tempfile, traceback, zipfile
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
SK = PKG / "skills" / "annotator"
WA = SK / "scripts" / "web" / "webannotate.py"
PRE = SK / "scripts" / "preflight.py"
sys.path[:0] = [str(SK / "scripts" / "web"), str(SK / "scripts")]

# ================================================================== fixtures


def png_bytes(w, h, kind="line"):
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline="black")
    if kind == "line":
        pts = [(40 + i * (w - 80) / 9, h - 40 - [10, 25, 22, 60, 90, 85, 150, 140, 175, 190][i] * (h - 80) / 200) for i in range(10)]
        d.line(pts, fill=(200, 30, 30), width=4)
        d.rectangle([w * 0.62, h * 0.12, w * 0.95, h * 0.5], outline=(0, 0, 255), width=3)   # reference marker region
    else:
        for i in range(0, w, 40):
            d.rectangle([i, 0, i + 20, h], fill=(220, 220, 250))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def data_uri(raw, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


SVG = ('<svg viewBox="0 0 400 240" width="400" height="240" role="img" aria-label="bar chart">'
       '<rect width="400" height="240" fill="#fff" stroke="#000"/>'
       '<rect x="40" y="140" width="50" height="60" fill="#3e63dd"/><rect x="120" y="100" width="50" height="100" fill="#3e63dd"/>'
       '<rect x="200" y="40" width="50" height="160" fill="#e5484d"/><rect x="280" y="90" width="50" height="110" fill="#3e63dd"/>'
       '<text x="40" y="225" font-size="12">A</text><text x="120" y="225" font-size="12">B</text><text x="200" y="225" font-size="12">C</text>'
       '<text x="280" y="225" font-size="12">D</text><text x="150" y="20" font-size="14">Latency by block</text></svg>')

PARAS = [
    "Reading copies of papers help you decide what to trust.",
    "We study a small set of 500 tokens drawn from one corpus, and report a single run.",
    "In the first experiment the <em>third block reads from the second</em> block, which we call the spike.",
    "Figure 1 shows latency per block; block C is clearly the largest at roughly 160 units.",
    "The second chart shows loss over ten checkpoints and a sharp drop near the end.",
    "A picture of the pipeline appears below as a responsive picture element.",
    "Finally the background panel is decorative but carries a data URI image.",
    "These results are great news for interpretability, and we expect them to generalise.",
]


def page(img_src_png, img_src_wide, local=False):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Fixture Post</title>
<style>body{{font:16px/1.5 Georgia,serif;max-width:760px;margin:2rem auto;padding:0 1rem}}figure{{margin:1rem 0}}img{{max-width:100%;height:auto}}
.contain{{width:300px;height:300px;object-fit:contain;background:#eee;display:block}}</style>
<script>document.title='Fixture Post (script ran)'; window.__pagejs=1;</script></head>
<body><nav><a href="#">Home</a> <button><svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/></svg></button></nav>
<article><h1>Fixture Post</h1>
<p>{PARAS[0]}</p><p>{PARAS[1]}</p><p>{PARAS[2]}</p><p>{PARAS[3]}</p>
<figure id="fig-svg">{SVG}<figcaption>Figure 1. Latency by block (inline SVG).</figcaption></figure>
<p>{PARAS[4]}</p>
<figure><img src="{img_src_png}" alt="loss curve" width="600" height="300"><figcaption>Figure 2. Loss over checkpoints (PNG).</figcaption></figure>
<p>{PARAS[5]}</p>
<picture><source srcset="{img_src_wide}" media="(min-width: 2000px)"><img src="{img_src_wide}" alt="pipeline wide"></picture>
<p>Below: an object-fit:contain image in a square box (letterboxed).</p>
<img class="contain" src="{img_src_wide}" alt="letterboxed">
<p>{PARAS[6]}</p>
<div role="img" aria-label="panel" style="width:600px;height:160px;background-image:url('{img_src_png}');background-size:cover"></div>
<p>{PARAS[7]}</p>
<img src="{img_src_png}" width="20" height="20" alt="icon">
</article></body></html>"""


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    chart, wide = png_bytes(600, 300, "line"), png_bytes(600, 200, "bars")
    (out / "saved.html").write_text(page(data_uri(chart), data_uri(wide)), encoding="utf-8")
    # webpage-complete zip with relative assets in a subfolder + external stylesheet
    z = out / "complete.zip"
    html = page("page_files/chart.png", "page_files/wide.png").replace("</head>", '<link rel="stylesheet" href="page_files/site.css"></head>')
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("index.html", html)
        f.writestr("page_files/chart.png", chart); f.writestr("page_files/wide.png", wide)
        f.writestr("page_files/site.css", "h1{color:#223}")
    # zip-slip
    with zipfile.ZipFile(out / "evil.zip", "w") as f:
        f.writestr("index.html", "<html><body><p>x</p></body></html>")
        f.writestr("../../escape.txt", "pwned")
    # path traversal inside an otherwise fine page: <img src="../secret.png">
    (out / "secret.png").write_bytes(chart)
    sub = out / "sub"; sub.mkdir(exist_ok=True)
    (sub / "traverse.html").write_text(page("../secret.png", "../secret.png"), encoding="utf-8")
    # PDF with a figure and a table
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((72, 80), "A Small Study of Latency", fontsize=18)
    pg.insert_textbox(pymupdf.Rect(72, 100, 520, 200), "Abstract. We measure latency per block on 500 tokens and find that block C dominates. "
                      "Results are shown in Figure 1 and Table 1.", fontsize=11)
    pg.insert_image(pymupdf.Rect(72, 210, 372, 360), stream=chart)
    pg.insert_text((72, 375), "Figure 1: Loss over ten checkpoints.", fontsize=10)
    pg.insert_text((72, 410), "Table 1. Latency", fontsize=10)
    for r, row in enumerate([("block", "latency"), ("A", "60"), ("B", "100"), ("C", "160")]):
        for c, cell in enumerate(row):
            pg.insert_text((72 + c * 120, 430 + r * 16), cell, fontsize=10)
    doc.save(out / "paper.pdf")
    return out





NOTES = [
    {"key": "c1", "type": "CONCERN", "pri": "high", "quote": "a small set of 500 tokens",
     "note": "Only 500 tokens from one corpus and a single run, so the effect could be noise; repeating over seeds and a second corpus would settle it.", "links": ["svgbox"]},
    {"key": "v1", "type": "VERIFY", "quote": "from the second block, which we",
     "note": "The quote crosses an inline em tag on purpose; the claim that block three reads from block two needs an ablation to confirm."},
    {"key": "svgbox", "type": "CHECKED", "figure": "f1", "box": [0.46, 0.15, 0.22, 0.7],
     "note": "Boxed bar C is the tallest at about 160 units, matching the text; the other three bars are 60, 100 and 110.", "links": ["c1"]},
    {"key": "pngbox", "type": "NOTE", "figure": "f2", "box": [0.62, 0.12, 0.33, 0.38],
     "note": "Boxed region marks the reference rectangle in the loss plot; the curve itself falls outside it, so the drop is not in this region."},
    {"key": "picwhole", "type": "STRENGTH", "figure": "f3",
     "note": "Whole-figure outline: the picture is a clear stripe pattern and the pipeline claim is stated plainly beside it."},
    {"key": "fit", "type": "CONCERN", "figure": "f4", "box": [0.0, 0.0, 0.2, 1.0],
     "note": "Left stripe region of a letterboxed image: the box must follow the image pixels, not the padded square around it."},
    {"key": "bg", "type": "VERIFY", "figure": "f5", "box": [0.55, 0.1, 0.4, 0.45],
     "note": "Boxed corner of the CSS background panel; decorative image, but the same normalised box machinery applies to it."},
    {"key": "spec", "type": "SPECULATION", "quote": "great news for interpretability",
     "note": "Decodable activations are not the same as understood computation; no test supports this extrapolation."},
    {"key": "str", "type": "STRENGTH", "quote": "decide what to trust",
     "note": "A clear framing of why the reader should check evidence themselves rather than rely on the summary."},
]

ANN = {"version": 1, "title": "Fixture Post", "summary": "Pass 1: toy post with thin evidence; figure regions annotated.",
       "coverage": {"paragraphs_read": "p1-p12", "figures_viewed": ["f1", "f2", "f3", "f4", "f5"]}, "notes": NOTES}

PASSES = {
    "pass1": {"category": "Toy blog post, small latency experiment", "context": "Builds on probing intermediate blocks",
              "contribution": "Claims a spike in block three explains reasoning", "scope": "One corpus, 500 tokens, a single run",
              "title_vs_abstract_vs_conclusion": "Title is modest; the conclusion extends to interpretability generally",
              "verdict": "Worth a second pass, but the evidence is thin and single-run.", "worth_more_time": True},
    "pass2": {"ledger": [
        {"claim": "Result holds on a small set of 500 tokens", "where": "p3", "evidence": "Single run, no seeds", "supports": "unclear",
         "limits": "Tiny sample, one corpus", "would_settle": "Repeat over seeds and corpora", "decision": "annotate:c1,svgbox"},
        {"claim": "Block three reads from block two", "where": "p4", "evidence": "Assertion only", "supports": "partly",
         "limits": "No ablation", "would_settle": "Ablate block two", "decision": "annotate:v1"},
        {"claim": "Opening framing of reading copies", "where": "p2", "evidence": "Opinion", "supports": "yes",
         "decision": "annotate:str"},
        {"claim": "Background panel is decorative", "where": "p11", "evidence": "No data in it", "supports": "yes",
         "decision": "skip: decorative image with no evidential role in the argument"}],
        "figures": [
            {"id": "f1", "inspected": True, "shows": "Bar chart of latency for blocks A to D with C tallest near 160 and the others lower",
             "axes_units": "x: block label, y: latency in arbitrary units, no error bars", "supports_text": "yes", "missing": "variance across runs"},
            {"id": "f2", "inspected": True, "shows": "Red loss curve over ten checkpoints rising to the right with a blue reference rectangle at top right",
             "axes_units": "no labelled axes; checkpoint index implied", "supports_text": "partly", "missing": "axis labels and units"},
            {"id": "f3", "inspected": True, "shows": "Pale blue vertical stripes on white, a purely decorative pattern with no data in it",
             "axes_units": "none", "supports_text": "partly", "missing": "any actual pipeline diagram"},
            {"id": "f4", "inspected": True, "shows": "The same pale stripe pattern letterboxed in a grey square, with empty bands above and below",
             "axes_units": "none", "supports_text": "partly", "missing": "any content"},
            {"id": "f5", "inspected": True, "shows": "A cropped red loss curve on white used as a cover-fit background panel with a blue rectangle",
             "axes_units": "none", "supports_text": "partly", "missing": "labels"}],
        "numbers_checked": "Bar heights 60, 100, 160, 110 are consistent with the stated 160 maximum"},
    "pass3": {"rebuild": "To test the claim I would ablate block two, compare against random-block ablations over several seeds and a second corpus.",
              "missing_controls": ["ablation of block two", "random baseline"], "alternatives": ["normalisation artefact"],
              "overclaims": ["great news for interpretability"], "would_change_conclusion": "A null ablation result would remove the headline claim."},
}


def write_ann(d: Path):
    (d / "annotations.json").write_text(json.dumps(ANN, indent=1), encoding="utf-8")
    (d / "passes.json").write_text(json.dumps(PASSES, indent=1), encoding="utf-8")


# ================================================================== real-browser checks


def browser_run(html_path, notes, shots_dir=None):
    from playwright.sync_api import sync_playwright
    fails, facts = [], {}
    fig_notes = [n for n in notes if n.get("figure")]
    text_notes = [n for n in notes if not n.get("figure")]
    with sync_playwright() as p:
        br = p.chromium.launch()
        for width in (1100, 480):
            pg = br.new_page(viewport={"width": width, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(Path(html_path).resolve().as_uri(), wait_until="load")
            pg.wait_for_timeout(1500)
            if errs:
                fails.append(f"[{width}] JS errors: {errs[:2]}")
            c = pg.evaluate("""() => ({marks: [...new Set([...document.querySelectorAll('.ga-mark')].map(e => e.dataset.key))],
                badges: document.querySelectorAll('.ga-badge').length, boxes: [...document.querySelectorAll('.ga-box')].map(e => e.dataset.key),
                cards: [...new Set([...document.querySelectorAll('.ga-card')].map(e => e.dataset.key))], drawer: !!document.getElementById('ga-drawer'),
                print: !!document.getElementById('ga-print'), chips: [...document.querySelectorAll('.ga-chip')].map(e => e.dataset.type),
                pageScriptRan: window.__pagejs === 1})""")
            if set(c["marks"]) != {n["key"] for n in text_notes}:
                fails.append(f"[{width}] text marks {c['marks']} != expected {[n['key'] for n in text_notes]}")
            if sorted(c["boxes"]) != sorted(n["key"] for n in fig_notes):
                fails.append(f"[{width}] figure boxes {c['boxes']} != expected")
            if set(c["cards"]) != {n["key"] for n in notes}:
                fails.append(f"[{width}] drawer cards missing: {set(n['key'] for n in notes) - set(c['cards'])}")
            if not (c["drawer"] and c["print"]):
                fails.append(f"[{width}] drawer/print section missing")
            if c["pageScriptRan"]:
                fails.append(f"[{width}] original page scripts still run in the annotated copy")
            facts[width] = {k: (len(v) if isinstance(v, list) else v) for k, v in c.items()}
            # geometry: expected px rect of each box from independent ground truth
            for n in fig_notes:
                r = pg.evaluate("""(key) => {
                    const box = document.querySelector('.ga-box[data-key="' + key + '"]');
                    const wrap = box.parentElement;
                    const media = wrap.classList.contains('ga-figwrap-self') ? wrap : wrap.querySelector('[data-wa-id]');
                    const br = box.getBoundingClientRect(), mr = media.getBoundingClientRect();
                    const tag = media.tagName.toLowerCase();
                    let nw = 0, nh = 0, fit = 'fill';
                    if (tag === 'img') { nw = media.naturalWidth; nh = media.naturalHeight; fit = getComputedStyle(media).objectFit; }
                    if (tag === 'svg') { const vb = media.getAttribute('viewBox').split(/[\\s,]+/).map(Number); nw = vb[2]; nh = vb[3]; fit = 'contain'; }
                    return {box: [br.left, br.top, br.width, br.height], media: [mr.left, mr.top, mr.width, mr.height], nw, nh, fit, tag,
                            wrapIsSelf: wrap.classList.contains('ga-figwrap-self')};
                }""", n["key"])
                mx, my, mw, mh = r["media"]
                cx, cy, cw, ch = mx, my, mw, mh
                if r["nw"] and r["fit"] in ("contain", "scale-down"):
                    s = min(mw / r["nw"], mh / r["nh"]); s = min(s, 1) if r["fit"] == "scale-down" else s
                    cw, ch = r["nw"] * s, r["nh"] * s
                    cx, cy = mx + (mw - cw) / 2, my + (mh - ch) / 2
                bx, by, bw, bh = n.get("box") or [0, 0, 1, 1]
                exp = [cx + bx * cw, cy + by * ch, bw * cw, bh * ch]
                err = max(abs(a - b) for a, b in zip(exp, r["box"]))
                if err > 2.0:
                    fails.append(f"[{width}] box {n['key']} ({r['tag']}, fit={r['fit']}) off by {err:.1f}px: expected {[round(v,1) for v in exp]} got {[round(v,1) for v in r['box']]}")
                facts.setdefault("geometry_max_err_px", 0)
                facts["geometry_max_err_px"] = max(facts["geometry_max_err_px"], round(err, 2))
            if width == 1100:
                # interaction: click a figure box -> drawer opens with that card selected
                key = fig_notes[0]["key"]
                pg.evaluate("(k) => document.querySelector('.ga-box[data-key=\"' + k + '\"]').scrollIntoView({block:'center'})", key)
                pg.click(f'.ga-box[data-key="{key}"]', position={"x": 6, "y": 6}, force=True)
                pg.wait_for_timeout(300)
                sel = pg.evaluate("() => [...document.querySelectorAll('.ga-card.sel')].map(e => e.dataset.key)")
                opened = pg.evaluate("() => document.getElementById('ga-drawer').classList.contains('open')")
                if not opened or key not in sel:
                    fails.append(f"clicking figure box {key} did not open its note card (open={opened}, selected={sel})")
                # click a card -> figure flashes / scroll; click a text mark -> card selected
                tkey = text_notes[0]["key"]
                pg.click(f'.ga-mark[data-key="{tkey}"]', force=True)
                pg.wait_for_timeout(200)
                sel = pg.evaluate("() => [...document.querySelectorAll('.ga-card.sel')].map(e => e.dataset.key)")
                if tkey not in sel:
                    fails.append(f"clicking text mark {tkey} did not select its card")
                pg.click(f'.ga-card[data-key="{key}"]')
                pg.wait_for_timeout(300)
                if not pg.evaluate("(k) => !!document.querySelector('.ga-figwrap.ga-flash, .ga-figwrap-self.ga-flash')", key):
                    fails.append("clicking the card did not navigate to/flash its figure")
                # six colour filters + hiding
                types = {n["type"] for n in notes}
                if set(c["chips"]) != types:
                    fails.append(f"filter chips {c['chips']} != note types {sorted(types)}")
                t0 = fig_notes[0]["type"]
                pg.click(f'.ga-chip[data-type="{t0}"]')
                hidden = pg.evaluate("(t) => document.querySelectorAll('.ga-box.ga-off, .ga-mark.ga-off').length", t0)
                if not hidden:
                    fails.append("type filter chip did not hide that type's marks/boxes")
                pg.click(f'.ga-chip[data-type="{t0}"]')
                # linked cards: 'Related' links exist for notes with links
                rel = pg.evaluate("() => document.querySelectorAll('.ga-card .lk a').length")
                if any(n.get("links") for n in notes) and not rel:
                    fails.append("linked note cards show no Related links")
                # colors: six types map to the documented colors
                colors = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('.ga-card')].map(e => [e.querySelector('.hd').textContent.trim().split(/\\s+/)[1], getComputedStyle(e).getPropertyValue('--c').trim()]))")
                facts["colors"] = colors
                if shots_dir:
                    Path(shots_dir).mkdir(exist_ok=True, parents=True)
                    pg.screenshot(path=str(Path(shots_dir) / f"annotated_{width}.png"), full_page=False)
                pg.emulate_media(media="print")
                vis = pg.evaluate("() => getComputedStyle(document.getElementById('ga-print')).display")
                if vis == "none":
                    fails.append("print notes section not shown in print media")
            elif shots_dir:
                pg.screenshot(path=str(Path(shots_dir) / f"annotated_{width}.png"))
            pg.close()
        br.close()
    return fails, facts




# ================================================================== tests
TMP = Path(tempfile.mkdtemp(prefix="annotator_tests_"))
FX = TMP / "fx"
RESULTS = []


def run(args, env=None, cwd=None, check=False):
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=e, cwd=cwd or FX)
    if check and r.returncode:
        raise AssertionError(f"{args} exit {r.returncode}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r


NO_BIN = {"PLAYWRIGHT_BROWSERS_PATH": str(TMP / "no-such-dir"), "ANNOTATOR_ENGINE": "static"}   # package present, browser disabled
shim = TMP / "shim"; shim.mkdir()
(shim / "sitecustomize.py").write_text("import sys\nsys.modules['playwright']=None\nsys.modules['playwright.sync_api']=None\n")
NO_PKG = {"PYTHONPATH": str(shim)}                                                  # playwright package not importable


def browser_ok():
    sys.path.insert(0, str(SK / "scripts" / "web"))
    import webannotate
    return webannotate.browser_status()[0]


def test(fn):
    def wrap(*a, **k):
        try:
            out = fn(*a, **k)
            RESULTS.append((fn.__name__, "SKIPPED" if out == "skip" else "PASS", ""))
        except Exception as e:
            RESULTS.append((fn.__name__, "FAIL", "".join(traceback.format_exception_only(type(e), e)).strip()[:600]))
    wrap.__name__ = fn.__name__
    return wrap


# ------------------------------------------------------------------ packaging
FM = lambda p: re.match(r"^---\n(.*?)\n---\n", Path(p).read_text(), re.S).group(1)


@test
def t_frontmatter_strict_yaml():
    import yaml
    d = yaml.safe_load(FM(SK / "SKILL.md"))
    assert d["name"] == "annotator" and len(d["description"]) < 1024 and isinstance(d["compatibility"], str)
    try:
        yaml.safe_load("name: x\ncompatibility: Python 3. PDF route: PyMuPDF\n"); raise AssertionError("unquoted colon should be invalid YAML")
    except yaml.YAMLError:
        pass


@test
def t_manifests_aligned_and_build_zip_layout():
    ms = [json.loads((PKG / p).read_text()) for p in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json")]
    mk = json.loads((PKG / ".claude-plugin/marketplace.json").read_text())["plugins"][0]
    assert {m["name"] for m in ms} == {"annotator"} and len({m["version"] for m in ms} | {mk["version"]}) == 1
    work = TMP / "repo_copy"; shutil.copytree(PKG, work, ignore=shutil.ignore_patterns("dist", "__pycache__", ".git"))
    r = subprocess.run(["sh", "scripts/build.sh"], cwd=work, capture_output=True, text=True); assert r.returncode == 0, r.stdout + r.stderr
    names = set(zipfile.ZipFile(work / "dist" / "annotator.zip").namelist())
    for need in ("annotator/SKILL.md", "annotator/README.md", "annotator/skills/annotator/SKILL.md", "annotator/plugin.json", "annotator/.codex-plugin/plugin.json",
                 "annotator/.claude-plugin/plugin.json", "annotator/scripts/preflight.py", "annotator/scripts/web/static_engine.py"):
        assert need in names, need
    assert not any("/tests/" in n or "__pycache__" in n for n in names)
    # version mismatch must fail the build
    j = json.loads((work / "plugin.json").read_text()); j["version"] = "9.9.9"; (work / "plugin.json").write_text(json.dumps(j))
    assert subprocess.run(["sh", "scripts/build.sh"], cwd=work, capture_output=True).returncode != 0


@test
def t_mirror_layout_runs_from_zip_root():
    work = TMP / "repo_copy"
    z = TMP / "unz"; zipfile.ZipFile(work.parent / "repo_copy" / "dist" / "annotator.zip").extractall(z) if (work / "dist" / "annotator.zip").exists() else None
    r = run([z / "annotator" / "scripts" / "preflight.py", FX / "saved.html"], env={"ANNOTATOR_ENGINE": "static"}); assert "engine=static" in r.stdout and "route=saved-page" in r.stdout, r.stdout + r.stderr


# ------------------------------------------------------------------ static extraction
def fetch_static(src, out, **kw):
    return run([WA, "fetch", src, "--engine", "static", "--out", out], **kw)


@test
def t_static_inventory_inline_svg_raster_picture_background():
    fetch_static("saved.html", "inv", check=True)
    m = json.loads((FX / "inv" / "manifest.json").read_text())
    assert m["engine"] == "static"
    kinds = [(f["id"], f["kind"]) for f in m["figures"]]
    assert kinds == [("f1", "svg"), ("f2", "img"), ("f3", "img"), ("f4", "img"), ("f5", "background")], kinds   # 16px icon + 20px img skipped
    for f in m["figures"]:
        assert (FX / "inv" / f["file"]).exists(), f
    assert (FX / "inv" / "figures" / "f1.svg").read_text().startswith("<svg"), "inline SVG source must be preserved"
    assert "rasterised" in m["figures"][0]["render"]
    assert "cropped" in m["figures"][4]["render"]
    assert len(m["paragraphs"]) == 12 and m["paragraphs"][3]["text"].count("third block reads from the second block") == 1


@test
def t_svg_without_renderer_is_unavailable_not_inspected():
    import static_engine as SE
    orig = SE.svg_to_png
    SE.svg_to_png = lambda *a, **k: (False, "no renderer (test)")
    try:
        out = TMP / "norender"; (out / "figures").mkdir(parents=True)
        src = (FX / "saved.html").read_text()
        data, _ = SE.extract(src, out, FX, (FX / "saved.html").as_uri(), 4, lambda *a: ([], False), root=FX)
    finally:
        SE.svg_to_png = orig
    f1 = data["figures"][0]
    assert f1["kind"] == "svg" and not f1.get("file") and "NOT viewable" in f1["error"]
    assert (out / "figures" / "f1.svg").exists()
    # the shared gate then forces an honest declaration
    d = TMP / "norender_bundle"; shutil.copytree(FX / "inv", d)
    man = json.loads((d / "manifest.json").read_text()); man["figures"][0].pop("file"); man["figures"][0]["error"] = f1["error"]
    (d / "manifest.json").write_text(json.dumps(man))
    write_ann(d)
    r = run([WA, "check", d]); assert r.returncode == 1 and "f1: image unavailable" in r.stdout, r.stdout
    ann = json.loads((d / "annotations.json").read_text()); ann["coverage"]["figures_viewed"].remove("f1"); ann["coverage"]["figures_unavailable"] = ["f1"]
    ann["notes"] = [n for n in ann["notes"] if n.get("figure") != "f1"]
    ann["notes"][0]["links"] = []
    (d / "annotations.json").write_text(json.dumps(ann))
    ps = json.loads((d / "passes.json").read_text())
    ps["pass2"]["figures"][0] = {"id": "f1", "inspected": False, "unavailable_reason": "SVG could not be rasterised; only its source was read"}
    ps["pass2"]["ledger"][0]["decision"] = "annotate:c1"
    (d / "passes.json").write_text(json.dumps(ps))
    r = run([WA, "check", d]); assert r.returncode == 0, r.stdout


@test
def t_zip_complete_relative_assets_resolved_and_inlined():
    fetch_static("complete.zip", "zipx", check=True)
    m = json.loads((FX / "zipx" / "manifest.json").read_text())
    assert [f["kind"] for f in m["figures"]] == ["svg", "img", "img", "img", "background"]
    assert all(f.get("file") for f in m["figures"]), [f.get("error") for f in m["figures"]]
    write_ann(FX / "zipx")
    run([WA, "render", "zipx"], check=True)
    html = (FX / "zipx" / "annotated.html").read_text()
    import re
    assert not re.search(r"""(src|srcset|href)=["']page_files/|url\(["']?page_files/""", html), "local assets must be inlined so the single HTML file is self-contained"
    assert "data:image/png;base64" in html and len(re.findall(r"<\w+ data-wa-id=\"f\d\"", html)) == 5
    assert "h1{color:#223}" in html, "local stylesheet inlined"


@test
def t_zip_slip_rejected():
    r = fetch_static("evil.zip", "evil")
    assert r.returncode != 0 and "escapes" in (r.stdout + r.stderr), r.stdout + r.stderr
    assert not (TMP / "escape.txt").exists() and not (FX.parent / "escape.txt").exists() and not (FX / "evil" / "escape.txt").exists()


@test
def t_path_traversal_in_img_src_reported_unavailable():
    r = fetch_static("sub/traverse.html", "trav", check=True)
    m = json.loads((FX / "trav" / "manifest.json").read_text())
    bad = [f for f in m["figures"] if f["kind"] == "img" and f.get("error")]
    assert bad and all("UnsafePath" in f["error"] or "escapes" in f["error"] for f in bad), [f.get("error") for f in m["figures"]]
    assert "WARNING figures without a viewable image" in r.stdout


@test
def t_remote_images_logged_unavailable_not_dropped():
    page = FX / "remote.html"
    page.write_text("<html><body><article><p>Hello there readers of this page today.</p>"
                    '<img src="https://img.invalid/chart.png" width="400" height="300" alt="remote chart">'
                    "<p>More words follow the remote figure here.</p></article></body></html>")
    fetch_static("remote.html", "remote", check=True)
    m = json.loads((FX / "remote" / "manifest.json").read_text())
    assert len(m["figures"]) == 1 and "did not load" in m["figures"][0]["error"] and not m["figures"][0].get("file")
    assert "img.invalid" in " ".join(m["failed_image_hosts"])


@test
def t_parser_matches_browser_tree_rules_for_implied_p_end():
    import static_engine as SE
    out = TMP / "impl"; (out / "figures").mkdir(parents=True)
    html = ("<html><body><article><p><b>Notices:</b> <details><summary>Show the licence</summary><pre>MIT text here\nsecond line</pre></details>"
            "<p>Next paragraph one<p>Next paragraph two<ul><li>item one<li>item two</ul></article></body></html>")
    data, _ = SE.extract(html, out, TMP, "file:///x.html", 2, lambda *a: ([], False), root=TMP)
    texts = [p["text"] for p in data["paragraphs"]]
    assert texts == ["Notices:", "Show the licence", "MIT text here second line", "Next paragraph one", "Next paragraph two", "item one", "item two"], texts


# ------------------------------------------------------------------ browserless end to end
def e2e(env, name):
    r = run([WA, "fetch", "saved.html", "--out", name], env=env); assert r.returncode == 0, r.stdout + r.stderr
    assert "engine=static" in r.stdout and "browserless static engine" in r.stdout
    write_ann(FX / name)
    r = run([WA, "check", name], env=env); assert r.returncode == 0 and "RESULT: OK" in r.stdout, r.stdout
    r = run([WA, "render", name], env=env); assert r.returncode == 0, r.stdout + r.stderr
    d = FX / name
    st = json.loads((d / "qa_status.json").read_text())
    assert st["engine"] == "static" and st["static_structural_qa"]["result"] == "PASS"
    assert st["browser_visual_qa"]["result"] == "NOT RUN", "must never claim browser QA from static checks"
    assert st["visual_inspection"]["figures_with_image"] == 5
    assert "browser visual QA was NOT run" in r.stdout
    assert (d / "annotated.html").exists() and not (d / "annotated.pdf").exists() and not (d / "annotated.user.js").exists()
    return d


@test
def t_e2e_saved_html_no_chromium_binary():
    e2e(NO_BIN, "e2e_nobin")
    r = run([PRE, "saved.html"], env=NO_BIN)
    assert "browser=disabled" in r.stdout and "engine=static" in r.stdout and "saved_page=True" in r.stdout and "dns" not in r.stdout.split("cap:")[1].split("\n")[0].replace("internet=dns-fail", "").replace("pip_index=dns-fail", "")


@test
def t_e2e_saved_html_no_playwright_package():
    e2e(NO_PKG, "e2e_nopkg")
    r = run([PRE, "saved.html"], env=NO_PKG)
    assert "browser=playwright_missing" in r.stdout and "engine=static" in r.stdout


@test
def t_system_chromium_discovery_by_env_path():
    if not browser_ok():
        return "skip"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
    if not Path(exe).exists():
        return "skip"
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(TMP / "no-such-dir"), "ANNOTATOR_CHROMIUM_PATH": exe}
    r = run([PRE, "saved.html"], env=env); assert "browser=ok" in r.stdout and f"system_chromium={exe}" in r.stdout, r.stdout
    r = run([WA, "fetch", "saved.html", "--out", "sysexe"], env=env); assert "engine=browser" in r.stdout, r.stdout + r.stderr
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(TMP / "no-such-dir"), "PLAYWRIGHT_CHROMIUM_EXECUTABLE": exe}      # fallback when the managed browser is absent
    r = run([WA, "fetch", "saved.html", "--out", "sysexe2"], env=env); assert "engine=browser" in r.stdout, r.stdout + r.stderr


@test
def t_live_url_without_browser_refuses_no_lookalike():
    r = run([WA, "fetch", "https://example.org/post", "--out", "urlx"], env=NO_BIN)
    assert r.returncode != 0 and "needs a browser" in (r.stdout + r.stderr) and not (FX / "urlx" / "manifest.json").exists()


@test
def t_render_pdf_refused_by_static_engine():
    r = run([WA, "render", "e2e_nobin", "--only", "pdf"]); assert r.returncode != 0 and "needs a browser" in (r.stdout + r.stderr)


@test
def t_output_preserves_original_document():
    d = FX / "e2e_nobin"
    out = (d / "annotated.html").read_text()
    for frag in ("<title>Fixture Post</title>", "font:16px/1.5 Georgia", "<h1>Fixture Post</h1>", "<figcaption>Figure 1. Latency by block (inline SVG).</figcaption>",
                 'aria-label="bar chart"', "background-size:cover", "object-fit:contain"):
        assert frag in out, frag
    assert out.count("<script") == 4, "page scripts removed; payload + common + overlay + boot injected"
    assert "window.__pagejs" not in out


@test
def t_structural_qa_catches_broken_output():
    import webannotate as W
    d = FX / "e2e_nobin"
    man = json.loads((d / "manifest.json").read_text()); ann = json.loads((d / "annotations.json").read_text())
    WAp, _ = W.build_payload(d, man, ann)
    html = (d / "annotated.html").read_text()
    e, _, _ = W.structural_qa(html, WAp, man, True); assert not e, e
    e, _, _ = W.structural_qa(html.replace('data-wa-id="f1"', ""), WAp, man, True); assert any("figure f1 maps to 0" in x for x in e), e
    e, _, _ = W.structural_qa(html.replace("a small set of 500 tokens", "a tiny set"), WAp, man, True); assert any("text anchors not found" in x for x in e), e
    e, _, _ = W.structural_qa(html.replace("const TYPES = {", "const TYPES = { /*tampered*/", 1), WAp, man, True); assert any("overlay.js missing or modified" in x for x in e), e
    e, _, _ = W.structural_qa(html.replace("(function () {", "(function () { )(", 1), WAp, man, True); assert e, "JS syntax error must be caught"


@test
def t_gates_reject_missing_passes_and_bad_anchor_in_static_bundle():
    d = FX / "gate_bundle"; shutil.copytree(FX / "e2e_nobin", d)
    (d / "passes.json").unlink()
    r = run([WA, "check", d]); assert r.returncode == 1 and "passes.json missing" in r.stdout
    write_ann(d)
    ann = json.loads((d / "annotations.json").read_text()); ann["notes"][0]["quote"] = "words that are not on the page"
    (d / "annotations.json").write_text(json.dumps(ann))
    r = run([WA, "check", d]); assert r.returncode == 1 and "anchor not found" in r.stdout
    ann["notes"][0]["quote"] = "a small set of 500 tokens"; ann["coverage"]["figures_viewed"] = ["f1"]
    (d / "annotations.json").write_text(json.dumps(ann))
    r = run([WA, "check", d]); assert r.returncode == 1 and "not viewed" in r.stdout


@test
def t_figure_preview_drawn_without_browser():
    from PIL import Image
    im = Image.open(FX / "e2e_nobin" / "qa_figures.png"); assert im.width > 500 and im.height > 300
    assert len(list((FX / "e2e_nobin" / "qa_figures").glob("*.png"))) == 5


# ------------------------------------------------------------------ real browser (skipped when no Chromium)
@test
def t_browser_overlay_geometry_interaction_on_static_output():
    if not browser_ok():
        return "skip"
    fails, facts = browser_run(FX / "e2e_nobin" / "annotated.html", NOTES, TMP / "shots")
    assert not fails, fails
    assert facts["geometry_max_err_px"] <= 2.0 and len(facts["colors"]) == 6


@test
def t_browser_engine_parity_with_static_engine():
    if not browser_ok():
        return "skip"
    run([WA, "fetch", "saved.html", "--engine", "browser", "--no-pdf", "--out", "par_b"], check=True)
    sm = json.loads((FX / "e2e_nobin" / "manifest.json").read_text()); bm = json.loads((FX / "par_b" / "manifest.json").read_text())
    assert [p["text"] for p in sm["paragraphs"]] == [p["text"] for p in bm["paragraphs"]]
    assert sm["order"] == bm["order"]
    assert [(f["id"], f["kind"], f["index"]) for f in sm["figures"]] == [(f["id"], f["kind"], f["index"]) for f in bm["figures"]]
    write_ann(FX / "par_b")
    r = run([WA, "render", "par_b", "--only", "html"]); assert r.returncode == 0, r.stdout + r.stderr
    assert "browser_visual_qa: PASS" in r.stdout and "static_structural_qa: PASS" in r.stdout, r.stdout
    fb, facts_b = browser_run(FX / "par_b" / "annotated.html", NOTES)
    fs, facts_s = browser_run(FX / "e2e_nobin" / "annotated.html", NOTES)
    assert not fb and not fs, (fb, fs)
    assert facts_b[1100] == facts_s[1100] and facts_b["colors"] == facts_s["colors"], (facts_b, facts_s)


# ------------------------------------------------------------------ PDF route (unchanged, regression)
@test
def t_pdf_with_figure_and_table():
    import pymupdf
    d = FX / "pdfw"; d.mkdir()
    r = run([SK / "scripts" / "pdf" / "extract_pdf.py", FX / "paper.pdf", d, "--render"]); assert r.returncode == 0, r.stdout + r.stderr
    assert (d / "png" / "page_01.png").exists()
    ann = {"paper": {"title": "A Small Study of Latency"}, "reviewer": "test", "lang": "en",
           "pass1": {"category": "Toy experiment report", "context": "Latency per block", "correctness": "Unclear, single run",
                     "contributions": "Claims block C dominates", "clarity": "Clear", "verdict": "Thin evidence; read the figure and table closely.",
                     "read_plan": "Pass 2 on the figure and the table"},
           "pages": [{"page": 1, "summary": "Abstract, loss figure and latency table"}],
           "annotations": [
               {"page": 1, "quote": "block C dominates", "type": "CLAIM", "pass": 1, "priority": "high", "key": "claim",
                "note": "States that block C dominates latency; the table below must show it with more than one run to be convincing."},
               {"page": 1, "type": "EVIDENCE", "pass": 2, "bbox": [72, 210, 372, 360], "note": "Figure region: the curve rises steadily, which is a loss plot, not the latency chart the text promises.", "key": "figbox", "links": ["claim"]},
               {"page": 1, "quote": "Table 1. Latency", "type": "CONCERN", "pass": 2, "note": "Table reports one number per block without variance, so differences of 40 units cannot be judged significant."}]}
    ps = {"pass1": {"category": "Toy report", "context": "Latency study", "contribution": "Claims C dominates", "scope": "One run",
                    "verdict": "Thin evidence overall.", "worth_more_time": True},
          "pass2": {"ledger": [{"claim": "Block C dominates latency", "where": "p1", "evidence": "Single table, no variance", "supports": "partly",
                                "limits": "One run", "would_settle": "Repeat runs", "decision": "annotate:claim,figbox"}],
                    "figures": [{"id": "fig1", "inspected": True, "shows": "A rising red loss curve over ten checkpoints with a blue reference rectangle",
                                 "axes_units": "unlabelled axes", "supports_text": "no", "missing": "labels and the latency data"}],
                    "numbers_checked": "Table values 60, 100, 160 are consistent with the stated maximum"},
          "pass3": {"rebuild": "I would repeat each block measurement many times and plot means with intervals before claiming dominance.",
                    "missing_controls": ["repeat runs"], "alternatives": ["measurement noise"], "overclaims": ["dominates"],
                    "would_change_conclusion": "Overlapping intervals would remove the dominance claim."}}
    (d / "annotations.json").write_text(json.dumps(ann)); (d / "passes.json").write_text(json.dumps(ps))
    out = d / "out.pdf"
    r = run([SK / "scripts" / "pdf" / "annotate_pdf.py", FX / "paper.pdf", d / "annotations.json", out, "--passes", d / "passes.json", "--extract-dir", d,
             "--font", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    assert r.returncode == 0 and out.exists(), r.stdout[-1500:] + r.stderr[-800:]
    doc = pymupdf.open(out)
    assert doc.page_count >= 2 and sum(len(list(p.annots())) for p in doc) >= 3


def main():
    build(FX)
    tests = [v for k, v in sorted(globals().items(), key=lambda kv: list(globals()).index(kv[0])) if k.startswith("t_")]
    for t in tests:
        t()
    w = max(len(n) for n, *_ in RESULTS)
    for n, s, msg in RESULTS:
        print(f"{s:8} {n:<{w}} {msg}")
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    skipped = [r for r in RESULTS if r[1] == "SKIPPED"]
    print(f"\n{len(RESULTS) - len(fails) - len(skipped)} passed, {len(fails)} failed, {len(skipped)} skipped   (workdir {TMP})")
    if skipped:
        print("SKIPPED tests did not run (no Chromium here): parity with the browser engine is NOT established by this run.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
