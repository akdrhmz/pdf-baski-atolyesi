# Referans PDF Seti

Bu klasördeki dosyalar `python tools/make_reference_set.py` ile üretilir.
Amaç, "açıklamalar/bağlantılar/yer imleri korunuyor mu?" sorusunu varsayımla
değil gerçek belgeyle test etmektir.

| Dosya | İçerik |
| --- | --- |
| `karisik_referans.pdf` | A4 + A5 + 90° döndürülmüş sayfa, raster görsel, iç bağlantı, web bağlantısı, vurgu açıklaması, metin notu, form alanı, üç yer imi |
| `a4_duplex_ornek.pdf` | 8 sayfalık düz A4 belge; duplex cilt payı, numaralandırma ve birleştirme denemeleri için |
| `parola_korumali_ornek.pdf` | Parola korumalı PDF; anlaşılır Türkçe hata mesajı testi (parola: `gizli`) |

Bu dosyalar elle düzenlenmemelidir; yeniden üretmek için betiği çalıştırın.
