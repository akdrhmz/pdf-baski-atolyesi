# Değişiklik Günlüğü (Changelog)

Bu dosyada **PDF Baskı Atölyesi** sürümlerindeki önemli yenilikler ve düzeltmeler özetlenir.

---

## [2.11.0] — 2026-11-25

### Yenilikler
* **Doğrudan Yazdırma (`Yazdır…` / `Ctrl+P`):** Üretilen çıktı veya kaynak PDF'i harici okuyucu kaynaklı ölçekleme/kenar kayması yaşamadan, yüksek çözünürlüklü ve sayfaya tam ortalı olarak doğrudan sistem yazıcısına gönderme özelliği eklendi.
* **Parola Korumalı PDF Açma & Düzenleme:** Şifreli PDF seçildiğinde parola sorarak oturum içinde açma ve *Güvenlik & Meta* aracında kaynak PDF parolası (`source_password`) alanı eklendi.
* **Genişletilmiş `studio_cli.py` ve Kalıcı Araç Ayarları:** Komut satırı aracına kitapçık/N-up baskı montajı (`--impose`), filigran/Bates (`--watermark`, `--bates-prefix`), sayfa ayıklama/bölme (`--pages`, `--split`) ve parola/görsel sıkıştırma (`--compress-dpi`, `--user-password`) modları eklendi; `4. Baskı ve Araçlar` sekmesi ayarları oturumlar arasında kalıcı hale getirildi.
* **Tam İngilizce Dil Desteği (`i18n`):** `4. Baskı ve Araçlar` sekmesi, canlı önizleme yaprak etiketleri ve yazdırma/parola pencereleri eksiksiz İngilizce çeviri kapsamına alındı.

### Düzeltmeler
* **Bates Sayfa Aralığı & Önizleme Tutarlılığı:** Sayfa aralığı verildiğinde canlı önizlemedeki Bates sayacı ile kaydedilen PDF çıktısı eşitlendi; gerçek sayfa boyutları (A3, yatay, taşma paylı) ve gömülü açıklamalar (`bake`) önizlemeye yansıtıldı.
* **Kayıt Diyaloğu, Thread Havuzu & Paketleme:** Kaydet diyaloğunda üzerine yazma seçildiğinde fazladan `(2).pdf` üretilmesi düzeltildi; kapanışta `ToolsTab` iş parçacığı havuzunun kapatılması, arka plan `QTimer` thread güvenliği, Wayland `desktopFileName` eşleşmesi ve `.deb`/`.rpm` kurulum sonrası ikon/menü önbellek betikleri eklendi.

---

## [2.10.3] — 2026-11-19

### Yenilikler
* **Yeni Marka ve İkon:** Uygulama adı **PDF Baskı Atölyesi** olarak güncellendi; 512×512 PNG ve çoklu boyutlu ICO simgesi eklendi.
* **Entegre `4. Baskı ve Araçlar` Sekmesi:** Sayfa düzenleme/bölme, Filigran & Bates, Baskı Montajı (Kitapçık, 2-up, 4-up) ve Güvenlik & Meta Veri araçları ana pencereye ve ana canlı önizleme paneline (`PreviewPanel`) bağlandı.
* **Kitapçık & N-Up Geliştirmeleri:** Forma boyutu (`signature_size`), sayfalar arası kesim/katlama çizgisi, sağdan-sola (RTL) dizilim, ön/arka yüz ve yaprak bilgisi eklendi.
* **Filigran, Bates & Güvenlik:** Filigran rengi, sayfa aralığı filtresi, 5 farklı Bates konumu, AES-256 parola koruma/izinleri, meta veri düzenleme/temizleme ve DPI bazlı görsel sıkıştırma eklendi.
* **Sayfa Numaralandırma:** Üst kenar (`top`) konum desteği ve yazı rengi seçici (`QColorDialog`) eklendi.
* **Profil Paylaşımı & Görsel Desteği:** Ayarlar'a JSON profil dışa/içe aktarma eklendi; Birleştirme listesine `.png`, `.jpg`, `.webp`, `.bmp`, `.tif` görselleri doğrudan eklenebilir hale getirildi.
* **Çoklu Platform & Otomatik Yayın:** Tam Linux/Windows uyumluluğu, Linux (`install_linux.sh`, `.tar.gz`, `.deb`, `.rpm`) ve Windows (`Setup.exe`, `Portable.exe`) paketleme betikleri ile GitHub Actions otomatik sürüm akışı eklendi.

### Düzeltmeler
* **Baskı Montajı Ortalama & Dikey 2-Up:** Ofsetli `CropBox` içeren PDF'lerde hücre içi kayma (`_place_in_cell`) ve dikey kağıtlarda 2-up (`1×2`) dizilimi düzeltildi.
* **Arayüz & Metin Yerleşimi:** Onay kutularında (`QtCheckBox.sizeHint`) ve uzun segment düğmelerinde sağdan metin kesilmeleri giderildi; *Özel sayfalar* bölümü katlanabilir yapıldı.
* **Mimari Düzenleme:** Çekirdek motor ve ayar modülleri `core/` paketi altına taşındı; yardımcı betikler `tools/` altında toplandı.

---

## [2.9.0] — 2026-11-10

* Boş durum yönlendirmeleri ve kaynak gerektiren düğme durumları eklendi.
* İşlem öncesi **Ön kontrol** özeti ve profil seçmeli **GUI Toplu İşlem** penceresi eklendi.
* Karışık ebatlı PDF'lerde hedef boyut kaynağı seçimi (*Baskın*, *İlk*, *En büyük*) getirildi.

---

## [2.8.0] — 2026-11

* **PDF Araçları, Filigran/Bates, Kitapçık & N-Up:** Kesim işaretleri, taşma payı (BleedBox/TrimBox) ve kitapçık kayma (creep) telafisi eklendi.
* **Bölüm Numaralandırması:** Roma/Arap rakamı geçişleri, bölüm başında numara gizleme ve sağ sayfada başlatma eklendi.
* **Birleştirme Performansı & Çoklu Dil:** 100+ dosyada tembel satır kurulumu, 56×72 küçük resimler, bağımsız sayfa eşitleme ve TR/EN dil desteği eklendi.
