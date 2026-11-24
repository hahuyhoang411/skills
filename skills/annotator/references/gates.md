# Gates

## passes.json (example: `assets/example_passes.json`)
```json
{"pass1": {"category","context","contribution","scope","title_vs_abstract_vs_conclusion","verdict","worth_more_time": true},
 "pass2": {"ledger": [{"claim","where","evidence","supports":"yes|partly|no|unclear","limits","would_settle","decision":"annotate:<key>[,<key>] | skip: <reason>"}],
           "figures": [{"id","inspected":true,"shows","axes_units","supports_text":"yes|partly|no","missing"},
                       {"id","inspected":false,"unavailable_reason"}],
           "numbers_checked": "..."},
 "pass3": {"rebuild","missing_controls":[],"alternatives":[],"overclaims":[],"none_found","would_change_conclusion"}}
```
- Write each pass record when that pass ends; annotations last.
- Ledger: one entry per major claim; `where` = paragraph id or page; every high-priority note is linked from a `decision`.
- `shows` = what the image displays (axes, groups, trend, exceptions), never the caption.

## Note quality
One issue per note; why it matters; what would settle it (control, baseline, ablation, n, unit, scale); author statement separate from inference; exact anchor; merged repeats; method and evidence over style.

## Results
1. Coverage: every paragraph/page read; figures viewed or listed unavailable.
2. Anchors and schema.
3. Analytical quality: `gates.py` (runs inside `check` and `annotate_pdf.py`).
4. Rendering QA, three statuses (`render` prints them, writes `qa_status.json`):
   - `visual_inspection`: figures with an image; which you viewed (`qa_figures.png` shows each box on its image).
   - `static_structural_qa`: payload JSON, unchanged runtime, JS syntax, one element per figure note, every text anchor present, no page scripts, media inlined. No layout.
   - `browser_visual_qa`: `PASS`/`FAIL` only when a real browser opened the output (`qa_html.png`); else `NOT RUN`. PDF: rasterise and view pages, else "not visually inspected".

## Complete when
100% coverage or listed unavailable | three passes recorded | anchors 100% or reported | gates OK | QA statuses reported | one deliverable, path verified.
