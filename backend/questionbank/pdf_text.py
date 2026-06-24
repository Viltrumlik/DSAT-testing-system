"""
The ONLY PDF-library-dependent module: turn a PDF file into per-page text.

Kept tiny and isolated so the parser (pdf_parser.py) stays pure and testable.
Prefers PyMuPDF (fitz), falls back to pdfplumber. If neither is installed, raises
a clear error telling the operator what to add to requirements — this is an M3
deploy-time dependency, intentionally not imported at module load.
"""
from __future__ import annotations


def extract_pages(pdf_path: str) -> list[str]:
    """Return a list of page text strings, one per page, in document order."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None

    if fitz is not None:
        with fitz.open(pdf_path) as doc:
            return [page.get_text("text") for page in doc]

    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    if pdfplumber is not None:
        pages: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return pages

    raise RuntimeError(
        "No PDF text backend available. Add 'PyMuPDF' (preferred) or 'pdfplumber' "
        "to requirements to enable PDF import (M3)."
    )


# Charts/figures are often VECTOR-drawn (not embedded raster), so get_images()
# misses them. We detect a substantial cluster of body drawings and render that
# region to a raster. Header-band table borders (a short strip near the top) are
# excluded so only real figures are captured.
_HEADER_BAND_BOTTOM = 120.0   # PDF points; the export's label-table sits above this
_MIN_FIGURE_W = 120.0
_MIN_FIGURE_H = 130.0
_FIGURE_ZOOM = 2.0            # 2× render for legible diagrams


def _vector_figure_png(page) -> bytes | None:
    """Render a page's body vector-figure region (a chart/graph) to PNG, or None."""
    import fitz

    pr = page.rect
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None or r.is_empty or r.is_infinite:
            continue
        if r.width >= pr.width * 0.95 and r.height >= pr.height * 0.95:
            continue  # full-page background
        if r.y1 <= _HEADER_BAND_BOTTOM:
            continue  # header label-table borders, not a figure
        rects.append(r)
    if not rects:
        return None
    x0 = min(r.x0 for r in rects); y0 = min(r.y0 for r in rects)
    x1 = max(r.x1 for r in rects); y1 = max(r.y1 for r in rects)
    if (x1 - x0) < _MIN_FIGURE_W or (y1 - y0) < _MIN_FIGURE_H:
        return None
    # Pad slightly so axis labels at the edges aren't clipped, clamped to the page.
    clip = fitz.Rect(
        max(pr.x0, x0 - 6), max(pr.y0, y0 - 6),
        min(pr.x1, x1 + 6), min(pr.y1, y1 + 6),
    )
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(_FIGURE_ZOOM, _FIGURE_ZOOM), clip=clip)
        return pix.tobytes("png")
    except Exception:
        return None


def extract_page_images(pdf_path: str) -> dict[int, list[tuple[str, bytes]]]:
    """Return ``{page_number(1-based): [(ext, image_bytes), ...]}`` for figures.

    Captures BOTH embedded raster images AND rendered vector figures (charts/
    graphs drawn with PDF vector ops, which get_images() alone would miss).
    Requires PyMuPDF; returns an empty dict without it so TEXT import still works.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {}

    out: dict[int, list[tuple[str, bytes]]] = {}
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            images: list[tuple[str, bytes]] = []
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                data = info.get("image") if info else None
                if data:
                    images.append((info.get("ext", "png"), data))
            if not images:
                # Only fall back to a rendered vector figure when there's no
                # embedded raster, so we don't double-capture the same diagram.
                fig = _vector_figure_png(page)
                if fig:
                    images.append(("png", fig))
            if images:
                out[page_index] = images
    return out
