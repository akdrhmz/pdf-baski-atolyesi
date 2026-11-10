# PDF Baskı ve Cilt Stüdyosu — Plan ve Yol Haritası

**Sürüm:** `2.9.0` · Tek ana referans. Ayrıntılar: [2.9.0 sürüm notları](v2.9.0-surum-notlari.md).

**Öncelik anahtarı:** **P1** kullanıcıyı engelleyen / yanlış sonuç gösteren · **P2** belirgin kalite sorunu · **P3** iyileştirme ve teknik borç · **P4** yeni özellik.

> **Çalışma kuralı (güncel kullanıcı talimatı):** Değişiklikler doğrudan yerel kaynakta uygulanır; ZIP hazırlanmaz. Plan ve sürüm güncellenir. Otomatik test, native Windows kontrolü ve kullanıcı/DPI saha gözlemi ayrı raporlanır.

---

## 1. Durum özeti

| Alan | Durum |
| :--- | :--- |
| Motor (`gutter_engine.py`) | Kararlı: döndürme/kırpma normalizasyonu, sığdırma, sayfa eşitleme (v2.6.21) + **yatayı dikeye döndürme (v2.7.0)**, birleşik geometri, **hızlı** çıktı doğrulama, atomik kayıt |
| Mimari | `app.py` ~450 satır; sekmeler, önizleme, kabuk, iş akışı ayrı modüllerde; arayüz PySide6, sıfır-QSS `QPainter` teması, açık `place()/put()` yerleşimi |
| Güncel teslim | **2.9.0:** Boş/başlangıç akışı, kaynak gerektiren düğme durumları, ön kontrol özeti ve profil seçmeli GUI toplu işlem eklendi |
| Güncel doğrulama | **566 test geçti** (Windows, Python 3.12, ekran dışı Qt; süre 2.9.0 notlarında). Toplu işlem ve arayüz regresyonları dahil. DPI başlangıç boyutu native Windows Qt sürücüsünde; tema tıklama/boyama kontrolü ayrıca geçti |
| Testler (önceki sürüm) | **540 geçti, 1 atlandı** (v2.7.4; Linux, ekran dışı Qt, PySide6 6.12). Windows'ta kullanıcı v2.6.21'i denedi (aşağıdaki S7–S12 bulguları); v2.7.0 Windows'ta kullanıcı tarafından denendi: S7–S11 tamam, tek sorun döndürme yönüydü (S13). v2.7.1 Windows'ta denendi (tamam). v2.7.2 Windows'ta denendi. v2.7.3 Windows'ta henüz çalıştırılmadı; **v2.7.4 de çalıştırılmadı** |
| Açık işler | **20 ve 43: fiziksel ekran/DPI görüntüsü ve kullanıcı saha kontrolü.** Gerçek monitör görüntüsü, yazıcı ve uzun süreli saha gözlemi bekliyor |

---

## 2. Kalıcı teknik sözleşmeler (yeni kod bunlara uyar)

- **2.8.0 güncellemesi önceliklidir:** `merge_handle_only` ve `merge_preview_sequence` widget değil, kalıcı depo tercihleridir. Düz birleştirme `merge_fit` bölümündeki bağımsız eşitleme ayarlarını kullanır. Alt çubuktaki çıktı tercihleri Ayarlar'a taşındı. Önizleme döndürmesi yalnız görünümü değiştirir; çıktı döndürmesi dosya/sayfa araçlarından yapılır. Aşağıdaki sürüm etiketli eski davranışların değişen kısımları için güncel sürüm notları esas alınır.

- **Yerleşim:** `grid()/pack()` sezgileri silindi. Yalnızca `place(row, col, align=, valign=, expand_x=, expand_y=, margins=)`, `put(direction, fill=, expand=, margins=)`, `place_restore()`. **Aralık yalnızca `set_padding(spacing=...)`** ile; örtük kenar boşluğu yok, her boşluk açık yazılır. Ölçüler/boşluklar `ui/theme.py` sabitlerinde (`SP_*`, `FORM_LABEL_W`, `CONTENT_MAX_W`, `PREVIEW_*`, `ROW_MAX_W` …).
- **Sekme erişimi:** pencere takma adı köprüsü (`EXPOSED`/`__getattr__`) yok. Alanlara `app._layout_tab()`, `_number_tab()`, `_merge_tab()` ile erişilir; kurulmamış sekme sessizce kurulmaz (eski ad `AttributeError`). Kabuğun paylaştığı modül anahtarları: `switch_gutter/margin/pnum`.
- **Widget yıkımı:** `QtWidgetMixin.__init_subclass__` `destroy()`'u Qt'nin gölgelemesine karşı sabitler. **v2.6.21:** `destroy()` çocukları üst düzey pencereye çevirmez (`setParent(None)` kaldırıldı); yalnızca kök gizlenir, yerleşimden çıkarılır, `deleteLater()` alt ağacı siler (Windows'ta "pythonw" pencereleri bundan doğuyordu).
- **Satır olayları:** sürüklenebilir satırlar (birleştirme listesi) tıklama/sürükleme anında **satırın güncel indeksini `self.rows` içinden bulur**; bağlama anındaki indeks kullanılmaz (sıra değişince eskir).
- **Sürükle-bırak (v2.7.4, `ui/tabs/merge_drag.py`):** sürüklerken satırlar **yer değiştirmez**; yalnız liste içeriğinin üstündeki `_DropLine` (fareyi geçiren, `QPainter` ile çizilen 3 px çizgi) taşınır. Bırakma aralığı `slot_at(y_root)` ile satır orta noktalarına göre ikili aramayla bulunur (0 = ilk satırın önü, n = son satırın sonrası); bırakınca `drop_selection_at(slot)` seçili satırları (tek/blok) **tek hamlede** taşır (`reorder_for_drop` saf işlev: seçilenlerin kendi sırası korunur, bitişik olmayan seçim bir araya gelir; kendi yerine bırakmak sıralamayı değiştirmez). `DRAG_START_PX` (4 px) altı oynama tıklamadır. Otomatik kaydırma: sürüklerken `QTimer` (`DRAG_SCROLL_MS`) fare listenin alt/üst `DRAG_SCROLL_ZONE` şeridindeyse ya da dışındaysa, fare kımıldamasa da kaydırır (`autoscroll_step`; hız kenara yaklaştıkça artar). `chk_merge_handle_only` açıkken sürükleme yalnız `⠿` tutamacından başlar (`row._handle_label`); satırın başka yerine basmak seçer ama sürüklemez (çoklu seçimde tıkla-bırak yine tekilleştirir). Sürükleme durumu `_end_drag()` ile sıfırlanır (bırakma, `refresh_list`, yeni basış). Sabitler `ui/theme.py` (`DRAG_*`, `DROP_LINE_H`). Eski `index_at` kaldırıldı (yerine `slot_at`).
- **Önizleme:** `PreviewPanel` sayfa sayısını `host.preview_page_count` (yoksa `orig_page_count`) ile alır; birleştirme sekmesinde seçili dosyanın (döndürme + sayfa aralığı uygulanmış) sayfa sayısıdır. İmzaya `variant=(döndürme, aralık)` girer: döndürme/aralık değişince önizleme hemen yenilenir. Birleştirmede önizleme **düz** çizimdir (`render_plain_preview`: cilt/boşluk/numara işareti yok); diğer sekmelerde `render_preview`.
- **Sayfa eşitleme ("sığdır", v2.6.21):** `PdfProcessConfig.fit_mode` (`off/first/largest/a5/a4/a3`) + `fit_keep_orientation`. `prepared_source(input, config)` kaynağın eşitlenmiş (önbellekli, en çok 3 kopya, çıkışta silinir) kopyasını verir; `process_pdf`, `scan_clipping`, `render_preview`, `verify_output` girişte bunu çağırır, böylece her yer aynı ebatları görür. Oran bozulmaz, ortalanır, büyütme de yapılır; bağlantı/yer imi/meta veri taşınır; açıklamalar `flatten_annotations` açıksa gömülür. Cilt payı/boşluk/numara eşitlenmiş sayfalara uygulanır. Düz birleştirmede `chk_merge_fit` (`build_fitted_pdf`); "birleştir + ayarları uygula" yolunda `fit_mode` zaten işleme hattındadır. **v2.7.0:** yön ayarı üçlüdür: `fit_keep_orientation` (yatay yatay kalsın) · kapalıysa `fit_rotate_landscape` (yatay sayfa **saat yönünün tersine** 90° döndürülüp dikey ebadı doldurur; kapalıysa döndürülmeden küçülerek sığar). Bağlantılar döndürmede de `fit_matrix(..., rotate=True)` ile taşınır; önbellek anahtarı döndürmeyi içerir. **Birleştirmedeki eşitleme, Sayfa Düzeni'ndeki ebat + yön ayarlarını kullanır** (kapalıysa en büyük sayfa, yön korunur). **Yalnız eşitleme bir işlemdir:** hiçbir modül açık olmasa da "Sayfaları eşitle" seçiliyse işleme/birleştirme çalışır (`_fit_active()`), eylem düğmesi "Eşitlenmiş PDF oluştur" olur, çıktı adına `_esitlenmis` eklenir.
- **Önizleme/doğrulama hızı (v2.7.0):** `PreviewPage.png` baytları artık sıkıştırmasız **PPM**'dir (alan adı geçmişten kalma; `encode_preview_pixmap`). PNG kodlaması en büyük yavaşlıktı; PPM kodlama ~13×, Pillow ile çözme ~5× hızlı. Çıktı doğrulamasındaki piksel karşılaştırması 8×8 blok ortalamasını `Pixmap.shrink(3)` ile C tarafında alır; Python yalnız küçük görüntüyü gezer (40 sayfada ~1,7 sn → ~0,2 sn).
- **Yeni iş (v2.7.0):** alt çubuktaki "Yeni iş" belgeyi, birleştirme listesini, bekleyen birleştirmeyi ve sonuç düğmelerini sıfırlar; **ayarlar korunur**. İşlem sürerken devre dışıdır (`_new_job`, `WorkflowMixin`).
- **Taşarsa ne olsun varsayılanı:** *Sayfa uzasın* (`clip+expand`) hem model hem motor varsayılanıdır; sekme kurulmamışken de aynı (`CHOICE_EXTEND`). Bu teslimde değiştirilmedi, yalnız doğrulandı.
- **Birleştirme performansı (v2.6.21):** `get_pdf_info(path, quick=True)` (karışık ebat taraması yok) ile ekleme; Döndür yalnız rozetleri günceller, Yukarı/Aşağı taşı satırları yeniden kurmaz (`reorder_rows`); önizleme yalnız istenen sayfaları çizer.
- **Sayfa Düzeni modeli** (`page_layout_model.py`, Qt'siz): "Taşarsa ne olsun" üç seçim → motor çifti: *Sayfa uzasın* = `clip+expand` (varsayılan; yalnız boyu uzatır, dar sabit hedefte sağdan kırpabilir) · *İçerik küçülsün* = `shrink+fit` · *Taşan kırpılsın* = `clip+shift`. Eski çiftler (`shrink+expand`, `shrink+shift`, `clip+fit`) yüklenince aynen korunur (`exact=False`, tek satırlık not). Özel sayfa kuralları (`SpecialRule`): *hiçbir pay / yalnız cilt payı (ara kapak) / yalnız alt-üst boşluk*; birden çok kural birleşir. `relevance()` hangi satırın hangi ebat modunda/seçimde etkili olduğunu tek yerde tutar; ilgisiz satırlar **gizlenir**. `settings.json` biçimi ve motor çıktısı bu model yüzünden değişmez.
- **Önizleme/ayraç:** gerçek `QSplitter` (içerik ≥ `CENTER_MIN_W` 540 px, önizleme 360–850 px); sayfalar `PreviewCanvas` ile `paintEvent`'te oranlı sığdırılır. Çift sayfa açılımı 1-2, 3-4 …; tek sayıda son sayfa tek başına. Ayrı önizleme penceresi sahipsiz (üstte tut kapalıyken arkaya düşebilir).
- **Terim sözlüğü:** arayüz adları tek yerde (`page_layout_model.CHOICE_NAMES`); motor mesajları arayüz katmanında çevrilir (`ui_warning`), motor çıktısı/testleri değişmez. Kırpma uyarıları ardışık aynı değerli sayfaları aralıkla gruplar.
- **Doğrulama yöntemi (yerleşim refaktörlerinde):** çevirmeden önce/sonra pencerenin yerleşim dökümü + ekran görüntüsü piksel karşılaştırması; kaynak taramalı testler eski çağrıların geri gelmesini engeller.
- **Tanılama:** Kılavuz & Hakkında → "Tanılama paketi oluştur (.zip)" (günlük, anonim ayar, sürüm, DPI).

---

## 3. Tamamlananlar (özet)

| Sürüm | Konu |
| :--- | :--- |
| **2.8.0** | **38, 40 devamı, 42, 45–46 ve P4 22/24–32/44:** tek kaynakta uygulandı. Windows otomatik testleri, gerçek Windows tema kontrolü ve 25/100/300 dosya ölçümü; ayrıntı ve kapsam sınırları sürüm notlarında |
| 2.7.8 | Birleşik dizi önizlemesi ve tutamaktan sürükleme Ayarlar’a taşındı; kalıcı kayıt, anında uygulama, fabrika sıfırlama ve kaydırılabilir Ayarlar penceresi. |
| 2.7.7 | **P3-41c: Cilt payı ve hazır baskı şablonu satırlarında ROW_MAX_W sınırı, expand_x yerleştirmesinden sonra uygulanır; 580 px sınırı artık kaldırılmaz.** Testler çalıştırılmadı; GUI doğrulaması bekliyor. |
| 2.7.6 | **P3-41b: Birleştirme listesindeki Sayfa: etiketi seçiliyken beyaz, seçim kaldırılınca ikincil metin rengine döner; tutamak da aynı kontrastı izler.** Testler çalıştırılmadı; GUI doğrulaması bekliyor. |
| 2.7.5 | **P3-41a: Kırpma riski diyaloğunda gerçek bir esnek dolgu ile düğmeler ve İptal sağa yaslandı.** Testler çalıştırılmadı; GUI doğrulaması bekliyor. |
| 2.2.x–2.4.x | Motor sağlamlaştırma (döndürme/CropBox normalizasyonu, taşma modları, Unicode yazı tipi, yer imi onarımı, atomik kayıt); mimari bölme (ayar bağlama, `BaseTab`, sekmeler, önizleme paneli, kabuk, iş akışı); CustomTkinter → PySide6 geçişi, sıfır-QSS tema; arayüz incelemesi (adım düğmesi aralığı, form bileşenleri, tasarım ölçekleri, hazır kağıt tutarlılığı); 1a boyama bozulması düzeltildi, 1b (240×319 mm gözlemi) hata değil; önizleme çift sayfa açılımı, üretim iptali, "Git" kutusu + klavye gezinmesi + lejant; "Sayfa Düzeni" modeli |
| 2.5.0–2.5.3 | Birleşik "Sayfa Düzeni" sekmesi (Cilt payı · Alt/üst boşluk · Sayfa boyutu · Özel sayfalar), serbest önizleme boyutlandırma, yatay kaydırma koruması; `QSplitter` + `PreviewCanvas`; motorda çift ölçekleme düzeltmesi (13f); "Üstte tut" sahipsiz pencere; sihirli sayılar → `theme.py`; ince kaydırma çubuğu; sol menü ipucu; tanılama paketi |
| 2.6.0 | Birleştirme listesinde çoklu seçim (Ctrl/Shift, Ctrl+A, çoklu sil/döndür, blok taşıma/sürükleme) |
| 2.6.1–2.6.11 | `qt_compat` sadeleştirme: `grid()/pack()` tamamen `place()/put()`'a çevrildi, sezgiler silindi (P3-15 kapandı) |
| 2.6.12–2.6.15 | Saha bulguları 33–36: dar pencerede birim etiketi, hedef ebat notu, kırpma uyarılarının gruplanması + tek terim sözlüğü + iki diyaloğun aynı aileye çekilmesi, "Sayfa boyutu ve sığdırma" sadeleştirmesi (ilgisiz satırlar gizli, sonuç cümlesi); "Hedefe uygula" kağıt satırına taşındı |
| 2.6.16–2.6.20 | Yapışan form satırları, kağıt satırı üst üste binmesi, `EXPOSED` köprüsünün tamamen silinmesi (P3-16 kapandı); **özel sayfa kuralı "kaldırılamıyor" hatasının kök nedeni:** `QWidget.destroy()` mixin'i gölgeliyordu → düzeltildi (birleştirme listesi satır sızıntısı da buydu) |
| 2.6.21 | Saha bulguları S1–S6: birleştirme sürükleme/seçim, "pythonw" pencereleri, önizleme tüm sayfalar + döndürme/aralık, performans, sayfa eşitleme (sığdır) |
| 2.7.0 | **Saha bulguları S7–S12 (aşağıda):** önizleme/doğrulama hızı, yalnız-eşitleme "en az bir modül" hatası, birleştirmede yön ayarının yok sayılması + yatayı dikeye döndürme, "Yeni iş" düğmesi |
| 2.7.1 | **S13:** "dikeye döndür" yönü saat yönünün tersine çevrildi (Windows'ta v2.7.0 denendi, yön ters çıktı) · **P3-38 ilk dilim:** birleştirme listesinde hedefli satır ekleme/silme |
| 2.7.2 | **P3-39a:** birleştirme önizlemesi artık sonucu gösterir (eşitleme / "birleştir + ayarları uygula") |
| 2.7.3 | **P3-39b+c:** birleştirmede tüm birleşik diziyi önizlemede gezme (dosya sınırı işaretli) · aralık yazarken önizleme yanıp sönmesi giderildi (39 kapandı) |
| **2.7.4** | **P3-40:** birleştirme listesinde bırakma yeri çizgisi · kenarda otomatik kaydırma · yalnız tutamaktan sürükleme · sürükleme maliyeti ölçüldü (40 kapandı) |

### v2.8.0 ayrıntısı

Yeni modüller, kullanım yolları, performans tablosu, test sonuçları ve kapsam sınırları: [2.8.0 sürüm notları](v2.8.0-surum-notlari.md). Önceki sürümlerdeki oturumluk tercih ve Sayfa Düzeni’ne bağımlı düz birleştirme notları tarihî bilgidir.

### v2.7.8: Arayüz tercihlerini düzenleme

- Ayarlar → Birleştirme: liste ve önizleme altında iki genel tercih toplanır. `merge_preview_sequence` ve `merge_handle_only` JSON alanları varsayılan kapalıdır; eski ayar dosyaları ve geçersiz değerler bu varsayılanla açılır.
- Birleştirme sekmesi kurulmadan tercih değiştirilebilir. Değişiklik hemen kaydedilir, sonraki oturumda ve Yeni iş sonrasında korunur. Fabrika sıfırlama ikisini de kapatır. Etkin sürükleme tercih değişikliğinde iptal edilir.
- Birleştirme ekranında üç çıktı seçeneği ve Ayarlar kısayolu kalır. Yer imi, eşitleme, diğer sekmelerin ayarları, numaralandırma, yön ve çıktı kontrolleri işe göre değiştiği için ilgili ekranlarda tutulur.
- Ayarlar penceresi yeniden boyutlandırılabilir ve kaydırılabilir; dar veya yüksek DPI ekranlarda seçenekler erişilebilir kalır.
- **Doğrulama:** Yalnızca kaynak ve sözdizimi incelemesi. Kullanıcı isteğiyle testler çalıştırılmadı; GUI açılmadı. Önceki sürümlerdeki oturumluk tercih notları bu sürümle geçersizdir.

### v2.7.7 ayrıntısı (41, adım 3/3)

41c: Cilt payı ve hazır baskı şablonu satırlarında ROW_MAX_W sınırı, expand_x yerleştirmesinden sonra uygulanır; 580 px sınırı artık kaldırılmaz.

**Doğrulama:** Kullanıcı isteğiyle testler çalıştırılmadı. Windows ortamında kaynak düzenlendi; uygulama/Qt arayüzü çalıştırılmadı. Görsel saha doğrulaması bekliyor.

### v2.7.6 ayrıntısı (41, adım 2/3)

41b: Birleştirme listesindeki Sayfa: etiketi seçiliyken beyaz, seçim kaldırılınca ikincil metin rengine döner; tutamak da aynı kontrastı izler.

**Doğrulama:** Kullanıcı isteğiyle testler çalıştırılmadı. Windows ortamında kaynak düzenlendi; uygulama/Qt arayüzü çalıştırılmadı. Görsel saha doğrulaması bekliyor.

### v2.7.5 ayrıntısı (41, adım 1/3)

41a: Kırpma riski diyaloğunda gerçek bir esnek dolgu ile düğmeler ve İptal sağa yaslandı.

**Doğrulama:** Kullanıcı isteğiyle testler çalıştırılmadı. Windows ortamında kaynak düzenlendi; uygulama/Qt arayüzü çalıştırılmadı. Görsel saha doğrulaması bekliyor.

### v2.7.4 ayrıntısı (önceki teslim)
**Doğrulama:** `python -m pytest` → **540 geçti, 1 atlandı** (519 + 21 yeni: hepsi `tests/test_merge_drag.py`; mevcut iki test güncellendi/yeniden yazıldı). **Windows'ta çalıştırılmadı** (Linux, ekran dışı Qt).

18. `[x]` **P3-40 — Birleştirme listesinde sürükle-bırak iyileştirmeleri.** Teknik sözleşme §2'de.
   - **Bırakma yeri göstergesi:** sürüklerken fare hangi aralıktaysa (satır ortalarına göre) ince bir mavi çizgi orada durur; satırlar yerinde kalır. Fare bırakılınca seçili satırlar çizginin gösterdiği yere taşınır. Kendi yerine bırakmak sırayı değiştirmez. **Davranış değişikliği:** eski sürümde satırlar fareyle birlikte canlı yer değiştiriyordu; artık taşıma bırakınca yapılır (çizgi neyin nereye gideceğini önceden gösterir).
   - **Kenarda otomatik kaydırma:** fare listenin alt/üst kenarındaki 28 px şeride ya da listenin dışına gelince liste kayar; hız kenara yaklaştıkça artar (en çok 18 px / 30 ms); fare durağan kalsa da kayar, kaydırırken bırakma çizgisi yeniden hesaplanır; liste sonunda durur.
   - **Yalnız tutamaktan sürükleme:** Birleştirme seçenekleri → **"Satırları yalnız ⠿ tutamacından sürükle"** (varsayılan kapalı). Açıkken satırın başka yerine basmak yalnız seçer; sürükleme ⠿'tan başlar. **Sınır:** bu ayar oturumluktur (kapatınca sıfırlanır; `settings.json`'a yazılmaz, `chk_merge_fit` / dizi önizlemesi gibi).
   - **Titreme ölçümü** (`tools/olcum_surukleme.py`; Linux, ekran dışı Qt; Windows'ta aynı betik çalıştırılabilir):

     | Dosya | Eski: fare adımı (satırları yeniden yerleştirme) | Yeni: fare adımı (yalnız çizgi) | Bırakmada tek taşıma |
     | ---: | ---: | ---: | ---: |
     | 25 | 1,05 ms | 0,022 ms | 1,06 ms |
     | 100 | 4,68 ms | 0,031 ms | 4,89 ms |
     | 300 | 24,17 ms | 0,038 ms | 19,05 ms |

     Eski sütun, kaldırılan yöntemin adım maliyetinin (`_move_block` + `reorder_rows`) aynı ortamda ölçümüdür. 300 dosyada fare adımı ~24 ms (60 Hz'de kare atlatır) → ~0,04 ms; ağır iş (yeniden yerleştirme) bırakmada **bir kez** yapılır. Gerçek ekranda kalan maliyet Qt'nin çizimidir; Windows'ta bakılacak (§5).
   - **Testler (`tests/test_merge_drag.py`):** `reorder_for_drop` (9 durum: tek/blok, başa/sona, bitişik olmayan seçim, no-op'lar), `autoscroll_step` bölgeleri, sürüklerken satırların yerinde kalması + çizginin aralığı izlemesi, bırakınca taşıma + çizginin gizlenmesi + önizleme yenileme, kendi yerine bırakma, eşik altı hareket = tıklama, blok sürükleme sona, yarım kalan sürüklemede `refresh_list`, otomatik kaydırma (alt/üst/orta/liste sonu; fare kımıldamadan), tutamak ayarı (kapalı/açık, çoklu seçimde tıkla-bırak). `test_drag_moves_whole_block` bırakmada taşıma için yeniden yazıldı; `test_index_at_...` → `test_slot_at_...`.

### v2.7.3 ayrıntısı (önceki teslim)
**Doğrulama:** `python -m pytest` → **519 geçti, 1 atlandı** (514 + 5 yeni). **Windows'ta çalıştırılmadı.**

16. `[x]` **P3-39b — Tüm birleşik diziyi önizlemede gezme.** Birleştirme sekmesi altında **"Önizlemede tüm birleşik diziyi gez"** (varsayılan kapalı). Açıkken sayfa sayısı tüm dosyaların (döndürme + sayfa aralığı uygulanmış) toplamıdır; Önceki/Sonraki/Git/çift sayfa açılımı birleşik belgenin gerçek sırasını izler. Her sayfanın altında "N. sayfa • ▶ dosya.pdf (1/3)" yazar; **▶** dosyanın ilk sayfasını (dosya sınırını) gösterir. Dosyalar geçici bir PDF'te birleştirilir ve liste/döndürme/aralık değişmedikçe önbellekte kalır (sayfa çevirmek hızlı; çıkışta silinir). Eşitleme ve "birleştir + ayarları uygula" bu birleşik belge üzerinden uygulanır; **numara, cilt yönü ve "ilk/en büyük sayfa" eşitlemesi gerçek çıktıyla birebirdir** (39a'daki yaklaşıklık dizi kipinde yok). Sınır: ilk açılışta (veya liste değişince) çok dosyada birleştirme birkaç saniye sürebilir; arka planda yapılır.
17. `[x]` **P3-39c — Aralık yazarken önizleme.** Kök neden: yarım yazılmış aralık ("1-", "3,") geçersiz sayılıp önizlemeyi tüm belgeye döndürüyor, tamamlanınca geri getiriyordu (yanıp sönme); ayrıca aralık kısalınca eski sayfa sınır dışında kalabiliyordu. Artık yalnız **geçerli** aralıkta (300 ms gecikmeli) yenilenir, geçersizken son önizleme kalır; sayfa yeni toplama göre sınırlanır.

### v2.7.2 ayrıntısı (daha önceki teslim)
**Doğrulama:** `python -m pytest` → **514 geçti, 1 atlandı** (511 + 3 yeni). **Windows'ta çalıştırılmadı.**

15. `[x]` **P3-39a — Birleştirme önizlemesi sonucu gösteriyor.** "Farklı ebatlı sayfaları eşitle" açıkken seçili dosya eşitlenmiş ebatta çizilir (`render_plain_preview(fit=...)`; Sayfa Düzeni'ndeki ebat + yön + "dikeye döndür" kullanılır). "Birleştir + aktif ayarları uygula" açıkken seçili dosya döndürme/aralıkla geçici PDF'e alınıp cilt/boşluk/numara/eşitleme uygulanmış çizilir (`render_merge_result_preview`). Onay kutuları değişince önizleme yenilenir. **Sınırlar:** "ilk sayfa/en büyük sayfa" eşitleme kipleri yalnız seçili dosyanın sayfalarına göre hesaplanır (yaklaşık; sabit A3/A4/A5 birebir); cilt yönü ve numara dosyanın kendi sayfa sırasına göredir (birleşik belgedeki konuma göre değil).

### v2.7.1 ayrıntısı (daha eski teslim)
**Doğrulama:** `python -m pytest` → **511 geçti, 1 atlandı** (508 + 3 yeni). **Windows'ta çalıştırılmadı.**

13. `[x]` **S13 — "Yatay sayfaları dikeye döndür" ters yöne dönüyordu.** Artık saat yönünün tersine (yatay sayfanın üstü sola gelir). Bağlantı matrisi de güncellendi; test bağlantının sol-alt köşeye gittiğini doğrular. Ters yön seçeneği yok.
14. `[x]` **P3-38 ilk dilim — hedefli satır ekleme/silme.** `rows_added(before)` yalnız yeni satırları kurar (dosya ekleme ve sürükle-bırak); `remove_selected` yalnız silinen satırları yok edip kalanları yeniden numaralar; satır kurulumu `_build_row`'a ayrıldı. Ölçüm (Linux, ekran dışı Qt, 300 dosya): tek satır silme ~0,36 sn → ~0,016 sn; 290 dosyaya 10 ekleme ~0,014 sn (tam yenileme ~0,26 sn). **Kalan (38):** satır sanallaştırma (yalnız görünen satırlar), `refresh_selection`/`update_summary` toplulaştırma, Windows'ta ölçüm (`APP_PERF=1`).

### v2.7.0 ayrıntısı (en eski teslim)
**Doğrulama:** `python -m pytest` → **508 geçti, 1 atlandı** (494 + 14 yeni `tests/test_v2_7_fit_rotate_newjob.py`; 2 eski önizleme testi PNG imzası yerine "Pillow açabiliyor" denetler). **Windows'ta çalıştırılmadı** (hız ölçümleri Linux'ta, 40 sayfalık örnek PDF).

7. `[x]` **S7 — Program çok yavaş (ilk dilim).** Ölçüm: önizleme PNG kodlaması en büyük yavaşlık (880→149 ms, 1859→245 ms düzeldi); çıktı doğrulamasındaki piksel karşılaştırması saf Python döngüsüydü (40 sayfada ~1,7 sn). **Çözüm:** önizleme baytları PPM (§2), blok ortalaması `Pixmap.shrink` ile. Test: bozuk yerleşim hâlâ yakalanıyor (`test_render_check_still_detects_a_wrong_placement`). **Kalan:** P3 madde 38 (listede ilk dilim v2.7.1'de yapıldı) ve arayüz tarafı ölçümü (`APP_PERF=1`).
8. `[x]` **S8 — "Sayfaları eşitle" tek başına seçilince "En az bir modülü etkinleştirin" hatası.** **Kök neden:** üç kontrol (işleme, birleştirme, eylem çubuğu) yalnız cilt/boşluk/numara anahtarlarına bakıyordu. Artık "Sayfaları eşitle" seçili olması da yeterli (§2). Birleştirme + ayarları uygula yolundaki aynı uyarı da düzeltildi.
9. `[x]` **S9 — Birleştirmede "Yatay sayfalar yatay kalsın" yok sayılıyordu.** **Kök neden:** düz birleştirmede eşitleme `PdfProcessConfig(fit_mode=...)` ile kuruluyordu; yön alanları varsayılana (yatay kalsın) düşüyordu. Artık Sayfa Düzeni'ndeki yön ayarı okunur.
10. `[x]` **S10 — Yatayı dikeye çevirme seçeneği.** Sayfa Düzeni → Sayfaları eşitle → **"Yatay sayfaları dikeye döndür"** (yalnız "yatay kalsın" kapalıyken seçilebilir). Birleştirmedeki eşitleme de bunu kullanır. Test: döndürülmüş sayfa dikey sayfayı doldurur, döndürmeyen küçülür, bağlantılar içerikle döner, ayar gidiş-dönüşü, önbellek.
11. `[x]` **S11 — "Yeni iş" düğmesi** (programı kapatıp açmak gerekiyordu). Bkz. §2. Testler: sıfırlama + ayarların korunması, işlem sürerken engelleme.
12. `[x]` **S12 — Taşarsa varsayılanı "sayfa uzasın".** Zaten varsayılandı (§2); değişiklik yok. **Saha notu:** A4'e eşitleme sayfaları kırpmıyor (kullanıcı gözlemi) — doğru.
   - **Sınırlar (bilerek):** birleştirmede eşitleme ayarı için ayrı bir menü yok, Sayfa Düzeni'ni kullanır (P3 42); döndürme yönü saat yönünün tersidir (v2.7.1), ters yön seçeneği yok.

### v2.6.21 ayrıntısı (önceki teslim)
**Doğrulama:** `python -m pytest` → **494 geçti, 1 atlandı** (478 + 15 yeni `tests/test_fit_and_merge_fixes.py` + 1 `test_gui_headless.py`). Sürükleme hatası ve sızıntı kodda yeniden üretildi (tıklanan satır yerine eski indeksteki dosya seçiliyordu); düzeltme sonrası aynı betik doğru. **Windows'ta çalıştırılmadı.**

1. `[x]` **S1 — Sürükle-bırak sonrası seçim/sıra bozuluyor** ("sırasını değiştirdiğim PDF'i seçemiyorum", "sekme değişince sıfırlanıyor" izlenimi). **Kök neden:** `bind_row_drag` satır indeksini kurulumda sabitliyordu; sürükleyince satır nesneleri yer değiştirir ama olay işleyicileri eski indeksi kullanmaya devam eder → tıklanan satır yerine eski sıradaki dosya seçilir/sürüklenir (sekme dönüşünde satırlar yeniden kurulunca "sıfırlanmış" görünür). **Çözüm:** indeks tıklama anında `self.rows` içinden bulunur. Testler: tıklama sonrası doğru seçim, her satırın kendini seçmesi.
2. `[x]` **S2 — Çok sayıda "pythonw" penceresi** (ekran görüntüsü: satır sayısı kadar boş pencere). **Kök neden (koddan; Windows'ta gözlenmedi):** v2.6.20'de `destroy()` çocukları tek tek `setParent(None)` yapıyordu; üst-pencereye dönüşen satır çocukları Windows'ta başlıksız yerel pencere olarak belirebiliyor. **Çözüm:** `destroy()` artık yeniden ebeveynlemez (bkz. §2). **Hâlâ görülürse** ekran görüntüsü + hangi işlemden sonra olduğu istenir.
3. `[x]` **S3 — Birleştirme önizlemesi yalnız 1. sayfayı gösteriyor.** **Kök neden:** gezinme sayfa sayısını ana belgeden (`orig_page_count`, belge açılmamışsa 0) alıyordu. Önizleme artık seçili dosyanın sayfa sayısını kullanır; farklı dosya seçilince 1. sayfadan başlar.
4. `[x]` **S4 — Döndürme önizlemede hemen yansımıyor.** Önizleme imzası döndürmeyi/sayfa aralığını içermiyordu ve birleştirme önizlemesi cilt ayarlarıyla çiziliyordu. Artık döndürme + aralık imzada; çizim düz (`render_plain_preview`). Döndürme yalnız rozeti günceller (satırlar yeniden kurulmaz).
5. `[x]` **S5 — Çok PDF eklemek programı kasıyor (ilk dilim).** `get_pdf_info` her eklemede tüm sayfa ebatlarını tarıyordu (`quick=True` ile atlanır); döndür/taşı tüm satırları yeniden kuruyordu (artık değil); önizleme yalnız istenen sayfaları çizer. **Kalan:** P3 madde 38.
6. `[x]` **S6 — Sayfa eşitleme ("sığdır").** Farklı ebatlı sayfalarda cilt payı/boşluk bırakırken kırpılma, Acrobat'ta "Yazdır > Adobe PDF > Sığdır" ile çözülüyordu; artık yazdırmadan: **Sayfa Düzeni → Sayfa boyutu ve sığdırma → "Sayfaları eşitle"** (Kapalı / İlk sayfanın ebadına / En büyük sayfanın ebadına / A5 / A4 / A3) + "Yatay sayfalar yatay kalsın". **Birleştirme → "Farklı ebatlı sayfaları eşitle"** düz birleştirmede aynı işi yapar. Testler: ebatların eşitlenmesi, oranın korunması/kırpmama, eşitleme öncesi kırpma uyarısı → sonrası yok, `verify_output` ebat eşleşmesi, bağlantı/yer imi taşınması, önbellek, ayar gidiş-dönüşü, arayüz gidiş-dönüşü.
   - **Sınırlar (bilerek):** özel ebat girişi yok; eşitleme sayfa başına istisna kabul etmez; birleştirme sekmesindeki önizleme eşitlenmiş hâli göstermez (bkz. P3 39a).

---

## 4. Yapılacaklar (öncelik sırasıyla)

### P1 — Önce yapılmalı
- `[ ]` **43 — Kullanıcı ortamında Windows saha kontrolü:** 2.9.0'da 566 otomatik test ve Windows Qt sürücüsünde tema/DPI kontrolleri tamamlandı. §5'teki gerçek pencere/monitör/yazıcı ve uzun süreli kullanım gözlemleri ayrıca bekliyor; otomatik sonuçlarla yapılmış sayılmaz.

### P2 — Belirgin kalite sorunları
*(Açık madde yok; 1–36 tamamlandı.)*

### P3 — İyileştirme ve teknik borç
45. `[x]` **Ayarlar ve arayüz sadeleştirme (2.8.0):** Optimizasyon ve açıklama/form gömme Ayarlar'a taşındı; dört bölüm, anında kayıt ve fabrika sıfırlama tamam. İşe bağlı çıktı kontrolleri ilgili ekranda kaldı.
46. `[x]` **Tema seçimi ikinci tıklamayı bekliyor (2.8.0):** Tema callback'inden sonraki Qt olay turunda görünür pencerelerin boyaması tamamlanır. Açık → koyu → açık tek tıklama kontrolü hem ekran dışı Qt hem native Windows sürücüsünde geçti.
20. `[ ]` **DPI saha gözlemi** (Windows, ekran görüntüsüyle; tanılama paketi DPI'ı toplar): açılış boyutu ve dar pencere düzeni artık Qt mantıksal ekran ölçüsüne göre uyarlanır; 1366×768 @ %150 senaryosu otomatik sınandı. Gerçek `1366×768` ve `1920×1080` @ %125/%150 monitörlerde kart yükseklikleri ve metin kırpılmaları için görüntü kontrolü bekliyor.
38. `[x]` **Liste performansı (2.8.0):** 100+ dosyada görünür satır kontrolleri tembel kurulur; görünmeyenlerde hafif yer tutucu kalır. Seçim ve toplamlar önbelleğe alındı; APP_PERF ölçüm noktaları eklendi. Windows'ta 25/100/300 dosya eski/yeni ölçüldü: 300 dosyada kurulum 2827,53 → 200,47 ms, temizleme 94,93 → 12,89 ms. Tek örnek ölçüm ve sınırlar sürüm notlarında.
39. `[x]` **Birleştirme önizlemesi geliştirmeleri:**
   - (a) `[x]` v2.7.2'de yapıldı (bkz. 15).
   - (b) `[x]` v2.7.3'te yapıldı (bkz. 16).
   - (c) `[x]` v2.7.3'te giderildi (bkz. 17).
40. `[x]` **Sürükle-bırak iyileştirmeleri:** v2.7.4'ün çizgi/kaydırma/tutamak davranışı korundu. 2.8.0'da tutamak tercihi kalıcıdır; sürüklenen satırlar soluklaşır ve `Esc` sürüklemeyi iptal eder.
41. `[x]` **Küçük gözlemler:**
   - (a) `[x]` v2.7.5: "Kırpma riski" diyaloğunda `İptal` sağa yaslandı.
   - (b) `[x]` v2.7.6: Seçili satırda "Sayfa:" etiketi ve tutamak kontrastı düzeltildi.
   - (c) `[x]` v2.7.7: `WrapButtonRow` `ROW_MAX_W` sınırı yerleştirmeden sonra uygulanarak korundu.
42. `[x]` **Birleştirmede eşitleme ayarı (2.8.0):** Kendi ebat/yön/özel ölçü/çevre boşluğu kontrolleri ve önizlemesi var. Yeni iş ve yeniden açılışta tercihler korunur; fabrika sıfırlama varsayılana döndürür. Aktif ayarları uygulama yolu Sayfa Düzeni'ni kullanır.
47. `[x]` **Boş durum ve işlem akışı (2.9.0):** Kaynak olmadan işlem, iki dosyadan az birleştirme ve boş önizleme durumları açıklayıcı yönlendirme gösterir. Sonuç/iptal düğmeleri ilgili işlem aşamasında görünür; isteğe bağlı ön kontrol kaynağı, etkin işlemi ve çıktı tercihlerini özetler.
48. `[x]` **GUI toplu işlem (2.9.0):** Dosya/klasör ve alt klasör seçimi, ekran ayarları veya profil, çıktı klasörü, riskli dosyaları atlama, ilerleme ve dosya başına doğrulanmış sonuç/hata. Kaynaklar korunur; iptalde tamamlanan çıktılar saklanır.

### P4 — Yeni özellikler (2.8.0’da uygulandı)
**Tur 1 (kısa vade)**
22. `[x]` Birleştirme listesinde sayfa küçük resmi (56×72 px, arka plan iş parçacığı, yalnız görünen satırlar → madde 38'e bağlı).
24. `[x]` Önizlemede yakınlaştırma, döndürme, öncesi/sonrası karşılaştırma (`PreviewCanvas` zemini hazır: tam çözünürlüklü pixmap tuvalde).
44. `[x]` Sayfa eşitlemeye **özel ebat** (genişlik × yükseklik), kenar payı ("sığdırırken çevreden X mm bırak") ve eşitleme önizlemesi (Sayfa Düzeni'nde seçilen ebadın gösterilmesi).

**Tur 2 (orta vade)**
25. `[x]` **PDF araçları penceresi:** küçük resim ızgarası, listeden kaldır/dışa aktar/sırala/döndür ve parça boyutuna göre bölme. Ana sekme yerine ayrı pencere kullanıldı.
26. `[x]` Bölüm bazlı numaralandırma (i, ii, iii → 1, 2, 3; bölüm başında numara gizleme, otomatik boş sayfa).
27. `[x]` Cilt yeri genişletme: üstten cilt, sağdan cilt.
28. `[x]` Filigran/damga ve Bates numaralandırma.

**Tur 3 (uzun vade)**
29. `[x]` Kesim işaretleri, taşma payı (bleed) ve kitapçık kayma (creep) telafisi.
30. `[x]` Kitapçık sıralaması ve N-Up (2'li/4'lü) impo.
31. `[x]` Klasör bazlı toplu işlem: GUI profili/sonuç kuyruğu ve CLI (`gutter_engine.py --profile ... --input ... --output ...`).
32. `[x]` Çoklu dil (`TR`/`EN`, `locales/*.json`).

---

## 5. Windows'ta bakılacaklar (birleşik kontrol listesi)
v2.5.2'den beri Windows'ta denenmemiş her şey için tek liste; sorun çıkarsa ekran görüntüsü + hangi adım istenir.

1. **Birleştirme (v2.6.21):** 5+ PDF ekle → bir satırı sürükleyip başka yere bırak → o satıra tıkla (doğru dosya seçilmeli, önizleme o dosyayı göstermeli) → başka sekmeye geçip dön (sıra korunmalı); sürüklerken/yenilerken **boş "pythonw" pencereleri çıkmamalı**; önizlemede Önceki/Sonraki ile **tüm sayfalar** gezilmeli; yatay PDF'i "Döndür" ile dikeye çevirince önizleme hemen dönmeli; sayfa aralığı yazınca önizleme sayfa sayısı değişmeli; 20+ PDF ekleyince akıcılık; Del / Alt+↑↓ / Ctrl+tık / Shift+tık / Ctrl+A.
0. **v2.7.4 yenilikleri:** Birleştirme → 5+ PDF ekle, bir satırı ⠿'tan ya da gövdesinden sürükle: **mavi çizgi** fare altındaki aralıkta duruyor mu, bırakınca satır oraya geliyor mu, numaralar ve seçim doğru mu; çoklu seçili bloğu sürükle (blok birlikte gidiyor mu); 20+ PDF'te fareyi listenin **alt/üst kenarına** getir: liste kayıyor mu (fare durağanken de), hız kenara yaklaştıkça artıyor mu, liste sonunda duruyor mu; küçük bir tıklama (sürüklemeden) yalnız seçiyor mu; "Satırları yalnız ⠿ tutamacından sürükle" açıkken satır gövdesinden sürüklenmiyor, tutamaktan sürükleniyor mu; sürüklerken titreme/takılma var mı (100–300 dosyada; `python tools/olcum_surukleme.py` sonucunu da paylaşabilirsin); koyu temada çizgi görünüyor mu; %125/%150 DPI'da çizgi kalınlığı/yeri.
0. **v2.7.3 yenilikleri:** Birleştirme → "Önizlemede tüm birleşik diziyi gez": sayfa sayısı toplam mı, ▶ dosya sınırı doğru mu, sırayı/döndürmeyi/aralığı değiştirince önizleme güncelleniyor mu, 20+ dosyada ilk açılış süresi; sayfa aralığı yazarken ('1-', '1-3') önizleme yanıp sönmüyor mu.
0. **v2.7.0 yenilikleri:** (a) 40+ sayfalık PDF'te önizleme ve "Sonuç doğrulanıyor" aşaması önceki sürüme göre belirgin hızlı mı; (b) hiçbir modül açık değilken yalnız "Sayfaları eşitle: A4'e" ile **"Eşitlenmiş PDF oluştur"** çalışıyor mu; (c) Birleştirme → "Farklı ebatlı sayfaları eşitle" + Sayfa Düzeni'nde "yatay kalsın" kapalı/açık, "dikeye döndür" açık/kapalı → çıktı ebatları ve yön; (d) alt çubukta **Yeni iş**: belge + liste temizleniyor, ayarlar duruyor, işlem sürerken pasif.
2. **Sayfaları eşitle (v2.6.21):** karışık ebatlı PDF + cilt payı + "Sayfaları eşitle: A4'e" → önizleme ve çıktı; kırpma uyarısı kalkmalı; "Yatay sayfalar yatay kalsın" açık/kapalı; Birleştirme → "Farklı ebatlı sayfaları eşitle" ile çıktı ebatları.
3. **Sayfa Düzeni:** Özel sayfalar'da 2–3 kural ekle, hepsini (sonuncu dahil) kaldır, satır aralığı korunuyor mu; "Hedefe uygula" menü/segmentle hizalı mı; dar pencerede kağıt satırı ve "mm" etiketleri üst üste binmiyor mu; "Ebat modu" değişince satırların gelip gitmesi ve kaydırma konumu; geçersiz alan değerinde hata metninin alt satıra sarılması.
4. **Genel görünüm:** ana pencere (üst çubuk, sol menü akordeonu, alt eylem çubuğu), önizleme (Tek/Çift sayfa, Git kutusu, lejant, ayraç sürükleme/çift tıklama, tam ekran, **Pencerede aç + Üstte tut** açık/kapalı Z sırası ve görev çubuğu düğmesi), koyu tema, %125/%150 DPI.
5. **Diyaloglar:** Ayarlar, Hakkında (tanılama paketi), "Kırpma riski" tarama/onay (düğme adları: İçerik küçülsün / Taşan kırpılsın / İptal; metin kutusu alt kenarında renkli çizgi var mı).
6. **Sayfa Numaraları / birim:** sekmeyi ilk kez açma, kayıtlı ayarın yüklenmesi, mm ↔ cm değişiminde tüm alan etiketleri; kayıtlı ayar yükleme ve "Oluştur"/"Birleştir".

---

## 6. Güncel modül haritası

| Modül | Sorumluluk |
| :--- | :--- |
| `app.py` | İnce uygulama kabuğu, yaşam döngüsü |
| `pdf_tools.py`, `ui/pdf_tools.py` | Sayfa ızgarası/ayıklama/bölme, filigran/Bates, kesim/taşma payı, kitapçık ve N-Up; arka plan işçisi, iptal ve araç penceresi |
| `studio_cli.py` | Profil ile dosya/klasör bazlı toplu işlem; `gutter_engine.py` CLI girişini buraya yönlendirir |
| `ui/section_editor.py`, `ui/i18n.py`, `locales/*.json` | Bölüm numaralandırma tablosu; TR/EN görünen metinler, dinamik rapor şablonları ve özgün seçenek kodlarının korunması |
| `gutter_engine.py` | PDF işleme motoru: geometri, **sayfa eşitleme (`fit_*`, `build_fitted_pdf`, `prepared_source`)**, önizleme (`render_preview`, `render_plain_preview`), birleştirme, doğrulama, kayıt |
| `settings_store.py`, `diagnostics.py`, `version.py` | Ayar/profil kalıcılığı, tanılama paketi, tek sürüm kaynağı |
| `page_layout_model.py` | Sayfa Düzeni modeli (taşma eşlemesi, özel sayfa kuralları, ilgililik, sonuç cümlesi); Qt'siz |
| `ui/qt_compat.py` | PySide6 uyum katmanı: `place/put/place_restore`, sabit genişlik sözleşmesi, `destroy()` sabitleme, ince kaydırma çubuğu |
| `ui/window.py`, `ui/shell_build.py` | Pencere/tema/sekme geçişi; kabuk (üst çubuk, sol menü, `QSplitter`, eylem çubuğu, gösterim kipleri) |
| `ui/preview.py`, `ui/preview_canvas.py` | `PreviewPanel` (üretim, gezinme, birleştirme için `preview_page_count`/`preview_variant`), `AppPreviewHost`; `PreviewCanvas` |
| `ui/tabs/{page_layout,number,merge}.py` | Üç sekme (`BaseTab` sözleşmesi); `page_layout` "Sayfaları eşitle" satırını (menü, "yatay kalsın", "dikeye döndür"), `merge` seçim modelini/liste işlemlerini/eşitle onay kutusunu taşır |
| `ui/tabs/merge_drag.py` | `MergeDragMixin`: birleştirme listesi sürüklemesi (bırakma çizgisi, otomatik kaydırma, tutamaktan sürükleme, `reorder_for_drop`, `autoscroll_step`) |
| `ui/config_binding.py`, `ui/context.py` | Ayar bağlama (`_layout_tab()` vb.), sekmeler arası bağlam |
| `ui/pipeline.py`, `ui/workflow.py`, `ui/merge_job.py` | Durum rozetleri (`_fit_active`), işleme ve birleştirme iş akışları, **Yeni iş** (`_new_job`) |
| `ui/batch_dialog.py`, `ui/batch_jobs.py` | Profil seçmeli GUI toplu işlem kuyruğu, risk taraması, iptal ve dosya başına sonuç |
| `ui/widgets.py`, `ui/theme.py` | `FieldRow`, `WrapButtonRow`; renkler, ölçüler, etiket tabloları (`FIT_LABELS`) |
| `ui/document.py`, `ui/dialogs.py`, `ui/shortcuts.py`, `ui/dnd.py` (dosya bırakma), `ui/perf.py` | Belge yaşam döngüsü, diyaloglar, kısayollar, dosya bırakma, ölçüm |
