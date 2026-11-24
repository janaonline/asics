"""Small PDFs made in memory for the scan-reading tests: no files, no network."""

import io

from pypdf import PdfWriter


def text_pdf(pages: int, words: int = 60) -> bytes:
    """A valid PDF whose pages have a text layer ("Section N. The Board shall word word ...")."""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(pages))}] /Count {pages} >>",
    ]
    font = 3 + 2 * pages
    for i in range(pages):
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>"
        )
        body = f"BT /F1 10 Tf 20 700 Td (Section {i + 1}. The Board shall {'word ' * words}) Tj ET"
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for n, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def scan_pdf(pages: int) -> bytes:
    """A PDF of blank pages: no text layer, like a scan."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(600, 800)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def damaged(data: bytes) -> bytes:
    """The same PDF with its cross-reference table and trailer cut off (pypdf: PdfStreamError; PDFium
    rebuilds the table from the objects and opens it)."""
    return data[: data.rfind(b"xref")]
