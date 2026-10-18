"""Minimal server-side PDF writer for receipts (one page, Helvetica text). No external dependency."""


def _escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(lines: list[str], title: str = "Receipt") -> bytes:
    content_lines = ["BT", "/F1 18 Tf", "50 790 Td", f"({_escape(title)}) Tj", "/F1 11 Tf", "0 -28 Td"]
    for line in lines:
        content_lines.append(f"({_escape(line)}) Tj")
        content_lines.append("0 -16 Td")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def money(minor: int) -> str:
    """450000 -> 'PKR 4500.00' (major units, two decimals, no thousands separator)."""
    sign = "-" if minor < 0 else ""
    minor = abs(minor)
    return f"PKR {sign}{minor // 100}.{minor % 100:02d}"


def qr_poster_pdf(matrix, title: str, lines: list[str]) -> bytes:
    """Part II 5.6: printable A4 QR poster — the modules as filled squares, labels underneath."""
    size = len(matrix)
    module = min(14.0, 380.0 / (size + 8))  # 4-module quiet zone on each side
    x0 = (595 - module * size) / 2
    y0 = 380.0
    ops = ["0 0 0 rg"]
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                ops.append(f"{x0 + c * module:.2f} {y0 + (size - 1 - r) * module:.2f} {module:.2f} {module:.2f} re f")
    ops += ["BT", "/F1 22 Tf", "50 320 Td", f"({_escape(title)}) Tj", "/F1 12 Tf"]
    for line in lines:
        ops += ["0 -20 Td", f"({_escape(line)}) Tj"]
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
