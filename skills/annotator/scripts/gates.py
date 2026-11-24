#!/usr/bin/env python3
"""Analytical gates shared by both routes (stdlib only).

  python gates.py passes <passes.json> [--manifest wa_x/manifest.json] [--annotations annotations.json]

Validates the three-pass record (passes.json) and lints the notes. Prints the ANALYTICAL QUALITY section and
exits 1 on errors. The web `check` calls the same functions. See references/gates.md for the schema.
It checks that the record is complete and consistent; it cannot prove the source was understood, so the
record must be written from what was actually read and viewed.
"""
import json, re, sys, difflib
from pathlib import Path

VAGUE = re.compile(r"^\W*(more research (is )?(needed|required)|interesting|good point|needs? (more )?work|unclear|see above|important|"
                   r"worth noting|further (study|work|research) (is )?(needed|required))\W*$", re.I)
HEDGE = re.compile(r"more research|further (study|research|work)|needs? more (data|work|research)", re.I)
SUPPORTS = {"yes", "partly", "no", "unclear"}


def _s(v):
    return " ".join(str(v or "").split())


def validate_passes(P, figure_ids=None, high_keys=None, require_figure_key=False):
    errs, warns = [], []
    if not isinstance(P, dict):
        return ["passes.json must be a JSON object"], warns
    p1, p2, p3 = P.get("pass1") or {}, P.get("pass2") or {}, P.get("pass3") or {}
    for f in ("category", "contribution", "scope", "verdict"):
        if len(_s(p1.get(f)).split()) < 2:
            errs.append(f"pass1.{f} missing or too thin (pass 1 not recorded)")
    if "worth_more_time" not in p1:
        errs.append("pass1.worth_more_time (true/false) missing")

    ledger = p2.get("ledger") or []
    need = max(1, len(high_keys or []))
    if len(ledger) < need:
        errs.append(f"pass2.ledger has {len(ledger)} entries; need at least {need} (one per major claim / high-priority note)")
    decided = set()
    for i, e in enumerate(ledger):
        tag = f"pass2.ledger[{i}]"
        for f in ("claim", "where", "evidence", "decision"):
            if not _s(e.get(f)):
                errs.append(f"{tag}.{f} missing")
        if e.get("supports") not in SUPPORTS:
            errs.append(f"{tag}.supports must be one of {sorted(SUPPORTS)}")
        d = _s(e.get("decision"))
        m = re.match(r"annotate:\s*([\w\-, ]+)$", d, re.I)
        if m:
            decided |= {k.strip() for k in m.group(1).split(",") if k.strip()}
        elif not d.lower().startswith("skip"):
            errs.append(f"{tag}.decision must be 'annotate:<key>[,<key>]' or 'skip: <reason>'")
        elif len(d.split()) < 3:
            errs.append(f"{tag}.decision: say why it is skipped")
        if e.get("supports") in ("no", "partly", "unclear") and not d.lower().startswith("annotate") and not _s(e.get("limits")):
            warns.append(f"{tag}: evidence is {e.get('supports')} but no annotation and no limits recorded")
    for k in (high_keys or []):
        if k not in decided:
            errs.append(f"high-priority note {k!r} is not linked to any evidence-ledger entry (decision 'annotate:{k}')")

    figs = p2.get("figures")
    if figs is None:
        if require_figure_key or figure_ids:
            errs.append("pass2.figures missing (use [] only if the source has no figures/tables)")
        figs = []
    seen = set()
    for i, f in enumerate(figs):
        tag = f"pass2.figures[{i}]"
        fid = f.get("id")
        seen.add(fid)
        if f.get("inspected") is True:
            if len(_s(f.get("shows")).split()) < 8:
                errs.append(f"{tag} ({fid}): 'shows' must describe what the image itself displays (axes, groups, trend), not repeat the caption")
            for fld in ("axes_units", "supports_text"):
                if not _s(f.get(fld)):
                    errs.append(f"{tag} ({fid}): {fld} missing")
        elif f.get("inspected") is False:
            if not _s(f.get("unavailable_reason")):
                errs.append(f"{tag} ({fid}): inspected=false needs unavailable_reason")
        else:
            errs.append(f"{tag} ({fid}): inspected must be true or false")
    for fid in (figure_ids or []):
        if fid not in seen:
            errs.append(f"figure {fid}: no inspection record in pass2.figures")

    if len(_s(p3.get("rebuild")).split()) < 8:
        errs.append("pass3.rebuild missing (reconstruct the argument independently before comparing)")
    lists = [p3.get(k) for k in ("missing_controls", "alternatives", "overclaims")]
    if not any(lists) and len(_s(p3.get("none_found")).split()) < 6:
        errs.append("pass3: list missing_controls / alternatives / overclaims, or explain in none_found why there are none")
    if len(_s(p3.get("would_change_conclusion")).split()) < 4:
        errs.append("pass3.would_change_conclusion missing (what evidence would change the verdict)")
    return errs, warns


def lint_notes(notes, n_paragraphs=None, text_field="note"):
    """Substance checks on notes. Returns (errs, warns)."""
    errs, warns = [], []
    seen = []
    for n in notes:
        k = n.get("key") or f"#{notes.index(n) + 1}"
        t = _s(n.get(text_field))
        w = len(t.split())
        typ = (n.get("type") or "").upper()
        if VAGUE.match(t):
            errs.append(f"{k}: vague note {t!r}: say what exactly is missing/wrong and what would settle it")
            continue
        if w < 6:
            errs.append(f"{k}: note too short ({w} words) to carry a reason")
        elif typ in ("CONCERN", "VERIFY", "ERROR", "GAP", "QUESTION") and w < 12:
            warns.append(f"{k}: {typ} note is {w} words; add why it matters and what would settle it")
        if HEDGE.search(t):
            warns.append(f"{k}: 'more research'-style wording; name the missing control, sample or analysis")
        for k2, t2 in seen:
            if difflib.SequenceMatcher(None, t.lower(), t2.lower()).ratio() > 0.8:
                warns.append(f"{k} repeats {k2}; merge or differentiate")
                break
        seen.append((k, t))
    if n_paragraphs and len(notes) > 0.5 * n_paragraphs and len(notes) > 10:
        warns.append(f"{len(notes)} notes for {n_paragraphs} paragraphs: annotate what changes the reader's judgement, not every paragraph")
    return errs, warns


def report(errs, warns, title="ANALYTICAL QUALITY"):
    print(f"[{title}]")
    for w in warns:
        print("  warn:", w)
    for e in errs:
        print("  ERROR:", e)
    print(f"  -> {'OK' if not errs else str(len(errs)) + ' problem(s)'}")


def main(argv):
    if len(argv) < 3 or argv[1] != "passes":
        sys.exit(__doc__)
    P = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    fig_ids, high, notes, npar = None, [], [], None
    if "--manifest" in argv:
        man = json.loads(Path(argv[argv.index("--manifest") + 1]).read_text(encoding="utf-8"))
        fig_ids = [f["id"] for f in man.get("figures", []) if f.get("file") and "did not load" not in (f.get("error") or "")]
        npar = len(man.get("paragraphs", []))
    if "--annotations" in argv:
        A = json.loads(Path(argv[argv.index("--annotations") + 1]).read_text(encoding="utf-8"))
        notes = A.get("notes") or A.get("annotations") or []
        high = [n.get("key") for n in notes if (n.get("pri") or n.get("priority")) == "high" and n.get("key")]
    e1, w1 = validate_passes(P, fig_ids, high, require_figure_key="--manifest" not in argv)
    e2, w2 = lint_notes(notes, npar)
    report(e1 + e2, w1 + w2)
    return 1 if (e1 or e2) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
