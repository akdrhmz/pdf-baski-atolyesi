"""PDF işleme ve klasör bazlı toplu işlem komut satırı."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gutter_engine import (config_from_dict, process_pdf, same_path,
                           unique_output_path, validate_config)
from settings_store import PRESETS, SettingsStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PDF Baskı ve Cilt Stüdyosu · toplu işlem")
    parser.add_argument("--input", required=True, nargs="+", help="PDF dosyaları veya klasörleri")
    parser.add_argument("--output", required=True, help="Tek dosya için .pdf yolu veya çıktı klasörü")
    parser.add_argument("--profile", help="JSON ayar dosyası veya kayıtlı/hazır profil adı")
    parser.add_argument("--recursive", action="store_true", help="Alt klasörlerdeki PDF'leri de al")
    args = parser.parse_args(argv)
    try:
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
        files = []
        output = Path(args.output).resolve()
        for value in args.input:
            path = Path(value).resolve()
            if path.is_dir():
                output_inside_input = path in output.parents
                candidates = path.rglob("*") if args.recursive else path.iterdir()
                files.extend(p for p in sorted(candidates) if p.is_file() and p.suffix.lower() == ".pdf"
                             and not (output_inside_input and output in p.parents))
            elif path.is_file() and path.suffix.lower() == ".pdf":
                files.append(path)
            else:
                parser.error(f"PDF veya klasör bulunamadı: {value}")
        files = list(dict.fromkeys(files))
        if not files:
            parser.error("İşlenecek PDF bulunamadı.")
        single_output = output.suffix.lower() == ".pdf"
        if single_output and len(files) != 1:
            parser.error("Birden fazla girdi için --output bir klasör olmalı.")
        if not single_output:
            output.mkdir(parents=True, exist_ok=True)
        failed = 0
        for source in files:
            target = output if single_output else output / f"{source.stem}_islenmis.pdf"
            if same_path(str(source), str(target)):
                parser.error("Kaynak dosyanın üzerine yazılamaz.")
            target = Path(unique_output_path(str(target)))
            try:
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
