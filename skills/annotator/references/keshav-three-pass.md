# Three-pass reading (Keshav 2007), adapted for annotation

Reading a lot is not the same as understanding. The method works because each pass has one goal. Decide *why* the user is reading (literature review? method to reuse? journal club? replicate?) and stop early when that purpose is satisfied.

## Pass 1: Is it worth more time? (5-10 min)
Read: title, abstract, last paragraph of Introduction, section headings, Conclusion, skim references. Answer the five Cs and record them in `pass1`:
- **Category**: what type of paper (measurement, method, system, review, theory, clinical study)?
- **Context**: which research line does it belong to; which papers does it build on?
- **Correctness**: are the assumptions reasonable?
- **Contributions**: what is actually new?
- **Clarity**: is it well written?
Also compare title vs abstract vs conclusion: do they claim the *same scope*? (Example: title says "tobacco", conclusion says "Nicotiana-derived".) Abstract with no numbers (no LOD, no n, no effect size) means the strength of evidence cannot be judged from the abstract alone.
Pass-1 notes are tagged `pass: 1`.

## Pass 2: Understand the content, inspect the evidence (about 1 h)
Put the authors' sentence next to the figure/table it relies on. For each result ask:
- Does the figure show what the text says it shows? (bands in negative lanes, wells empty where the text claims removal, error bars missing, n not stated)
- Are the claims worded stronger than the data (specific, robust, validated, "strong potential for practical application")?
- Controls: positive, negative, same-gel controls, replicate numbers, blinding, randomisation.
- Numbers: detection limits vs what the method can actually resolve (a threshold read off a log-scale gel is not a measurement); units; percentages; statistics and multiple-testing.
- Scope: how many species/samples/patients/conditions were tested versus what is claimed. "Specific to X" tested against 13 other species is not specific to everything else.
- Cited support: is the reference used actually about the thing it supports?
Tag with `pass: 2`. Mark ill-supported claims `CONCERN`, supporting data `EVIDENCE`, the author's sentence `CLAIM`.

## Pass 3: Rebuild it yourself, compare to the authors (4-5 h for a newcomer)
Ask "if it were me, what control would I need?" and list what is missing: comparison against the obvious alternative (short vs long marker; baseline method), real-world samples, ground-truth composition, replication, negative results, ablations, external validation. Look for small errors (wrong concentrations in a buffer recipe, mismatched figure/legend, off-topic references, inconsistent sample numbers). Tag with `pass: 3` and use `GAP`/`QUESTION`/`ERROR`.

## Outcome
Not "good paper / bad paper" but: *what the paper demonstrates, and what it does not yet demonstrate.* That is the raw material for an analytical literature review instead of a list. Put it in `pass1.verdict` and in the high-priority notes.

## Red-flag checklist (scan every paper)
- Scope drift between title, abstract, results, conclusion
- Abstract with no quantitative result
- Specificity/robustness claimed after testing few negatives; no real-world or blinded samples
- Positive control present but no negative/blank lane on the same gel/plate/run
- A key control missing (e.g. unwashed vs washed; short vs long amplicon; vehicle)
- Threshold or LOD stated more precisely than the method can resolve
- Wild relatives / related taxa / related conditions turning up positive but described as "specific"
- Methods typos with physical consequences (concentrations, temperatures, pH)
- Off-topic or mismatched references; self-citation clusters; references that do not support the sentence
- "Article in Press"/preprint: figures and numbers may change; say so on the cover
