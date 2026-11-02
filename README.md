# PDF Baskı & Cilt Stüdyosu

**Sürüm:** `version.py` içindeki tek kaynaktan okunur (şu an 2.2.2)  
**Geliştirici:** Abdülkadir Hamza — hamza_kadir@hotmail.com

PyMuPDF ile vektörel (yeniden örneklemesiz) PDF hazırlığı yapan Windows masaüstü
uygulaması: duplex cilt payı, sabit alt/üst pay, sayfa numaralandırma, kırpma
taraması, sonuç doğrulama ve kayıpsız birleştirme.

Kaynak dosyaya asla yazılmaz. Çıktı önce geçici dosyaya yazılır, başarılı olursa
hedefe taşınır.

## Özellikler

### Cilt payı ve sayfa düzeni
- Tek ve çift sayfalar için ayrı X/Y ofseti (duplex kitap düzeni).
- İki ebat modu: **hedef ebat sabit** veya **kaynak ebat + cilt payı** (karışık
  ebatlı belgelerde kırpma olmaz).
- Sabit ebatta taşma davranışı: **Kırp** (eski davranış) veya **Sayfaya sığdır**
  (içeriği orantılı küçültür, hiçbir şeyi kırpmaz). Kırpma riski taraması risk
  bulduğunda üç seçenek sunar: sığdır, kırp, iptal.
- Döndürülmüş (`/Rotate`) ve kırpılmış (`CropBox`) sayfalar görünür hâlleriyle
  işlenir; döndürmeden kaynaklanan içerik kaybı olmaz.
- Hazır cilt payı düğmeleri: 10 / 15 / 20 mm.
- Kağıt şablonları: A4, A5, B5, Letter; dikey/yatay.
- **İşlem dışı sayfalar**: cilt payı sekmesinde yalnızca cilt payından, kenar
  boşluğu sekmesinde yalnızca alt/üst paydan hariç tutar. İki liste bağımsızdır;
  örn. ara kapağa cilt payı verip alt boşluk vermemek mümkündür.
- **Tek yerden modül açma**: "Uygulanacak işlemler" şeridindeki üç onay kutusu
  cilt payı, kenar boşluğu ve numarayı yönetir; her sekmede ayrı anahtar yoktur.
  Bir alana değer girdiğinizde ilgili modül kendiliğinden etkinleşir; istemezseniz
  üst şeritten kapatabilirsiniz. Şeritteki düğme, duruma göre **Tümünü aç** veya
  **Tümünü kapat** olarak değişir.
- Alt payda üç mod: **Uzat** (kırpmaz, varsayılan), **Sığdır** (orantılı
  küçültür), **Kaydır** (kırpabilir; önizlemede kırmızı uyarı).

### Sayfa numaralandırma
- Dış kenar, alt orta veya iç kenar.
- Biçimler: `1`, `- 1 -`, `1 / Toplam`, `Sayfa 1`.
- Başlangıç sayfası, ilk numara, taban ve yan boşluk.
- Numarasız sayfalar (`1, 2, 15, 24-26`) ve ardışık sayaç (90 → kapak → 91).

### Kalite ve güvenilirlik
- **Kırpma riski taraması**: işlemden önce hangi sayfada ne kadar içeriğin
  taşacağını listeler; onay olmadan devam etmez.
- **Sonuç doğrulama raporu**: sayfa sayısı, ebat, metin, bağlantı ve
  açıklama/form karşılaştırması.
- **Atomik kayıt**: yarım/bozuk çıktı bırakmaz, kaynağı değiştirmez.
- **Günlük**: `%LOCALAPPDATA%\PDFBaskiCiltStudyosu\studio.log` (1 MB'ta döner,
  3 yedek). Hata penceresinde "Panoya kopyala" vardır.
- **Canlı önizleme**: ilk sayfa ve karşı sayfa; cilt şeridi, alt/üst pay ve
  numara konumu işaretli. Ayar değişince kendiliğinden yenilenir; "Önizlemeyi
  yenile" düğmesi vardır. Birleştirme sekmesinde **seçili PDF** önizlenir.
- **Sürükle-bırak**: PDF'leri pencereye bırakın; Türkçe karakterli yollar
  desteklenir. Birleştirme sekmesinde hepsi listeye eklenir, diğer sekmelerde
  ilki açılır ve durum çubuğu kaç dosya olduğunu bildirir.
- **Alan bazlı doğrulama**: hatalı kutu kırmızı olur, altında kısa açıklama çıkar.

### Birleştirme
- Sürükleyerek sıralama, dosya başına 0/90/180/270° rotasyon; seçim yokken
  rotasyon düğmeleri hiçbir dosyayı değiştirmez, **Tümünü döndür** ayrıdır.
- Satır başında sürükleme tutamacı, dosya adı, sayfa aralığı alanı ve rotasyon
  rozeti; seçili satırda rozet okunabilirliğini korur.
- Kısayollar: `Del` seçili dosyayı kaldırır, `Alt+↑/↓` sıralar.
- Seçili dosya canlı önizleme panelinde gösterilir.
- Yer imleri (TOC) sayfa numaraları kaydırılarak korunur; ilk dosyanın meta
  verisi korunur.
- "Birleştirdikten sonra aktif ayarları uygula" ile tek geçişte cilt payı,
  boşluk ve numaralandırma.
- Eksik dosyalar atlanır ve sonuç raporunda açıkça bildirilir.

### Arayüz
- Açık / koyu / sistem teması; okunabilir seçili düğme renkleri.
- Tema değişiminde pencere gizlenmez: başlık çubuğu rengi doğrudan Windows
  özniteliğiyle değişir (CustomTkinter'in gizle/göster hilesi devre dışı).
- Pencere boyutu ve minimum boyut, ekran ölçeğinden bağımsız doğru hesaplanır.
- Profiller: kaydet, yükle, sil (JSON). Hazır öneriler: Tez, Spiral cilt,
  Sıcak tutkal cilt, Kitapçık.
- Birim: mm, cm, pt. İnç motor desteği ileride açılmak üzere arayüzde kapalıdır.
- Son ayarlar ve tema otomatik hatırlanır.
- Hakkında penceresi: sürüm, geliştirici, altyapı, kısayollar, ayar/günlük yolları
  ve bu klasörleri açma düğmeleri.
- Kısayollar: `Ctrl+O` dosya aç, `Ctrl+Enter` işle, `Enter` işle, `Esc` iptal.
- Çıktı adı çakışırsa `ad (2).pdf` biçiminde otomatik numaralanır.

## Kurulum ve çalıştırma

Python 3.10+ gerekir.

```bat
python -m pip install -r requirements.txt
Baslat.bat
```

`Baslat.bat` Python'u ve `pythonw`'yi kendisi arar; eksikse anlaşılır mesaj verir.

Elle çalıştırma:

```bat
python app.py
```

## Testler

```bat
python -m pytest
```

- Motor testleri gerçek PDF üretip PyMuPDF ile sonucu yeniden okur.
- Arayüz testleri gerçek Tk penceresi kurar; taşma, doğrulama, birim dönüşümü,
  önizleme, işlem hattı ve birleştirme akışını dener.
- Görsel regresyon altın görüntülerle karşılaştırır:
  `tests/golden/`. Bilinçli güncelleme:

```bat
set UPDATE_GOLDENS=1
python -m pytest tests/test_visual_regression.py
set UPDATE_GOLDENS=
```

Referans PDF setini yeniden üretmek için:

```bat
python tools/make_reference_set.py
```

## EXE oluşturma

```bat
build_exe.bat
```

Betik bağımlılıkları denetler, testleri çalıştırır, simgeyi üretir ve
`dist\PDF_Baski_Cilt_Studyosu_<sürüm>.exe` dosyasını oluşturur.

## Dosya düzeni

```
app.py                  Arayüz; tek build_config() ile motora bağlanır
gutter_engine.py        Geometri, numaralandırma, tarama, doğrulama, birleştirme
settings_store.py       Ayar/profil deposu, günlük kurulumu
version.py              Tek sürüm kaynağı
make_icon.py            Çok boyutlu simge üreticisi
tests/                  Motor, arayüz, depo ve görsel regresyon testleri
tools/                  Referans PDF seti üreticisi
samples/referans/       Gerçek referans PDF seti
```

## Ayarlar ve gizlilik

- Ayarlar: `%APPDATA%\PDFBaskiCiltStudyosu\settings.json`
- Günlük: `%LOCALAPPDATA%\PDFBaskiCiltStudyosu\studio.log`
- Hiçbir veri ağa gönderilmez; dosyalar yalnızca yerelde işlenir.

## Bilinen kapsam sınırları

Bu sürüm planın Tur 1 kapsamını tamamlar. Şunlar sonraki turlara bırakılmıştır:
Roma rakamı ve bölüm bazlı numaralama, özel metin şablonu/Unicode gömülü yazı
tipi, 4'ün katına tamamlama, sayfa ayıklama sekmesi, toplu işlem, filigran,
kesim işaretleri/bleed, kitapçık ve n-up impozisyon, creep telafisi, CLI,
kurulum paketi ve İngilizce arayüz.

Windows %125/%150 ölçeklemede son görsel onay kullanıcı makinesinde
yapılmalıdır.
