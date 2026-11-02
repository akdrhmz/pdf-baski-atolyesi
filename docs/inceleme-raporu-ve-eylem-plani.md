# PDF Baskı & Cilt Stüdyosu 2.2.1: İnceleme Raporu ve Eylem Planı

*2 Kasım 2026 (güncellenmiş sürüm) · `app.py` (3.561 satır), `gutter_engine.py` (1.399 satır), testler, plan dosyası, README ve dört ekran görüntüsü incelendi. Bu sürümde ek olarak sürükle-bırak, birleştirme sekmesi, düğme/menü yerleşimi ve cilt payındaki yazı kaybı sorunu kaynak koddan ve çalıştırılan deneylerden değerlendirildi.*

**Kanıt etiketleri:** **Kanıtlı** = bu ortamda çalıştırıp sonucu gördüm. **Kesin** = kodu ve bağımlılık kaynağını okuyarak doğruladım. **Güçlü şüphe** = koddan çıkarım; Windows'ta denenmedi.

## Özet

Motor tarafında iki ciddi bulgu var; ikisi de **sessiz içerik kaybı** üretiyor ve arayüz sorunlarından önce ele alınmalı:

1. **Döndürülmüş sayfalar yanlış işleniyor (kanıtlı).** `process_pdf`, `/Rotate` değeri sıfırdan farklı olan her sayfada içeriği döndürmeden ve alt kısmı keserek yeni sayfaya basıyor. Birleştirme sekmesindeki "90° sola/sağa" düğmeleri tam olarak bu değeri yazıyor, taranmış PDF'lerin çoğunda da zaten var. "Birleştirdim, cilt payı verince yazılar kayboluyor" şikâyetinin en olası kök nedeni bu.
2. **Sabit hedef ebatta taşan içerik kırpılıyor (kesin).** Varsayılan 225×297 mm hedef yalnızca 210 mm genişliğinde sayfalarda tutuyor. Yatay veya daha geniş sayfada sağdaki içerik kesiliyor. Acrobat'ta "yazdır → sığdır → Adobe PDF" bunu düzeltiyordu, çünkü yazdırma hem döndürmeyi uyguluyor hem de sayfayı küçültüyor. Uygulamaya benzer bir **"Cilt payına sığdır"** özelliği eklenebilir; bir prototipini denedim, çalışıyor (Bölüm 1).

Sürükle-bırak büyük olasılıkla Türkçe karakter içeren yollarda sessizce başarısız oluyor (Bölüm 2). Birleştirme sayfası işlevsel ama yalın bir liste; küçük resimli kartlara geçmek hem kullanılabilirliği hem hata olasılığını iyileştirir (Bölüm 3).

Önceki turdaki bulgular (tema/tam ekran bozulması) aşağıda korundu: motor testleri geçti (39 geçti, 1 atlandı), sorun arayüz katmanında. Tema ve tam ekran geçişindeki bozulmanın ana nedeni yavaş çizim değil, **geçiş sırasında üst üste binen üç mekanizma**: CustomTkinter'in kendi pencere gizle/göster hilesi, uygulamanın eklediği ekran görüntüsü maskesi ve sabit süreli zamanlayıcılar.

**Doğrulama notu:** Windows'ta çalıştıramadım. Tema ve sürükle-bırak teşhisleri kod okumasına ve CustomTkinter 5.2.2 ile windnd 1.0.7 kaynağına dayanıyor. PDF motoru bulguları Linux'ta PyMuPDF 1.24.14, 1.26.4 ve 2.0 ile çalıştırıldı; üçünde de sonuç aynı.

## Öncelik özeti

| # | Bulgu | Etki | Kanıt | Emek |
| --- | --- | --- | --- | --- |
| 1 | Döndürülmüş sayfa içeriği kesiliyor ve döndürülmüyor | Basılı çıktıda sessiz veri kaybı | Kanıtlı | 0,5–1 gün |
| 2 | Sabit ebatta taşan içerik kırpılıyor, "sığdır" yok | Yazı kaybı, Acrobat'a mecbur kalma | Kanıtlı | 1–1,5 gün |
| 3 | Sürükle-bırak Türkçe karakterli yolda çöküyor ve hata gizleniyor | Özellik çalışmıyor | Kesin (kod), Windows'ta denenmedi | 2–3 saat |
| 4 | Tema/tam ekran geçişi bozuluyor | Boş/yarım çizili pencere | Kesin | 1–2 gün |
| 5 | Birleştirme sekmesi: önizlemesiz liste, belirsiz düğme davranışları | Hatalı birleştirme riski, yavaş iş akışı | Kesin | 2–3 gün |
| 6 | Pencere boyutu ölçekleme uyumsuzluğu | %125–150'de pencere ekrana sığmaz | Kesin | 2 saat |

## 1. Cilt payında yazı kaybı ve "Sığdır" özelliği

### 1.1 Döndürülmüş sayfa hatası (kanıtlı)

`process_pdf` her sayfayı `target_page.show_pdf_page(lay.content, src_doc, pno)` ile basıyor. Kaynak sayfada `/Rotate` varsa PyMuPDF, içeriği döndürmeden alıp döndürülmüş boyuta (genişlik ve yükseklik yer değiştirmiş) kırpıyor. Deneyde 595×842 pt bir sayfaya iki satır metin yazıp `/Rotate 90` verdim:

| Durum | Kaynakta görünen | `show_pdf_page` çıktısında görünen |
| --- | --- | --- |
| `/Rotate 0` | Üst ve alt metin | Üst ve alt metin (fark yok) |
| `/Rotate 90` | Üst ve alt metin, yatay yerleşim | Yalnız üst metin, **döndürülmemiş**, alt metin yok |
| `/Rotate 180` | Üst ve alt metin | İçerik ters çevrilmemiş |
| `/Rotate 270` | Üst ve alt metin | Yalnız bir kısmı, döndürülmemiş |

Piksel karşılaştırmasında 0° dışındaki her açı büyük fark verdi (yaklaşık 7.000–10.000 piksel, 0° için 0). Üç PyMuPDF sürümünde de aynı. `rotate=±açı` parametresi tek başına düzeltmiyor (90° ve 270°'de fark sürüyor).

**Neden birleştirmeden sonra görünüyor:** `merge_pdfs`, düğmelerle verilen döndürmeyi `page.set_rotation(...)` ile sayfaya yazıyor. "Birleştirdikten sonra aktif ayarları uygula" seçiliyse aynı geçişte, değilse birleşik dosya cilt payı sekmesine açıldığında bu sayfalar yanlış işleniyor. Taranmış veya telefonla çekilmiş belgelerde `/Rotate` zaten yaygın.

**Kırpma taraması da yanıltıyor:** `scan_clipping` döndürülmüş uzayda ölçüyor, `process_pdf` ise döndürmesiz basıyor. Deneyde tarama "sağ 70,8 mm taşıyor" dedi, gerçek çıktıda kaybolan şey alt satırdı ve tarama onu hiç bildirmedi. Yani kullanıcı uyarıyı görüp devam etse de ne kaybedeceğini bilemiyor.

**Test boşluğu:** `test_engine.py` içinde döndürülmüş sayfa için tek test var (`test_preview_handles_rotated_and_mixed_sizes`) ve yalnız önizlemeyi sınıyor, çıktı PDF'ini sınamıyor.

**Düzeltme önerisi:**
1. `process_pdf` içinde bellekteki `src_doc` kopyasında, bağlantılar toplandıktan **sonra** (veya bağlantı dikdörtgenleri de dönüştürülerek) `page.remove_rotation()` çağır. Deneyde tam sayfa için dört açıda da piksel farkı sıfır çıktı.
2. **Açık nokta:** CropBox'ı olan ve döndürülmüş sayfada `remove_rotation` tek başına yetmedi, hızlı denemem net sonuç vermedi. Bu kombinasyon `clip=page.cropbox` ve doğru `rotate` ile ayrıca çözülmeli.
3. Test matrisi ekle: `{0, 90, 180, 270} × {CropBox var/yok} × {fixed/auto}`; çıktıyı render edip kaynağın render'ıyla piksel karşılaştırması yap. Altın görüntü yerine "kaynak ile eşdeğer" kontrolü.
4. `scan_clipping` ve `page_content_bbox` aynı normalleştirilmiş sayfayı kullansın ki tarama ile gerçek çıktı tutarlı olsun.

### 1.2 Sabit hedef ebatta taşma ve "Cilt payına sığdır" (kanıtlı)

`compute_layout` yalnız alt/üst pay "Sığdır" modunda küçültme yapıyor; cilt payı tek başına verildiğinde (`margins.enabled = False` veya mod `expand`) içerik %100 ölçekte kalıyor ve sayfa dışına çıkan kısım kırpılıyor. Kitap düzeninde 15 mm pay verilen A4 (210 mm) dışındaki her geniş sayfada sağ kenar gidiyor.

**Prototip:** `PageBoxSettings`'e `fit_overflow: bool` ekleyip `compute_layout` içinde bu bayrak açıkken mevcut "fit" dalını kullandım (yaklaşık 5 satır). Aynı test setinde:

| Sayfa | Mevcut davranış | `fit_overflow=True` |
| --- | --- | --- |
| A4 dikey | Sorunsuz | Sorunsuz, ölçek %100 |
| A4 yatay (842×595) | Kelimelerin 10'dan 4'ü kalıyor | Hepsi sayfa içinde |
| Letter | Sorunsuz (içerik kenara dayanmıyor) | Sorunsuz |
| Döndürülmüş | Bölüm 1.1'deki hata | Hata sürüyor (önce 1.1 düzeltilmeli) |

Tarama sonucu da "uyarı yok" oldu. Bağlantılar zaten `layout.scale` ile taşındığı için küçültme bağlantıları bozmuyor; sayfa numarası hedef ebada göre konumlandığı için etkilenmiyor.

**Önerilen özellik tasarımı:**

- **Ayar:** Cilt Payı sekmesinde "Sayfa ebadı" alanının altına "İçerik hedef sayfaya sığmazsa:" ve iki seçenekli bir düğme: **Küçült (sığdır)** | **Kırp**. Varsayılan *Küçült*: sessiz kayıp, sessiz küçülmeden kötüdür. Yalnız taşan sayfalar küçülür, normal sayfalar %100 kalır.
- **İsteğe bağlı kutular:** "Tüm sayfalarda aynı oran" (kitapta tutarlı görünüm için en küçük oran herkese uygulanır; ön geçiş gerekir) ve "Yazıcı güvenli kenarı" (0–5 mm).
- **Tarama diyaloğu:** Mevcut "devam / iptal" yerine üç düğme: *Sığdırarak devam et (önerilen)*, *Yine de kırp*, *İptal*.
- **Önizleme:** Küçülen sayfada rozet: "Bu sayfa %88'e küçültülür". Önizleme zaten `compute_layout` kullandığı için ek hesap gerekmiyor.
- **Adlandırma:** README'de alt/üst payda da bir "Sığdır" modu var. Karışmaması için yeni ayarın etiketi "Cilt payına sığdır / taşanı küçült" olsun.
- **Geliştirme fikri:** Sayfa ebadına göre değil, `page_content_bbox` ile ölçülen gerçek içeriğe göre küçültmek. Geniş beyaz kenarlıklı sayfalar gereksiz küçülmez. Acrobat'ın "sığdır"ından daha iyi sonuç verir.
- **Yapılandırma:** `config_to_dict` / `config_from_dict` ve profillere yeni alanlar eklenmeli; eski profillerde alan yoksa varsayılan geçerli olmalı.

## 2. Sürükle-bırak çalışmıyor

Uygulama `windnd.hook_dropfiles(self, func=self._on_drop_files)` kullanıyor. windnd 1.0.7 kaynağını okudum:

- **Dosya adı çözümlemesi (kesin, kodla doğrulandı):** `force_unicode` verilmediği için windnd ANSI `DragQueryFile` çağırıyor ve yolu **Windows kod sayfasında bayt** olarak veriyor (Türkçe Windows'ta cp1254). Uygulama ise bunu `f.decode("utf-8")` ile çözüyor. Yolda `ü ş ğ ı ö ç` varsa `UnicodeDecodeError` oluşuyor. Türkçe Windows'ta masaüstü klasörü **`Masaüstü`** olduğu için masaüstünden sürüklenen her dosya bu duruma düşüyor. Örnek yolu cp1254 ile kodlayıp utf-8 ile çözmeyi denedim: hata veriyor.
- **Hata gizleniyor:** `_on_drop_files` tüm istisnaları yakalayıp günlüğe yazıyor, kullanıcıya hiçbir şey göstermiyor. Belirti: "bırakıyorum, hiçbir şey olmuyor".
- **Yol uzunluğu:** windnd 260 karakterlik tampon kullanıyor; uzun yollar kesilir.
- **Geri çağrı pencere iletisi içinde çalışıyor:** `_append_merge_file` hata olduğunda `messagebox` açıyor. Bu, Explorer'ın bırakma işlemini iletişim kutusu kapanana kadar bloke eder.
- **Yanlış yönlendirme ve geri bildirimsiz:** PDF olmayan dosyalar sessizce atlanıyor. Cilt Payı sekmesinde birden çok PDF bırakılırsa yalnız ilki yükleniyor, gerisi sessizce yok sayılıyor. Bırakma alanı görsel olarak belirtilmiyor (windnd giriş/çıkış olayı vermiyor).
- **Başka olası neden (güçlü şüphe):** Uygulama yönetici olarak çalışıyorsa Windows, normal Explorer'dan bırakmayı engeller (UIPI). `Baslat.bat` bunu yapmıyor ama kısayol "yönetici olarak çalıştır" ise olur. Hakkında penceresine "Yönetici modunda: sürükle-bırak çalışmaz" uyarısı konabilir.

**Düzeltme:**

```python
windnd.hook_dropfiles(self, func=self._on_drop_raw, force_unicode=True)

def _on_drop_raw(self, files):
    paths = [f if isinstance(f, str) else f.decode("mbcs", "replace") for f in files]
    self.after(0, lambda: self._on_drop_files(paths))   # Explorer'ı bloklama
```

Ardından `_on_drop_files` şunları yapmalı: PDF olmayanları sayıp durum çubuğunda bildirmek ("3 PDF eklendi, 1 dosya PDF değil"), tek PDF değil birden çok PDF bırakılmışsa Cilt Payı sekmesinde "Birleştirmeye ekle / yalnız ilkini aç" sorusunu sormak, hata olursa kullanıcıya göstermek.

**İkinci adım (isteğe bağlı):** `tkinterdnd2` ile pencere yerine belirli alanlara bırakma (birleştirme listesi, belge çubuğu) ve üzerine gelince çerçeve vurgusu (`DropEnter/DropLeave`). windnd ile vurgu yapılamaz. CustomTkinter ile çalışır ama kök sınıfa katkı gerektirir, tema/gizle-göster düzeltmesiyle (Aşama 4) birlikte denenmeli.

## 3. Birleştirme sekmesi ve arayüz yerleşimi

### 3.1 Birleştirme listesi

Şu an her dosya bir satır: sıra no, "ad • sayfa • MB", sayfa aralığı kutusu, döndürme rozeti. Sıralama satırı sürükleyerek veya "Yukarı/Aşağı" ile yapılıyor.

Sorunlar (kesin, kodla):
- **Küçük resim yok.** Dosyanın ne olduğu yalnız adından anlaşılıyor; döndürme yalnız "90° sağa" rozetiyle bildirilip görsel olarak gösterilmiyor. Yanlış dosyayı veya yanlış yönü fark etmek için çıktıyı açmak gerekiyor.
- **Döndürme düğmeleri seçim yoksa tüm dosyaları döndürüyor** (`_rotate_selected`). Hiçbir satır seçili değilken "90° sağa" tüm listeyi sessizce çeviriyor. Bölüm 1.1'deki hatayla birleşince bu özellikle riskli.
- **Yinelenen dosya sessizce yok sayılıyor.** Aynı dosya ikinci kez eklenmek istenirse hiçbir mesaj yok.
- **Sürükleme ipucu yok:** Tutamak simgesi, "tut" imleci ve bırakma çizgisi yok; yalnız altta küçük yazı var. Sıralama `<B1-Motion>` ile anlık yer değiştirme yapıyor, uzun satırlarda zıplar.
- **Boş durum sönük:** Liste boşken yalnız küçük bir cümle var. Bırakma alanı görünmüyor, dolayısıyla sürükle-bırak çalışsa bile kullanıcı "buraya bırakılır" diye anlamıyor.
- **Klavye desteği yok:** Del ile kaldırma, Alt+↑/↓ ile taşıma, çoklu seçim, tümünü seç yok.
- **Ağır satırlar:** Her satır 5 CTk widget'ı (her biri bir `Canvas`). 40 dosyada 200 widget; sekme zaten 324 widget'lık pencerenin yükünü artırıyor.
- **Önizleme paneli bu sekmede ilgisiz:** Sağdaki "Canlı önizleme" cilt payı önizlemesi; birleştirme sekmesinde seçili belgeyi göstermiyor veya anlamsız kalıyor.

**Önerilen tasarım (kart görünümü):**

```
┌─ Birleştirme ───────────────────────────────────────────────────┐
│ [+ Dosya ekle]  [Ada göre sırala ▾]            [Listeyi temizle] │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ ⠿ 1  ┌────┐ rapor_bolum1.pdf              Sayfalar: [Tümü ]│  │
│ │      │ ▒▒ │ 24 sayfa · 3,1 MB              ⟲  ⟳  ✕        │  │
│ │      └────┘ 210×297 mm · dikey            (döndürme küçük  │  │
│ │                                             resimde görünür)│  │
│ │ ───────────────── bırakma çizgisi ────────────────────────│  │
│ │ ⠿ 2  ┌────┐ ek_tablolar.pdf               Sayfalar: [3-10]│  │
│ └───────────────────────────────────────────────────────────┘  │
│  Boşsa: kesikli çerçeve "PDF'leri buraya bırakın veya Dosya ekle"│
│ Toplam: 2 dosya · 31 sayfa            ☐ Yer imi  ☐ Ayarları uygula│
└──────────────────────────────────────────────────────────────────┘
```

- **Küçük resim:** İlk sayfa, arka planda iş parçacığında `get_pixmap` ile 56×72 px, tembel ve önbellekli. Döndürme küçük resme uygulanır.
- **Satır içi eylemler:** Döndür, kaldır, yukarı/aşağı her satırın içinde; üstteki araç çubuğundaki seçime bağlı düğme kalabalığı kalkar. "Seçim yokken hepsini döndür" davranışı kalkar ("Tümünü döndür" ayrı ve açık bir düğme olur).
- **Sürükleme:** Sol kenarda tutamak, imleç değişimi, bırakma çizgisi gösterimi; satır yalnız bırakıldığında yer değiştirir.
- **Uyarılar:** Yinelenen dosya ve bozuk/şifreli dosya için satırda rozet; döndürülmüş veya karışık ebatlı dosya için "ebat uyumsuz" rozeti (Bölüm 1.2 ile bağlantılı).
- **Sayfa aralığı:** Metin kutusu kalsın; yanına "…" düğmesiyle sayfa küçük resimleri açılıp işaretlenebilsin (Aşama 7'deki sayfa ayıklama sekmesiyle ortak bileşen).
- **Klavye:** Del, Alt+↑/↓, Ctrl+A, çoklu seçim.
- **Performans:** Kart yerine tek bir `Canvas` üzerinde çizmek (sanal liste) ağır widget sorununu da çözer; ancak karmaşıklığı artırdığı için önce widget sayısını azaltan hafif bir satır tasarımıyla başlanmalı.

### 3.2 Genel yerleşim (kod okumasından)

| Alan | Bulgu | Öneri |
| --- | --- | --- |
| **Belge çubuğu, ikinci satır** | Birim, Profil menüsü, Yükle, Kaydet, Sil aynı satırda; "Sil" "Kaydet"in hemen yanında, 26 px yüksekliğinde. Belge kimliğiyle ilgisi olmayan genel ayarlar belge çubuğuna karışmış. Sil için onay var (iyi), ama yanlış tıklama riski yüksek. | Profil ve birimi üst çubuğa veya ayrı bir "Ayarlar" menüsüne taşı. Yükle/Kaydet/Sil tek bir "Profil ▾" açılır menüsü olsun, Sil ayrı satırda ve kırmızı. |
| **Üst çubuk** | Yalnız "Hakkında" sağda; tema anahtarı başka yerde. | Tema, hakkında ve yardım tek "⋯" menüsünde veya sağ üstte simge düğmeleri. |
| **Alt eylem çubuğu** | Dört düğme eşit genişlikte (`weight=1`): "Klasörde göster", "PDF'i aç", "İptal", asıl düğme "PDF'i işle ve kaydet". Önem sırası görsel olarak eşit. Sonuç düğmeleri işlem bitmeden pasif ama yer kaplıyor. | Ana düğme iki kat geniş. "Klasörde göster/PDF'i aç" yalnız işlem bitince, durum satırının yanında görünsün. "İptal" yalnız işlem sürerken görünsün. |
| **Ana düğme etiketi** | Birleştirme sekmesinde de "PDF'i işle ve kaydet" yazıyor; yalnız başlık metni değişiyor. | Sekmeye göre "Birleştir ve kaydet" / "PDF'i işle ve kaydet". |
| **Çıktı seçenekleri** | "Optimize et" ve "Açıklamaları göm" kutuları işlem durumu kartında, sekmelerden uzakta. | "Çıktı seçenekleri" başlığı altında ayrı bir katlanır bölüm. |
| **Birleştirme araç çubuğu** | Yedi düğme aynı ağırlıkta; yıkıcı olanlar ("Kaldır", "Temizle") "Aşağı"nın hemen yanında. | Bölüm 3.1'deki gruplama: ekle | sırala/döndür | temizle (sağda, ayrı). |
| **Önizleme paneli** | 380 px sabit, birleştirme sekmesinde anlamsız. | Geniş ekranda genişlesin, birleştirme sekmesinde gizlensin veya birleştirme sonucu önizlemesine dönüşsün. |
| **Kısayollar** | Yalnız Ctrl+O, Ctrl+S, Enter, Esc. Ctrl+S "işle" anlamına geliyor, çoğu kullanıcı "kaydet" bekler. | Ctrl+S yerine Ctrl+Enter; Ctrl+S profili kaydetsin veya kısayol hiç atanmasın. |
| **Yardımcı metinler** | Sonuç/uyarı metinleri kart içinde küçük punto, `wraplength` zinciriyle yeniden akıtılıyor (performans maliyeti de var). | Uyarıları şeritle (renkli satır) ve en önemli iki bilgiyi tek satırda ver. |

## 4. Ekran görüntülerinde ne görünüyor

**Görüntü 1 ve 2 (açık ve koyu tema, tamamen boş pencere).** Başlık çubuğu çizilmiş, içerik hiç yok. Üstteki başlık, dosya çubuğu ve alt eylem çubuğu da boş. Yani yalnız `_hold_workspace` ile gizlenen sekme alanı değil, tüm pencere çizilmemiş. Bu, `_hold_workspace` mantığıyla açıklanamaz; pencerenin kendisinin gizlenip yeniden gösterildiği bir ana işaret ediyor (Bölüm 5.1).

**Görüntü 3.** Sekme çubuğu iki kez görünüyor: biri gerçek yerinde, biri sekme içeriğinin içinde. Cilt Payı metinleri sağda kesiliyor, siyah bloklar var, sağdaki önizleme kartları boş. Bu, eski yerleşimin pikselleriyle yeni yerleşimin üst üste çizilmiş hali. Sağ altta "Ekran Alıntısı Aracı" bildirimi var, yani kare bir geçişin ortasından yakalanmış olabilir. Ama aynı görüntüyü kullanıcı kendi ekranında da görüyorsa kök neden aynı.

**Görüntü 4.** Parçalı ve yinelenen arayüz: "Numaraları" başlığı yanlış yerde, düğme grupları iki kez, çerçeveler birbirine geçmiş. Ayrıca pencerenin arkasındaki terminal metni sol kenarda görünüyor. Bu da ana pencerenin o anda tam opak çizilmediğini gösteriyor.

## 5. Kök nedenler (tema ve tam ekran)

### 5.1 CustomTkinter her tema değişiminde pencereyi gizleyip gösteriyor (kesin)

CTk kaynağında `_windows_set_titlebar_color` şunu yapıyor: pencere durumunu kaydeder, `withdraw()` çağırır, başlık çubuğu rengini DWM ile değiştirir, sonra `deiconify()` ile (pencere büyütülmüşse `state("zoomed")` ile) geri getirir. Bu, her `ctk.set_appearance_mode()` çağrısında çalışır. Yani tema düğmesine basıldığında pencere bir an ekrandan kalkıyor ve geri geliyor. Görüntü 1 ve 2 tam olarak bu aralığın görüntüsü.

`_on_theme_changed` içinde maske bu çağrıdan **önce** alınıp `-topmost` bir `Toplevel` olarak gösteriliyor. Ana pencere gizlenip yeniden gösterilirken 324 CTk widget'ı (her biri bir `Canvas`) yeniden çiziliyor. Ölçüm 430 ms tema ve 290 ms ilk çizim diyor, toplam yaklaşık 720 ms. Maske ise `after(90, ...)` ile düşüyor. Yani maske, çizim bitmeden yaklaşık 600 ms önce kalkıyor.

### 5.2 Sabit süreli zamanlayıcılar yarış durumu üretiyor (kesin)

`_release_workspace` 260 ms, `_repaint_window` 60 ms, maske 90 ms sonra tetikleniyor. Hiçbiri "çizim bitti" olayına bağlı değil. Geliştirme makinesinde tutuyor, yavaş bir dizüstünde veya %150 ölçekte tutmuyor. Bu yüzden sorun "bazen" oluyor.

### 5.3 Ekran görüntüsü maskesi kırılgan (güçlü şüphe)

`_freeze_frame` pencereyi geçici olarak `-topmost` yapıp `ImageGrab` ile ekrandan görüntü alıyor. Sorunlar: odak çalabilir ve titreşim yapar, üstte başka pencere varsa onu da yakalar, `winfo_rootx` ile `ImageGrab` koordinatları çok monitörlü veya karışık ölçekli kurulumda kayabilir, ayrıca `overrideredirect` bir pencere görev değiştirmede (Alt+Tab, Win+Shift+S) davranışı öngörülemez. Plan dosyasındaki "bilinen sınırlar" bölümü bunların bir kısmını zaten kabul ediyor.

### 5.4 Tam ekran geçişinde her şey aynı anda yeniden yerleşiyor (kesin)

Dört sekmenin hepsi `grid` ile aynı hücreye konuyor ve `tkraise()` ile öne alınıyor. Gizli üç sekme de ekranda değilmiş gibi ama pencere boyutu değişince yerleşim ve `<Configure>` işlemine katılıyor. Üstüne dört `CTkScrollableFrame` (her biri kendi canvas'ı ve iç çerçevesiyle), her etiket için `_bind_wraplength` ile `after(80)` zinciri var. Ölçüm: büyütmede yaklaşık 8.900 Tcl çağrısı. 100 widget'lık minimal bir CTk penceresi bile 500 ms harcıyorsa, 324 widget'lık bir pencerenin 800–900 ms'ye çıkması şaşırtıcı değil.

### 5.5 `_on_client_configure` her `Configure` olayında `state()` soruyor (zayıf şüphe)

Pencere büyütülmüş durumdayken (`zoomed`) her boyut değişikliği bu yoldan geçiyor. %15 eşiği çoğu durumu eliyor ama sürükleyerek yeniden boyutlandırmada da tetiklenebilir. Düzeltmede bu yol tamamen kalkacağı için ayrıca ele alınmıyor.

## 6. Ek bulgular

### 6.1 Pencere boyutu ve ölçekleme uyumsuz (kesin, kodla doğrulandı)

`__init__` sonunda `winfo_screenheight()` ile ekran yüksekliği okunup `geometry` ve `minsize` buna göre ayarlanıyor. CTk `geometry()` değerlerini ölçekleme katsayısıyla çarpıyor, `winfo_screenheight()` ise fiziksel piksel veriyor. 1920×1080 ekranda %150 ölçekle: `min(900, 1080-140) = 900` mantıksal piksel, bu 1350 fiziksel piksel eder. Pencere ekrandan yüksek. Minimum yükseklik de `700 × 1,5 = 1050` oluyor ve görev çubuğuyla birlikte sığmıyor. Plan dosyası %125–150 ölçekte "son görsel onay kullanıcıdan" diyor ama bu hata onay beklemeden kodda görülebiliyor. Ayrıca CTk 1000 ms sonra `_set_scaled_min_max` ile minimum boyutu yeniden yazıyor; uygulamanın `minsize` çağrısı bu gecikmeyle çakışabilir.

### 6.2 `__init__` içinde geç tanımlanan öznitelikler (küçük risk)

`_transition_mask`, `_repaint_job`, `_workspace_job`, `_guard_client` arayüz kurulduktan sonra tanımlanıyor, ama `destroy()` bunlara başvuruyor. Kurucu bu arada hata verirse `destroy` ikinci bir `AttributeError` fırlatır ve asıl hata gizlenir. Çözüm tek satır: hepsini `super().__init__()` hemen sonrasına taşımak.

### 6.3 Mimari borç

- `app.py` tek sınıfta 3.561 satır. Sekmeler, önizleme, birleştirme, geçiş koruması ve iletişim kutuları tek `ModernGutterApp` içinde. Test yazmayı ve hata ayıklamayı zorlaştırıyor.
- 324 `ctk.CTk*` çağrısının 115'i `CTkFont`, 71'i `CTkLabel`. Statik metin için `CTkLabel` gereksiz ağır (her biri canvas + etiket).
- Plan dosyası "Açık işler" bölümünde `test_full_process_pipeline_from_ui` testinin toplu koşuda zaman aşımına düştüğünü yazıyor. Bu da aynı kök nedene bağlı olabilir: arayüz iş parçacığı tıkalı.
- GUI testleri (`test_gui_headless.py`, 23 test) tema ve büyütme geçişinin **sonucunu** sınıyor, ama pencerenin gizlenip gösterildiğini, maskenin zamanlamasını veya çizim süresini ölçmüyor. Bu yüzden testler yeşil, kullanıcı ekranı bozuk.
- **Motor testleri döndürülmüş ve karışık ebatlı çıktıyı doğrulamıyor** (Bölüm 1.1). Yeşil test takımı bu veri kaybını yakalamadı.

## 7. Düzeltme seçenekleri (tema ve tam ekran)

| Seçenek | Ne yapar | Artı | Eksi |
| --- | --- | --- | --- |
| **A. Kök nedeni gider** | `_windows_set_titlebar_color` alt sınıfta ezilir: `withdraw/deiconify` yerine DWM özniteliği ayarlanır, ardından `SetWindowPos(SWP_FRAMECHANGED)` ile çerçeve yenilenir. Maske, `_hold_workspace`, `_repaint_window` ve zamanlayıcılar silinir. | Boş pencere anı ortadan kalkar. Yaklaşık 250 satır kod gider. | Başlık çubuğu rengi bazı Windows sürümlerinde bir sonraki yeniden çizime kadar eski kalabilir; Windows 10 ve 11'de denenmeli. |
| **B. Widget diyeti** | Sekmeleri tembel kur, gizli sekmeleri `grid_remove` ile yerleşimden çıkar. Statik etiketleri `tk.Label`'a çevir ve temayı tek bir kayıt defteriyle elle uygula. | Tema ve büyütme süresi ciddi düşer. Mevcut CTk görünümü korunur. | Orta emek. Kazanç ölçülmeden vaat edilemez (plan dosyasındaki yazı tipi önbelleği denemesi sıfır kazanç verdi). |
| **C. Çizimi dondur** | Geçiş boyunca `WM_SETREDRAW` kapatılır, sonra açılıp `RDW_UPDATENOW` ile tek seferde çizilir. | Küçük kod. | Tk kendi çizim kuyruğunu yönettiği için garanti yok; deneme gerekir. |
| **D. Arayüz çatısını değiştir** | PySide6 veya benzeri. | Kalıcı çözüm, doğal ölçekleme, sanal liste ve sürükle-bırak desteği yerleşik. | Büyük yeniden yazım. Şimdilik önermiyorum. |

**Önerim: A, ardından B. C yalnızca A yetmezse denenir. D bu aşamada gereksiz.** Gerekçe: A, boş pencere belirtisinin kaynağını kaldırıyor ve kodu azaltıyor. B yavaşlığı gideriyor. Maske yaklaşımına geri dönülmemeli; çizim hızlıysa maskeye ihtiyaç kalmaz, yavaşsa maske zaten yetmiyor. Birleştirme listesi ve önizleme küçük resimleri gibi yeni arayüz işleri artırıldıkça D'nin değeri de artıyor; Aşama 4 sonrasında yeniden değerlendirilmeli.

## 8. Eylem planı

### Aşama 0: Veri kaybını kapat (0,5–1 gün, **en önce**)

1. `process_pdf` içinde `/Rotate` sayfalarını normalleştir (`remove_rotation`), bağlantı toplama sırasını ve dikdörtgen dönüşümünü doğrula (Bölüm 1.1).
2. CropBox + döndürme kombinasyonunu `clip` ve `rotate` ile çöz; çözülene kadar bu kombinasyonda tarama "güvenilmez" uyarısı versin.
3. Test matrisi: `{0, 90, 180, 270} × {CropBox var/yok} × {fixed/auto}`; çıktıyı render edip kaynakla piksel karşılaştır. `scan_clipping` ile gerçek çıktının tutarlı olduğunu da sına.
4. Birleştirme "tümünü döndür" davranışını hemen düzelt: seçim yokken hiçbir şey yapmasın veya açık onay istesin.

### Aşama 1: Sürükle-bırak ve ölçüm (yarım gün)

1. `force_unicode=True`, `after(0, ...)` ile geciktirilmiş işleme, kullanıcıya görünen hata ve sayım mesajı (Bölüm 2). Test: `Masaüstü` gibi Türkçe karakterli yoldan bırakma.
2. Yönetici modunda çalışma uyarısı (isteğe bağlı).
3. `APP_PERF=1` ortam değişkeniyle geçiş sürelerini günlüğe yazan küçük bir ölçüm kodu ekle: tema değişimi, büyütme, geri küçültme, `withdraw/deiconify` çağrı sayısı.
4. Kendi makinende 100, 125 ve 150 ölçekte aynı üç eylemi dene, günlüğü gönder. Böylece 5.1 ve 5.2 "güçlü şüphe"den "kanıtlı"ya geçer.
5. `__init__` öznitelik sırasını düzelt (6.2). Risksiz.

### Aşama 2: "Cilt payına sığdır" özelliği (1–1,5 gün)

1. `PageBoxSettings`'e `overflow_mode` (`"shrink"` | `"clip"`), `uniform_scale`, `safe_edge_mm` ekle; `compute_layout`, `config_to_dict/from_dict`, `validate_config` güncelle. Eski profiller varsayılanla yüklensin.
2. Arayüz: Cilt Payı sekmesinde ayar düğmesi, tarama diyaloğunda üç düğme, önizlemede ölçek rozeti (Bölüm 1.2).
3. Testler: yatay A4, Letter, karışık ebat; çıktıda hiçbir kelimenin sayfa dışına taşmadığını, bağlantıların ölçekle taşındığını, normal sayfaların %100 kaldığını doğrula. Altın görüntü ekle.
4. README ve profil önerilerine (Tez, Spiral, Sıcak tutkal, Kitapçık) varsayılan olarak "Küçült" ekle.

### Aşama 3: Tema ve tam ekran geçişini kökten düzelt (1–2 gün)

1. `CTk` alt sınıfı: `_windows_set_titlebar_color` ezilir, pencere gizlenmeden başlık rengi değişir.
2. `_freeze_frame`, `_drop_transition_mask`, `_hold_workspace`, `_release_workspace`, `_schedule_repaint`, `_repaint_window`, `_on_client_configure` ve ilgili test beklentileri silinir.
3. Pencere boyutu: `geometry` ve `minsize` mantıksal pikselle hesaplanır (`winfo_screenwidth() / ölçek`). Küçük ekranda içerik zaten kaydırılabilir olduğundan minimum 1060×700 yerine 900×600'e inmek yeterli.
4. `<Configure>` yoğunluğunu azalt: `_bind_wraplength` içindeki güncellemeler tek bir `after_idle` ile toplanır, sürükleme sırasında değil bırakınca uygulanır.

### Aşama 4: Birleştirme sekmesi ve yerleşim (2–3 gün)

1. Kart satırları: küçük resim (arka plan iş parçacığı, önbellekli), tutamak, satır içi döndür/kaldır/taşı, rozetler (Bölüm 3.1).
2. Boş durum bırakma alanı ve (isteğe bağlı) `tkinterdnd2` ile bırakma vurgusu.
3. Klavye: Del, Alt+↑/↓, Ctrl+A. Yinelenen/bozuk dosya için satır uyarısı.
4. Yerleşim: eylem çubuğu hiyerarşisi (ana düğme geniş, sonuç düğmeleri yalnız işlem bitince), ana düğme etiketi sekmeye göre, profil/birim kontrollerinin belge çubuğundan taşınması, Ctrl+S anlamının düzeltilmesi (Bölüm 3.2).
5. Önizleme paneli: birleştirme sekmesinde gizle veya sonuç önizlemesine çevir; genişliği ekrana göre ayarla.

### Aşama 5: Widget diyeti (2–3 gün)

1. Sekmeler tembel kurulur; ilk açılışta yalnız Cilt Payı yapılır. Diğerleri ilk tıklamada kurulur, aktif olmayan sekme `grid_remove` ile yerleşimden çıkarılır (`tkraise` bırakılır).
2. Statik başlık ve açıklama etiketleri (71 `CTkLabel`'ın çoğu) `tk.Label` olur; renk güncellemesi tek bir `ThemeRegistry.apply(mode)` içinde yapılır.
3. Her adımdan önce ve sonra Aşama 1'deki ölçüm çalıştırılır. Bir adım ölçülebilir kazanç vermiyorsa geri alınır.

### Aşama 6: Test ve kalıcılık (1 gün)

1. GUI testine süre bütçesi ekle: tema değişimi ve büyütme için üst süre (ör. 1,5 sn) aşılırsa test kırmızı olsun.
2. `withdraw` çağrı sayacı testi: tema değişiminde pencere hiç gizlenmemeli.
3. `test_full_process_pipeline_from_ui` bekleme mantığını olay tabanlı hale getir (sabit 20 sn yerine "iş bitti" olayını bekle).
4. Windows'ta %100/%125/%150 kontrol listesi README'ye eklenir: tema, büyütme, geri küçültme, sekme değiştirme, ikinci monitör, **Türkçe karakterli yoldan sürükle-bırak, döndürülmüş dosya birleştirip cilt payı verme**.

### Aşama 7: Planın kalan işleri (geçişten bağımsız)

Plan dosyasındaki Tur 2 kalanları değişmedi: bölüm bazlı numaralandırma, filigran, sayfa ayıklama/döndürme/bölme sekmesi, toplu işlem. Birleştirme sekmesindeki "sayfa aralığı …" seçicisi ile sayfa ayıklama sekmesi **aynı küçük resim ızgarası bileşenini** paylaşmalı; birini yazınca diğeri hazır olur. Ayrıca `app.py` bölünmeli: `ui/tabs/`, `ui/preview.py`, `ui/dialogs.py` ve çekirdek pencere sınıfı. Yeni özellikler eklenmeden önce bölünmesi, her yeni sekmenin tembel kurulum ve tema kaydıyla uyumlu yazılmasını sağlar.

## 9. Geliştirilebilecek yönler (öncelik sırasıyla)

Bu bölüm plan dosyasındaki listeye ek, onunla çakışmayan öneriler.

1. **Önizleme paneli genişliği.** Panel 380 px'e sabitlenmiş. Geniş ekranda büyütülebilir olmalı; küçük ekranda panel katlanabilir olmalı. Bu aynı zamanda 1060 px minimum genişliği düşürmeye izin verir.
2. **Hata geri bildirimi.** Günlük var ama kullanıcı hata ayrıntısını kopyalayıp bana veya size gönderebilsin diye "Tanılama paketi" düğmesi (günlük + ayar + sürüm + ölçek) faydalı olur. Yukarıdaki ölçüm günlüğüyle aynı altyapı.
3. **Önizleme belleği.** `_preview_history` son 40 `PhotoImage`'ı tutuyor. Titremeyi önlemek için bilinçli, ama büyük sayfalarda bellek tüketir. 6–8 görüntü yeterli olmalı.
4. **İnç birimi.** Plan inç desteğini listeliyor, arayüzde kapalı (`DISPLAY_UNITS = ("mm", "cm", "pt")`). Ya açılmalı ya da plandan çıkarılmalı; ikisi de tutarsız.
5. **Paketleme.** `build_exe.bat` testler geçmese de devam etme seçeneği sunuyor. Sürüm dağıtımında test başarısızken derlemeyi engellemek daha güvenli.
6. **İşlem sonrası doğrulama genişletmesi.** `verify_output` sayfa sayısı, ebat ve metni karşılaştırıyor; kaynak ile çıktının **render karşılaştırması** (düşük çözünürlükte, içerik kaybı yok mu) eklenirse Bölüm 1.1 gibi hatalar kullanıcıya ulaşmadan yakalanır.

## 10. Önerilen sıra

Önce Aşama 0: bu, basılı çıktıda sessiz veri kaybı olduğu için diğer her şeyden önce gelir ve küçük bir değişiklik. Ardından Aşama 1 (sürükle-bırak düzeltmesi, ölçüm sürümü) ve Aşama 2 ("Cilt payına sığdır"). Tema geçişi düzeltmesi (Aşama 3) ölçüm sonuçlarına göre; birleştirme sekmesi yeniden tasarımı (Aşama 4) Aşama 3'ten sonra, çünkü yeni kart satırları tema kaydıyla uyumlu yazılmalı.

**Senden gereken:**
1. Aşama 1'deki ölçüm sürümünü kendi makinende %100/%125/%150'de çalıştırıp günlüğü paylaşmak.
2. Cilt payı sorunu yaşadığın birleşik PDF'in (veya benzerinin) `/Rotate` içerip içermediğini doğrulamam için küçük bir örnek paylaşmak; paylaşamazsan Aşama 0'daki testlerle zaten yakalanacak.
3. "Cilt payına sığdır" varsayılanının **Küçült** olması konusunda onay (öneri bu, eski davranış "Kırp" olarak seçilebilir kalır).

---

## 11. Uygulama sonucu — sürüm 2.2.2 (2 Kasım 2026)

Bu raporun bulguları uygulandı. Aşağıdaki tablo, her maddenin **gerçek sonucunu** ve
doğrulama yöntemini gösterir. Tüm testler: `python -m pytest -q` → **88 geçti, 0 düştü**.

| # | Bulgu | Durum | Kanıt |
| --- | --- | --- | --- |
| 1 | Döndürülmüş sayfa içeriği kesiliyor | **Düzeltildi** | 4 açı × CropBox var/yok = 16/16 piksel piksel aynı; 4 köşe etiketi korunuyor |
| 2 | Sabit ebatta taşan içerik kırpılıyor | **Düzeltildi (opsiyonel)** | `overflow_mode="shrink"`: 10/10 kelime korunuyor, sayfa 225×297 kalıyor |
| 3 | Sürükle-bırak Türkçe yolda çöküyor | **Düzeltildi** | `force_unicode=True` + `utf-8`/`mbcs` yedeği; bayt çözümü test edildi |
| 4 | Tema geçişinde pencere boşalıyor | **Düzeltildi (kök neden)** | `_windows_set_titlebar_color` eklendi: `withdraw/deiconify` yok; 400 ms'de dolu arayüz |
| 5 | Birleştirme sekmesi belirsiz | **Kısmen** | Tutamak, "Sayfa:" etiketi, seçili PDF önizlemesi, Del/Alt+↑↓, ayrı "Tümünü döndür" |
| 6 | Pencere boyutu ölçek uyumsuz | **Düzeltildi** | `geometry/minsize` mantıksal pikselle hesaplanıyor |

### 11.1 Uygulama ayrıntıları

- **Döndürme:** `gutter_engine.normalize_page_rotations()`. CropBox ∩ MediaBox, xref ile
  MediaBox'a taşınır ve içerik `cm` ile kaydırılır; sonra `page.remove_rotation()`.
  Yalnızca bellekteki kopya değişir. `process_pdf` ve `render_preview` bunu kullanır.
  Bağlantı hedefleri (`to`) normalize edilmeden önce toplanır.
- **Sığdırma:** `PageBoxSettings.overflow_mode` (`clip`/`shrink`) ve `safe_edge_mm`.
  En-boy oranı her zaman korunur (`uniform_scale` uygulanmadı, orantısız küçültme yok).
  Kırpma riski diyaloğu üç seçenek sunar: **Sayfaya sığdır (önerilen) / Kırp ve devam et / İptal**.
- **Sürükle-bırak:** `windnd.hook_dropfiles(..., force_unicode=True)`; iş `after(0)` ile ana
  döngüye aktarılır; PDF dışı öğe ve çoklu dosya durumu durum çubuğunda bildirilir.
- **Tema:** `StudioWindow(ctk.CTk)` alt sınıfı; yalnızca DWM özniteliği (19/20) güncellenir.
  Maske, ekran görüntüsü, `_hold_workspace`, `_schedule_repaint` ve ilgili ~120 satır silindi.
- **Arayüz:** birime duyarlı pay ön ayarları (`+10` mm / `+1` cm / `+28` pt), `Ctrl+Enter`
  ile işle (Ctrl+S kaldırıldı), birleştirmede seçili PDF canlı önizlemede.
- **Bakım:** `build_exe.bat` test geçmezse derlemeyi durdurur; GUI testlerinde sabit
  zaman aşımı yerine olay tabanlı bekleme (60 sn üst sınır).

### 11.2 Raporun düzeltilen noktaları

- Kurulu CustomTkinter **6.0.0** (rapor 5.2.2 diyordu); hatalı koşul aynı yerde duruyor.
- "Maske çizimden ~600 ms önce kalkıyor" **yanlış**: maske kaldırma işi, bloklayan
  `update_idletasks()` bittikten sonra planlanıyordu.
- `app.py` 3.192, `gutter_engine.py` 1.203 satır (rapor 3.561 / 1.399 diyordu); farklı
  kopyaya bakılmış.
- `SetWindowPos(SWP_FRAMECHANGED)` gerekmedi; DWM özniteliği tek başına yeterli.

### 11.3 Bildirilen çökme: sürükle-bırakta uygulama kapanması (2.2.2 sonrası)

Kullanıcı bildirimi: PDF sürükleyip bırakınca uygulama kapanıyor.

**Neden (kod okuması, güçlü şüphe):** windnd geri çağrısı Windows pencere yordamı
(WndProc) içinden çalışıyor. Önceki kod burada `self.after(0, ...)` çağırıyordu;
Tcl'i pencere yordamı içinden yeniden çağırmak süreci sessizce sonlandırabilir.

**Yapılan:**
- Geri çağrı artık yalnızca `queue.Queue`'ya yazıyor; Tk'ye hiç dokunmuyor.
  İş, mevcut `_drain_ui_queue` döngüsünde ana iş parçacığında çalışıyor.
- `faulthandler` günlük dosyasına etkinleştirildi; çökme yinelerse yığın izi
  `studio.log` içine düşecek.
- Test: `test_drop_callback_only_queues_work`.

**Durum:** Gerçek fare ile sürükleme bu makinede denenemedi; kullanıcı makinesinde
teyit edilmeli.

### 11.4 Tema ve pencere geçişi performansı (ölçüldü)

| İşlem | Süre (ort.) | Not |
| --- | --- | --- |
| Tema değişimi (tüm sekmeler kurulu) | ~250 ms | 281 CTk widget'ı yeniden çiziliyor |
| Tam ekran ↔ normal | ~25 ms | Sorun görünmüyor |

Profil: sürenin **%80'i Tk canvas çağrıları**; CTk her düğme için yuvarlatılmış
dikdörtgeni Python'da yeniden çiziyor (`draw_engine`). Tek tek renk atamakla
kısalacak bir yol yok; güvenli kazanç widget sayısını azaltmaktan geçiyor:

1. Sekmeleri tembel kur, gizli sekmeleri `grid_remove` ile yerleşimden çıkar.
2. 71 statik `CTkLabel`'ı `tk.Label`'a çevir; tema güncellemesini tek bir
   kayıt defterinden yürüt.

Bu iki adım yapılmadan tema geçişi ~250 ms'nin altına inmez. Pencere büyütme
zaten hızlı; kullanıcıya "takılıyor" gibi gelen şey tema geçişi.

### 11.5 Açık kalanlar

1. **Gerçek fare ile sürükle-bırak** ve **%125/%150 ölçek** bu makinede denenemedi;
   README'deki kontrol listesi kullanıcı makinesinde çalıştırılmalı.
2. **Ctrl+A çoklu seçim** yapılmadı: liste modeli tek seçim. Del ve Alt+↑/↓ var.
3. **`safe_edge_mm`** modelde var, arayüz alanı yok (varsayılan 0).
4. **Kart/küçük resim satırları** ve **widget diyeti (Aşama 5)** yapılmadı.
5. Üç seçenekli diyalog yalnızca `_switch_to_shrink()` düzeyinde test edildi;
   tıklama akışı elle doğrulanmalı.
