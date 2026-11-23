# annotations.json schema and writing guide

```json
{"version": 1,
 "title": "...", "summary": "pass-1 verdict, 2-3 sentences",
 "coverage": {
   "paragraphs_read": "p1-p118",
   "figures_viewed": ["f1", "f2"],
   "frames_viewed": {"f2": [1, 2, 3, 4, 5, 6]},
   "figures_unavailable": ["f7"]
 },
 "notes": [
   {"key": "k1", "type": "CONCERN", "pri": "high", "quote": "short anchor from the page", "note": "...", "links": ["k2"]},
   {"key": "k2", "type": "VERIFY", "figure": "f4", "box": [0.1, 0.2, 0.4, 0.3], "note": "..."},
   {"key": "k3", "type": "NOTE", "figure": "f2", "frame": 3, "box": [0.3, 0.3, 0.25, 0.4], "note": "..."}
 ]}
```

## Fields
- `coverage.paragraphs_read`: ids as ranges (`p1-p40,p42`). Must cover every paragraph in `manifest.json` or `check` fails.
- `figures_viewed` / `frames_viewed`: only what you actually opened. `figures_unavailable`: images that failed to load; mention them in `summary`.
- `key`: unique short id. `links`: keys of related notes (shown as "Related: #n").
- `pri: "high"`: the handful of things a reader must not miss (shown first in the drawer, starred in the PDF).
- Text note: `quote` anchors the note. Figure note: `figure` (+ optional `box` and `frame`).
- `box` = [x, y, w, h] normalised 0..1 on the figure image, origin top-left. Omit `box` for a whole-figure note (dashed outline).
- `frame`: 1-based index of the sampled GIF/video frame (file `fNN.frameNN.png`). The PDF shows that real frame with the box drawn on it.

## Types
CONCERN (a flaw or overreach), VERIFY (could be wrong, check a number or source), SPECULATION (the author guesses, no test), NOTE (context or clarification), CHECKED (you verified it and it holds), STRENGTH (good practice).

## Anchors
3-8 words copied exactly from `article.md`, from one paragraph (inline tags are fine), plain text not math, ideally unique. Never 15+ words. `check` fails when an anchor is not on the page.

## Good notes
- Say what is wrong or unproven and what would settle it (control, ablation, baseline, sample size, unit, scale).
- Tie claims to figures: does the plot show what the text says? Axis, n, error bars, cherry-picked range?
- Recompute simple arithmetic and say when it checks out (CHECKED).
- Pass 1: verdict and whether it deserves more time. Pass 2: claims vs evidence. Pass 3: assumptions, missing controls, alternative explanations.
- Your own words, short, concrete. One idea per note.
