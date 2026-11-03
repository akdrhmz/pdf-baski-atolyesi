# PDF Baskı ve Cilt Stüdyosu — Mimari Bölme, Geliştirme ve Yol Haritası Planı

**Son Güncelleme:** Sürüm `2.2.2` (PySide6 / Qt 6 Geçişi, Sıfır-QSS `QPainter` Tema Motoru, Sadeleştirilmiş Yeni Arayüz, `235 / 235` Test Yeşil)

Bu belge; `docs/` altındaki tüm inceleme, kök neden analizi, `app.py` modüler bölme adımları ve gelecek özellik yol haritası belgelerinin (`app-bolme-plani.md`, `app-bolme-plani-adim2-8.md`, `duzeltme-ve-gelistirme-plani.md`, `inceleme-raporu-ve-eylem-plani.md`) tek bir ana referans belgesinde birleştirilmiş halidir. **Yapılanlar (`[x]`)** ve **Kalanlar (`[ ]`)** net olarak ayrılmıştır.

---

## 1. Proje Özeti ve Güncel Durum (v2.2.2)

### 1.1 Mimari Dönüşüm Özeti
1. **Arayüz Altyapısı (Tkinter/CustomTkinter → PySide6 / Qt 6):**
   - Eski `CustomTkinter` + `Tkinter` + `windnd` altyapısında her kart, satır ve düğme ayrı birer Windows HWND alt penceresi (`1.041` widget) oluşturduğu için sekme ve Açık/Koyu tema geçişlerinde şelale halinde yeniden çizim (`100–430 ms` gecikme, siyah/beyaz flaş ve pencere gizleme) yaşanıyordu.
   - `CustomTkinter`, `Tkinter` ve `windnd` tamamen kaldırılarak **PySide6 (Qt 6)** tek yüzeyli çift tamponlu (`QBackingStore`) mimarisine geçildi (`ui/qt_compat.py`, `ui/window.py`).
   - Tema geçişlerinde QSS (`setStyleSheet`) ayrıştırma yükü tamamen sıfırlanarak doğrudan `QPainter` + `QPalette` tabanlı özel boyama (`paintEvent`) motoruna geçildi.
2. **Modüler Kod Tabanı (`app.py` Bölünmesi):**
   - Başlangıçta `3.657` satır olan monolitik `app.py`, 9 aşamalı mimari bölme planıyla **`447` satırlık** ince bir uygulama kabuğuna indirildi.
   - Tüm sekmeler (`ui/tabs/`), önizleme paneli (`ui/preview.py`), pencere kabuğu (`ui/shell_build.py`), iş akışı (`ui/workflow.py`), belge yaşam döngüsü (`ui/document.py`), kısayollar (`ui/shortcuts.py`) ve ayar bağlama (`ui/config_binding.py`) bağımsız modüllere ayrıldı.
3. **Sade ve Anlaşılır Arayüz Tasarımı:**
   - Karmaşık iç içe çerçeveler kaldırıldı; 4 sekmenin tamamı (`1. Sayfa Numarası`, `2. Kenar Boşluğu`, `3. Cilt Payı`, `4. PDF Birleştir`) varsayılan pencere boyutunda **dikey kaydırma çubuğu gerektirmeyen**, numaralı (`1 · 2 · 3`) adım kartları ve doğrudan tıklanabilir segment düğmeleriyle yeniden tasarlandı.

### 1.2 Ölçülen Performans ve Doğrulama Tablosu (`APP_PERF=1`)

| Ölçüt | Eski Durum (CustomTkinter) | Adım 2.9 Sonrası (Tembel Kurulum) | Güncel Durum (PySide6 + Sıfır-QSS) |
| :--- | :--- | :--- | :--- |
| **`app.py` Satır Sayısı** | `3.657` satır | `447` satır | **`447` satır** |
| **Açılış Arayüz Kurulumu (`acilis_arayuz_kurulumu`)** | `~1.050 ms` | `~633 ms` | **`~180 – 283 ms`** |
| **Sekme Geçişi (`sekme_gecisi:*`)** | `100 – 430 ms` | `8 – 130 ms` | **`2,8 – 15 ms`** |
| **Açık ↔ Koyu Tema Değişimi (`tema_degisimi`)** | `400+ ms` (gri/siyah flaşlı) | `~150 ms` | **`6,5 – 11,4 ms` (tek karede atomik)** |
| **Tema Geçişinde Pencere Gizleme (`withdraw`)** | `> 0` (pencere kayboluyordu) | `0` | **`0`** |
| **Otomatik Test Paketi (`pytest`)** | `98 geçti, 3 hata` | `235 / 235 geçti` | **`235 / 235 geçti (~15 sn)`** |

---

## 2. Tamamlanan İşler (`[x]` Yapılanlar)

### 2.1 Motor, PDF İşleme ve Doğrulama İyileştirmeleri (`gutter_engine.py`)

- **[x] Döndürülmüş (`/Rotate` 90°/180°/270°) ve Kırpılmış (`CropBox != MediaBox`) Sayfaların Normalizasyonu:**
  - *Kök Neden:* PyMuPDF `show_pdf_page(..., clip=r)` çağrısı kaynak sayfanın `/Rotate` bayrağını yok sayarak ham içerik akışını yerleştirdiği için 90°/180°/270° döndürülmüş sayfalarda içerik yan dönüyor ve yanlış bölgeden kırpılıyordu.
  - *Çözüm:* `normalize_page_rotations(doc)` eklendi. `rotation != 0` veya `cropbox != mediabox` olan sayfalar işlem öncesinde tek geçişli PDF XObject (`Form XObject`) olarak sarılıp görünür yönü koruyacak şekilde `/Rotate 0` ve tam `MediaBox` haline getiriliyor. Metin katmanı, vektör grafikler, şeffaflık ve bağlantılar kayıpsız korunuyor.
- **[x] Sabit Kağıt Boyutunda Taşma Önleme (`overflow_mode="shrink"` ve `safe_edge_mm`):**
  - *Kök Neden:* Sabit kağıt boyutunda (`page_size_mode != "same"`) cilt payı eklendiğinde içerik yalnızca dışa kaydırılıyor (`clip`), dış kenardaki metin kağıt dışına taşarak kesiliyordu.
  - *Çözüm:* `GutterConfig.overflow_mode` (`"shrink"` varsayılan / `"clip"` isteğe bağlı) ve `safe_edge_mm` (varsayılan `5,0 mm`) eklendi. `"shrink"` modunda içerik tek ölçek katsayısıyla küçültülerek hem cilt payı hem de dış güvenli kenar boşluğu korunuyor; hiçbir içerik kesilmiyor.
- **[x] Sayfa Numaralandırma Alt Boşluk Modları (`Uzat` / `Sığdır` / `Kaydır`):**
  - `number_margin_mode` için `extend` (sayfa boyunu uzat), `fit` (sayfa boyunu koruyup içeriği sığdır) ve `shift` (içeriği yukarı kaydır) seçenekleri birleşik geometri hesabıyla (`_compute_unified_layout`) tek geçişte uygulanıyor.
- **[x] Gömülü Unicode Yazı Tipi (`assets/DejaVuSans.ttf`):**
  - Sistem yazı tipi bulunamasa bile Türkçe karakterlerin (`ğ, ü, ş, ı, ö, ç, İ`) her platformda eksiksiz basılması için açık lisanslı `DejaVuSans.ttf` depoya eklendi ve `_resolve_turkish_font()` içinde birincil yedek yapıldı.
- **[x] Yer İmi (TOC) Hiyerarşisi Onarımı (`sanitize_toc`) ve Sayfa Aralığı Doğrulaması:**
  - `merge_pdfs` sırasında kaynak PDF'in ilk yer imi seviyesi `> 1` olduğunda veya seviye atlandığında (`1 → 3`) oluşan `ValueError: hierarchy level of item 0 must be 1` hatası `sanitize_toc()` ile giderildi.
  - Sayfa aralığı ayrıştırıcısına üst sınır (`MAX_PAGE_NUMBER = 100_000`) ve geçersiz parça tespiti (`invalid_range_tokens`) eklendi.
- **[x] `merge_pdfs` Bellek Optimizasyonu (`_contiguous_runs`):**
  - Sayfa aralığı seçildiğinde kaynak PDF'in tamamını bellekte kopyalamak yerine ardışık sayfa aralıkları (`insert_pdf(src, from_page=a, to_page=b)`) doğrudan hedefe aktarılıyor.
  - Önizleme geçmişi (`_preview_history`) `40` girdiden `8` girdiye düşürülerek bellek tüketimi sınırlandı.
- **[x] İşlem Öncesi ve Sonrası Sıkı Doğrulama (`validate_config`, `verify_output`, `render_page_differs`) ve Atomik Kayıt:**
  - İşlem öncesinde tüm parametreler `validate_config(config)` ile denetleniyor.
  - Çıktı önce `.part` geçici dosyasına yazılıp `verify_output()` (sayfa sayısı, boyut, metin katmanı ve `render_page_differs` ile görsel piksel farkı doğrulaması) geçtikten sonra `os.replace` ile atomik olarak hedef dosyaya taşınıyor.

---

### 2.2 `app.py` Modüler Bölme ve Tembel Kurulum Mimarisi (Adım 0, 1 ve 2.1–2.9)

#### `[x]` Adım 0 & 1 — Ölçüm Altyapısı ve Test Tabanı
- `ui/perf.py` (`APP_PERF=1` ortam değişkeniyle etkinleşen `perf_span`, `count_widgets`, `install_withdraw_counter`) eklendi.
- Platform bağımlı test hataları giderilerek tüm test tabanı %100 yeşile çekildi.

#### `[x]` Adım 2.1 — Ayar ve Profil Bağlama Katmanı (`ui/config_binding.py`)
- `ConfigBindingMixin`: `_build_config`, `_apply_config`, `_collect_state`, `_restore_settings`, profil (`_load_selected_profile`, `_save_current_profile`, `_delete_selected_profile`) ve hazır ayar yöntemleri `app.py`'den ayrıldı.

#### `[x]` Adım 2.2 — Paylaşılan Bağlam Nesnesi (`ui/context.py`)
- Sekmelerin ve panellerin `ModernGutterApp` örneğine doğrudan bağımlı olmaması için `TabContext` (`AppContext`) veri sınıfı tanımlandı:
  - `config_vars`, `theme`, `unit` (`get_unit`, `set_unit`, `format_mm`, `unit_Factor`, `unit_step`), `on_setting_changed`, `select_tab`, `open_pdf_dialog`, `status` ve `scheduler`.

#### `[x]` Adım 2.3 – 2.6 — Sekmelerin Bağımsız Sınıflara Ayrılması (`ui/tabs/`)
- `ui/tabs/base.py` (`BaseTab`): Ortak temel sınıf (`ensure_built`, `read_fields`, `apply_config`, `collect_state`, `restore_state`, `on_unit_changed`, `on_theme_changed`, `validate`, `reset_defaults`, `_pending_sections` tembel alt bölüm mekanizması).
- `ui/tabs/number.py` (`NumberTab`): Sayfa Numarası sekmesi (`update_side_state`, konum seçici, canlı rozet, gelişmiş ayarlar).
- `ui/tabs/margin.py` (`MarginTab`): Kenar Boşluğu sekmesi (simetrik/asimetrik boşluk, sayfa aralığı, temizleme şekli).
- `ui/tabs/gutter.py` (`GutterTab`): Cilt Payı sekmesi (`sync_overflow_state`, cilt payı/forma/güvenli kenar, kağıt boyutu ve sığdırma kuralları).
- `ui/tabs/merge.py` (`MergeTab`): PDF Birleştir sekmesi (`files`, `selected_indexes`, sürükle-bırak sıralama, sayfa aralığı, yer imi ve sayfa boyutu eşitleme).

#### `[x]` Adım 2.7 — Önizleme Paneli Sınıfı (`ui/preview.py`)
- `PreviewPanel`: Üst araç çubuğu, sayfa gezinme, yakınlaştırma, döndürme, öncesi/sonrası karşılaştırma (`compare_enabled`), cetvel/kılavuz çizgileri ve arka plan işçisi (`_preview_worker`) bağımsız bileşen haline getirildi.

#### `[x]` Adım 2.8 — Pencere Kabuğu, Belge, Boru Hattı ve İş Akışlarının Ayrılması
- `ui/shell_build.py`: Üst başlık çubuğu (`_build_header`), sekme çubuğu, sol/sağ çalışma alanı ve alt eylem çubuğu (`_build_action_bar`).
- `ui/document.py`: PDF açma, kapatma, şifreli PDF çözme ve son kullanılan dosyalar (`recent_files`).
- `ui/pipeline.py`: Canlı durum rozetleri (`_refresh_pipeline_status`), sekme özetleri ve geçerlilik kontrolü.
- `ui/shortcuts.py`: Klavye kısayolları (`Ctrl+O`, `Ctrl+S`, `Ctrl+1..4`, yön tuşları, `Delete`).
- `ui/merge_job.py`: Birleştirme doğrulaması, arka plan işçisi ve ilerleme penceresi.
- `ui/workflow.py`: Tekli PDF işleme, ön tarama, ilerleme ve sonuç diyaloğu.
- `ui/dialogs.py`: Yardım, kısayollar ve Hakkında pencereleri.
- `ui/dnd.py`: Sürükle-bırak dosya doğrulama ve yönlendirme katmanı.

#### `[x]` Adım 2.9 — Tembel Sekme Kurulumu (`ensure_built`) ve Arka Plan Ön-Isıtma (`_prewarm_next_tab`)
- Açılışta yalnızca aktif sekme (`1. Sayfa Numarası`) inşa edilir; diğer 3 sekme ve kapalı daraltılabilir paneller (`_pending_sections`) ilk ihtiyaç anında veya açılıştan `120 ms` sonra boşta kalan zaman dilimlerinde (`_prewarm_next_tab`, `60 ms` aralıklarla) sessizce kurulur.

### 2.3 Güncel Modül Haritası

| Modül | Sorumluluk |
| :--- | :--- |
| `app.py` | İnce uygulama kabuğu (`ModernGutterApp`), yaşam döngüsü ve dış uyumluluk yüzeyi (`447` satır) |
| `gutter_engine.py` | PDF işleme motoru, döndürme normalizasyonu, birleşik geometri, birleştirme ve çıktı doğrulama |
| `ui/qt_compat.py` | PySide6 (Qt 6) Sıfır-QSS (`QPainter` + `QPalette`) widget ve düzenleme katmanı |
| `ui/window.py` | `StudioWindow`, `TabNav`, `freeze_redraw` ve atomik tema yenileme (`_invalidate_visible_subtree`) |
| `ui/theme.py` | Açık/Koyu tema renk paletleri, tipografi ölçeği ve sabit etiket tabloları |
| `ui/widgets.py` | `FieldRow`, `WrapButtonRow`, `FieldError`, `SectionCard` ve yardımcı bileşenler |
| `ui/context.py` | Sekmeler ve paneller arası paylaşılan `TabContext` (`AppContext`) |
| `ui/config_binding.py` | Ayar okuma/yazma, profil yönetimi ve durum kalıcılığı (`settings.json`) |
| `ui/tabs/base.py` | `BaseTab` soyut sekme arayüzü ve tembel alt-bölüm (`_pending_sections`) yönetimi |
| `ui/tabs/number.py` | `NumberTab` — 1. Sayfa Numarası sekmesi |
| `ui/tabs/margin.py` | `MarginTab` — 2. Kenar Boşluğu sekmesi |
| `ui/tabs/gutter.py` | `GutterTab` — 3. Cilt Payı sekmesi |
| `ui/tabs/merge.py` | `MergeTab` — 4. PDF Birleştir sekmesi |
| `ui/preview.py` | `PreviewPanel` — Canlı PDF önizleme, yakınlaştırma, döndürme ve karşılaştırma paneli |
| `ui/shell_build.py` | Üst bar, çalışma alanı ve alt eylem çubuğu kurulumu |
| `ui/pipeline.py` | İşlem sırası rozetleri, özet metinleri ve sekme doğrulama akışı |
| `ui/document.py` | PDF yükleme, şifre çözme ve son dosyalar yönetimi |
| `ui/workflow.py` | PDF kaydetme, arka plan işleme ve sonuç penceresi |
| `ui/merge_job.py` | Çoklu PDF birleştirme arka plan işçisi |
| `ui/dialogs.py` | Yardım, Kısayollar ve Hakkında pencereleri |
| `ui/shortcuts.py` | Klavye kısayolları yöneticisi |
| `ui/dnd.py` | Qt yerel UTF-16 sürükle-bırak (`dragEnterEvent`/`dropEvent`) entegrasyonu |
| `ui/perf.py` | Performans ve widget sayacı ölçüm araçları (`APP_PERF=1`) |

---

### 2.4 Kalıcı Arayüz Altyapısı — PySide6 (Qt 6) Geçişi ve Sıfır-QSS Tema Motoru (Adım 3 & 4)

- **[x] PySide6 (Qt 6) Tek Yüzeyli Çift Tamponlu (`QBackingStore`) Mimari:**
  - `requirements.txt`, `baslat.bat` ve `build_exe.bat` güncellendi (`PyMuPDF`, `Pillow`, `PySide6`).
  - `customtkinter`, `tkinter` ve `windnd` bağımlılıkları tamamen kaldırıldı.
- **[x] Sıfır-QSS (`QPainter` + `QPalette`) Çizim Motoru ve Atomik Tema Geçişi:**
  - `QtWidgetMixin.update()` içinden bireysel `QApplication.processEvents()` çağrıları kaldırılarak ara karelerde yarım boyanmış pencere oluşumu engellendi.
  - `QtScrollableFrame._inner` kapsayıcısı `_child_widgets` ağacına bağlandı; `QtSegmentedButton` ve `QtOptionMenu` alt düğmelerine `_refresh_style()` eklendi.
  - `StudioWindow.freeze_redraw()` çıkışında `_invalidate_visible_subtree()` ile tüm görünür widget ağacı tek bir `QBackingStore` karesinde (`~8–11 ms`) yeniden boyanıyor.
- **[x] Sadeleştirilmiş Yeni Arayüz Tasarımı ve Taşınabilir EXE (`v2.2.2`):**
  - Üst çubukta profil yönetimi doğrudan görünür `[Yükle]` · `[Kaydet]` · `[Sil]` düğmelerine dönüştürüldü; sağ üstteki mükerrer tema düğmesi kaldırılıp `[Açık / Koyu]` geçişine birleştirildi.
  - Alt çubukta işlem adımları renkli durum rozetleri (`[1. Numara: Açık/Kapalı]` vb.) ve geniş birincil eylem düğmesiyle sadeleştirildi.
  - Taşınabilir tek dosya `dist/PDF_Baski_Cilt_Studyosu_2.2.2.exe` derlendi ve doğrulandı.

---

## 3. Kalan İşler ve Gelecek Yol Haritası (`[ ]` Yapılacaklar)

Aşağıdaki maddeler mevcut kararlı `v2.2.2` çekirdeği üzerine eklenecek **gelecek geliştirme ve yeni özellik** kalemleridir:

### 3.1 Kısa Vadeli Kullanılabilirlik ve Birleştirme İyileştirmeleri (Tur 1 Kalanlar)

- `[ ]` **Birleştirme Listesinde Sayfa Küçük Resmi (Thumbnail):**
  - `MergeTab` içindeki her dosya satırının soluna arka plan iş parçacığında üretilen `56×72 px` ilk sayfa küçük resmi eklenmesi (bellek sızıntısını önlemek için görünür satır önbelleklemesiyle).
- `[ ]` **Birleştirme Listesinde `Ctrl+A` ve Çoklu Seçim Operasyonları:**
  - `Ctrl+A` ile tüm satırları seçme, seçili birden fazla dosyayı tek tuşla silme (`Delete`) veya blok halinde yukarı/aşağı taşıma.
- `[ ]` **Tanılama Paketi Dışa Aktarma (`Yardım → Tanılama Paketi Kaydet`):**
  - Kullanıcının tek tıklamayla `app.log`, son kullanılan anonimleştirilmiş ayar (`settings.json`), uygulama sürümü ve ekran DPI/ölçek bilgisini tek bir `.zip` dosyası olarak masaüstüne kaydedebilmesi.
- `[ ]` **Farklı Windows DPI Ölçeklerinde (%100 / %125 / %150) Saha Gözlemi:**
  - Yüksek DPI ölçekli dizüstü ekranlarda (`1366×768` ve `1920×1080` @ `%125`/`%150`) kart yükseklikleri ve metin kırpılmalarının kullanıcı geri bildirimlerine göre ince ayarı.

---

### 3.2 Orta Vadeli İşlevsel Genişleme (Tur 2)

- `[ ]` **Sayfa Ayıklama ve Bölme (Split) Sekmesi:**
  - Tek bir PDF içindeki sayfaları küçük resim (thumbnail) ızgarasında görme, seçili sayfaları silme, ayrı PDF olarak dışa aktarma, sürükleyip yeniden sıralama ve tekil sayfaları 90° döndürme.
- `[ ]` **Bölüm Bazlı Numaralandırma Tablosu:**
  - Ön kısım (`1–8. sayfalar → i, ii, iii`), ana metin (`9–200. sayfalar → 1, 2, 3`) gibi çok parçalı numaralandırma kuralları.
  - Bölüm başlangıç sayfalarında numarayı otomatik gizleme ve yeni bölümü sağ (tek) sayfadan başlatmak için otomatik boş sayfa ekleme seçeneği.
- `[ ]` **Cilt Yeri Seçeneklerinin Genişletilmesi:**
  - Mevcut karşılıklı (iç kenar) ve tek yüz (sol kenar) seçeneklerine ek olarak: **Üstten Cilt** (takvim / bloknot) ve **Sağdan Cilt** (Arapça/Osmanlıca eserler için sağ-sol ters forma hesabı).
- `[ ]` **Filigran / Damga ve Bates Numaralandırma:**
  - Sayfa ortasına veya çaprazına açı, boyut ve saydamlık (opaklık) ayarlı metin filigranı ("TASLAK", "GİZLİ", kurum adı) ekleme.
  - Hukuki ve resmi evraklar için ön/son ekli, sıfır dolgulu ardışık **Bates numarası** (`EVRAK-2026-000142`) basımı.

---

### 3.3 Uzun Vadeli Matbaa, İmpolar ve Otomasyon (Tur 3)

- `[ ]` **Kesim İşaretleri (Crop Marks), Taşma Payı (Bleed) ve Kitapçık Kayma (Creep) Telafisi:**
  - Matbaa giyotin kesimi için köşe kesim çizgileri ve `3–5 mm` taşma payı kontrolü.
  - Kalın formalarda iç sayfaların dışa taşmasını önlemek için forma içindeki sayfa sırasına göre kademeli **creep (kayma)** telafisi.
- `[ ]` **Kitapçık Sıralaması ve N-Up (2'li / 4'lü) İmpolar:**
  - A4 sayfaları A3 kağıda ortadan katlanacak kitapçık sırasıyla (`son-ilk`, `ikinci-sondan bir önceki`) dizme veya 1 yaprağa 2 / 4 sayfa yerleştirme.
- `[ ]` **Klasör Bazlı Toplu İşlem (Batch Processing) ve Komut Satırı Arayüzü (CLI):**
  - Seçilen bir klasördeki tüm PDF'lere kayıtlı bir profili tek seferde uygulama ve `python gutter_engine.py --profile "Tez Baski" --input klasor/ --output cikti/` şeklinde arayüzsüz (headless) çalıştırma.
- `[ ]` **Çoklu Dil Desteği (`TR` / `EN`):**
  - `ui/theme.py` ve sekme metinlerinin dil sözlüğü (`locales/tr.json`, `locales/en.json`) üzerinden dinamik yüklenmesi.
