#!/usr/bin/env python3
"""Independently derived geometry expectations for TEST-04.

Every expected coordinate in expected.json is produced here by exact
rational arithmetic (fractions.Fraction) plus closed-form per-rotation
formulas — never by executing or inverting the TypeScript implementation
under test. Two independent derivations are cross-checked inside this
script and must agree exactly before anything is emitted:

1. Matrix path: exact compose/apply/inverse over Fraction matrices,
   implemented from the COORDINATES.md formulas (C, R, Scale, Translate).
2. Closed-form path: direct per-rotation equations derived by hand:
     R0:   (u*(px-cx0),   u*(cy1-py))
     R90:  (u*(py-cy0),   u*(px-cx0))
     R180: (u*(cx1-px),   u*(py-cy0))
     R270: (u*(cy1-py),   u*(cx1-px))
   where [cx0,cy0,cx1,cy1] is the effective view and u is UserUnit.

Usage:
    python3 tests/geometry/derive_expectations.py            # write golden
    python3 tests/geometry/derive_expectations.py --check    # verify freshness
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "expected.json"

F = Fraction


# ---------------------------------------------------------------------------
# Exact matrix path (independent implementation; column-vector [a,b,c,d,e,f])
# ---------------------------------------------------------------------------

def apply_m(m, p):
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def compose_m(a, b):
    """a*b: apply b first, then a."""
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return [
        a0 * b0 + a2 * b1,
        a1 * b0 + a3 * b1,
        a0 * b2 + a2 * b3,
        a1 * b2 + a3 * b3,
        a0 * b4 + a2 * b5 + a4,
        a1 * b4 + a3 * b5 + a5,
    ]


def inverse_m(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    assert abs(det) > F(1, 10**12), "singular"
    return [
        d / det,
        -b / det,
        -c / det,
        a / det,
        (c * f - d * e) / det,
        (b * e - a * f) / det,
    ]


def scale_m(sx, sy=None):
    return [sx, F(0), F(0), sy if sy is not None else sx, F(0), F(0)]


def translate_m(tx, ty):
    return [F(1), F(0), F(0), F(1), tx, ty]


def canonical_m(view, u):
    """C = [u,0,0,-u,-u*cx0, u*cy1]; W,H = u*span."""
    cx0, cy0, cx1, cy1 = view
    return [u, F(0), F(0), -u, -u * cx0, u * cy1]


def rotation_m(deg, w, h):
    """Clockwise display rotation in top-left canonical space."""
    return {
        0: [F(1), F(0), F(0), F(1), F(0), F(0)],
        90: [F(0), F(1), F(-1), F(0), h, F(0)],
        180: [F(-1), F(0), F(0), F(-1), w, h],
        270: [F(0), F(-1), F(1), F(0), F(0), w],
    }[deg]


def canonical_size(view, u):
    return (u * (view[2] - view[0]), u * (view[3] - view[1]))


def display_size(deg, w, h):
    return (h, w) if deg in (90, 270) else (w, h)


# ---------------------------------------------------------------------------
# Closed-form path (hand-derived; no matrices at all)
# ---------------------------------------------------------------------------

def display_closed_form(deg, view, u, p):
    px, py = p
    cx0, cy0, cx1, cy1 = view
    if deg == 0:
        return (u * (px - cx0), u * (cy1 - py))
    if deg == 90:
        return (u * (py - cy0), u * (px - cx0))
    if deg == 180:
        return (u * (cx1 - px), u * (py - cy0))
    if deg == 270:
        return (u * (cy1 - py), u * (cx1 - px))
    raise AssertionError(deg)


def num(v):
    """Emit a Fraction as a JSON number.

    Integral values emit as ints. Non-dyadic rationals (e.g. 1/3 from an
    inverted 1.5 scale) emit as the nearest double; the representation
    error is <=1e-16, four orders below the 1e-5 pt conformance bound.
    """
    assert isinstance(v, Fraction)
    f = float(v)
    return f if f != int(f) else int(f)


def pt(pair):
    return [num(pair[0]), num(pair[1])]


def mat(m):
    return [num(v) for v in m]


def derive_page(name, media, crop, u, rotation, points):
    view = [
        max(media[0], crop[0]),
        max(media[1], crop[1]),
        min(media[2], crop[2]),
        min(media[3], crop[3]),
    ]
    assert view[2] > view[0] and view[3] > view[1]
    w, h = canonical_size(view, u)
    c = canonical_m(view, u)
    c_inv = inverse_m(c)
    r = rotation_m(rotation, w, h)
    d = compose_m(r, c)
    dw, dh = display_size(rotation, w, h)
    s = scale_m(F(3, 2))  # 1.5 px/pt raster leg
    p_m = compose_m(s, d)
    crop_t = translate_m(F(-500), F(-60))
    resize_k = scale_m(F(2))
    o_m = compose_m(resize_k, compose_m(crop_t, p_m))
    recover_m = compose_m(c, inverse_m(o_m))

    maps = {}
    for label, p in points.items():
        p = (F(p[0]), F(p[1]))
        canonical = apply_m(c, p)
        display = apply_m(d, p)
        raster = apply_m(p_m, p)
        ocr = apply_m(o_m, p)
        recovered = apply_m(recover_m, ocr)
        # Independent cross-check: closed-form display must equal the
        # matrix path exactly (Fraction equality, zero tolerance).
        assert apply_m(r, canonical) == display
        assert display_closed_form(rotation, view, u, p) == display, (
            name,
            label,
            display,
        )
        assert recovered == canonical, (name, label, recovered, canonical)
        maps[label] = {
            "pdf_user": pt(p),
            "canonical": pt(canonical),
            "display": pt(display),
            "raster_1_5": pt(raster),
            "ocr_crop_500_60_k2": pt(ocr),
            "recovered_canonical": pt(recovered),
        }
    return {
        "media_box": [num(v) for v in media],
        "crop_box": [num(v) for v in crop],
        "user_unit": num(u),
        "rotation": rotation,
        "effective_view": [num(v) for v in view],
        "canonical_size_pt": pt((w, h)),
        "C": mat(c),
        "C_inverse": mat(c_inv),
        "R": mat(r),
        "display_size": pt((dw, dh)),
        "D": mat(d),
        "P_scale_1_5": mat(p_m),
        "O_crop_500_60_k2": mat(o_m),
        "recover_matrix": mat(recover_m),
        "maps": maps,
    }


def derive():
    # F07: nonzero/negative-origin pages, all four rotations, UserUnit 2.
    media = [F(-20), F(-30), F(520), F(420)]
    crop = [F(20), F(40), F(500), F(390)]
    u = F(2)
    points = {
        # Text anchor: "48 220 Td" in every geometry-* fixture stream.
        "text_anchor": [48, 220],
        # Effective-view corners in pdf_user space.
        "view_top_left": [20, 390],
        "view_bottom_right": [500, 40],
        # Below the crop: legal pdf_user point outside the effective view
        # (canonical y > H — an out-of-crop observation, not an error).
        "below_crop": [60, 20],
        # Above-right outside the view (canonical x > W).
        "beyond_right": [530, 300],
        # Inside the negative-origin media region but outside the crop.
        "negative_origin": [0, 0],
    }
    pages = {}
    for deg in (0, 90, 180, 270):
        pages[f"geometry-{deg}"] = derive_page(
            f"geometry-{deg}", media, crop, u, deg, points
        )
    # F07 clean control: zero origin, rotation 0, UserUnit 1.
    control_media = [F(0), F(0), F(520), F(400)]
    pages["geometry-control"] = derive_page(
        "geometry-control", control_media, control_media, F(1), 0, points
    )

    # F08: UserUnit 0.5/1/2/10 physical-size equivalents; the fixture draws
    # a 100x100 user-unit stroke square at pdf_user (372,250).
    userunit = {}
    for us in ("0.5", "1", "2", "10"):
        uu = F(us)
        box = [F(0), F(0), F(520), F(400)]
        w, h = canonical_size(box, uu)
        # Fiducial rect x in [372,472], y in [250,350] -> canonical
        # (x*u, (400-y)*u): closed form, no matrix needed.
        fid = [
            (F(372) * uu, (F(400) - F(350)) * uu),
            (F(472) * uu, (F(400) - F(350)) * uu),
            (F(472) * uu, (F(400) - F(250)) * uu),
            (F(372) * uu, (F(400) - F(250)) * uu),
        ]
        # Cross-check via the matrix path.
        c = canonical_m(box, uu)
        for corner, p in zip(
            fid, [(372, 350), (472, 350), (472, 250), (372, 250)]
        ):
            assert apply_m(c, (F(p[0]), F(p[1]))) == corner
        userunit[us] = {
            "user_unit": num(uu),
            "canonical_size_pt": pt((w, h)),
            "fiducial_polygon": [pt(v) for v in fid],
            "fiducial_physical_size_pt": pt((F(100) * uu, F(100) * uu)),
            "text_anchor_canonical": pt(apply_m(c, (F(48), F(220)))),
        }

    # Rotation corner expectations (canonical origin under each R on a
    # 960x700 page) — independent anchors, never produced by inverting.
    corner = {}
    w, h = F(960), F(700)
    for deg in (0, 90, 180, 270):
        corner[str(deg)] = pt(apply_m(rotation_m(deg, w, h), (F(0), F(0))))

    # F09 text-transform genus: skewed text matrix maps a rect to a
    # parallelogram — a polygon, never an axis-aligned box approximation.
    skew_tm = [F(1), F(2, 5), F(3, 10), F(1), F(0), F(0)]
    skew_rect = [(F(10), F(10)), (F(110), F(10)), (F(110), F(40)), (F(10), F(40))]
    skew_poly = [apply_m(skew_tm, p) for p in skew_rect]
    xs = [p[0] for p in skew_poly]
    ys = [p[1] for p in skew_poly]
    skew = {
        "tm": mat(skew_tm),
        "rect": [pt(p) for p in skew_rect],
        "expected_polygon": [pt(p) for p in skew_poly],
        "expected_bounds": pt((min(xs), min(ys))) + pt((max(xs), max(ys))),
    }
    # The parallelogram must differ from its own axis-aligned bounds:
    # bounds corners are not polygon vertices (shear has nonzero b and c).
    bx = skew["expected_bounds"]
    bound_corners = {(bx[0], bx[1]), (bx[2], bx[1]), (bx[2], bx[3]), (bx[0], bx[3])}
    poly_set = set(tuple(p) for p in skew_poly)
    assert bound_corners != poly_set

    # Clipping metadata cases against view [0,0]x[100,80]: statuses and
    # vertex sets are hand-derived closed-form, not re-run clipping code.
    clip_cases = [
        {
            "name": "fully_inside",
            "polygon": [[10, 10], [50, 10], [50, 40], [10, 40]],
            "status": "inside",
            "clipped_area": 1200,
            "clipped_bounds": [10, 10, 50, 40],
            "clipped_vertices": [[10, 10], [50, 10], [50, 40], [10, 40]],
        },
        {
            "name": "straddles_left_edge",
            "polygon": [[-20, 10], [50, 10], [50, 40], [-20, 40]],
            "status": "partial",
            "clipped_area": 1500,
            "clipped_bounds": [0, 10, 50, 40],
            "clipped_vertices": [[0, 10], [50, 10], [50, 40], [0, 40]],
        },
        {
            "name": "straddles_top_left_corner",
            "polygon": [[-20, -10], [50, -10], [50, 40], [-20, 40]],
            "status": "partial",
            "clipped_area": 2000,
            "clipped_bounds": [0, 0, 50, 40],
            "clipped_vertices": [[0, 0], [50, 0], [50, 40], [0, 40]],
        },
        {
            "name": "covers_whole_view",
            "polygon": [[-10, -10], [200, -10], [200, 100], [-10, 100]],
            "status": "partial",
            "clipped_area": 8000,
            "clipped_bounds": [0, 0, 100, 80],
            "clipped_vertices": [[0, 0], [100, 0], [100, 80], [0, 80]],
        },
        {
            "name": "fully_outside",
            "polygon": [[-200, 10], [-150, 10], [-150, 40], [-200, 40]],
            "status": "outside",
            "clipped_area": 0,
            "clipped_bounds": None,
            "clipped_vertices": None,
        },
        {
            # Out-of-crop canonical observation (y > H): stays outside the
            # view for the inset, never snapped onto the page.
            "name": "below_view_out_of_crop",
            "polygon": [[10, 700], [90, 700], [90, 760], [10, 760]],
            "status": "outside",
            "clipped_area": 0,
            "clipped_bounds": None,
            "clipped_vertices": None,
        },
    ]

    # CSS/DPR anchors on the F07 rotation-0 page (canonical 960x700).
    css = {
        "canonical_point": [56, 340],
        "zooms": [0.5, 1, 1.25, 2, 4],
        "dprs": [1, 1.25, 2, 3],
        "cases": [],
    }
    for z in css["zooms"]:
        zp = F(str(z))
        for dpr in css["dprs"]:
            dp = F(str(dpr))
            css_pt = (zp * F(56), zp * F(340))
            backing = (dp * css_pt[0], dp * css_pt[1])
            css["cases"].append(
                {
                    "zoom": num(zp),
                    "dpr": num(dp),
                    "css": pt(css_pt),
                    "backing": pt(backing),
                }
            )

    return {
        "provenance": (
            "Derived by tests/geometry/derive_expectations.py using exact "
            "fractions.Fraction arithmetic plus closed-form per-rotation "
            "equations; independent of packages/geometry. The matrix path "
            "and closed-form path are asserted equal for every mapped "
            "point before emission."
        ),
        "pages": pages,
        "rotation_corner_map": corner,
        "userunit": userunit,
        "skew": skew,
        "clip": {"view": [0, 0, 100, 80], "cases": clip_cases},
        "css": css,
    }


def main() -> int:
    expected = derive()
    text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv[1:]:
        if not GOLDEN.is_file():
            print("expected.json missing; run derive_expectations.py", file=sys.stderr)
            return 1
        current = GOLDEN.read_text()
        if current != text:
            print("expected.json is stale; regenerate derive_expectations.py", file=sys.stderr)
            return 1
        print("expected.json matches the independent derivation")
        return 0
    GOLDEN.write_text(text)
    print(f"wrote {GOLDEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
