# Three-pass reading

State the reader's purpose first (review, reuse method, journal club, replicate); stop when it is met.

## Pass 1: worth more time?
Read title, abstract, last intro paragraph, headings, conclusion, skim references. Record the five Cs in `pass1`:
- Category (measurement, method, system, review, theory, clinical)
- Context (research line, prior work)
- Correctness (assumptions)
- Contributions (what is new)
- Clarity
Compare title, abstract, conclusion for identical scope. Abstract without numbers (n, effect, LOD) = strength unjudgeable. Tag notes `pass: 1` (PDF).

## Pass 2: evidence
Put each claim next to its figure/table. Check:
- Figure shows what the text says (empty negative lanes, missing error bars, n unstated)
- Wording stronger than data (specific, robust, validated)
- Controls: positive, negative, same-run, replicates, blinding, randomisation
- Numbers: LOD vs resolution, units, statistics, multiple testing
- Scope tested vs scope claimed
- Cited reference supports the sentence
Tag `pass: 2`. Fill ledger and figure records.

## Pass 3: rebuild
List the controls you would need and what is missing: baselines, real-world samples, ground truth, replication, negative results, ablations, external validation. Find small errors (concentrations, legend mismatch, inconsistent n, off-topic references). Tag `pass: 3`; fill `pass3`.

## Types per route
| meaning | PDF | web |
|---|---|---|
| assertion | CLAIM | NOTE |
| supporting data | EVIDENCE | STRENGTH / CHECKED |
| overreach, weak evidence | CONCERN | CONCERN |
| verifiable mistake | ERROR | CONCERN ("error:") |
| unstated limitation | GAP | CONCERN / NOTE |
| check or ask authors | QUESTION | VERIFY |
| untested guess | CONCERN | SPECULATION |
| method / must-read / citation | METHOD / MUST_READ / CITE | NOTE / VERIFY |
PDF set: CITE CLAIM CONCERN ERROR EVIDENCE GAP METHOD MUST_READ QUESTION SKIP. Web set: CONCERN VERIFY SPECULATION NOTE CHECKED STRENGTH. Other types are rejected.

## Outcome
State what the paper demonstrates and what it does not yet demonstrate: `pass1.verdict` and the high-priority notes.

## Red flags
- Scope drift across title/abstract/results/conclusion
- No quantitative result in abstract
- Specificity claimed after few negatives; no blinded or real-world samples
- Positive control without negative/blank on the same run
- Missing key control (vehicle, washed vs unwashed, short vs long amplicon)
- Threshold finer than the method resolves
- Related taxa/conditions positive yet called "specific"
- Methods typos with physical consequences
- Off-topic references; self-citation clusters
- Preprint / "in press": numbers may change
