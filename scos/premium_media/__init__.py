"""SCOS Premium Media production system."""
from .compositing import CompositeSpec, MaskSpec
from .transitions import TransitionRuntimeSpec, compile_transition_filter
from .audio_reactivity import AudioReactiveAnalysis, BeatEvent, EnergyEvent, analyze_audio
from .typography import TypographyPlan, TypographyStyle, WordCue
from .lookdev import LookProfile
from .scene3d import Camera3D, DepthLayer, ProductScene
from .shot_intelligence import ShotPlanSpec, StoryboardPlan, plan_storyboard, storyboard_to_motion_shell
from .video_generation import (
    DEFAULT_PROVIDER_PROFILES,
    GenerationArtifact,
    GenerationPlan,
    GenerationTask,
    GenerationTaskState,
    ProviderDecision,
    ProviderProfile,
    ProviderRegistry,
    ReferenceAsset,
    ShotGenerationSpec,
    build_generation_plan,
    compile_director_prompt,
    generation_plan_from_props,
)
from .benchmark import BenchmarkCase, BenchmarkResult, benchmark_case, benchmark_suite
from .motion import (
    AnimatedNumber,
    Camera2D,
    EffectStack,
    Keyframe,
    MotionLayer,
    PremiumMotionGraph,
    PremiumShot,
    ShotTransition,
    Transform2D,
    with_fingerprint,
)
from .models import (
    AssetRights,
    AudioRole,
    AudioStem,
    MediaAsset,
    PremiumRenderProfile,
    PremiumRenderSpec,
    RightsClass,
    SubtitleCue,
    SubtitleStyle,
)
from .asset_intelligence import (
    AssetCandidate,
    AssetIndexReport,
    AssetQuery,
    LocalAssetIndexer,
    rank_assets,
    select_best_asset,
)
from .brand import (
    BrandProfile,
    BrandKitError,
    brand_profile_to_props,
    repository_root,
    resolve_brand_profile,
)
from .canonical_backend import PremiumRenderBackend
from .creative_graph import (
    AssetNode,
    AudioNode,
    CaptionNode,
    CreativeBrief,
    CreativeVariantSpec,
    ProductionGraph,
    SceneNode,
    apply_creative_variant,
    generate_creative_variants,
    graph_from_props,
)
from .delivery import DELIVERY_PROFILES, DeliveryProfile, get_delivery_profile
from .delivery_render import DeliveryRenderError, render_delivery
from .hardware import HardwareCapabilities, detect_hardware, resolve_finish_profile
from .pipeline import finalize_video, validate_publish_assets
from .render_cache import CacheHit, RenderCache, RenderCacheError, cache_key
from .safe_zone import BASELINE_SAFE_ZONE, LayoutBox, SafeZoneProfile, validate_layout
from .qc import QCReport, validate_render
from .rights import AssetRegistry, RightsError
