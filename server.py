from __future__ import annotations

import argparse
import json
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8765


class PetitionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != "/extract":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(length)
            filename, data = parse_multipart_file(content_type, body)
            if not filename or not data:
                self.send_json({"error": "Dosya bulunamadı."}, status=400)
                return

            filename = Path(filename).name
            text = extract_text(filename, data)
            if not text.strip():
                self.send_json(
                    {"error": "Dosyadan okunabilir metin çıkarılamadı."},
                    status=422,
                )
                return

            self.send_json({"filename": filename, "text": text})
        except Exception as exc:
            self.send_json({"error": f"Dosya işlenemedi: {exc}"}, status=500)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    if suffix == ".docx":
        document = Document(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    if suffix == ".txt":
        return data.decode("utf-8", errors="replace")

    raise ValueError("Yalnızca PDF, DOCX ve TXT dosyaları desteklenir.")


def parse_multipart_file(content_type: str, body: bytes) -> tuple[str, bytes]:
    boundary_match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not boundary_match:
        raise ValueError("Geçersiz dosya yükleme isteği.")

    boundary = boundary_match.group("boundary").strip('"')
    delimiter = f"--{boundary}".encode("utf-8")
    for part in body.split(delimiter):
        part = part.strip()
        if not part or part == b"--":
            continue

        header_bytes, separator, file_bytes = part.partition(b"\r\n\r\n")
        if not separator:
            continue

        headers = header_bytes.decode("utf-8", errors="replace")
        if 'name="file"' not in headers:
            continue

        filename_match = re.search(r'filename="(?P<filename>[^"]+)"', headers)
        filename = filename_match.group("filename") if filename_match else ""
        return filename, file_bytes.rstrip(b"\r\n-")

    return "", b""


def main():
    parser = argparse.ArgumentParser(description="İYUK dilekçe kontrol web sunucusu")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", HOST),
        help="Sunucu adresi",
    )
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PORT", PORT)),
        type=int,
        help="Sunucu portu",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), PetitionHandler)
    visible_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"İYUK dilekçe kontrol aracı: http://{visible_host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
