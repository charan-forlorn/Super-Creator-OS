from scos.premium_media.creative_graph import CreativeBrief, ProductionGraph
from scos.premium_media.shot_intelligence import plan_storyboard
from scos.premium_media.video_generation import (
    DEFAULT_PROVIDER_PROFILES,
    GenerationArtifact,
    GenerationTask,
    ProviderProfile,
    ProviderRegistry,
    ReferenceAsset,
    build_generation_plan,
    compile_director_prompt,
    generation_plan_from_props,
)

_SHA = "a" * 64


def test_generation_task_state_machine_is_fail_closed():
    task = GenerationTask("task-1", "shot-01", "runway", "gen4.5")
    submitted = task.transition("submitted", provider_task_id="remote-1")
    running = submitted.transition("running")
    failed = running.transition("failed", error_code="RATE_LIMIT")
    retried = failed.transition("queued")
    artifact = GenerationArtifact("file:///tmp/a.mp4", _SHA, width=1080, height=1920, duration_s=5)
    succeeded = retried.transition("submitted").transition("running").transition("succeeded", artifact=artifact)
    assert succeeded.state == "succeeded"
    assert succeeded.artifact.validate() == ()
    try:
        succeeded.transition("running")
    except ValueError as exc:
        assert "invalid generation task transition" in str(exc)
    else:
        raise AssertionError("terminal task unexpectedly transitioned")

def test_reference_asset_validates_and_serializes():
    ref = ReferenceAsset("hero", "character", "assets/hero.png", _SHA, "hero-v1")
    assert ref.validate() == ()
    assert ref.to_props()["continuity_key"] == "hero-v1"


def test_provider_registry_routes_multimodal_audio_shot_to_seedance():
    registry = ProviderRegistry(DEFAULT_PROVIDER_PROFILES)
    storyboard = plan_storyboard("sell the product", 15, "ad")
    plan = build_generation_plan(
        "p1",
        "sell the product",
        storyboard,
        registry=registry,
        native_audio=True,
        global_references=(
            ReferenceAsset("hero", "character", "assets/hero.png", _SHA, "hero-v1"),
        ),
    )
    assert plan.validate() == ()
    assert all(d.selected_provider_id == "bytedance_seedance" for d in plan.decisions)


def test_generation_plan_roundtrip_is_fingerprint_stable():
    registry = ProviderRegistry(DEFAULT_PROVIDER_PROFILES)
    storyboard = plan_storyboard("launch a product", 30, "ad")
    plan = build_generation_plan("p1", "launch a product", storyboard, registry=registry)
    restored = generation_plan_from_props(plan.to_props())
    assert restored.validate() == ()
    assert restored.fingerprint() == plan.fingerprint()


def test_director_prompt_compiles_structured_controls():
    registry = ProviderRegistry(DEFAULT_PROVIDER_PROFILES)
    storyboard = plan_storyboard("sell a watch", 15, "ad")
    plan = build_generation_plan("p1", "sell a watch", storyboard, registry=registry)
    prompt = compile_director_prompt(
        "sell a watch",
        plan.shots[0],
        continuity_summary="same hero watch, same studio lighting direction",
    )
    assert "SHOT PURPOSE: hook" in prompt
    assert "CAMERA:" in prompt
    assert "CONTINUITY:" in prompt
    assert "DELIVERY:" in prompt


def test_graph_fingerprint_changes_when_generation_plan_is_added():
    registry = ProviderRegistry(DEFAULT_PROVIDER_PROFILES)
    storyboard = plan_storyboard("sell a product", 15, "ad")
    plan = build_generation_plan("p1", "sell a product", storyboard, registry=registry)
    brief = CreativeBrief("p1", "sell a product", "ad", duration_s=15)
    base = ProductionGraph(brief=brief, storyboard=storyboard)
    upgraded = ProductionGraph(brief=brief, storyboard=storyboard, generation_plan=plan)
    assert base.fingerprint() != upgraded.fingerprint()
    props = upgraded.to_remotion_props()
    assert props["production_graph"]["generation_plan"]["fingerprint"] == plan.fingerprint()


def test_router_fails_closed_when_no_provider_meets_requirements():
    registry = ProviderRegistry((
        ProviderProfile(
            "text_only",
            "text-only",
            "Text Only",
            frozenset({"text_to_video"}),
        ),
    ))
    storyboard = plan_storyboard("sell a product", 15, "ad")
    try:
        build_generation_plan(
            "p1",
            "sell a product",
            storyboard,
            registry=registry,
            native_audio=True,
        )
    except LookupError as exc:
        assert "no configured/available provider" in str(exc)
    else:
        raise AssertionError("router unexpectedly selected an incapable provider")
