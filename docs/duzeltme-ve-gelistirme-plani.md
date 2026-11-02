# PDF Baskı & Cilt Stüdyosu: Düzeltme ve Geliştirme Planı

*Kod incelemesi bulgularına dayalı uygulama planı · 2 Kasım 2026*

## Kapsam notu

"Cilt Payı kısmında yazıyı kaydırıyor ve sayfa dışına taşıyor" ifadesi, Cilt Payı sekmesindeki arayüz yazılarının pencereden taşıması olarak yorumlanmıştır. Kodda nedenleri açıktır: hazır şablon düğmeleri dört sütuna sıkışıyor, durum etiketi tek satıra sabit, giriş kutuları ve etiketler sabit piksel genişlikte, sekme içeriği kaydırılamıyor. Windows'ta %125–150 ölçekleme açıksa bu sorunlar daha da kötüleşiyor. PDF çıktısındaki içerikten söz ediliyorsa o kısım ayrıca ele alınacaktır.

## Aşama 0: Hazırlık

- Proje temizlenir: `__pycache__` ve `tests/temp` çıkarılır, `.gitignore` ve `requirements.txt` eklenir.
- Tüm sürüm bilgileri tek bir `VERSION` sabitine bağlanır.
- Gerçek bir referans PDF seti hazırlanır: karışık boyutlu, bağlantılı, yer imli ve form alanlı. Böylece "açıklamalar kayboluyor mu" sorusu varsayımla değil testle cevaplanır.

## Aşama 1: Motor (`gutter_engine.py`)

| Sorun | Çözüm |
| --- | --- |
| Alt pay modu üstten içerik kırpıyor | Üç mod: **Uzat** (varsayılan), **Sığdır** (içerik orantılı küçülür, kırpma yok), **Kaydır** (kırpar ve önizlemede kırmızı uyarı verir) |
| Hedef ebat kaynaktan küçük, sessiz kırpma | İşlemden önce `validate_config()` çalışır ve sorunları listeler |
| Girdi ve çıktı yolu aynı | Engellenir, otomatik farklı ad önerilir |
| Şifreli veya bozuk PDF | Anlaşılır Türkçe hata sınıfları |
| Numara konumlandırma tahmine dayalı | `get_text_length` ile kesin hesap, yedek yöntem kalkar |
| Bağlantı hedefleri kaymıyor | Hedef noktaları da ofsetlenir |
| Açıklama ve form alanı kaybı | Aşama 0'daki testle doğrulanır. Kayıp varsa taşınır, taşınamıyorsa kullanıcıya açıkça bildirilir |
| "Matbaa/Standart" seçimi yanıltıcı | "Dosyayı optimize et" onay kutusu olur |
| Birleştirmede kalan `.tmp.pdf` | Geçici dosya `try/finally` ile her durumda silinir, eksik dosya için uyarı verilir |
| Birleştir + ayarları uygula modunda Y ofsetleri kayboluyor | Tek `build_config()` ile tüm değerler motora geçirilir |

**Yeni testler:** kırpma yok, Y ofseti birleştirmede korunuyor, sığdırma oranı, aynı yol engeli, şifreli PDF.

## Aşama 2: Arayüz

### Taşma sorununun kalıcı çözümü (Cilt Payı sekmesi dahil)

- Tüm sekmeler sabit `pack` yerine `grid` ile yeniden kurulur, sütunlar `weight` ile esner.
- Hazır şablon düğmeleri tek satırda sabit değil, daralınca iki satıra inen düzende olur.
- Durum etiketleri `wraplength` ile konteyner genişliğine bağlanır.
- Sekme içeriği kaydırılabilir olur, böylece küçük pencerede hiçbir şey taşmaz.
- Minimum pencere boyutu gerçek içeriğe göre hesaplanır. Boyut ve yazı ölçeği tek bir yerden yönetilir (en az 12 px gövde yazısı).

### Mimari

- Tek `build_config()` hem normal işlemde hem birleştirmede kullanılır, kopya kod silinir.
- `_tab_dict` gibi özel API'ler bırakılır.
- Tema renkleri (durum yeşili dahil) açık ve koyu için çift tanımlanır.

### Yeni özellikler

- **Canlı önizleme paneli:** PDF'in ilk sayfası ve karşı sayfası yan yana çizilir. Cilt şeridi, alt/üst pay ve numara konumu üzerinde gösterilir. Ayar değişince güncellenir.
- Alan bazlı doğrulama: hatalı kutu kırmızı olur, altında kısa açıklama çıkar.
- İptal düğmesi, ayarları hatırlama, çıktı adı çakışmasında otomatik numaralama.
- Birleştirme listesi: sürükleyerek sıralama ve titremesiz yenileme.

## Aşama 3: Simge

- Yeni tasarım: kalın sayfa silueti ve sol kenarda belirgin cilt şeridi.
- 16, 24 ve 32 px için ayrı sadeleştirilmiş çizim, büyük boyutlar için detaylı çizim.
- Çıktı: çok boyutlu `.ico` ve `.png`. Küçük boyutlarda okunurluk ayrıca kontrol edilir.
- `make_icon.py` içindeki sabit `D:\Projeler\...` yolu göreli yola taşınır.

## Aşama 4: Paketleme ve belgeler

- `Baslat.bat` Python'u ve `pythonw`'yi kendisi bulur, yoksa anlaşılır mesaj verir.
- `build_exe.bat` düzeltilir.
- README kodla uyumlu olarak baştan yazılır ("WinUI 3" ve emoji ifadeleri kalkar).

## Doğrulama

- Motor testlerinin tümü geçmelidir (şu an 13/13 geçiyor).
- Arayüz sanal ekranla (xvfb) farklı pencere boyutlarında çalıştırılıp taşma kontrolü denenecek. Olmazsa widget boyutlarını ölçen otomatik bir test yazılacak.
- Windows'taki %125 ve %150 ölçekleme ile gerçek görünümün son onayı kullanıcının makinesinde yapılmalıdır. Bu, geliştirme ortamında birebir test edilemez.

## Açık karar

Alt pay modunun varsayılanı **Uzat** (kayıpsız, Acrobat davranışı, önerilen) mı kalsın, yoksa **Sığdır** mı olsun?

## Karar güncellemesi

Alt pay modunun varsayılanı **Uzat** olacaktır. Deneyde bu modun beş metin öğesinin hiçbirini kırpmadığı, "Kaydır" modunun ise üstteki metinleri sayfa dışına itip sildiği doğrulandı. Kaydır modu ya "Sığdır" ile değiştirilecek ya da kırpma riski önizlemede kırmızı gösterilip uyarıyla birlikte bırakılacaktır.

## Ek öneriler: kaliteyi ve işlevi artıran özellikler

Aşağıdaki öneriler yukarıdaki düzeltmelere ek olarak düşünülmüştür. Hepsini tek turda yapmak yerine üç tura bölmek riski azaltır.

### Kalite ve güvenilirlik

| Özellik | Ne sağlar | Zorluk |
| --- | --- | --- |
| **Kırpma riski taraması** | İşlemden önce her sayfanın içerik sınırları ölçülür. Seçilen ayarlarla hangi sayfalarda içeriğin dışarı taşacağı önceden listelenir. | Orta |
| **Sonuç doğrulama raporu** | İşlem bitince çıktı otomatik kontrol edilir: sayfa sayısı, sayfa boyutları, kaynak ve çıktı metninin karşılaştırılması (eklenen numaralar hariç). "Hiçbir şey kaybolmadı" iddiası kanıtlanmış olur. | Orta |
| **Atomik kaydetme** | Çıktı önce geçici dosyaya yazılır, başarılı olursa aslı dosyanın yerine geçer. Yarım kalan veya bozuk çıktı olmaz, kaynak dosyaya hiç dokunulmaz. | Kolay |
| **Günlük kaydı (log)** | Hatalar bir günlük dosyasına yazılır. Arayüzde "Hata ayrıntılarını kopyala" düğmesi olur. | Kolay |
| **Görsel regresyon testi** | Referans PDF'ler işlenip sayfa görüntüleri önceki sürümle karşılaştırılır. Gelecekteki değişikliklerin yerleşimi bozması yakalanır. | Orta |
| **Klavye kullanımı** | Ctrl+O, Ctrl+S, Enter, Esc kısayolları ve mantıklı Tab sırası. | Kolay |
| **Birim seçimi** | mm, cm, inç ve pt arasında geçiş. Ayarlar kaybolmadan dönüştürülür. | Kolay |
| **Dil dosyası** | Metinler koddan ayrılır. Türkçe kalmaya devam eder, İngilizce eklemek kolaylaşır. | Orta |

### Ön ayar profilleri ve şablonlar

- Kaydet / yükle / adlandırılabilir profiller (JSON). Örnek hazır profiller: **Tez**, **Spiral cilt**, **Sıcak tutkal cilt**, **Kitapçık**. Hazır değerler öneridir. Üniversite veya matbaa kılavuzuna göre kullanıcı düzenleyebilir.
- Kağıt boyutu şablonları (A4, A5, B5, Letter) ve dikey/yatay seçimi.
- Son kullanılan dosyalar ve son ayarların otomatik hatırlanması.

### Cilt payı geliştirmeleri

- **Cilt yeri seçimi:** şimdiki ayna düzenine ek olarak yalnız sol (tek taraflı baskı), üst (takım not defteri) ve sağ.
- **Cilt şeridi göstergesi:** Önizlemede cilt payı renkli band olarak gösterilir. İstenirse çıktıya ince kılavuz çizgisi de eklenir.
- **Kayma (creep) telafisi:** Dikili kitapçıklarda iç sayfalar dışa kayar. Sayfa sayısına göre ilerleyen oranda ek pay verilebilir. İleri seviye özellik.

### Sayfa numaralamada gelişmeler

- **Roma rakamları ve bölüm bazlı numaralama:** Ön kısım i, ii, iii; ana metin 1, 2, 3 şeklinde. Bunun için "bölüm tanımla" tablosu eklenir. Tez ve kitaplar için önemlidir.
- **Özel metin şablonu:** `{n}`, `{N}` gibi değişkenlerle özel metin, üst/alt bilgi.
- **Yazı tipi ve renk seçimi:** Türkçe karakterli özel metin için Unicode yazı tipi gömülür. Mevcut yerleşik yazı tipi Ş, Ğ, İ gibi harfleri güvenle bastırmaz. Şu an yalnız rakam basıldığı için sorun görünmez, ancak özel metin gelince bu kritik olur.
- **Bates numarası:** Başına/sonuna ön ek olan sürekli belge numarası (hukuki belgeler).

### Sayfa düzeni ve matbaa işlevleri

- **Sayfa sayısını 4'ün katına tamamlama:** Sonuna otomatik boş sayfa eklenir. Kitapçık ve cilt için gerekli.
- **Bölüm başlarını sağ sayfaya almak:** Gerekirse araya boş sayfa eklenir. Bu boş sayfalar numaralanmaz.
- **Kesim işaretleri ve taşma payı (bleed):** Matbaaya gönderilecek PDF'ler için.
- **Filigran ve damga:** "Taslak", "Gizli" gibi, opaklık ve açı ayarlı.
- **Kitapçık sıralaması ve n-up (impozisyon):** 2'li ve 4'lü düzen. Büyük bir özellik, ayrı tura bırakılması daha sağlıklı.

### Sayfa işlemleri ve birleştirme

- **Sayfa ayıklama:** Sayfa silme, çıkarma, yeniden sıralama, döndürme, PDF'yi bölme (split). Birleştirmenin tamamlayıcısı olarak ayrı bir sekme.
- **Birleştirmede sayfa aralığı:** Bir dosyanın yalnız seçilen sayfalarını almak (örn. 3-10).
- **Birleştirmede dosya başına yer imi:** Dosya adından otomatik oluşturulur, mevcut yer imleri korunur.
- **Boyutları eşitleme:** Karışık boyutlu sayfalar ortak bir boyuta (örn. A4) ortalanarak yerleştirilir.

### Otomasyon ve dağıtım

- **Toplu işlem:** Klasördeki tüm PDF'lere aynı profil, çıktı klasörü ve ad şablonu.
- **Komut satırı (CLI):** Aynı motor ve profillerle betikten çalıştırılabilir.
- **Kurulum paketi:** Mevcut tek dosya EXE'ye ek olarak kurulum sihirbazı (Inno Setup).
- **Meta veri ve optimizasyon:** İstenirse dosya bilgilerini temizleme ve dosya boyutunu azaltma. Görsel yeniden örnekleme kayıpsız olmadığı için açıkça işaretli, varsayılan kapalı seçenek olur.

## Önerilen tur planlaması

| Tur | İçerik |
| --- | --- |
| **Tur 1: Mevcut plan + temel kalite** | Aşamalar 0–4, kırpma riski taraması, sonuç doğrulama raporu, atomik kaydetme, günlük, profiller, birim seçimi, kısayollar |
| **Tur 2: İşlevsel genişleme** | Roma rakamı ve bölüm bazlı numaralama, özel metin şablonu ve Unicode yazı tipi, 4'ün katına tamamlama, birleştirmede sayfa aralığı ve yer imi, sayfa ayıklama sekmesi, toplu işlem, filigran |
| **Tur 3: İleri matbaa özellikleri** | Kesim işaretleri ve bleed, kitapçık ve n-up impozisyon, creep telafisi, CLI, kurulum paketi, İngilizce arayüz |

Her tur kendi testleriyle bitirilir ve bir sonrakine geçilmeden kullanıcıya teslim edilir. Böylece her adımda çalışan, test edilmiş bir sürüm elde kalır.

---

## Uygulama bulguları — 2 Kasım 2026 (sürüm 2.2.1)

Bu bölüm, Tur 2 sırasında yapılan arayüz düzeltmelerinin ve geçiş (tema / pencere durumu) sorununun çözüm kaydıdır.

### Kapatılan işler

| Konu | Yapılan | Doğrulama |
| --- | --- | --- |
| Tema geçişinde boşalma | Geçiş öncesi pencere görüntüsü alınıp ayrı bir maske penceresinde sabitleniyor; yeni tema tamamen çizilince maske kaldırılıyor | Geçişin 0,12. sn'sinde alınan görüntüde eski tema eksiksiz duruyor, ardından yeni tema tek seferde geliyor |
| Tam ekran ↔ pencere geçişi | Pencere durumu değişince sekme içeriği gizleniyor, maske altında yeniden yerleştirilip hazır olduğunda gösteriliyor | Büyütme sonrası arayüz tam ve temiz; sekme değiştirme çalışıyor; geri küçültme temiz |
| Kenarda kalan eski pikseller | Geçiş sonunda pencere `RDW_INVALIDATE + RDW_ALLCHILDREN` ile geçersiz kılınıp yeniden çizdiriliyor | Büyütme sonrası sağ kenardaki yarım metin şeritleri kayboldu |
| Segmented kontrollerin gri çerçevesi | Varsayılan 3 px gri çerçeve ve gri gövde kaldırıldı, kart zeminiyle bütünleşti | Görsel kontrol |
| Seçim rengi | Açık tema `#B7DCFF`, koyu tema `#17456E`; hover bir ton koyusu | Görsel kontrol |
| Açılır menüler | Menü listesi için temaya uygun zemin, seçili satır vurgusu, okunur metin | Görsel kontrol |
| Canlı önizleme | Panel 380 px; tek/çift sayfa modu; `PhotoImage` ile tema değişiminden etkilenmeyen görüntüler; beyaz sayfa kartları | Testler + görsel kontrol |
| Alt orta konumunda yan boşluk | Alan pasifleşiyor, etiket metni değişmiyor; altında "Alt orta konumunda yan boşluk kullanılmaz" notu çıkıyor | `test_center_position_disables_side_margin_without_shifting` |
| Üst pay ön ayarları | `+25` eklendi; alt ve üst düğme setleri eşitlendi | Görsel kontrol |
| Sürüm / paket | `2.2.1`, README güncellendi, EXE yeniden derlendi (50,7 MB), açılış testi yapıldı | EXE 9 sn sorunsuz çalıştı |

### Ölçümler (geliştirme makinesi, 274 widget)

- `ctk.set_appearance_mode`: ~430 ms; ardından gelen ilk çizim ~290 ms.
- Pencere büyütme: ~800–900 ms (yaklaşık 8.900 Tcl çağrısı). Python tarafı ~200 ms, kalan süre Tk/CTk canvas çizimi.
- Karşılaştırma: 100 widget'lık minimal CustomTkinter penceresi de büyütmede ~500 ms harcıyor. Maliyet uygulamaya özgü değil, kütüphanenin canvas tabanlı çizimine ait.

### Denenip elenen yöntemler

| Yöntem | Sonuç |
| --- | --- |
| Yazı tipi önbelleği (aynı `CTkFont` nesnesini paylaşma) | Ölçülebilir kazanç yok (783 ms → 783 ms) |
| `DrawEngine.preferred_drawing_method = "polygon_shapes"` | Tema 437 → 115 ms, ama büyütme 797 → 1087 ms; görsel kalite de değişiyor |
| `PrintWindow` ile pencere içeriği yakalama | Önizleme görselleri ve alt eylem çubuğu eksik çiziliyor |
| `RedrawWindow` + `RDW_ERASE` | Kaydırma çubuğunu siliyor |
| Pencereyi 1 px büyütüp küçültme ("nudge") | Büyütülmüş pencerede `geometry()` yok sayıldığı için etkisiz |

### Mimari notlar

- `_freeze_frame()`: sahipsiz bir `Toplevel` + `ImageGrab`. Görüntü alınırken ana pencere kısa süreliğine `-topmost` yapılıp öne alınır; bölge monitörün çalışma alanına kırpılır, böylece görev çubuğu maskeye girmez.
- `_on_client_configure()` yalnız pencere durumu değiştiğinde (büyütme/geri küçültme) ve boyut farkı %15'i geçtiğinde devreye girer. Sürükleme ile yapılan küçük boyut değişimlerinde içerik gizlenmez.
- `_release_workspace()` içeriği maskenin altında geri yerleştirir; `_repaint_window()` geçiş sonunda artık pikselleri temizler.
- Yan boşluk alanında etiket metni değiştirilmediği için alt orta seçiminde düğmeler kaymıyor; yalnız renk ve pasiflik değişiyor.

### Bilinen sınırlar

- Maske ekran görüntüsüne dayanır: geçiş anında uygulamanın üzerinde başka bir pencere varsa maske o pencereyi gösterebilir. Normal kullanımda (uygulama önde) sorun görünmüyor.
- Geçişte içerik kısa süre (yaklaşık 0,3 sn) boş görünür, sonra tek seferde gelir. Bu bilinçli tercih: yarım çizilmiş düğmeler ve siyah bloklar yerine temiz bekleme.
- Tk/CustomTkinter yeniden çizim maliyeti düşürülemedi; tam ekran geçişi bu makinede ~0,5–1 sn sürüyor. Daha hızlısı için arayüzün temel widget'larının değiştirilmesi gerekir.

### Açık işler

1. `test_full_process_pipeline_from_ui` toplu koşuda bir kez 20 sn zaman aşımına düştü; tek başına ve dosya bazında geçiyor. Bekleme mantığı sağlamlaştırılmalı.
2. Tur 2 kalanları: bölüm bazlı numaralandırma (bölüm tablosu), filigran, sayfa ayıklama/döndürme/bölme sekmesi, toplu işlem.
3. Tam ekran ve tema geçişinin kullanıcının kendi makinesinde (%125–150 ölçek) son görsel onayı.
