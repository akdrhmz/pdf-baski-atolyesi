"""P3 13d, 1. parça: birleşik "Sayfa Düzeni" ayar modeli (Qt'siz, motor değişmez).

Eşleme tabloları, eski ayarların korunması ve özel sayfa kurallarının motorda
gerçekten beklenen sayfa ebadını/yerleşimini vermesi denenir.
"""

from __future__ import annotations

import itertools

import pytest

from core.gutter_engine import (
    PdfProcessConfig, compute_layout, config_from_dict, config_to_dict, mm_to_pt, pt_to_mm,
    validate_config,
)
import core.page_layout_model as plm
from core.page_layout_model import (
    CHOICE_CLIP, CHOICE_EXTEND, CHOICE_SHRINK, CHOICE_TO_ENGINE, MODE_GUTTER_ONLY,
    MODE_MARGIN_ONLY, MODE_NONE, SpecialRule,
)


def _config(choice=None, pair=None, tw=225.0, th=297.0, odd_x=15.0, bottom=10.0):
    config = PdfProcessConfig()
    b, m = config.page_boxes, config.margins
    b.enabled, b.size_mode = True, "fixed"
    b.target_width_mm, b.target_height_mm, b.odd_x_mm = tw, th, odd_x
    m.enabled, m.extra_bottom_mm = True, bottom
    b.overflow_mode, m.bottom_mode = pair or plm.choice_to_engine(choice)
    return config


def _layout(config, pno=0):
    lay = compute_layout(mm_to_pt(210), mm_to_pt(297), config, pno)
    return (round(pt_to_mm(lay.target_w), 1), round(pt_to_mm(lay.target_h), 1),
            round(lay.scale, 4), lay)


# ---------------------------------------------------------------------------
# Taşarsa ne olsun: eşleme tablosu
# ---------------------------------------------------------------------------
def test_mapping_table_is_explicit_and_bijective():
    assert CHOICE_TO_ENGINE == {
        CHOICE_EXTEND: ("clip", "expand"),
        CHOICE_SHRINK: ("shrink", "fit"),
        CHOICE_CLIP: ("clip", "shift"),
    }
    assert set(plm.OVERFLOW_CHOICES) == set(CHOICE_TO_ENGINE)
    assert len(set(CHOICE_TO_ENGINE.values())) == 3
    for choice, pair in CHOICE_TO_ENGINE.items():
        state = plm.engine_to_choice(*pair)
        assert (state.choice, state.exact) == (choice, True)


def test_default_engine_values_map_to_extend():
    """Yeni kullanıcı varsayılanı (clip + expand) = "Sayfa uzasın" (çıktı değişmez)."""
    config = PdfProcessConfig()
    state = plm.engine_to_choice(config.page_boxes.overflow_mode, config.margins.bottom_mode)
    assert (state.choice, state.exact) == (CHOICE_EXTEND, True)


@pytest.mark.parametrize("choice", list(CHOICE_TO_ENGINE))
def test_canonical_pairs_pass_validation(choice):
    result = validate_config(_config(choice))
    assert not result.errors


@pytest.mark.parametrize("pair", list(itertools.product(plm.VALID_OVERFLOW, plm.VALID_BOTTOM)))
def test_every_engine_pair_has_a_choice_and_roundtrips_unchanged(pair):
    """Altı motor birleşiminin hepsi yüklenir; dokunulmazsa çift AYNEN geri yazılır."""
    state = plm.engine_to_choice(*pair)
    assert state.choice in plm.OVERFLOW_CHOICES
    assert plm.resolve_engine_pair(state.choice, loaded=pair) == pair


@pytest.mark.parametrize("pair,expected", [
    (("shrink", "expand"), CHOICE_SHRINK),
    (("shrink", "shift"), CHOICE_SHRINK),
    (("clip", "fit"), CHOICE_SHRINK),
])
def test_legacy_pairs_are_flagged_inexact_and_kept_until_user_changes(pair, expected):
    state = plm.engine_to_choice(*pair)
    assert (state.choice, state.exact) == (expected, False)
    # kullanıcı aynı seçimde kalırsa eski çift korunur
    assert plm.resolve_engine_pair(expected, loaded=pair) == pair
    # başka seçim yaparsa kanonik çift yazılır
    other = CHOICE_EXTEND
    assert plm.resolve_engine_pair(other, loaded=pair) == CHOICE_TO_ENGINE[other]
    # kullanıcı sonra aynı seçime geri dönerse artık kanonik çift yazılır
    assert plm.resolve_engine_pair(expected, loaded=CHOICE_TO_ENGINE[other]) == CHOICE_TO_ENGINE[expected]


def test_unknown_values_fall_back_to_defaults_and_unknown_choice_raises():
    assert plm.engine_to_choice("???", "???") == plm.OverflowState(CHOICE_EXTEND, True)
    with pytest.raises(ValueError):
        plm.choice_to_engine("yok")


# ---------------------------------------------------------------------------
# Taşarsa ne olsun: motorda gerçek çıktı ebadı (A4 + 15 mm pay + 10 mm alt boşluk)
# ---------------------------------------------------------------------------
def test_extend_grows_page_height_and_keeps_scale():
    w, h, scale, _ = _layout(_config(CHOICE_EXTEND))
    assert (w, h, scale) == (225.0, 307.0, 1.0)


def test_shrink_keeps_page_size_fixed_and_scales_down_without_clipping():
    w, h, scale, lay = _layout(_config(CHOICE_SHRINK))
    assert (w, h) == (225.0, 297.0) and scale < 1.0
    page = lay.content
    assert page.x0 >= -0.01 and page.y0 >= -0.01
    assert page.x1 <= lay.target_w + 0.01 and page.y1 <= lay.target_h + 0.01


def test_clip_keeps_page_size_and_scale_but_content_overflows():
    w, h, scale, lay = _layout(_config(CHOICE_CLIP))
    assert (w, h, scale) == (225.0, 297.0, 1.0)
    assert lay.content.y0 < 0   # alt boşluk kadar yukarı kayar; taşan kısım kırpılır


def test_shrink_when_target_too_small_never_overflows():
    """Hedef A4'ün kendisi (210): cilt payı sığmaz; "küçül" kırpmadan sığdırır, "kırp" taşar."""
    shrink = _layout(_config(CHOICE_SHRINK, tw=210.0))[3]
    clip = _layout(_config(CHOICE_CLIP, tw=210.0))[3]
    assert shrink.content.x1 <= shrink.target_w + 0.01
    assert clip.content.x1 > clip.target_w + 0.01


def test_shrink_choice_should_not_double_shrink():
    _w, _h, scale, _lay = _layout(_config(CHOICE_SHRINK))
    # içerik genişliği (210) + cilt payı (15) = 225: yalnızca yükseklik için 287/297 gerekir
    assert scale == pytest.approx(287.0 / 297.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Özel sayfalar: kurallar <-> iki motor listesi
# ---------------------------------------------------------------------------
def test_compact_ranges():
    assert plm.compact_ranges({1, 5, 9, 10}) == "1, 5, 9-10"
    assert plm.compact_ranges([3, 2, 1, 7]) == "1-3, 7"
    assert plm.compact_ranges([]) == ""
    assert plm.compact_ranges([0, -2, 4]) == "4"


@pytest.mark.parametrize("mode,boxes,margins", [
    (MODE_NONE, "1, 5", "1, 5"),
    (MODE_GUTTER_ONLY, "", "1, 5"),
    (MODE_MARGIN_ONLY, "1, 5", ""),
])
def test_rules_to_excludes_each_mode(mode, boxes, margins):
    assert plm.rules_to_excludes([SpecialRule("1, 5", mode)]) == (boxes, margins)


def test_multiple_rules_are_merged():
    rules = [SpecialRule("1", MODE_GUTTER_ONLY), SpecialRule("9-10", MODE_NONE),
             SpecialRule("20", MODE_MARGIN_ONLY)]
    assert plm.rules_to_excludes(rules) == ("9-10, 20", "1, 9-10")


def test_overlapping_rules_union_to_none_and_are_reported():
    rules = [SpecialRule("3-4", MODE_GUTTER_ONLY), SpecialRule("4", MODE_MARGIN_ONLY)]
    assert plm.overlapping_pages(rules) == [4]
    assert plm.rules_to_excludes(rules) == ("4", "3-4")   # sayfa 4 iki listede: hiçbir pay yok


def test_invalid_range_is_rejected_with_tokens():
    with pytest.raises(plm.RuleError) as exc:
        plm.rules_to_excludes([SpecialRule("1, abc, 3-x")])
    assert exc.value.tokens == ["abc", "3-x"]
    with pytest.raises(plm.RuleError):
        plm.rules_to_excludes([SpecialRule("1", "bilinmeyen")])


def test_long_dash_and_semicolon_accepted():
    assert plm.rules_to_excludes([SpecialRule("1; 3–5", MODE_NONE)]) == ("1, 3-5", "1, 3-5")


def test_excludes_to_rules_groups_by_effect():
    config = PdfProcessConfig()
    config.page_boxes.exclude_pages_str = "1, 9-10"
    config.margins.exclude_pages_str = "1, 5"
    rules = plm.excludes_to_rules(config.page_boxes, config.margins)
    assert rules == [SpecialRule("1", MODE_NONE), SpecialRule("5", MODE_GUTTER_ONLY),
                     SpecialRule("9-10", MODE_MARGIN_ONLY)]


def test_excludes_to_rules_reads_legacy_sets_too():
    config = PdfProcessConfig()
    config.page_boxes.exclude_pages_set = {2}
    config.margins.exclude_pages_set = {2, 3}
    assert plm.excludes_to_rules(config.page_boxes, config.margins) == [
        SpecialRule("2", MODE_NONE), SpecialRule("3", MODE_GUTTER_ONLY)]


def test_empty_excludes_give_no_rules():
    config = PdfProcessConfig()
    assert plm.excludes_to_rules(config.page_boxes, config.margins) == []
    assert plm.rules_to_excludes([]) == ("", "")


@pytest.mark.parametrize("boxes_text,margins_text", [
    ("", ""), ("1, 5", "1, 5"), ("", "1-3, 8"), ("2, 4-6", ""), ("1-3, 7", "2-4, 7, 9"),
])
def test_excludes_roundtrip_preserves_effective_pages(boxes_text, margins_text):
    from core.gutter_engine import excluded_pages
    config = PdfProcessConfig()
    config.page_boxes.exclude_pages_str = boxes_text
    config.margins.exclude_pages_str = margins_text
    before = (excluded_pages(config.page_boxes), excluded_pages(config.margins))
    rules = plm.excludes_to_rules(config.page_boxes, config.margins)
    plm.apply_rules(config.page_boxes, config.margins, rules)
    assert (excluded_pages(config.page_boxes), excluded_pages(config.margins)) == before
    # ikinci tur aynı kuralları verir (kararlı)
    assert plm.excludes_to_rules(config.page_boxes, config.margins) == rules


def test_apply_rules_clears_legacy_sets():
    config = PdfProcessConfig()
    config.page_boxes.exclude_pages_set = {7}
    rules = plm.excludes_to_rules(config.page_boxes, config.margins)
    plm.apply_rules(config.page_boxes, config.margins, rules)
    assert config.page_boxes.exclude_pages_set == set()
    assert config.page_boxes.exclude_pages_str == "7"


# ---------------------------------------------------------------------------
# Özel sayfalar: motorda gerçek sonuç (ara kapak: cilt payı var, alt boşluk yok)
# ---------------------------------------------------------------------------
def _special_config(rules):
    config = _config(CHOICE_EXTEND)
    plm.apply_rules(config.page_boxes, config.margins, rules)
    return config


def test_ara_kapak_keeps_gutter_but_drops_bottom_margin():
    config = _special_config([plm.ara_kapak_rule("2")])
    normal = _layout(config, pno=0)[:2]      # 1. sayfa: cilt payı + alt boşluk
    cover = _layout(config, pno=1)           # 2. sayfa: özel
    assert normal == (225.0, 307.0)
    assert (cover[0], cover[1]) == (225.0, 297.0)   # genişlik hâlâ hedef (pay korunur), alt boşluk yok
    # çift sayfa: ofset 0; cilt payı tek sayfalar için. Tek sayfa ara kapak denenir:
    cover_odd = _layout(_special_config([plm.ara_kapak_rule("1")]), pno=0)
    assert (cover_odd[0], cover_odd[1]) == (225.0, 297.0)
    assert cover_odd[3].content.x0 == pytest.approx(mm_to_pt(15.0))   # cilt payı uygulandı


def test_mode_none_drops_both():
    config = _special_config([SpecialRule("1", MODE_NONE)])
    lay = _layout(config, pno=0)[3]
    assert (round(pt_to_mm(lay.target_w)), round(pt_to_mm(lay.target_h))) == (210, 297)
    assert lay.content.x0 == 0


def test_mode_margin_only_drops_gutter_but_keeps_bottom_margin():
    config = _special_config([SpecialRule("1", MODE_MARGIN_ONLY)])
    lay = _layout(config, pno=0)[3]
    assert round(pt_to_mm(lay.target_h)) == 307
    assert lay.content.x0 == 0


# ---------------------------------------------------------------------------
# Birleşik okuma/yazma ve settings.json gidiş-dönüşü
# ---------------------------------------------------------------------------
def test_write_then_read_unified_and_json_roundtrip():
    config = PdfProcessConfig()
    rules = [SpecialRule("1", MODE_GUTTER_ONLY), SpecialRule("9-10", MODE_NONE)]
    plm.write_unified(config.page_boxes, config.margins, CHOICE_SHRINK, rules)
    assert (config.page_boxes.overflow_mode, config.margins.bottom_mode) == ("shrink", "fit")

    restored = config_from_dict(config_to_dict(config))
    state, back = plm.read_unified(restored.page_boxes, restored.margins)
    assert (state.choice, state.exact) == (CHOICE_SHRINK, True)
    assert back == [SpecialRule("9-10", MODE_NONE), SpecialRule("1", MODE_GUTTER_ONLY)]
    assert config_to_dict(restored) == config_to_dict(config)   # ayar dosyası biçimi aynı


def test_old_settings_without_new_keys_load_as_defaults():
    restored = config_from_dict({})
    state, rules = plm.read_unified(restored.page_boxes, restored.margins)
    assert (state.choice, state.exact, rules) == (CHOICE_EXTEND, True, [])


def test_legacy_pair_survives_write_unified_when_untouched():
    config = PdfProcessConfig()
    config.page_boxes.overflow_mode, config.margins.bottom_mode = "shrink", "expand"
    loaded = (config.page_boxes.overflow_mode, config.margins.bottom_mode)
    state, rules = plm.read_unified(config.page_boxes, config.margins)
    plm.write_unified(config.page_boxes, config.margins, state.choice, rules, loaded_pair=loaded)
    assert (config.page_boxes.overflow_mode, config.margins.bottom_mode) == ("shrink", "expand")
