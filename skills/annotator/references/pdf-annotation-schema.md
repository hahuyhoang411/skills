# PDF annotations.json

```json
{
  "paper": {"title": "Full paper title"},
  "reviewer": "Claude",
  "lang": "en",                      // default "en"; "vi" for Vietnamese labels, legend, cover text
  "pass1": {
    "category": "...", "context": "...", "correctness": "...",
    "contributions": "...", "clarity": "...",
    "verdict": "one or two sentences: what is demonstrated / not demonstrated",
    "read_plan": "which pass to do for which purpose, which pages to read closely"
  },
  "pages": [ {"page": 1, "summary": "one line"}, ... ],      // REQUIRED for every page
  "annotations": [
    {"page": 2, "quote": "verbatim text from the page", "type": "CONCERN",
     "pass": 2, "priority": "high", "title": "optional short heading",
     "note": "2-3 sentences: what, why it matters, what would fix it",
     "key": "spec",                  // optional id, so others can link to it
     "links": ["wash"],              // optional: keys of related annotations (clickable both ways)
     "refs": [7, 11],                // optional: reference numbers shown as clickable links in the card
     "occurrence": 0,                // optional: which hit if a short quote appears several times
     "bbox": [x0, y0, x1, y1]}       // optional: for figures or when text search fails (original page points)
  ],
  "ref_notes": {"11": "Why this reference matters / looks off-topic (verified or 'to verify')"}
}
```

## Types (color + when to use)
| type | color | use for |
|---|---|---|
| MUST_READ | orange | the passages the user must read themselves (e.g. the gap paragraph in the Introduction) |
| CLAIM | blue | what the authors assert or promise |
| EVIDENCE | green | data/figure/number that supports a claim |
| CONCERN | red | weak evidence, overclaim, missing control, scope mismatch |
| ERROR | magenta (squiggle) | verifiable mistakes: wrong value, mismatch, typo with consequences |
| METHOD | purple | design details that matter for reuse/replication |
| GAP | yellow | research gap or limitation (stated or unstated) |
| CITE | teal (underline) | references worth following, off-topic or suspicious references |
| QUESTION | pink | things to answer yourself or ask the authors |
| SKIP | gray | safe to skim (boilerplate, long author lists, standard methods) |

`pass`: 1, 2 or 3 (shown as L1/L2/L3 on the card in Vietnamese, P1/P2/P3 in English). `priority: "high"` adds a star, a thicker border and a place on the cover.

## Anchoring
- Copy quotes from `work/page_NN.txt`; end before superscripts; avoid hyphenated line breaks.
- Repeated quote: lengthen it or set `occurrence`.
- `WARN: could not anchor`: shorten the quote, rebuild.

## Density
Cover/Abstract/Intro/Results/Discussion: 3-8 notes per page. Methods: METHOD/ERROR/GAP only. References: `ref_notes` for those that matter. Appendix: read fully, annotate only what changes judgment.

## Required
`--passes passes.json` (`references/gates.md`). Unknown `type` is an error. Every `priority: high` note has a `key` linked from the ledger. Set `reviewer` and `lang`.
