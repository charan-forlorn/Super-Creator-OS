import json
from pathlib import Path

import pytest

from scos.premium_media.audio import build_mix_plan, role_gain_preset
from scos.premium_media.models import (
    AssetRights,
    AudioRole,
    AudioStem,
    MediaAsset,
    PremiumRenderProfile,
    SubtitleCue,
    RightsClass,
)
from scos.premium_media.rights import RightsError, validate_asset_for_publish
from scos.premium_media.subtitles import SubtitleError, parse_srt, to_ass, wrap_caption
from scos.premium_media.asset_intelligence import AssetQuery, rank_assets, select_best_asset
from scos.premium_media.brand import BrandKitError, resolve_brand_profile
from scos.premium_media.creative_graph import graph_from_props
from scos.premium_media.delivery import DELIVERY_PROFILES, MASTER_VERTICAL, get_delivery_profile
# asset models imported above
from scos.premium_media.safe_zone import LayoutBox, validate_layout
from scos.premium_media.intake import ingest_local


def test_srt_round_trip_and_wrap():
    cues = parse_srt(
        "1\n00:00:00,000 --> 00:00:01,200\nสวัสดีครับ โลกนี้ยาวมาก\n\n"
        "2\n00:00:01,300 --> 00:00:02,000\nHello premium video\n",
        language="th",
    )
    assert len(cues) == 2
    assert cues[0].language == "th"
    assert "\n" in wrap_caption("This is a subtitle line that should wrap cleanly", max_chars=20)
    assert "Dialogue:" in to_ass(cues)


def test_srt_overlap_fails():
    with pytest.raises(SubtitleError):
        parse_srt(
            "1\n00:00:00,000 --> 00:00:02,000\nOne\n\n"
            "2\n00:00:01,000 --> 00:00:03,000\nTwo\n"
        )


def test_rights_fail_closed_for_ads(tmp_path: Path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"wav")
    asset = ingest_local(
        source,
        asset_id="x",
        media_type="audio",
        rights=None,
    )
    with pytest.raises(RightsError):
        validate_asset_for_publish(asset, platform="tiktok", for_ad=True)


def test_cc_by_requires_attribution(tmp_path: Path):
    asset_rights = AssetRights(
        source_url="https://example.com",
        license_name="CC-BY",
        rights_class=RightsClass.CC_BY,
        commercial_ok=True,
        attribution_required=False,
    )
    source = tmp_path / "font.ttf"
    source.write_bytes(b"font")
    with pytest.raises(RightsError):
        validate_asset_for_publish(
            ingest_local(source, asset_id="font", media_type="font", rights=asset_rights),
            platform="youtube",
            for_ad=True,
        )


def test_audio_plan_keeps_voice_anchor():
    profile = PremiumRenderProfile(name="test", platform="ad")
    plan = build_mix_plan(
        [
            AudioStem("voice.wav", AudioRole.VOICE),
            AudioStem("music.wav", AudioRole.MUSIC),
            AudioStem("sfx.wav", AudioRole.SFX),
        ],
        profile,
    )
    assert "sidechaincompress" in plan.filter_complex
    assert "loudnorm=" in plan.filter_complex
    assert role_gain_preset(AudioRole.MUSIC) < role_gain_preset(AudioRole.VOICE)


def test_ad_profile_is_single_screen():
    profile = PremiumRenderProfile(
        name="ad", platform="ad", for_ad=True, single_screen=True
    )
    assert profile.width == 1080
    assert profile.height == 1920
    assert profile.single_screen is True


def test_master_and_delivery_are_distinct_contracts():
    tiktok = get_delivery_profile("tiktok_ads_global_app_bundle")
    assert MASTER_VERTICAL.platform == "master"
    assert MASTER_VERTICAL.profile_id != tiktok.profile_id
    assert tiktok.require_916 is True
    assert tiktok.min_duration_s == 5
    assert tiktok.max_duration_s == 60


def test_creative_graph_is_deterministic_and_carries_learning_identity():
    props = {"project_id": "p1", "duration_s": 2, "states": [{"start": 0, "end": 2, "headline": "Hello"}],
             "production_graph": {"loop_run_id": "run-1", "delivery_profile_ids": ["tiktok_ads_global_app_bundle"]}}
    graph = graph_from_props(props)
    assert graph.brief.loop_run_id == "run-1"
    assert graph.fingerprint() == graph.fingerprint()
    compiled = graph.to_remotion_props()
    assert compiled["production_graph"]["loop_run_id"] == "run-1"
    assert compiled["production_graph"]["delivery_profile_ids"] == ["tiktok_ads_global_app_bundle"]
    props_with_audio = {**props, "musicSrc": "music.wav", "sfx": [{"src": "sfx.wav"}]}
    assert graph_from_props(props_with_audio).to_remotion_props()["sfx"][0]["src"] == "sfx.wav"


def test_safe_zone_baseline_rejects_content_outside_inner_90_percent():
    ok = validate_layout(
        width=1080,
        height=1920,
        boxes=(LayoutBox("headline", 70, 180, 1010, 1650),),
    )
    assert ok == ()
    bad = validate_layout(
        width=1080,
        height=1920,
        boxes=(LayoutBox("cta", 10, 1800, 1070, 1900),),
    )
    assert bad


def test_asset_intelligence_ranks_and_filters_rights():
    rights = AssetRights(
        source_url="local://licensed",
        license_name="Commercial",
        rights_class=RightsClass.COMMERCIAL_CLEARED,
        commercial_ok=True,
        allowed_platforms=("tiktok",),
    )
    a = MediaAsset("a", "a.wav", "audio", 4.0, ("focus",), "en", "sha-a", rights)
    b = MediaAsset("b", "b.wav", "audio", 15.0, ("focus",), "en", "sha-b", rights)
    result = rank_assets(
        (a, b),
        AssetQuery(
            media_type="audio",
            tags=("focus",),
            language="en",
            target_duration_s=4.0,
            platform="tiktok",
            for_ad=True,
        ),
    )
    assert result[0].asset.asset_id == "a"
    assert (
        select_best_asset(
            (a, b),
            AssetQuery(media_type="audio", target_duration_s=4.0, platform="tiktok", for_ad=True),
        ).asset.asset_id
        == "a"
    )


def test_brand_bridge_is_fail_closed_and_reads_authoritative_shape(tmp_path):
    store = tmp_path / "memory" / "runtime" / "control-center" / "brand-kit-v1.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps({
            "schema_version": 1,
            "store_kind": "scos.brand_kit.v1",
            "record_count": 1,
            "records": [{
                "brand_kit_id": "bkb-demo",
                "schema_version": 1,
                "name": "Demo",
                "colors": {
                    "primary": "#000000",
                    "secondary": "#101010",
                    "accent": "#B7EF83",
                    "neutrals": ["#fff"],
                },
                "fonts": {"heading": "Tahoma", "body": "Arial"},
                "logo": {"asset_ref": "local-logo", "kind": "local-ref"},
                "contact": {"name": "x", "email": "x@example.com", "socials": []},
                "basic_cta": {"label": "Learn", "target": "internal"},
            }],
        }),
        encoding="utf-8",
    )
    profile = resolve_brand_profile(tmp_path, "bkb-demo")
    assert profile is not None
    assert profile.accent == "#B7EF83"
    assert profile.fingerprint()
    try:
        resolve_brand_profile(tmp_path, "missing")
        assert False
    except BrandKitError:
        pass
