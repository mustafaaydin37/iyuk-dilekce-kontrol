from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
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
        if self.path == "/ai-analyze":
            self.handle_ai_analyze()
            return

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

    def handle_ai_analyze(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            petition_text = str(payload.get("text", "")).strip()
            if not petition_text:
                self.send_json({"error": "Dilekçe metni boş."}, status=400)
                return

            analysis = analyze_with_openai(petition_text)
            self.send_json({"analysis": analysis})
        except MissingOpenAIKeyError as exc:
            self.send_json({"error": str(exc)}, status=503)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.send_json({"error": f"OpenAI API hatası: {detail}"}, status=502)
        except Exception as exc:
            self.send_json({"error": f"OpenAI analizi çalıştırılamadı: {exc}"}, status=500)

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

class MissingOpenAIKeyError(RuntimeError):
    pass


def analyze_with_openai(petition_text: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise MissingOpenAIKeyError(
            "OPENAI_API_KEY tanımlı değil. Render Environment bölümüne OpenAI API anahtarı eklenmeli."
        )

    model = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
    prompt = build_legal_prompt(petition_text)
    body = {
        "model": model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "iyuk_petition_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "verdict": {"type": "string", "enum": ["Geçer", "Riskli", "Geçmez"]},
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "detectedCaseType": {"type": "string"},
                        "detectedCaseTypeReason": {"type": "string"},
                        "summary": {"type": "string"},
                        "checklist": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "status": {"type": "string", "enum": ["uygun", "riskli", "eksik", "düzeltilmeli"]},
                                    "explanation": {"type": "string"},
                                    "recommendation": {"type": "string"},
                                },
                                "required": ["id", "title", "status", "explanation", "recommendation"],
                            },
                        },
                        "missingInformation": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "revisedPetition": {"type": "string"},
                    },
                    "required": [
                        "verdict",
                        "score",
                        "detectedCaseType",
                        "detectedCaseTypeReason",
                        "summary",
                        "checklist",
                        "missingInformation",
                        "revisedPetition",
                    ],
                },
            }
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))

    output_text = extract_response_text(data)
    return json.loads(output_text)


def build_legal_prompt(petition_text: str) -> str:
    return f"""
Sen idari yargılama usulü alanında çalışan, İYUK m.3 ve idari dava dilekçelerinin ön inceleme şartları bakımından uzmanlaşmış bir dilekçe kontrol motorusun.

Görev:
- Kullanıcı dava türünü bilmek zorunda değildir. Önce dilekçenin türünü içerikten kendin belirle: iptal davası, tam yargı davası, iptal + tam yargı davası, yürütmenin durdurulması talepli dava veya belirsiz/karma.
- Tespit ettiğin dava türünü ve gerekçesini yaz.
- İYUK m.3 kapsamındaki unsurları tek tek değerlendir.
- Görev, yetki, süre, ehliyet, husumet, dava konusu işlem, kesin/yürütülebilir işlem, tebliğ/öğrenme tarihi, sonuç ve istem, deliller, ekler, imza/tarih ve dava türüne özgü biçimsel unsurlar bakımından riskleri yaz.
- Dilekçede yürütmenin durdurulması isteniyor veya olayın niteliği YD talebini gerektiriyor gibi görünüyorsa, “YÜRÜTMENİN DURDURULMASI TALEPLİDİR” ibaresinin bulunup bulunmadığını özellikle kontrol et.
- Kullanıcı iptal davası gibi görünen bir dilekçe sunmuş ama YD talebine ilişkin olgular/istemler var ve ibare eksikse bunu açıkça eksik/riskli unsur olarak işaretle.
- Eksik gerçek bilgileri uydurma. Eksik bilgi gereken yerlere köşeli parantezli açıklama koy.
- Düzeltilebilen anlatım, başlık, konu, sonuç ve istem bölümlerini uygun dilekçe formuna getir.
- Yürütmenin durdurulması talepli olduğu sonucuna varırsan ilgili ibareyi büyük harfli ve belirgin şekilde taslağa ekle.
- Cevabı yalnızca istenen JSON şemasına uygun ver.

Dilekçe metni:
{petition_text}
""".strip()


def extract_response_text(data: dict) -> str:
    if data.get("output_text"):
        return data["output_text"]

    chunks = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)

    raise ValueError("OpenAI yanıtında metin bulunamadı.")


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
