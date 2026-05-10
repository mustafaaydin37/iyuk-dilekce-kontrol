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
    evidence = extract_local_evidence(petition_text)
    prompt = build_legal_prompt(petition_text, evidence)
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
                                    "evidence": {"type": "string"},
                                    "explanation": {"type": "string"},
                                    "recommendation": {"type": "string"},
                                },
                                "required": ["id", "title", "status", "evidence", "explanation", "recommendation"],
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
    analysis = json.loads(output_text)
    return enforce_mechanical_findings(analysis, evidence)


def build_legal_prompt(petition_text: str, evidence: dict) -> str:
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
- Her kontrol maddesinde kararını dilekçedeki somut metin parçasına bağla.
- Dayanak alanına mümkün olduğunca dilekçeden aynen kısa alıntı yaz. Yorum, özet veya uydurma metin yazma.
- Bir unsur için “uygun” diyebilmen için dilekçede o unsuru açıkça gösteren bir metin parçası bulunmalıdır.
- Metinde açık karşılığı yoksa “eksik” veya “riskli” de; tahminle uygun deme.
- Aynı dilekçe aynı kanıtlarla değerlendirildiğinde aynı sonuca varacak şekilde tutarlı davran.
- Kendi ilk kararını ayrıca denetle: “uygun” dediğin her maddenin dayanağı gerçekten dilekçede var mı, yoksa durumu riskli/eksik yap.
- Aşağıdaki yerel kanıt çıkarımını yardımcı veri olarak kullan; ancak nihai kararı dilekçenin tamamına göre ver.
- Cevabı yalnızca istenen JSON şemasına uygun ver.

Yerel kanıt çıkarımı:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

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


def enforce_mechanical_findings(analysis: dict, evidence: dict) -> dict:
    checklist = analysis.get("checklist", [])
    evidence_requirements = {
        "court": ("mahkemeye_hitap", "Mahkemeye hitap bölümü mekanik kontrolde tespit edilemedi."),
        "mahkemeye_hitap": ("mahkemeye_hitap", "Mahkemeye hitap bölümü mekanik kontrolde tespit edilemedi."),
        "plaintiff": ("davacı", "Davacı bölümü mekanik kontrolde tespit edilemedi."),
        "davacı": ("davacı", "Davacı bölümü mekanik kontrolde tespit edilemedi."),
        "defendant": ("davali", "Davalı idare bölümü mekanik kontrolde tespit edilemedi."),
        "davalı": ("davali", "Davalı idare bölümü mekanik kontrolde tespit edilemedi."),
        "subject": ("konu", "Konu bölümü mekanik kontrolde tespit edilemedi."),
        "konu": ("konu", "Konu bölümü mekanik kontrolde tespit edilemedi."),
        "notice": ("teblig_ogrenme_tarihi", "Tebliğ/öğrenme tarihi mekanik kontrolde tespit edilemedi."),
        "teblig": ("teblig_ogrenme_tarihi", "Tebliğ/öğrenme tarihi mekanik kontrolde tespit edilemedi."),
        "tebliğ": ("teblig_ogrenme_tarihi", "Tebliğ/öğrenme tarihi mekanik kontrolde tespit edilemedi."),
        "amount": ("tazminat_miktari", "Tam yargı bakımından tazminat miktarı mekanik kontrolde tespit edilemedi."),
        "miktar": ("tazminat_miktari", "Tam yargı bakımından tazminat miktarı mekanik kontrolde tespit edilemedi."),
        "request": ("sonuc_istem", "Sonuç ve istem bölümü mekanik kontrolde tespit edilemedi."),
        "sonuç": ("sonuc_istem", "Sonuç ve istem bölümü mekanik kontrolde tespit edilemedi."),
        "istem": ("sonuc_istem", "Sonuç ve istem bölümü mekanik kontrolde tespit edilemedi."),
        "annex": ("ekler_deliller", "Ekler/deliller bölümü mekanik kontrolde tespit edilemedi."),
        "ek": ("ekler_deliller", "Ekler/deliller bölümü mekanik kontrolde tespit edilemedi."),
        "delil": ("ekler_deliller", "Ekler/deliller bölümü mekanik kontrolde tespit edilemedi."),
        "signature": ("imza_tarih", "İmza/tarih alanı mekanik kontrolde tespit edilemedi."),
        "imza": ("imza_tarih", "İmza/tarih alanı mekanik kontrolde tespit edilemedi."),
    }

    for item in checklist:
        status = fold_tr(str(item.get("status", "")))
        item_evidence = str(item.get("evidence", "")).strip()
        if status != "uygun":
            continue

        if not item_evidence or fold_tr(item_evidence) in {"-", "yok", "bulunamadı"}:
            downgrade_item(item, "Uygunluk dayanağı gösterilmediği için bu unsur riskli kabul edildi.")
            continue

        requirement = find_requirement(item, evidence_requirements)
        if requirement:
            evidence_key, note = requirement
            if not evidence_value_present(evidence_key, evidence):
                downgrade_item(item, note)

    missing_count = sum(1 for item in checklist if fold_tr(str(item.get("status", ""))) != "uygun")
    if checklist:
        recalculated = round(((len(checklist) - missing_count) / len(checklist)) * 100)
        current_score = int(analysis.get("score", recalculated))
        analysis["score"] = current_score if 0 <= current_score <= 100 else recalculated

    if missing_count >= max(4, len(checklist) // 3):
        analysis["verdict"] = "Geçmez"
    elif missing_count > 0 and analysis.get("verdict") == "Geçer":
        analysis["verdict"] = "Riskli"

    return analysis


def find_requirement(item: dict, requirements: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    text = fold_tr(f"{item.get('id', '')} {item.get('title', '')}")
    if "davacı" in text and ("adres" in text or "kimlik" in text or "tc" in text or "t.c" in text):
        return ("davacı_kimlik_adres", "Davacı kimlik/adres bilgisi mekanik kontrolde birlikte tespit edilemedi.")
    if "davacı" in text and "adres" in text:
        return ("davacı_adresi_olabilir", "Davacı adresi mekanik kontrolde tespit edilemedi.")
    for keyword, requirement in requirements.items():
        if keyword in text:
            return requirement
    return None


def evidence_value_present(key: str, evidence: dict) -> bool:
    if key == "davacı_kimlik_adres":
        return bool(evidence.get("davacı")) and bool(evidence.get("davacı_kimlik_no")) and bool(evidence.get("davacı_adresi_olabilir"))
    value = str(evidence.get(key, "")).strip()
    return bool(value)


def downgrade_item(item: dict, note: str) -> None:
    item["status"] = "riskli"
    explanation = str(item.get("explanation", "")).strip()
    item["explanation"] = f"{explanation} {note}".strip()


def extract_local_evidence(petition_text: str) -> dict:
    sections = extract_sections(petition_text)
    text = re.sub(r"\s+", " ", petition_text).strip()
    plaintiff_section = sections.get("davacı") or find_labeled_excerpt(text, "davacı", ["vekili", "davalı", "konu"])
    return {
        "mahkemeye_hitap": sections.get("mahkeme") or find_excerpt(text, r"(danıştay|idare mahkemesi|vergi mahkemesi).{0,110}(başkanlığı'?na|dairesi'?ne)"),
        "davacı": plaintiff_section,
        "davacı_kimlik_no": find_excerpt(plaintiff_section, r"(t\.?\s*c\.?\s*)?(kimlik\s*)?(no|numarası)?\s*:?\s*[1-9][0-9]{10}"),
        "davacı_adresi_olabilir": find_excerpt(plaintiff_section, r"(adres\s*:|mahallesi|mah\.|sokak|sok\.|cadde|cad\.|bulvar|bulv\.|no\s*:|daire|d\s*:|/\s*[A-ZÇĞİÖŞÜa-zçğıöşü]+)"),
        "davali": sections.get("davalı") or find_labeled_excerpt(text, "davalı", ["konu", "tebellüğ", "tebliğ", "açıklamalar"]),
        "konu": sections.get("konu") or find_labeled_excerpt(text, "konu", ["tebellüğ", "tebliğ", "açıklamalar", "olaylar"]),
        "teblig_ogrenme_tarihi": sections.get("tebliğ") or find_excerpt(text, r"(tebellüğ|tebliğ|öğrenme|bildirim).{0,80}\d{1,2}[./]\d{1,2}[./]\d{4}"),
        "tazminat_miktari": find_excerpt(text, r"\d[\d.,]*\s*(tl|₺|türk lirası)"),
        "yd_ibaresi": find_excerpt(text, r"YÜRÜTMENİN\s+DURDURULMASI\s+TALEPLİDİR|yürütmenin\s+durdurulması"),
        "sonuc_istem": sections.get("sonuç") or find_excerpt(text, r"(sonuç|netice).{0,30}(talep|istem)"),
        "ekler_deliller": sections.get("ekler") or find_excerpt(text, r"(ekler|deliller|ek\s*:)"),
        "imza_tarih": find_excerpt(text[-900:], r"\d{1,2}[./]\d{1,2}[./]\d{4}.{0,180}(davacı|vekili|av\.)"),
    }


def find_excerpt(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - 60)
    end = min(len(text), match.end() + 100)
    return text[start:end].strip()


def find_labeled_excerpt(text: str, label: str, stop_labels: list[str] | None = None) -> str:
    match = re.search(
        rf"(?:^|\s){label}\s*:?(?=\s|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    start = match.start()
    stops = stop_labels or ["vekili", "davalı", "konu", "tebellüğ", "tebliğ", "açıklamalar", "hukuki sebepler", "sonuç"]
    stop_pattern = "|".join(re.escape(stop) for stop in stops)
    next_label = re.search(
        rf"\b({stop_pattern})\s*:?(?=\s|$)",
        text[match.end() :],
        flags=re.IGNORECASE,
    )
    end = match.end() + next_label.start() if next_label else min(len(text), start + 450)
    return text[start:end].strip()


def extract_sections(petition_text: str) -> dict[str, str]:
    lines = [line.strip() for line in petition_text.replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    sections: dict[str, list[str]] = {}
    current_key = "mahkeme"
    sections[current_key] = []

    for line in lines:
        heading = detect_heading(line)
        if heading:
            current_key = heading
            sections.setdefault(current_key, [])
            remainder = strip_heading(line, heading)
            if remainder:
                sections[current_key].append(remainder)
            continue
        sections.setdefault(current_key, []).append(line)

    return {key: " ".join(value).strip() for key, value in sections.items() if " ".join(value).strip()}


def detect_heading(line: str) -> str | None:
    cleaned = normalize_heading(line)
    aliases = {
        "davacı": ["davacı", "davacı bilgileri", "davacı taraf", "davacılar"],
        "vekili": ["vekili", "davacı vekili", "vekil", "vekiller"],
        "davalı": ["davalı", "davalı idare", "davalı taraf", "davalılar"],
        "konu": ["konu", "dava konusu", "davanın konusu"],
        "açıklamalar": ["açıklamalar", "olaylar", "izahlar", "maddi olaylar"],
        "hukuki sebepler": ["hukuki sebepler", "hukuki nedenler", "yasal sebepler"],
        "tebliğ": ["tebellüğ tarihi", "tebliğ tarihi", "öğrenme tarihi", "bildirim tarihi"],
        "sonuç": ["sonuç ve talep", "sonuç ve istem", "netice ve talep", "sonuç", "istem"],
        "ekler": ["ekler", "deliller", "ek", "ekler ve deliller"],
    }
    for key, names in aliases.items():
        for name in names:
            if cleaned == name or re.match(rf"^{re.escape(name)}\s*:", cleaned):
                return key
    return None


def strip_heading(line: str, heading: str) -> str:
    aliases = {
        "davacı": r"davacı(?:lar| bilgileri| taraf)?",
        "vekili": r"(?:davacı\s+)?vekil(?:i|ler)?",
        "davalı": r"davalı(?:lar| idare| taraf)?",
        "konu": r"(?:dava(?:nın)?\s+)?konu(?:su)?",
        "açıklamalar": r"açıklamalar|olaylar|izahlar|maddi olaylar",
        "hukuki sebepler": r"hukuki sebepler|hukuki nedenler|yasal sebepler",
        "tebliğ": r"tebellüğ tarihi|tebliğ tarihi|öğrenme tarihi|bildirim tarihi",
        "sonuç": r"sonuç\s+ve\s+(?:talep|istem)|netice\s+ve\s+talep|sonuç|istem",
        "ekler": r"ekler\s+ve\s+deliller|ekler|deliller|ek",
    }
    pattern = aliases.get(heading)
    if not pattern:
        return ""
    return re.sub(rf"^\s*{pattern}\s*:?\s*", "", line, flags=re.IGNORECASE).strip()


def normalize_heading(value: str) -> str:
    value = re.sub(r"[:：]+$", "", value.strip())
    value = re.sub(r"\s+", " ", value)
    return fold_tr(value)


def fold_tr(value: str) -> str:
    return value.translate(str.maketrans({"I": "ı", "İ": "i"})).casefold()


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
