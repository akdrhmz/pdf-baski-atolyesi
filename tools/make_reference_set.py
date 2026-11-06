"""
Gerçek referans PDF setini üretir (Aşama 0).

Kullanım:
    python tools/make_reference_set.py
Çıktı: samples/referans/
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.pdf_factory import create_encrypted_pdf, create_mixed_sample_pdf, create_sample_a4_pdf

OUTPUT_DIR = os.path.join(ROOT, "samples", "referans")


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mixed = os.path.join(OUTPUT_DIR, "karisik_referans.pdf")
    duplex = os.path.join(OUTPUT_DIR, "a4_duplex_ornek.pdf")
    encrypted = os.path.join(OUTPUT_DIR, "parola_korumali_ornek.pdf")

    create_mixed_sample_pdf(mixed)
    create_sample_a4_pdf(duplex, pages=8)
    create_encrypted_pdf(encrypted)

    print("Referans seti hazır:")
    for path in (mixed, duplex, encrypted):
        print(" -", path)


if __name__ == "__main__":
    main()
