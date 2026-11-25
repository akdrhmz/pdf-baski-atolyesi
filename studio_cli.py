"""PDF işleme, baskı montajı, damga/Bates, sayfa ayıklama ve güvenlik komut satırı."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.gutter_engine import (
    config_from_dict,
    parse_page_ranges,
    process_pdf,
    same_path,
    unique_output_path,
    validate_config,
)
from core.pdf_tools import (
    PrintOptions,
    SecurityMetaOptions,
    StampOptions,
    apply_security_and_metadata,
    export_pages,
    impose_pdf,
    split_pages,
    stamp_pdf,
)
from core.settings_store import PRESETS, SettingsStore


def _collect_inputs(raw_inputs: list[str], output: Path, recursive: bool) -> list[Path]:
    files: list[Path] = []
    for value in raw_inputs:
        path = Path(value).resolve()
        if path.is_dir():
            output_inside_input = path in output.parents
            candidates = path.rglob("*") if recursive else path.iterdir()
            files.extend(
                p for p in sorted(candidates)
                if p.is_file() and p.suffix.lower() == ".pdf"
                and not (output_inside_input and output in p.parents)
            )
        elif path.is_file() and path.suffix.lower() == ".pdf":
            files.append(path)
        else:
            raise ValueError(f"PDF veya klasör bulunamadı: {value}")
    return list(dict.fromkeys(files))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PDF Baskı Atölyesi · toplu işlem ve baskı araçları")
    parser.add_argument("--input", required=True, nargs="+", help="PDF dosyaları veya klasörleri")
    parser.add_argument("--output", required=True, help="Tek dosya için .pdf yolu veya çıktı klasörü")
    parser.add_argument("--profile", help="JSON ayar dosyası veya kayıtlı/hazır profil adı")
    parser.add_argument("--recursive", action="store_true", help="Alt klasörlerdeki PDF'leri de al")

    # 4. Sekme (Baskı ve Araçlar) komut satırı seçenekleri
    tool_grp = parser.add_argument_group("Baskı ve Araçlar (isteğe bağlı modlar)")
    tool_grp.add_argument(
        "--impose", choices=["2up", "4up", "booklet", "marks"],
        help="Baskı montajı kipi (2up, 4up, booklet, marks)",
    )
    tool_grp.add_argument("--paper-width", type=float, default=297.0, help="Montaj yaprak genişliği (mm)")
    tool_grp.add_argument("--paper-height", type=float, default=210.0, help="Montaj yaprak yüksekliği (mm)")
    tool_grp.add_argument("--margin", type=float, default=5.0, help="Montaj dış kenar payı (mm)")
    tool_grp.add_argument("--gap", type=float, default=2.0, help="Montaj sayfalar arası boşluk (mm)")
    tool_grp.add_argument("--bleed", type=float, default=0.0, help="Taşma payı / bleed (mm)")
    tool_grp.add_argument("--creep", type=float, default=0.0, help="Kitapçık iç sayfa kayma telafisi (mm)")
    tool_grp.add_argument("--signature", type=int, default=0, help="Kitapçık forma boyutu (0 veya 4'ün katı)")
    tool_grp.add_argument("--crop-marks", action="store_true", help="Matbaa kesim işaretleri ekle")
    tool_grp.add_argument("--divider-line", action="store_true", help="Sayfalar arası kesim/katlama çizgisi")
    tool_grp.add_argument("--rtl", action="store_true", help="Sağdan-sola (RTL) kitap dizilimi")

    tool_grp.add_argument("--watermark", default="", help="Şeffaf filigran metni")
    tool_grp.add_argument("--watermark-opacity", type=float, default=18.0, help="Filigran saydamlığı (0-100 %)")
    tool_grp.add_argument("--watermark-angle", type=int, default=45, help="Filigran açısı (-180..180)")
    tool_grp.add_argument("--watermark-size", type=float, default=40.0, help="Filigran yazı boyutu (pt)")
    tool_grp.add_argument("--stamp-pages", default="", help="Damga/Bates sayfa aralığı (ör. 2-10, 15)")
    tool_grp.add_argument("--bates-prefix", default="", help="Bates ön eki (verilirse veya --bates ile aktifleşir)")
    tool_grp.add_argument("--bates-suffix", default="", help="Bates son eki")
    tool_grp.add_argument("--bates-start", type=int, default=1, help="Bates başlangıç numarası")
    tool_grp.add_argument("--bates-digits", type=int, default=6, help="Bates basamak sayısı")
    tool_grp.add_argument(
        "--bates-position",
        choices=["bottom_left", "bottom_center", "bottom_right", "top_left", "top_right"],
        default="bottom_left",
        help="Bates numara konumu",
    )
    tool_grp.add_argument("--bates", action="store_true", help="Bates numaralandırmasını etkinleştir")

    tool_grp.add_argument("--pages", default="", help="Yalnız belirtilen sayfa aralığını dışa aktar (ör. 1-5, 8)")
    tool_grp.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="Dışa aktarılan sayfaları döndür")
    tool_grp.add_argument("--split", type=int, default=0, help="Her N sayfada bir ayrı PDF dosyasına böl")

    tool_grp.add_argument("--compress-dpi", type=int, default=0, help="Görselleri hedef DPI değerine yeniden örnekle (36-600)")
    tool_grp.add_argument("--clear-metadata", action="store_true", help="Mevcut PDF meta verilerini temizle")
    tool_grp.add_argument("--title", default="", help="PDF Başlık (Title) meta verisi")
    tool_grp.add_argument("--author", default="", help="PDF Yazar (Author) meta verisi")
    tool_grp.add_argument("--user-password", default="", help="AES-256 açılış parolası")
    tool_grp.add_argument("--owner-password", default="", help="AES-256 izin parolası")
    tool_grp.add_argument("--source-password", default="", help="Şifreli kaynak PDF'i açmak için parola")
    tool_grp.add_argument("--no-print", action="store_true", help="Parola korumasında yazdırma iznini kapat")
    tool_grp.add_argument("--no-copy", action="store_true", help="Parola korumasında kopyalama iznini kapat")

    args = parser.parse_args(argv)
    try:
        output = Path(args.output).resolve()
        try:
            files = _collect_inputs(args.input, output, args.recursive)
        except ValueError as exc:
            parser.error(str(exc))
        if not files:
            parser.error("İşlenecek PDF bulunamadı.")

        stamp_active = bool(args.watermark or args.bates or args.bates_prefix or args.bates_suffix)
        pages_active = bool(args.pages or args.split > 0 or args.rotate != 0)
        security_active = bool(
            args.compress_dpi > 0 or args.clear_metadata or args.title or args.author
            or args.user_password or args.owner_password
        )
        active_modes = sum(bool(x) for x in (args.impose, stamp_active, pages_active, security_active))
        if active_modes > 1:
            parser.error("Aynı anda yalnızca bir araç kipi (--impose, damga/Bates, sayfa/bölme veya güvenlik) seçilebilir.")

        single_output = output.suffix.lower() == ".pdf"
        if args.split > 0 and single_output:
            parser.error("--split kullanıldığında --output bir klasör olmalı.")
        if single_output and len(files) != 1:
            parser.error("Birden fazla girdi için --output bir klasör olmalı.")
        if not single_output:
            output.mkdir(parents=True, exist_ok=True)

        config = None
        if active_modes == 0:
            store = SettingsStore()
            if args.profile:
                profile_path = Path(args.profile)
                if profile_path.is_file():
                    raw = json.loads(profile_path.read_text(encoding="utf-8-sig"))
                    raw = raw.get("last_state", raw)
                elif args.profile in PRESETS:
                    raw = PRESETS[args.profile]
                else:
                    raw = store.data.get("profiles", {}).get(args.profile)
                    if raw is None:
                        parser.error(f"Profil bulunamadı: {args.profile}")
            else:
                raw = store.last_state
            if not isinstance(raw, dict):
                parser.error("Profil bir JSON nesnesi olmalı.")
            config = config_from_dict(raw)
            validation = validate_config(config)
            if not validation.ok:
                parser.error("; ".join(validation.errors))

        failed = 0
        for source in files:
            if args.split > 0:
                import pymupdf
                with pymupdf.open(str(source)) as doc:
                    total = len(doc)
                wanted = sorted(parse_page_ranges(args.pages)) if args.pages.strip() else list(range(1, total + 1))
                page_spec = [(p - 1, args.rotate) for p in wanted if 1 <= p <= total]
                try:
                    parts = split_pages(str(source), str(output), page_spec, group_size=args.split)
                    print(f"OK: {source} -> {len(parts)} parça ({output})")
                except Exception as exc:
                    failed += 1
                    print(f"HATA: {source}: {exc}", file=sys.stderr)
                continue

            suffix = (
                "_baski" if args.impose else
                "_damga" if stamp_active else
                "_sayfalar" if pages_active else
                "_guvenli" if security_active else
                "_islenmis"
            )
            target = output if single_output else output / f"{source.stem}{suffix}.pdf"
            if same_path(str(source), str(target)):
                parser.error("Kaynak dosyanın üzerine yazılamaz.")
            if not single_output:
                target = Path(unique_output_path(str(target)))
            try:
                if args.impose:
                    opts = PrintOptions(
                        mode=args.impose,
                        width_mm=args.paper_width,
                        height_mm=args.paper_height,
                        margin_mm=args.margin,
                        gap_mm=args.gap,
                        bleed_mm=args.bleed,
                        creep_mm=args.creep,
                        signature_size=args.signature,
                        crop_marks=args.crop_marks,
                        divider_line=args.divider_line,
                        rtl=args.rtl,
                    )
                    impose_pdf(str(source), str(target), opts)
                elif stamp_active:
                    opts = StampOptions(
                        watermark=args.watermark,
                        opacity=max(0.0, min(1.0, args.watermark_opacity / 100.0)),
                        angle=args.watermark_angle,
                        font_size=args.watermark_size,
                        page_range=args.stamp_pages,
                        bates_enabled=bool(args.bates or args.bates_prefix or args.bates_suffix),
                        bates_prefix=args.bates_prefix,
                        bates_suffix=args.bates_suffix,
                        bates_start=args.bates_start,
                        bates_digits=args.bates_digits,
                        bates_position=args.bates_position,
                    )
                    stamp_pdf(str(source), str(target), opts)
                elif pages_active:
                    import pymupdf
                    with pymupdf.open(str(source)) as doc:
                        total = len(doc)
                    wanted = sorted(parse_page_ranges(args.pages)) if args.pages.strip() else list(range(1, total + 1))
                    page_spec = [(p - 1, args.rotate) for p in wanted if 1 <= p <= total]
                    export_pages(str(source), str(target), page_spec)
                elif security_active:
                    opts = SecurityMetaOptions(
                        title=args.title,
                        author=args.author,
                        clear_metadata=args.clear_metadata,
                        user_password=args.user_password,
                        owner_password=args.owner_password,
                        allow_print=not args.no_print,
                        allow_copy=not args.no_copy,
                        compress_images=args.compress_dpi > 0,
                        image_dpi=args.compress_dpi if args.compress_dpi > 0 else 150,
                        source_password=args.source_password,
                    )
                    apply_security_and_metadata(str(source), str(target), opts)
                else:
                    process_pdf(str(source), str(target), config)
                print(f"OK: {source} -> {target}")
            except Exception as exc:
                failed += 1
                print(f"HATA: {source}: {exc}", file=sys.stderr)
        return 1 if failed else 0
    except KeyboardInterrupt:
        print("İşlem iptal edildi.", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
