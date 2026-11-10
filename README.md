# PDF Baskı & Cilt Stüdyosu

**Sürüm:** `version.py` içindeki tek kaynaktan okunur (şu an 2.9.0)  
**Geliştirici:** Abdülkadir Hamza — hamza_kadir@hotmail.com

PyMuPDF ile vektörel (yeniden örneklemesiz) PDF hazırlığı yapan Windows masaüstü
uygulaması: duplex cilt payı, sabit alt/üst pay, sayfa numaralandırma, kırpma
taraması, sonuç doğrulama ve kayıpsız birleştirme.

Kaynak dosyaya asla yazılmaz. Çıktı önce geçici dosyaya yazılır, başarılı olursa
hedefe taşınır.

## 2.9.0 arayüz ve toplu işlem yenilikleri

- Kaynak PDF veya birleştirme listesi hazır değilse ana işlem düğmesi devre dışı kalır ve gereken adımı söyler.
- Belge yokken önizleme alanı sade bir yönlendirme gösterir; işlem öncesi **Ön kontrol** özeti kaynağı, etkin ayarları ve çıktı tercihlerini listeler.
- Üst çubuktan **Toplu işlem…** ile dosya/klasör seçin, alt klasörleri tarayın, mevcut ayarı veya kayıtlı profili kullanın; kırpma riski bulunanları atlayın ve dosya başına sonucu izleyin.
- İşlem, iptal ve sonuç düğmeleri yalnız uygun aşamada görünür. Tema seçimi tek yerde, üst çubuktadır.

## 2.8.0 özellikleri

- Ayarlar: görünüm/birim/dil, liste ve önizleme, PDF çıktısı, sıfırlama. Optimizasyon ve form/açıklama gömme buraya taşındı.
- Birleştirmede bağımsız eşitleme; özel ebat ve çevre boşluğu; uzun listede görünür satır kontrolleri ve 56×72 küçük resimler.
- Önizlemede yakınlaştırma (Ctrl+tekerlek), gezinme, görünümü döndürme, Önce/Sonra geçişi.
- Bölüm numaralandırması ve boş sayfa; soldan/sağdan/üstten cilt.
- Üst çubuk → **PDF araçları…**: sayfa ayıklama/bölme, filigran/Bates, kesim işaretleri ve taşma payı, kitapçık ve 2-up/4-up montaj.
- Açık/koyu tema tek tıklamayla boyanır; Türkçe/English arayüz Ayarlar’dan seçilir.

Ayrıntı ve doğrulama: [2.9.0 sürüm notları](docs/v2.9.0-surum-notlari.md) · [2.8.1 DPI düzeltmesi](docs/v2.8.1-surum-notlari.md) · [2.8.0 özellikleri](docs/v2.8.0-surum-notlari.md). Yol haritası: [güncel plan](docs/app-bolme-plani.md).

### Klasör bazlı toplu işlem

```powershell
python gutter_engine.py --profile "Tez (üniversite)" --input "C:\PDFler" --output "C:\Ciktilar"
python studio_cli.py --profile "ayarlar.json" --input "C:\PDFler" --output "C:\Ciktilar" --recursive
```

## Özellikler

### Sayfa düzeni
- **Tek sekme**: Cilt payı, alt/üst boşluk, sayfa boyutu ve özel sayfalar aynı
  "Sayfa Düzeni" adımında; her bölüm kendi kartında.
- Cilt payı ve alt/üst boşluk **ayrı anahtarlarla** açılır; anahtar bölüm
  başlığındadır, rozet (Etkin / Devre dışı) durumu gösterir.
- Tek ve çift sayfalar için ayrı X/Y ofseti (duplex kitap düzeni).
- İki ebat modu: **hedef ebat sabit** veya **kaynak ebat + cilt payı** (karışık
  ebatlı belgelerde kırpma olmaz).
- Tek "Taşarsa ne olsun" seçimi: **Sayfa uzasın** (kırpmaz, varsayılan),
  **İçerik küçülsün** (orantılı küçültür) veya **Taşan kırpılsın** (kırpabilir;
  önizlemede kırmızı uyarı). Kırpma riski taraması risk bulduğunda seçim
  yapılmasını ister.
- Döndürülmüş (`/Rotate`) ve kırpılmış (`CropBox`) sayfalar görünür hâlleriyle
  işlenir; döndürmeden kaynaklanan içerik kaybı olmaz.
- Hazır cilt payı düğmeleri: 10 / 15 / 20 mm.
- Kağıt şablonları: A4, A5, B5, Letter; dikey/yatay.
- **Özel sayfalar**: sayfa aralığı + üç mod (yalnız cilt payı, yalnız alt/üst
  boşluk, hiçbiri) kural satırları; ara kapak için tek tık kuralı. Çakışan
  aralıklar satır altında uyarıyla gösterilir.
- **Tek yerden modül açma**: şeritteki üç onay kutusu cilt payı, boşluk ve
  numarayı da yönetir; bir alana değer girildiğinde ilgili modül kendiliğinden
  etkinleşir. Şeritteki düğme duruma göre **Tümünü aç** veya **Tümünü kapat**
  olur.
- Alt/üst boşluk bölümünde "Kitapçık için 4'ün katına tamamla" onayı vardır.

### Sayfa numaralandırma
- Dış kenar, alt orta veya iç kenar.
- Biçimler: `1`, `- 1 -`, `1 / Toplam`, `Sayfa 1`.
- Başlangıç sayfası, ilk numara, taban ve yan boşluk.
- Numarasız sayfalar (`1, 2, 15, 24-26`) ve ardışık sayaç (90 → kapak → 91).

### Kalite ve güvenilirlik
- **Kırpma riski taraması**: işlemden önce hangi sayfada ne kadar içeriğin
  taşacağını listeler; onay olmadan devam etmez.
- **Sonuç doğrulama raporu**: sayfa sayısı, ebat, metin, bağlantı ve
  açıklama/form karşılaştırması; ayrıca kaynak ile çıktının **görsel (piksel)
  karşılaştırması** (60 sayfaya kadar eşit aralıklı örnekleme). Taranmış PDF'lerde
  ve döndürme/yerleşim hatalarında metin karşılaştırmasının göremediği içerik
  kaybını yakalar.
- **Atomik kayıt**: yarım/bozuk çıktı bırakmaz, kaynağı değiştirmez.
- **Günlük**: `%LOCALAPPDATA%\PDFBaskiCiltStudyosu\studio.log` (1 MB'ta döner,
  3 yedek). Hata penceresinde "Panoya kopyala" vardır.
- **Tanılama paketi**: Kılavuz & Hakkında → "Tanılama paketi oluştur (.zip)" günlüğü,
  anonim ayarları (son dosyalar ve yollar çıkarılır) ve sürüm/DPI bilgisini tek zip'e koyar;
  destek istenirken gönderilebilir. PDF içeriği pakete girmez.
- **Canlı önizleme**: çift sayfa açılımı (1-2, 3-4…; tek sayıda son sayfa tek); cilt şeridi, alt/üst pay ve
  numara konumu işaretli. Ayar değişince kendiliğinden yenilenir; "Önizlemeyi
  yenile" düğmesi vardır. Birleştirme sekmesinde **seçili PDF** önizlenir.
- **Sürükle-bırak**: PDF'leri pencereye bırakın; Türkçe karakterli yollar
  desteklenir. Birleştirme sekmesinde hepsi listeye eklenir, diğer sekmelerde
  ilki açılır ve durum çubuğu kaç dosya olduğunu bildirir.
- **Alan bazlı doğrulama**: hatalı kutu kırmızı olur, altında kısa açıklama çıkar.

### Birleştirme
- Sürükleyerek sıralama: sürüklerken satırlar yerinde kalır, **bırakılacak yer mavi çizgiyle** gösterilir
  ve fare bırakılınca seçili satırlar (tek ya da blok) oraya taşınır; fareyi listenin alt/üst
  kenarına getirince liste kendiliğinden kayar. "Satırları yalnız ⠿ tutamacından sürükle"
  seçeneği yanlışlıkla taşımayı önler.
- Dosya başına 0/90/180/270° rotasyon; seçim yokken
  rotasyon düğmeleri hiçbir dosyayı değiştirmez, **Tümünü döndür** ayrıdır.
- Satır başında sürükleme tutamacı, dosya adı, sayfa aralığı alanı ve rotasyon
  rozeti; seçili satırda rozet okunabilirliğini korur.
- **Çoklu seçim:** `Ctrl+tık` ekler/çıkarır, `Shift+tık` aralık seçer, `Ctrl+A` tümünü seçer.
  Silme, döndürme ve taşıma tüm seçili dosyalara uygulanır; seçili satırlar sürüklenince blok olarak taşınır.
- Kısayollar: `Del` seçilenleri kaldırır, `Alt+↑/↓` seçilenleri sıralar, `Ctrl+A` tümünü seçer.
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
python -m pytest tests -q
```

- Motor testleri gerçek PDF üretip PyMuPDF ile sonucu yeniden okur.
- Arayüz testleri gerçek Qt penceresi kurar; taşma, doğrulama, birim dönüşümü,
  önizleme, işlem hattı ve birleştirme akışını dener.
- Görsel regresyon altın görüntülerle karşılaştırır:
  `tests/golden/`. Bilinçli güncelleme:

```bat
set UPDATE_GOLDENS=1
python -m pytest tests/test_visual_regression.py
set UPDATE_GOLDENS=
```

Performans ölçümü (tema değişimi, sekme geçişi, açılış süresi, `withdraw` sayısı,
widget sayısı) kapalı gelir; açmak için:

```bat
set APP_PERF=1
python app.py
```

Süreler `studio.log` içinde `PERF` satırları olarak, kapanışta özet olarak yazılır.
Widget diyetinde her adımdan önce ve sonra bu çıktı karşılaştırılır.

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
app.py                  Pencere kabuğu (ModernGutterApp): yaşam döngüsü, sekme seçimi, ortak durum, geçiş köprüleri, main()
ui/shell_build.py       Pencere kurulumu: üst çubuk, dosya çubuğu, çalışma alanı (sekmeler | QSplitter | önizleme), modül şeridi, eylem çubuğu
ui/pipeline.py          Modül anahtarlarını topluca açma/kapama, eylem çubuğunun işlem hattı özeti
ui/document.py          Ana belgenin seçilmesi ve yüklenmesi
ui/shortcuts.py         Klavye kısayolları (Ctrl+O, Ctrl+Enter, Esc, Delete, Alt+Yön) ve ana eylem yönlendirmesi
ui/bridge.py            forward: eski pencere öznitelik adlarını taşınmış nesnelere yönlendiren geçiş köprüsü (2.9'da kalkar)
ui/paths.py             ROOT_DIR ve ASSETS_DIR (simge/yazı tipi yolları tek yerde)
ui/theme.py             Renkler, yazı boyutları, etiket tabloları
ui/widgets.py           FieldRow, WrapButtonRow, FieldError
ui/window.py            StudioWindow (tema geçişinde gizlemeyen CTk), sekme denetleyicisi
ui/merge_job.py         Birleştirme eylemi: doğrulama, arka plan işçisi, kırpma onayı, geçici dosya
ui/preview.py           PreviewPanel: canlı önizleme kartı, durum, üretim iş parçacığı, gezinme (PreviewHost yüzeyi)
ui/preview_canvas.py    PreviewCanvas: sayfayı paintEvent ile oranlı sığdıran tuval (yeniden örnekleme yok)
ui/workflow.py          İşleme, tarama, ilerleme ve sonuç akışı
ui/dialogs.py           İletişim kutuları, Hakkında penceresi
ui/config_binding.py     Ayar okuma/yazma, profiller, ön ayarlar (alanlar ↔ PdfProcessConfig)
ui/context.py           AppContext: sekmelerin pencereyle konuştuğu dar yüzey
ui/tabs/base.py         BaseTab sözleşmesi (build / on_show / apply_theme) ve LegacyTab geçiş bağdaştırıcısı (artık kullanan sekme yok)
ui/tabs/number.py       Sayfa Numaraları sekmesi (BaseTab; ilk taşınan sekme)
ui/tabs/page_layout.py   Sayfa Düzeni sekmesi: cilt payı, alt/üst boşluk, ebat ve özel sayfa kuralları (BaseTab)
ui/tabs/merge.py        Birleştirme sekmesi: dosya listesi, sıralama, döndürme, sayfa aralığı (BaseTab)
ui/tabs/merge_drag.py   Birleştirme listesi sürükleme: bırakma çizgisi, kenarda otomatik kaydırma, tutamaktan sürükleme
ui/dnd.py               Sürükle-bırak
ui/perf.py              APP_PERF=1 ölçüm kaydedicisi (kapalıyken maliyetsiz)
gutter_engine.py        Geometri, numaralandırma, tarama, doğrulama, birleştirme
settings_store.py       Ayar/profil deposu, günlük kurulumu
page_layout_model.py    Birleşik Sayfa Düzeni ayar modeli (taşma seçimi, özel sayfa kuralları; Qt'siz)
version.py              Tek sürüm kaynağı
make_icon.py            Çok boyutlu simge üreticisi
tests/                  Motor, arayüz, depo ve görsel regresyon testleri
tools/                  Referans PDF seti üreticisi, ölçüm betikleri (ör. `olcum_surukleme.py`)
samples/referans/       Gerçek referans PDF seti
```

## Ayarlar ve gizlilik

- Ayarlar: `%APPDATA%\PDFBaskiCiltStudyosu\settings.json`
- Günlük: `%LOCALAPPDATA%\PDFBaskiCiltStudyosu\studio.log`
- Hiçbir veri ağa gönderilmez; dosyalar yalnızca yerelde işlenir.

## Bilinen kapsam sınırları

2.8.0, plandaki P4 geliştirmelerini içerir. Sayfa araçları ayrı pencerededir;
Önce/Sonra karşılaştırması geçişlidir; taşma payı mevcut tasarımın dışında yeni
görsel üretmez. Katalog dışı işletim sistemi/kitaplık hataları özgün dilinde
gösterilebilir. Ayrıntılı kapsam ve sınırlar sürüm notlarında belirtilmiştir.

Windows %125/%150 ölçeklemede son görsel onay kullanıcı makinesinde
yapılmalıdır.

**Doğrulama:** Windows'ta nihai pakette **559 test geçti**. Tema geçişi ayrıca
native Windows penceresinde tek tıklamayla boyama kontrolünden geçti.

### Arayüz tercihleri (2.8.0)

Ayarlar penceresindeki Birleştirme bölümünden tüm birleşik belgeyi önizleme ve yalnız tutamaktan sürükleme tercihleri belirlenir. Değişiklikler hemen uygulanır ve sonraki oturumlarda korunur. Birleştirme ekranındaki “Liste ve önizleme tercihleri…” düğmesi Ayarlar’ı açar. Çıktıya etki eden yer imi, eşitleme ve diğer sekmelerin ayarlarını uygulama seçenekleri Birleştirme ekranında kalır.
