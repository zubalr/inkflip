# Rights and provenance for the pdf-g78 checkpoint

All added fixture content, fixed structures, scenario JSON, and generator
code are original Inkflip synthetic material under the project's MIT terms.
No private document, held-out label, challenge answer, font program, or
third-party implementation is included. Text uses unembedded base-14
Helvetica. F17 reuses the original repository-owned 5×7 bitmap raster recipe.

The fixed encryption recipe follows the Standard revision 2 algorithms
3.1–3.5 in Adobe's [PDF Reference 1.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf).
The fetched primary-source search extract confirmed the Standard handler
and RC4 algorithm; the full PDF fetch timed out. Actual pypdf
unlock/extraction and PDFium rendering independently verify the resulting
file. The recipe is an original implementation and copies no source code.

Painting, clipping, and mapping intent follow the existing repository PDF
recipes and frozen fixture catalog. Independent rendered-pixel checks and
structural assertions establish the effects used in this checkpoint.
Generator expectations are authored before reader observations and never
replaced with reader answers.

`fixtures/manifest.json` records each source and expectation digest, byte
count, rights, split, clean control, and `g78.1` recipe group. Its generator
and catalog hashes bind the two generator inputs. No new font is embedded
in this checkpoint. F13/F14 asset rights remain to be established before
those families can be generated.
