---
name: PDF-Baski-Atolyesi-Design-System
description: "Tactile, precision prepress studio UI built on PySide6 (Qt 6) with zero per-widget QSS compilation. Uses a clean GitHub-Primer / Linear hybrid surface hierarchy, strict 4px spacing rhythm, WCAG AA-verified Light/Dark color pairs, and high-visibility 2px focus/validation rings."
---

# PDF Baskı Atölyesi — Design System (`DESIGN.md`)

Single source of code tokens: `ui/theme.py` (rendered via `QPainter` + `QPalette` in `ui/qt_compat.py`).

## 1. Design Principles

1. **Clarity & Active-State Visibility First:** Focused inputs, focused buttons, selected segments, and validation errors always show an unmistakable `2px` border or high-contrast fill (`>= 9:1` on selected segments).
2. **Single Source of Truth:** Colors, font sizes, and layout dimensions live exclusively in `ui/theme.py` — never hardcode hex colors or arbitrary font sizes in tabs.
3. **Zero Flicker, Instant Theme Switch:** Dual `(light, dark)` tuples resolved at paint time (`< 5 ms` theme switch, zero per-widget stylesheet recompilation).

## 2. Color Palette & Surface Hierarchy (WCAG AA Verified)

| Token | Light | Dark | Role & Contrast |
| :--- | :--- | :--- | :--- |
| `COLOR_BG` | `#F6F8FA` | `#0D1117` | Root window canvas |
| `COLOR_CARD` | `#FFFFFF` | `#161B22` | Primary section / panel surface |
| `COLOR_SUBCARD` | `#F6F8FA` | `#1F242C` | Recessed control group / preview surface |
| `COLOR_BORDER` | `#D0D7DE` | `#30363D` | `1px` hairline card & input border |
| `COLOR_TEXT_PRIMARY` | `#1F2328` | `#F0F6FC` | Primary ink (`15.8:1` Light / `15.9:1` Dark) |
| `COLOR_TEXT_SECONDARY` | `#656D76` | `#8B949E` | Labels, hints, units (`5.25:1` Light / `5.62:1` Dark) |
| `COLOR_ACCENT` | `#0969DA` | `#58A6FF` | Focus ring (`2px`), links, active indicators |
| `COLOR_SOLID` | `#0969DA` | `#1F6FEB` | Primary CTA & active step button (`#FFFFFF` ink) |
| `COLOR_SELECTED` | `#B7DCFF` | `#17456E` | Active segmented control (`11.0:1` / `9.1:1`) |
| `COLOR_OK` / `COLOR_OK_BG` | `#1A7F37` / `#DAFBE1` | `#3FB950` / `#133E1D` | Verified output & safe status |
| `COLOR_WARN` / `COLOR_WARN_BG` | `#9A6700` / `#FFF8C5` | `#D29922` / `#3D2C00` | Clipping / padding warnings |
| `COLOR_ERROR` / `COLOR_ERROR_BG` | `#CF222E` / `#FFEBE9` | `#FF7B72` / `#3D1A1C` | Validation error & `2px` error ring |

## 3. Typography Scale

* **Font Family (`FONT_FAMILY`):** Platform-native clean sans (`Noto Sans` on Linux, `Segoe UI` on Windows, `Helvetica Neue` on macOS).
* **Scale:**
  * `FS_TITLE` (`22px`, Bold): App header title (used once).
  * `FS_SUBTITLE` (`15px`, Bold): Card / dialog section headers.
  * `FS_BODY` (`14px`, Regular/Bold): Primary inputs, primary CTA button.
  * `FS_SMALL` (`12px`, Regular/Bold): Form labels, segmented mode selectors, secondary buttons (`BODY_MIN_PX = 12`).
  * `FS_TINY` (`11px`, Regular): Compact unit suffixes and auxiliary captions only — never for interactive mode selectors.

## 4. Spacing & Layout Rhythm

* **4px Base Scale:** `SP_XS = 4`, `SP_S = 8`, `SP_M = 12`, `SP_L = 20`.
* **Hierarchy Rule:** Outer container padding (`>= 12px`) > inter-row gap (`8px`) > intra-control gap (`4px`).
* ** Explicit Placement Only:** All UI containers use explicit `.place(...)` and `.put(...)` wrappers (`set_padding(..., spacing=...)`). Raw `.grid()` / `.pack()` calls are prohibited across `ui/` and `app.py`.
