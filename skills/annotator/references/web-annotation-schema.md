# Web annotations.json

```json
{"version": 1, "title": "...", "summary": "pass-1 verdict, 2-3 sentences",
 "coverage": {"paragraphs_read": "p1-p118", "figures_viewed": ["f1"], "frames_viewed": {"f2": [1,2,3]}, "figures_unavailable": ["f7"]},
 "notes": [
  {"key": "k1", "type": "CONCERN", "pri": "high", "quote": "short verbatim anchor", "note": "...", "links": ["k2"]},
  {"key": "k2", "type": "VERIFY", "figure": "f4", "box": [0.1, 0.2, 0.4, 0.3], "note": "..."},
  {"key": "k3", "type": "NOTE", "figure": "f2", "frame": 3, "box": [0.3, 0.3, 0.25, 0.4], "note": "..."}]}
```
- `paragraphs_read`: ranges covering every paragraph in `manifest.json`.
- `figures_viewed` / `frames_viewed`: only what you opened. `figures_unavailable`: figures with no image (`render`/`error` fields in `article.md` say why).
- `quote`: 3-8 words copied from `article.md`, one paragraph, inline tags allowed, plain text not math, ideally unique.
- `box`: [x,y,w,h] in 0-1 of the PNG you viewed, origin top-left. Omit for a whole-figure outline. `frame`: 1-based sampled frame.
- `pri:"high"`: shown first in the drawer.
- Requires `passes.json` in the bundle (`references/gates.md`).

## Types and colors
| type | color | use |
|---|---|---|
| CONCERN | #e5484d | flaw, overreach, missing control |
| VERIFY | #f5a524 | possibly wrong; check number/source |
| SPECULATION | #8e4ec6 | untested guess |
| NOTE | #3e63dd | context, clarification |
| CHECKED | #12a594 | verified, holds |
| STRENGTH | #30a46c | good practice |

## Output contract (both engines, same `common.js` + `overlay.js`)
Original page and styles kept; local assets inlined; page scripts removed (static); one `data-wa-id="f#"` per figure. Interface: highlights and numbered badges; figure boxes on the displayed media (responsive, `object-fit`, SVG `viewBox`, `<picture>`, CSS background; re-laid-out on resize); six type filter chips; notes drawer (summary, high-priority list, reading order, cards, "Related" links); click mark/box/card to jump and flash; hide/show highlights; persistent open state; dark mode; print notes section.
Engines: `manifest.json` has `engine`; ids and indexes match across engines, so one `annotations.json` fits both.
