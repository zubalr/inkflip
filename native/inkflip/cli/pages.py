"""1-based page and region argument parsing (CLI_AND_REGRESSION)."""
from __future__ import annotations

MAX_PAGES_ALL = 1000
MAX_OCR_PAGES = 20


class PageSpecError(ValueError):
    """Invalid page/region specification."""


def parse_page_spec(spec: str | None, total_pages: int) -> list[int]:
    if not spec:
        return [1]
    text = spec.strip()
    if text.lower() == "all":
        if total_pages > MAX_PAGES_ALL:
            raise PageSpecError(
                f"--pages all exceeds maximum page limit of {MAX_PAGES_ALL} "
                f"(document has {total_pages} pages)"
            )
        return list(range(1, total_pages + 1))

    seen: set[int] = set()
    pages: list[int] = []
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise PageSpecError(f"Invalid empty page specification: {spec!r}")
    for part in parts:
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2:
                raise PageSpecError(f"Invalid page range: {part!r}")
            try:
                start = int(bounds[0].strip())
                end = int(bounds[1].strip())
            except ValueError as exc:
                raise PageSpecError(f"Invalid integer in page range: {part!r}") from exc
            if start <= 0 or end <= 0:
                raise PageSpecError(f"Page numbers must be 1-based positive integers, got range {part!r}")
            if start > end:
                raise PageSpecError(f"Page range start must be <= end, got {part!r}")
            for page in range(start, end + 1):
                if page in seen:
                    raise PageSpecError(f"Duplicate page {page} in page specification")
                seen.add(page)
                pages.append(page)
        else:
            try:
                page = int(part)
            except ValueError as exc:
                raise PageSpecError(f"Invalid page number: {part!r}") from exc
            if page <= 0:
                raise PageSpecError(f"Page numbers must be 1-based positive integers, got {page}")
            if page in seen:
                raise PageSpecError(f"Duplicate page {page} in page specification")
            seen.add(page)
            pages.append(page)
    for page in pages:
        if page > total_pages:
            raise PageSpecError(f"Requested page {page} exceeds document page count of {total_pages}")
    return sorted(pages)


def parse_ocr_pages(spec: str | None, selected_pages: list[int]) -> list[int]:
    if not spec:
        return []
    ocr = parse_page_spec(spec, max(selected_pages) if selected_pages else 1)
    selected = set(selected_pages)
    for page in ocr:
        if page not in selected:
            raise PageSpecError(f"OCR page {page} is not among selected document pages")
    if len(ocr) > MAX_OCR_PAGES:
        raise PageSpecError(f"OCR pages count ({len(ocr)}) exceeds maximum limit of {MAX_OCR_PAGES} per run")
    return ocr


def parse_region(spec: str | None, selected_pages: list[int]) -> list[float] | None:
    if not spec:
        return None
    if len(selected_pages) != 1:
        raise PageSpecError("One selected region requires exactly one selected page")
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 4:
        raise PageSpecError(f"--region requires exactly four comma-separated numbers, got {spec!r}")
    try:
        x0, y0, x1, y1 = (float(value) for value in parts)
    except ValueError as exc:
        raise PageSpecError(f"Invalid floating-point value in --region {spec!r}") from exc
    if x0 >= x1 or y0 >= y1:
        raise PageSpecError(f"Region coordinates must satisfy x0 < x1 and y0 < y1, got {spec}")
    return [x0, y0, x1, y1]


def region_to_polygon(region: list[float]) -> list[list[float]]:
    x0, y0, x1, y1 = region
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def polygon_intersects_region(polygon: list[list[float]] | None, region: list[float]) -> bool:
    if not polygon:
        return False
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    rx0, ry0, rx1, ry1 = region
    return not (max(xs) < rx0 or min(xs) > rx1 or max(ys) < ry0 or min(ys) > ry1)
