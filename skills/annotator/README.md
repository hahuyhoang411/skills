# Annotator

Reads a PDF or web page with Keshav's three-pass method and returns ONE annotated copy in the same format: PDF in → PDF out, saved page in → self-contained HTML out.

## Use
1. Start a new chat. Claude: type `/annotator`. ChatGPT: type `@annotator`.
2. Attach the file:
   - **PDF:** attach it.
   - **Web page:** save it as one `.html` with the [SingleFile extension](https://chromewebstore.google.com/detail/singlefile/mpiodijhokgodhhofbcjdecpffjipkle?hl=en) (install, open the page, click the SingleFile icon), then attach the `.html`. A "Webpage, complete" `.zip` also works.
3. Say `annotate this`. Optional: state your purpose (literature review, reuse the method, journal club).
4. Download `<name>_annotated.pdf` / `<name>_annotated.html`.

## What you get
| color | type | meaning |
|---|---|---|
| red | CONCERN | flaw, overreach, missing control |
| amber | VERIFY | possibly wrong, check it |
| purple | SPECULATION | untested guess |
| blue | NOTE | context |
| teal | CHECKED | verified, holds |
| green | STRENGTH | good practice |

HTML output: numbered highlights, colored boxes on figure regions, notes drawer with filters, summary, high-priority list, related-note links, print section. Notes explain why, and what would settle it.

## Limits
- Pages built by JavaScript need a saved `.html` from SingleFile (it captures the rendered page).
- Without a browser, canvas, iframe and video figures cannot be captured; they are listed as not inspected.
- The annotated HTML contains a copy of the page: do not publish it.
