from __future__ import annotations

from scos.control_center.platform_delivery_plan import (
    BrandPresentationSpec,
    STATE_BLOCKED,
    STATE_READY_FOR_MANUAL_PUBLISH,
    build_platform_delivery_plan,
    validate_artifact_binding,
)


_SHA = "a" * 64
_BRAND = BrandPresentationSpec(
    brand_profile_id="brand-demo",
    logo_asset_id="logo-1",
    primary_color="#111111",
    accent_color="#00A0A0",
    font_family="Inter",
    tone_label="concise",
)


def test_multi_platform_plan_is_deterministic_and_manual_only() -> None:
    kwargs = dict(
        source_artifact_id="artifact-1",
        source_artifact_sha256=_SHA,
        brand=_BRAND,
        format_ids=("square_1_1", "vertical_9_16", "landscape_16_9"),
        title="Launch",
        caption="Launch caption",
        hashtags=("#test", "#launch"),
    )
    a = build_platform_delivery_plan(**kwargs)
    b = build_platform_delivery_plan(**kwargs)
    assert a.plan_id == b.plan_id
    assert a.content_hash == b.content_hash
    assert a.state == STATE_READY_FOR_MANUAL_PUBLISH
    assert a.external_dispatch_allowed is False
    assert a.human_publish_required is True
    assert [v.format_id for v in a.variants] == [
        "landscape_16_9",
        "square_1_1",
        "vertical_9_16",
    ]


def test_artifact_hash_binding_fail_closes() -> None:
    plan = build_platform_delivery_plan(
        source_artifact_id="artifact-1",
        source_artifact_sha256=_SHA,
        expected_artifact_sha256=_SHA,
        brand=_BRAND,
        format_ids=("vertical_9_16",),
        title="Launch",
        caption="Launch caption",
    )
    assert validate_artifact_binding(plan, actual_artifact_sha256=_SHA) == ()
    assert "ARTIFACT_SHA256_MISMATCH" in validate_artifact_binding(
        plan, actual_artifact_sha256="b" * 64
    )


def test_invalid_inputs_block_delivery_plan() -> None:
    plan = build_platform_delivery_plan(
        source_artifact_id="",
        source_artifact_sha256="bad",
        brand=_BRAND,
        format_ids=("not-real",),
        title="",
        caption="",
    )
    assert plan.state == STATE_BLOCKED
    assert plan.external_dispatch_allowed is False
    assert "INVALID_ARTIFACT_SHA256" in plan.blockers
    assert "UNSUPPORTED_FORMAT:not-real" in plan.blockers
    assert "MISSING_TITLE" in plan.blockers
    assert "MISSING_CAPTION" in plan.blockers


def test_brand_change_invalidates_plan_identity() -> None:
    base = build_platform_delivery_plan(
        source_artifact_id="artifact-1",
        source_artifact_sha256=_SHA,
        brand=_BRAND,
        format_ids=("vertical_9_16",),
        title="Launch",
        caption="Launch caption",
    )
    changed = build_platform_delivery_plan(
        source_artifact_id="artifact-1",
        source_artifact_sha256=_SHA,
        brand=BrandPresentationSpec(
            **{**_BRAND.to_dict(), "accent_color": "#FF0000"}
        ),
        format_ids=("vertical_9_16",),
        title="Launch",
        caption="Launch caption",
    )
    assert base.plan_id != changed.plan_id
    assert base.content_hash != changed.content_hash
