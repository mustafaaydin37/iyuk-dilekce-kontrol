const fileEl = document.querySelector("#petitionFile");
const fileStatusEl = document.querySelector("#fileStatus");
const textEl = document.querySelector("#petitionText");
const analyzeBtn = document.querySelector("#analyzeBtn");
const clearBtn = document.querySelector("#clearBtn");
const checklistEl = document.querySelector("#checklist");
const summaryTextEl = document.querySelector("#summaryText");
const verdictBadgeEl = document.querySelector("#verdictBadge");
const scoreValueEl = document.querySelector("#scoreValue");
const scoreBarEl = document.querySelector("#scoreBar");
const caseTypeValueEl = document.querySelector("#caseTypeValue");
const criticalValueEl = document.querySelector("#criticalValue");
const fixableValueEl = document.querySelector("#fixableValue");
const missingInfoListEl = document.querySelector("#missingInfoList");
const fixableListEl = document.querySelector("#fixableList");
const attachmentListEl = document.querySelector("#attachmentList");
const analysisOutputEl = document.querySelector("#analysisOutput");
const draftOutputEl = document.querySelector("#draftOutput");
const detailTableEl = document.querySelector("#detailTable");
const buildDraftBtn = document.querySelector("#buildDraftBtn");
const downloadTxtBtn = document.querySelector("#downloadTxtBtn");
const printBtn = document.querySelector("#printBtn");

let lastAnalysis = null;
let lastAiAnalysis = null;

const caseTypeLabels = {
  auto: "Sistem tarafından belirlenecek",
  "tam-yargi": "Tam yargı davası",
  iptal: "İptal davası",
  "iptal-tam-yargi": "İptal + tam yargı davası",
  yd: "Yürütmenin durdurulması talepli dava",
};

const checks = [
  {
    id: "court",
    title: "Mahkemeye hitap",
    weight: 8,
    test: (text) => /mahkemesi\s+(sayın\s+)?başkanlığı'?na|danıştay\s+(başkanlığı|.*dairesi)/i.test(text),
    missing: "Dilekçe Danıştay, idare mahkemesi veya vergi mahkemesi başkanlığına hitaben yazılmalı.",
    ok: "Mahkemeye hitap bölümü mevcut.",
  },
  {
    id: "plaintiff",
    title: "Davacı bilgileri",
    weight: 10,
    test: (text) => /davacı\s*:/i.test(text) && hasPersonLikeValue(afterLabel(text, "davacı")),
    missing: "Davacı ad/soyad veya unvan bilgisi açık biçimde gösterilmeli.",
    ok: "Davacı bölümü mevcut.",
  },
  {
    id: "plaintiffId",
    title: "Davacı T.C. kimlik numarası",
    weight: 7,
    test: (text) => /t\.?\s*c\.?\s*(kimlik|no|numara)|\b[1-9][0-9]{10}\b/i.test(text),
    missing: "Gerçek kişi davacı için T.C. kimlik numarası bulunmalı.",
    ok: "T.C. kimlik numarası tespit edildi.",
  },
  {
    id: "plaintiffAddress",
    title: "Davacı adresi",
    weight: 9,
    test: (text) => {
      const davaciBlock = afterLabel(text, "davacı", ["vekili", "davalı", "konu"]);
      return /adres|mah\.|mahallesi|sokak|cadde|cad\.|no:|\/\s*[a-zçğıöşü]+/i.test(davaciBlock);
    },
    missing: "Davacının açık adresi eksik görünüyor. Vekil adresi tek başına davacı adresinin yerini tutmayabilir.",
    ok: "Davacı adresi tespit edildi.",
  },
  {
    id: "attorney",
    title: "Vekil/temsilci bilgileri",
    weight: 5,
    test: (text) => !/vekili\s*:/i.test(text) || /av\.|avukat|adres|sokak|cadde|no:/i.test(afterLabel(text, "vekili")),
    missing: "Vekil varsa vekilin ad/soyad ve adres bilgileri açık yazılmalı.",
    ok: "Vekil bilgileri mevcut veya vekil gösterilmemiş.",
  },
  {
    id: "defendant",
    title: "Davalı idare",
    weight: 9,
    test: (text) => /davalı\s*:/i.test(text) && /bakanlığı|başkanlığı|müdürlüğü|valiliği|belediyesi|idare/i.test(afterLabel(text, "davalı")),
    missing: "Davalı idare açık unvanıyla gösterilmeli.",
    ok: "Davalı idare gösterilmiş.",
  },
  {
    id: "subject",
    title: "Davanın konusu",
    weight: 10,
    test: (text) => /konu\s*:/i.test(text) && afterLabel(text, "konu", ["açıklamalar", "olaylar"]).length > 45,
    missing: "Konu bölümü dava konusu işlemi ve istemi açıkça göstermeli.",
    ok: "Konu bölümü mevcut.",
  },
  {
    id: "reasons",
    title: "Davanın sebepleri",
    weight: 10,
    test: (text) => /açıklamalar|izah|gerekçe|hukuki\s+sebepler|nedenler/i.test(text) && text.length > 900,
    missing: "Davanın maddi ve hukuki sebepleri yeterli açıklıkta anlatılmalı.",
    ok: "Açıklama/gerekçe bölümü mevcut.",
  },
  {
    id: "evidence",
    title: "Dayanılan deliller ve ekler",
    weight: 8,
    test: (text) => /delil|ekler|ek\s*:/i.test(text),
    missing: "Dayanılan deliller ve dava konusu belgeler dilekçede veya eklerde gösterilmeli.",
    ok: "Delil/ek bölümü mevcut.",
  },
  {
    id: "noticeDate",
    title: "Yazılı bildirim veya öğrenme tarihi",
    weight: 8,
    test: (text) => /tebellüğ|tebliğ|öğrenme\s+tarihi|bildirim\s+tarihi/i.test(text) && /\b\d{1,2}[./]\d{1,2}[./]\d{4}\b/.test(text),
    missing: "Dava konusu işlemin yazılı bildirim veya öğrenme tarihi açıkça yazılmalı.",
    ok: "Bildirim/öğrenme tarihi tespit edildi.",
  },
  {
    id: "amount",
    title: "Uyuşmazlık konusu miktar",
    weight: 8,
    applies: (caseType) => ["tam-yargi", "iptal-tam-yargi"].includes(caseType),
    test: (text) => /\b\d[\d.,]*\s*(tl|₺|türk lirası)\b/i.test(text),
    missing: "Tam yargı davalarında uyuşmazlık konusu miktar gösterilmeli.",
    ok: "Uyuşmazlık miktarı yazılmış.",
  },
  {
    id: "request",
    title: "Sonuç ve istem",
    weight: 9,
    test: (text) => /sonuç\s*(ve|\/)?\s*(talep|istem)|netice\s*(ve|\/)?\s*talep/i.test(text),
    missing: "Sonuç ve istem bölümü açıkça bulunmalı.",
    ok: "Sonuç ve istem bölümü mevcut.",
  },
  {
    id: "signature",
    title: "İmza ve tarih",
    weight: 7,
    test: (text) => /\b\d{1,2}[./]\d{1,2}[./]\d{4}\b/.test(text) && /(davacı|vekili|av\.)/i.test(lastPart(text)),
    missing: "Dilekçenin sonunda tarih ve davacı/vekil imzası bulunmalı.",
    ok: "Tarih ve imza alanı tespit edildi.",
  },
  {
    id: "ydFormat",
    title: "Yürütmenin durdurulması biçimi",
    weight: 7,
    applies: (caseType) => caseType === "yd",
    test: (text) => /YÜRÜTMENİN\s+DURDURULMASI\s+TALEPLİDİR/.test(text),
    missing: "YD talepli dilekçede “YÜRÜTMENİN DURDURULMASI TALEPLİDİR” ibaresi büyük ve belirgin yazılmalı.",
    ok: "YD ibaresi biçimsel olarak uygun görünüyor.",
  },
];

fileEl.addEventListener("change", async () => {
  const file = fileEl.files?.[0];
  if (!file) return;

  if (file.type === "text/plain" || file.name.toLowerCase().endsWith(".txt")) {
    textEl.value = await file.text();
    fileStatusEl.textContent = `${file.name} yüklendi.`;
    return;
  }

  if (!location.origin.startsWith("http")) {
    fileStatusEl.textContent = `${file.name} seçildi. PDF/DOCX metin çıkarımı için sayfayı yerel sunucudan açın.`;
    draftOutputEl.textContent =
      "PDF/DOCX yükleme için bu dosyanın file:// olarak değil, yerel web sunucusu üzerinden açılması gerekir. Terminalde şu komutla çalıştırılabilir:\n\npython3 server.py\n\nSonra http://127.0.0.1:8765 adresinden deneyin.";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  fileStatusEl.textContent = `${file.name} okunuyor...`;

  try {
    const response = await fetch("/extract", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Dosya okunamadı.");
    }
    textEl.value = result.text;
    fileStatusEl.textContent = `${file.name} yüklendi.`;
    analysisOutputEl.textContent = "Dosya metni dilekçe alanına aktarıldı. Dilekçeyi analiz et düğmesiyle analizi başlatabilirsiniz.";
    draftOutputEl.textContent = "Taslak oluşturulduğunda burada görünecek.";
  } catch (error) {
    fileStatusEl.textContent = `${file.name} okunamadı.`;
    draftOutputEl.textContent = `Dosya yükleme hatası: ${error.message}`;
  }
});

analyzeBtn.addEventListener("click", async () => {
  const petitionText = textEl.value.trim();
  if (!petitionText) {
    draftOutputEl.textContent = "Analiz için önce dilekçe metni girilmeli veya dosya yüklenmelidir.";
    return;
  }

  if (!location.origin.startsWith("http")) {
    draftOutputEl.textContent = "Analiz için sayfayı yerel sunucu veya Render adresi üzerinden açın.";
    return;
  }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analiz ediliyor...";
  summaryTextEl.textContent = "Dilekçe türü belirleniyor ve ayrıntılı ön inceleme kontrolü yapılıyor.";

  try {
    const response = await fetch("/ai-analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: petitionText,
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "OpenAI analizi tamamlanamadı.");
    }

    lastAnalysis = mapAiAnalysis(result.analysis);
    lastAiAnalysis = result.analysis;
    renderAnalysis(lastAnalysis);
    renderAiPanels(result.analysis);
    analysisOutputEl.textContent = buildAiReport(result.analysis);
    draftOutputEl.textContent = result.analysis.revisedPetition || "Taslak üretilemedi.";
  } catch (error) {
    summaryTextEl.textContent = "Analiz çalıştırılamadı.";
    analysisOutputEl.textContent = `Analiz hatası: ${error.message}`;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Dilekçeyi analiz et";
  }
});

clearBtn.addEventListener("click", () => {
  textEl.value = "";
  fileEl.value = "";
  fileStatusEl.textContent = "PDF, DOCX veya TXT dosyasını yükleyin.";
  lastAnalysis = null;
  lastAiAnalysis = null;
  summaryTextEl.textContent = "Henüz analiz yapılmadı.";
  verdictBadgeEl.textContent = "Bekliyor";
  verdictBadgeEl.className = "badge neutral";
  scoreValueEl.textContent = "0%";
  scoreBarEl.value = 0;
  caseTypeValueEl.textContent = "-";
  criticalValueEl.textContent = "0";
  fixableValueEl.textContent = "0";
  renderList(missingInfoListEl, ["Analizden sonra listelenecek."]);
  renderList(fixableListEl, ["Analizden sonra listelenecek."]);
  renderList(attachmentListEl, ["Analizden sonra listelenecek."]);
  checklistEl.className = "checklist empty";
  checklistEl.textContent = "Dilekçe kontrolü burada listelenecek.";
  analysisOutputEl.textContent = "Analizden sonra rapor burada görünecek.";
  draftOutputEl.textContent = "Taslak oluşturulduğunda burada görünecek.";
  detailTableEl.className = "detail-table empty-table";
  detailTableEl.textContent = "Analizden sonra tablo burada görünecek.";
});

buildDraftBtn.addEventListener("click", () => {
  if (lastAiAnalysis?.revisedPetition) {
    draftOutputEl.textContent = lastAiAnalysis.revisedPetition;
    return;
  }

  if (!lastAnalysis) {
    lastAnalysis = analyzePetition(textEl.value, "auto");
    renderAnalysis(lastAnalysis);
    analysisOutputEl.textContent = "OpenAI analizi yapılmadığı için hızlı kontrol sonucuna göre yerel taslak oluşturuldu.";
  }
  draftOutputEl.textContent = buildDraft(textEl.value, lastAnalysis);
});

downloadTxtBtn.addEventListener("click", () => {
  const content = draftOutputEl.textContent.trim();
  if (!content || content.startsWith("Taslak")) return;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "iyuk-duzeltilmis-dilekce.txt";
  link.click();
  URL.revokeObjectURL(link.href);
});

printBtn.addEventListener("click", () => window.print());

function analyzePetition(rawText, caseType) {
  const text = normalize(rawText);
  const activeChecks = checks.filter((check) => !check.applies || check.applies(caseType));
  const items = activeChecks.map((check) => {
    const passed = text.length > 0 && check.test(text, caseType);
    return {
      ...check,
      status: passed ? "ok" : "missing",
      message: passed ? check.ok : check.missing,
    };
  });

  const totalWeight = activeChecks.reduce((sum, check) => sum + check.weight, 0);
  const earnedWeight = items
    .filter((item) => item.status === "ok")
    .reduce((sum, item) => sum + item.weight, 0);
  const score = Math.round((earnedWeight / totalWeight) * 100);
  const missingCount = items.filter((item) => item.status === "missing").length;

  let verdict = "Geçer";
  let badge = "good";
  if (score < 72 || missingCount >= 4) {
    verdict = "Geçmez";
    badge = "bad";
  } else if (missingCount > 0 || score < 90) {
    verdict = "Riskli";
    badge = "warn";
  }

  return {
    caseType,
    caseTypeLabel: caseTypeLabels[caseType],
    score,
    verdict,
    badge,
    items,
    missingCount,
  };
}

function renderAnalysis(analysis) {
  verdictBadgeEl.textContent = analysis.verdict;
  verdictBadgeEl.className = `badge ${analysis.badge}`;
  scoreValueEl.textContent = `${analysis.score}%`;
  scoreBarEl.value = analysis.score;

  summaryTextEl.textContent = `${analysis.caseTypeLabel} için ${analysis.items.length} unsur kontrol edildi. Eksik/riskli unsur sayısı: ${analysis.missingCount}.`;

  checklistEl.className = "checklist";
  checklistEl.innerHTML = "";
  analysis.items.forEach((item) => {
    const row = document.createElement("article");
    row.className = `check-item ${item.status === "ok" ? "" : item.rawStatus === "eksik" ? "missing" : "risk"}`;
    row.innerHTML = `
      <span class="pill ${item.status === "ok" ? "ok" : item.rawStatus === "eksik" ? "missing" : "risk"}">${item.label}</span>
      <div>
        <strong>${item.title}</strong>
        <p>${item.message}</p>
      </div>
    `;
    checklistEl.appendChild(row);
  });
}

function mapAiAnalysis(ai) {
  const items = (ai.checklist || []).map((item) => {
    const rawStatus = normalizeStatus(item.status);
    return {
      id: item.id || item.title,
      title: item.title || "Kontrol unsuru",
      weight: 1,
      rawStatus,
      label: statusLabel(rawStatus),
      status: rawStatus === "uygun" ? "ok" : "missing",
      message: item.explanation || item.recommendation || "Değerlendirme bulunamadı.",
    };
  });

  const missingCount = items.filter((item) => item.status !== "ok").length;
  const score = Number.isFinite(ai.score) ? ai.score : Math.max(0, Math.round(((items.length - missingCount) / Math.max(items.length, 1)) * 100));
  const verdictMap = {
    "geçer": "Geçer",
    "riskli": "Riskli",
    "geçmez": "Geçmez",
  };
  const verdict = verdictMap[String(ai.verdict || "").toLowerCase()] || "Riskli";
  const badge = verdict === "Geçer" ? "good" : verdict === "Geçmez" ? "bad" : "warn";

  return {
    caseType: ai.detectedCaseType || "auto",
    caseTypeLabel: ai.detectedCaseType || caseTypeLabels.auto,
    score,
    verdict,
    badge,
    items,
    missingCount,
  };
}

function renderAiPanels(ai) {
  const checklist = ai.checklist || [];
  const criticalItems = checklist.filter((item) => ["eksik", "riskli"].includes(normalizeStatus(item.status)));
  const fixableItems = checklist.filter((item) => normalizeStatus(item.status) === "düzeltilmeli");

  caseTypeValueEl.textContent = ai.detectedCaseType || "-";
  criticalValueEl.textContent = String(criticalItems.length);
  fixableValueEl.textContent = String(uniqueTextList([
    ...fixableItems.map((item) => item.title || item.recommendation || item.explanation),
    ...(ai.fixableIssues || []),
  ]).length);

  renderList(missingInfoListEl, ai.missingInformation?.length ? ai.missingInformation : ["Eksik gerçek bilgi bildirilmedi."]);
  renderList(
    fixableListEl,
    uniqueTextList([
      ...(ai.fixableIssues || []),
      ...fixableItems.map((item) => `${item.title}: ${item.recommendation || item.explanation}`),
    ]).length
      ? uniqueTextList([
          ...(ai.fixableIssues || []),
          ...fixableItems.map((item) => `${item.title}: ${item.recommendation || item.explanation}`),
        ])
      : ["Biçimsel düzeltme önerisi bildirilmedi."],
  );
  renderList(
    attachmentListEl,
    ai.attachmentIssues?.length ? ai.attachmentIssues : ["Ek/dosya kontrolü için ayrıca uyarı bildirilmedi."],
  );
  renderDetailTable(checklist);
}

function uniqueTextList(values) {
  const seen = new Set();
  const result = [];
  values.forEach((value) => {
    const cleaned = String(value || "").trim();
    if (!cleaned) return;
    const key = cleaned.toLocaleLowerCase("tr-TR");
    if (seen.has(key)) return;
    seen.add(key);
    result.push(cleaned);
  });
  return result;
}

function renderList(target, items) {
  target.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    target.appendChild(li);
  });
}

function renderDetailTable(items) {
  if (!items.length) {
    detailTableEl.className = "detail-table empty-table";
    detailTableEl.textContent = "Kontrol tablosu oluşturulamadı.";
    return;
  }

  detailTableEl.className = "detail-table";
  const rows = items
    .map((item) => {
      const status = normalizeStatus(item.status);
      return `<tr>
        <td><span class="pill ${status === "uygun" ? "ok" : status === "eksik" ? "missing" : "risk"}">${escapeHtml(statusLabel(status))}</span></td>
        <td>${escapeHtml(item.title || "-")}</td>
        <td>${escapeHtml(item.evidence || "-")}</td>
        <td>${escapeHtml(item.recommendation || item.explanation || "-")}</td>
      </tr>`;
    })
    .join("");

  detailTableEl.innerHTML = `<table>
    <thead>
      <tr>
        <th>Durum</th>
        <th>Unsur</th>
        <th>Dayanak</th>
        <th>Öneri</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function normalizeStatus(status) {
  return String(status || "").trim().toLocaleLowerCase("tr-TR");
}

function statusLabel(status) {
  const labels = {
    uygun: "Uygun",
    riskli: "Riskli",
    eksik: "Eksik",
    düzeltilmeli: "Düzeltilmeli",
  };
  return labels[status] || "Riskli";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildAiReport(ai) {
  const checklist = (ai.checklist || [])
    .map((item, index) => {
      return `${index + 1}. ${item.title}
Durum: ${item.status}
Dayanak: ${item.evidence || "-"}
Değerlendirme: ${item.explanation}
Öneri: ${item.recommendation || "-"}`;
    })
    .join("\n\n");

  const missingInfo = (ai.missingInformation || [])
    .map((item, index) => `${index + 1}. ${item}`)
    .join("\n");
  const fixableInfo = (ai.fixableIssues || [])
    .map((item, index) => `${index + 1}. ${item}`)
    .join("\n");
  const attachmentInfo = (ai.attachmentIssues || [])
    .map((item, index) => `${index + 1}. ${item}`)
    .join("\n");

  return `OPENAI DESTEKLİ ÖN İNCELEME RAPORU

Sonuç: ${ai.verdict || "Riskli"}
Uygunluk puanı: ${ai.score ?? "-"}%
Tespit edilen dava türü: ${ai.detectedCaseType || "-"}
Tespit gerekçesi: ${ai.detectedCaseTypeReason || "-"}

Kısa değerlendirme:
${ai.summary || "-"}

İYUK m.3 ve ön inceleme kontrolü:
${checklist || "-"}

Eksik gerçek bilgiler:
${missingInfo || "-"}

Düzeltilebilir noktalar:
${fixableInfo || "-"}

Ek/dosya kontrolü:
${attachmentInfo || "-"}

Uygun hale getirilmiş dilekçe taslağı:
${ai.revisedPetition || "[Taslak üretilemedi.]"}
`;
}

function buildDraft(rawText, analysis) {
  const text = normalize(rawText);
  if (!text) {
    return "Düzenlenmiş taslak oluşturmak için önce dilekçe metni girilmelidir.";
  }

  const extracted = {
    court: extractLine(text, /mahkemesi\s+(sayın\s+)?başkanlığı'?na.*|danıştay.*başkanlığı'?na.*/i),
    plaintiff: extractSection(text, "davacı", ["vekili", "davalı", "konu"]),
    attorney: extractSection(text, "vekili", ["davalı", "konu"]),
    defendant: extractSection(text, "davalı", ["konu", "tebellüğ", "tebliğ", "açıklamalar"]),
    subject: extractSection(text, "konu", ["tebellüğ", "tebliğ", "açıklamalar"]),
    noticeDate: extractLine(text, /(tebellüğ|tebliğ|öğrenme|bildirim).*?\d{1,2}[./]\d{1,2}[./]\d{4}/i),
    body: extractBody(text),
    request: extractFrom(text, /sonuç\s*(ve|\/)?\s*(talep|istem)|netice\s*(ve|\/)?\s*talep/i),
    annexes: extractFrom(text, /ekler|ek\s*:/i),
  };

  const hasMissingAddress = analysis.items.some((item) => item.id === "plaintiffAddress" && item.status === "missing");
  const ydLine = analysis.caseType === "yd" ? "YÜRÜTMENİN DURDURULMASI TALEPLİDİR\n\n" : "";

  return `${extracted.court || "[GÖREVLİ VE YETKİLİ İDARE MAHKEMESİ BAŞKANLIĞI'NA]"}

${ydLine}DAVACI:
${cleanOrPlaceholder(extracted.plaintiff, "[Davacı ad/soyad veya unvanı]")}
${hasMissingAddress ? "Adres: [Davacının açık adresi yazılmalıdır]\n" : ""}

VEKİLİ:
${cleanOrPlaceholder(extracted.attorney, "[Varsa vekil ad/soyad ve adres bilgileri]")}

DAVALI:
${cleanOrPlaceholder(extracted.defendant, "[Davalı idarenin açık unvanı ve adresi]")}

DAVA TÜRÜ:
${analysis.caseTypeLabel}

KONU:
${refineSubject(extracted.subject, analysis.caseType)}

YAZILI BİLDİRİM / ÖĞRENME TARİHİ:
${cleanOrPlaceholder(extracted.noticeDate, "[Dava konusu işlem veya ret cevabının tebliğ/öğrenme tarihi]")}

AÇIKLAMALAR:
${cleanOrPlaceholder(extracted.body, "[Maddi olaylar kronolojik ve açık şekilde yazılmalıdır.]")}

HUKUKİ SEBEPLER:
2577 sayılı İdari Yargılama Usulü Kanunu, ilgili özel kanun hükümleri ve somut olaya uygulanacak sair mevzuat.

DELİLLER:
${cleanOrPlaceholder(extracted.annexes, "[Dava konusu işlem, başvuru belgeleri, tebliğ belgesi ve diğer deliller]")}

SONUÇ VE İSTEM:
${refineRequest(extracted.request, analysis.caseType)}

Tarih: [Gün/Ay/Yıl]

Davacı / Vekili
[İmza]`;
}

function normalize(text) {
  return (text || "").replace(/\r/g, "").replace(/[ \t]+/g, " ").trim();
}

function afterLabel(text, label, stopLabels = []) {
  const labelPattern = new RegExp(`${label}\\s*:`, "i");
  const start = text.search(labelPattern);
  if (start === -1) return "";
  const rest = text.slice(start).replace(labelPattern, "");
  const stops = stopLabels
    .map((stop) => rest.search(new RegExp(`\\b${stop}\\s*:`, "i")))
    .filter((index) => index > 0);
  const end = stops.length ? Math.min(...stops) : Math.min(rest.length, 450);
  return rest.slice(0, end).trim();
}

function hasPersonLikeValue(value) {
  return /[A-ZÇĞİÖŞÜa-zçğıöşü]{2,}\s+[A-ZÇĞİÖŞÜa-zçğıöşü]{2,}|[A-ZÇĞİÖŞÜa-zçğıöşü]{4,}/.test(value);
}

function lastPart(text) {
  return text.slice(Math.max(0, text.length - 700));
}

function extractLine(text, regex) {
  const match = text.match(regex);
  return match ? match[0].trim() : "";
}

function extractSection(text, label, stops) {
  return afterLabel(text, label, stops).replace(/\s+/g, " ").trim();
}

function extractFrom(text, regex) {
  const index = text.search(regex);
  if (index === -1) return "";
  return text.slice(index).trim();
}

function extractBody(text) {
  const start = text.search(/açıklamalar|olaylar/i);
  const end = text.search(/sonuç\s*(ve|\/)?\s*(talep|istem)|netice\s*(ve|\/)?\s*talep/i);
  if (start === -1) return "";
  return text.slice(start, end > start ? end : undefined).trim();
}

function cleanOrPlaceholder(value, placeholder) {
  const cleaned = (value || "").replace(/\s+/g, " ").trim();
  return cleaned || placeholder;
}

function refineSubject(subject, caseType) {
  const cleaned = cleanOrPlaceholder(subject, "");
  if (!cleaned) {
    if (caseType === "iptal") {
      return "[Dava konusu idari işlemin tarih/sayısı belirtilerek iptali istemidir.]";
    }
    if (caseType === "iptal-tam-yargi") {
      return "[Dava konusu idari işlemin iptali ile bu işlem nedeniyle doğan zararın tazmini istemidir.]";
    }
    return "[İdari işlem/eylem nedeniyle uğranılan zararın tazmini istemidir.]";
  }
  return cleaned;
}

function refineRequest(request, caseType) {
  const cleaned = cleanOrPlaceholder(request, "");
  if (cleaned) return cleaned;
  if (caseType === "iptal") {
    return "Açıklanan nedenlerle dava konusu idari işlemin iptaline, yargılama giderleri ile vekalet ücretinin davalı idare üzerinde bırakılmasına karar verilmesini arz ve talep ederim.";
  }
  if (caseType === "iptal-tam-yargi") {
    return "Açıklanan nedenlerle dava konusu idari işlemin iptaline, uğranılan zararın yasal faiziyle birlikte tazminine, yargılama giderleri ile vekalet ücretinin davalı idare üzerinde bırakılmasına karar verilmesini arz ve talep ederim.";
  }
  if (caseType === "yd") {
    return "Açıklanan nedenlerle öncelikle yürütmenin durdurulmasına, dava konusu işlemin iptaline, yargılama giderleri ile vekalet ücretinin davalı idare üzerinde bırakılmasına karar verilmesini arz ve talep ederim.";
  }
  return "Açıklanan nedenlerle uğranılan zararın yasal faiziyle birlikte tazminine, yargılama giderleri ile vekalet ücretinin davalı idare üzerinde bırakılmasına karar verilmesini arz ve talep ederim.";
}
