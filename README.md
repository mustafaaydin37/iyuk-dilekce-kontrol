# İdari Dava Dilekçelerinin Kabulü

Bu prototip, idari dava dilekçelerini İYUK m.3 bakımından ön inceleme mantığıyla kontrol eden bağımsız bir web arayüzüdür.

## Çalıştırma

Başka bir bilgisayarda çalıştırmak için bu klasörü komple taşıyın. Bilgisayarda Python 3 yüklü olmalıdır.

Mac:

```bash
chmod +x start-mac.command
./start-mac.command
```

Windows:

```text
start-windows.bat dosyasına çift tıklayın.
```

Manuel çalıştırma:

```bash
python3 -m pip install -r requirements.txt
python3 server.py
```

Sonra tarayıcıdan şu adres açılır:

```text
http://127.0.0.1:8765
```

Yerel ağdaki başka cihazlardan erişmek için:

```bash
python3 server.py --host 0.0.0.0 --port 8765
```

Bu durumda aynı ağdaki cihazlar bilgisayarın yerel IP adresiyle bağlanabilir.

## Render ile yayınlama

Bu proje Render üzerinde web service olarak çalışacak şekilde hazırlanmıştır.

1. Projeyi bir GitHub reposuna yükleyin.
2. Render hesabında **New +** menüsünden **Blueprint** veya **Web Service** seçin.
3. GitHub reposunu bağlayın.
4. Blueprint seçerseniz Render `render.yaml` dosyasını otomatik okur.
5. Web Service seçerseniz şu ayarları girin:

```text
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: python server.py --host 0.0.0.0
```

Render deploy tamamlandığında uygulama herkese açık bir `.onrender.com` adresinden çalışır.

OpenAI destekli derin analiz için Render servisinde şu environment variable eklenmelidir:

```text
OPENAI_API_KEY=sk-...
```

İsteğe bağlı model seçimi:

```text
OPENAI_MODEL=gpt-5.4-mini
```

## İlk sürüm kapsamı

- Dilekçe metni yapıştırma
- PDF/DOCX/TXT dosya yükleme ve metin çıkarımı
- Dava türü seçimi
- İYUK m.3 kontrol listesi
- Eksik unsur bildirimi
- Uygun hale getirilmiş taslak üretimi
- Metin indirme
- Tarayıcı yazdırma üzerinden PDF çıktısı

## Üretim sürümünde eklenecekler

- Word ve PDF dosyası üretimi
- OpenAI API ile derin hukuki kontrol
- Kullanıcı hesapları ve kayıtlı analiz geçmişi
- Dava türüne göre daha ayrıntılı özel kontrol kuralları
