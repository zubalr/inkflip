# Canonical coordinates and provenance

Contract version **1.0.0**. All boxes use `[x0,y0,x1,y1]`, never width/height disguised as maxima. All affine matrices use six components `[a,b,c,d,e,f]` with `x'=a*x+c*y+e`, `y'=b*x+d*y+f`. Compose column-vector transforms right to left. Page indices are zero-based internally and one-based only in UI/CLI page arguments.

## Spaces

1. `pdf_user:pN`: original unrotated PDF user coordinates; nonzero or negative box origins are legal. One unit is `UserUnit/72` inch. MediaBox, CropBox and effective view are not synonyms.
2. `canonical:pN`: unrotated effective-view space, top-left origin, right/down axes, physical points (1/72 inch). It is the storage coordinate system for occurrence/region polygons.
3. `display:pN`: canonical page after the document's quarter-turn rotation, before zoom/pan. Rotation changes display, not stored occurrence coordinates.
4. `raster:<id>`: integer image pixel grid used by a recorded render. Pixel edges are coordinates; centers are `i+0.5`. A crop is not a new PDF page.
5. `ocr:<id>`: OCR crop/resized pixel coordinates. Every crop and resize has a reversible recorded matrix.
6. `css:<viewport>`: CSS pixels after fit/zoom/pan; device-pixel ratio is applied only when crossing to a backing canvas, not again to overlay DOM coordinates.

Let effective view be `[cx0,cy0,cx1,cy1]`, `u=UserUnit>0`. Store

```text
C = [u, 0, 0, -u, -u*cx0, u*cy1]
W = u*(cx1-cx0); H = u*(cy1-cy0)
```

For clockwise display rotations in top-left canonical space:

```text
R0   = [ 1, 0, 0, 1, 0, 0 ]       display W,H
R90  = [ 0, 1,-1, 0, H, 0 ]       display H,W
R180 = [-1, 0, 0,-1, W, H ]       display W,H
R270 = [ 0,-1, 1, 0, 0, W ]       display H,W
```

`D = R * C`. For a raster scale `s` pixels per physical point, `P = Scale(s) * R * C`. For an OCR crop starting at raster `(rx,ry)` and resized by `kx,ky`, `O = Scale(kx,ky) * Translate(-rx,-ry) * P`. Recover a canonical point by `C * inverse(O) * ocrPoint`. Do not assume an OCR crop starts at (0,0) of the page.

### Numeric example

Media `[-20,-30,520,420]`, crop/effective `[20,40,500,390]`, UserUnit 2. Canonical width=960 pt, height=700 pt. Original point `(48,220)` maps to canonical `(56,340)`. At 90° it maps to display `(360,56)`. At 1.5 px/pt it maps to raster `(540,84)`. A crop at `(500,60)`, resized 2×, maps it to OCR `(80,48)`. Inversion must recover `(56,340)` canonical. DPR 2 affects backing pixels, not a CSS highlight already scaled by the viewport.

## Reader-specific conversion

**PDF.js.** `page.view` is the effective view, not proof of original MediaBox/CropBox. Store unknown original boxes as null. `getViewport({scale,rotation})` accounts for UserUnit; never multiply UserUnit a second time. Retain its actual transform. Validate it against `R*C` on analytic fixtures; a mismatch disables precise overlays until resolved. `TextItem.transform`, width/height and font ascent/descent provide an estimated text extent. Rotation/skewed text requires transformed quads; bounding an unrotated rectangle first is wrong. A multi-character TextItem is not per-character advance data: do not interpolate a precise digit box from string length. Highlight the whole measured item/line with “estimated region”. [S22](../research/SOURCES.md#s22).

**PDFium.** The executed 5.8.0 binding / PDFium 149.0.7825.0 probe reports the crop width/height without multiplying UserUnit and renders the supplied scale accordingly. Native adapter must derive physical dimensions from pypdf metadata and explicitly compensate its rendering scale. This is an observed build-specific behavior, not a general claim about all PDFium versions. `get_charbox` coordinates are reported API geometry; verify raw/crop origin and rotation on every supported build. Geometry under malformed page boxes is unsupported, not guessed. [native probe](../probes/results/native-probe.json), [S26](../research/SOURCES.md#s26).

**pypdf text.** Its independent extraction is page-only by default. Visitor matrices may inform experiments but do not earn precise occurrence geometry automatically. Metadata parsing is separate from PDFium extraction; if box metadata and actual raster cannot be reconciled, retain page text and mark the anchor unavailable.

**OCR.** Preserve raw word/line boxes and actual image dimensions; confidence is merely the recognizer's score. A box is an estimated pixel interpretation. A second pass gets a new reader/settings identity and a new transform chain, even if it reads the same source. Never replace the old text while retaining its unrelated box.

## Precision, clipping and order

`exact` means the coordinates are exactly those provided by a validated source API or analytic fixture, not that the polygon equals visible ink. `estimated` covers TextItem extents and OCR boxes. `page_only` and `unknown` have `polygon:null`; precise highlighting is forbidden. Geometry retains polygons, not just enclosing boxes. Hit-testing can use boxes as an acceleration index, followed by polygon testing.

Clipping affects what is shown, not the underlying source occurrence. Clip the overlay to the effective view without deleting its original polygon. Partial overlap is not full visibility. Out-of-crop observations may use canonical coordinates outside `[0,W]×[0,H]` in native reports; show a separate “outside displayed page” inset rather than silently moving them onto the page. Cross-page matching is prohibited except an explicitly page-level document-version comparison.

Store transform numbers rounded to 6 decimal places, finite only, negative zero normalized to zero. Validate positive boxes, determinant magnitude >1e-12, matrix/inverse composition error <=1e-5 physical points on the test extent. At extreme coordinates relative error also matters: reject dimensions/extent that amplify round-off beyond the overlay budget. No NaN/Infinity JSON.

## Verification

Analytic suite includes all four rotations, negative/nonzero origins, UserUnit 0.5/1/2/10, crop offsets, text skew, DPR 1/1.25/2/3, zoom 0.5–4, crop/resizing and inverse mapping. Assertions: 10,000 deterministic sampled points round-trip within 1e-5 pt; rendered overlays p95 <=2 CSS px and max <=4 on supported fixture anchors at specified zoom; page identity errors are always release blockers. Coarse geometry is valid output, misplaced precise geometry is not.

Tests compare actual raster dimensions and reader transforms, not only two algebraically related functions. A self-consistent wrong transform can pass a round-trip test; independent known anchor pixels are mandatory. `probes/geometry_probe.py` proves only analytic math until its render overlay tests are implemented under T04/T09.
