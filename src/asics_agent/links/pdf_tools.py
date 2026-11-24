"""PDF handling the scan reading needs, in plain code with no model call: page counts, splitting into
chunks, repairing a file whose structure is broken, and rendering pages to images.

pypdf reads and splits; pypdfium2 (the PDFium engine of Chrome) rewrites a damaged file, rebuilding its
cross-reference table, and renders pages to PNG. Both are plain wheels (no system tools to install).
"""

import io
import re

from pypdf import PdfReader, PdfWriter

CHUNK_PAGES = 15  # most pages Claude reads in one request (the API allows 100)
IMAGE_SCALE = 1.5  # PDFium points -> pixels (about 108 dpi): sharp enough to read, small to send
# One request may carry about this much PDF; a chunk over it is read as page images instead.
REQUEST_LIMIT_BYTES = 20 * 1024 * 1024


def chunk_ranges(pages: int, size: int = CHUNK_PAGES) -> list[tuple[int, int]]:
    """(first, last) 1-based page numbers of each chunk: 46 pages -> (1,15) (16,30) (31,45) (46,46)."""
    return [(a, min(a + size - 1, pages)) for a in range(1, pages + 1, size)]


def page_count(data: bytes) -> int | None:
    """Pages in the PDF, by pypdf or else by PDFium; None when neither can open it."""
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        pass
    try:
        import pypdfium2 as pdfium

        return len(pdfium.PdfDocument(data))
    except Exception:
        return None


def repair(data: bytes) -> bytes | None:
    """The same document rewritten by PDFium (which tolerates a broken cross-reference table, a bad
    trailer or a cut-off tail), or None when PDFium cannot open it either."""
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(data)
        if not len(doc):
            return None
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    except Exception:
        return None


class Pdf:
    """One opened document: split out a range of pages as a PDF, or render them as PNG images. The
    readers are opened once and reused for every chunk (a 58 MB file is slow to open)."""

    def __init__(self, data: bytes):
        self.data = data
        self._reader = None
        self._pdfium = None

    def pages(self) -> int | None:
        return page_count(self.data)

    def split(self, first: int, last: int) -> bytes:
        """Pages first..last (1-based, inclusive) as a PDF of their own."""
        if self._reader is None:
            self._reader = PdfReader(io.BytesIO(self.data))
        writer = PdfWriter()
        for i in range(first - 1, last):
            writer.add_page(self._reader.pages[i])
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    def render(self, first: int, last: int, scale: float = IMAGE_SCALE) -> list[bytes]:
        """PNG images of pages first..last (1-based, inclusive)."""
        import pypdfium2 as pdfium

        if self._pdfium is None:
            self._pdfium = pdfium.PdfDocument(self.data)
        images = []
        for index in range(first - 1, last):
            buf = io.BytesIO()
            self._pdfium[index].render(scale=scale).to_pil().save(buf, format="PNG", optimize=True)
            images.append(buf.getvalue())
        return images


_PAGE_MARK = re.compile(r"(?m)^\[page (\d+)\][ \t]*")


def read_pages(text: str) -> dict[int, str]:
    """A "[page N]"-marked text -> {N: that page's text}. A repeated marker keeps the longer text."""
    found = list(_PAGE_MARK.finditer(text))
    pages: dict[int, str] = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        n, body = int(m.group(1)), text[m.end() : end].strip()
        if n not in pages or len(body) > len(pages[n]):
            pages[n] = body
    return pages
