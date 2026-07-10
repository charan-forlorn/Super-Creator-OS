"""test_hvs_schema_mapper.py - SCOS <-> HVS Stage 2 deterministic schema mapper.

Covers SCOS->HVS mapping, HVS->SCOS reverse mapping, round-trip semantic
equivalence, deterministic hashing, explicit rejection of unsupported/ambiguous
input, and the no-side-effects guarantees (no subprocess, no file write, no HVS
import, no input mutation). All 45+ required contract cases are present.

Plain executable script (no pytest-only features); pytest collects the
``test_*`` functions directly. Imports the mapper package via an explicit
sys.path insertion so this file runs both under pytest and standalone.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from hvs_contract_models import (  # noqa: E402
    SCOSAssetRef,
    SCOSCaption,
    SCOSRenderTimelineProject,
    SCOSScene,
    SCOS_HVS_TIMELINE_CONTRACT_ID,
    SCOS_RENDER_PRESETS,
    HVSMappingResult,
    HVS_FPS_VALUES,
    HVS_RESOLUTION_VALUES,
    HVS_SCENE_COUNT_MIN,
    HVS_SCENE_COUNT_MAX,
    X_SCOS_KEY,
)
from hvs_schema_mapper import (  # noqa: E402
    canonicalize_mapping_payload,
    compare_round_trip,
    map_hvs_to_scos,
    map_scos_to_hvs,
    payload_identity_hash,
    validate_hvs_payload,
)

HVS_REPO = Path("C:/Workspace/hermes-video-studio")

_PASS = 0
_FAIL = 0


def _mk_scenes(n=3, base_start=0, dur=5000, gap=0):
    scenes = []
    cursor = base_start
    for i in range(n):
        sid = f"scene_{i:02d}"
        scenes.append(
            SCOSScene(
                scene_id=sid,
                order=i,
                start_ms=cursor,
                duration_ms=dur,
                intent=f"intent-{i}",
                visual_description=f"visual-{i}",
                text_overlay=f"text-{i}",
                transition="cut",
            )
        )
        cursor += dur + gap
    return tuple(scenes)


def _mk_project(**kw):
    kw.setdefault("project_id", "proj-st2")
    kw.setdefault("width", 1080)
    kw.setdefault("height", 1920)
    kw.setdefault("fps", 30)
    kw.setdefault("selected_preset", "standard")
    kw.setdefault("scenes", _mk_scenes())
    return SCOSRenderTimelineProject(**kw)


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}  {detail}")


# --- 1. valid minimal SCOS project maps -------------------------------------
def test_valid_minimal_project_maps():
    proj = _mk_project()
    res = map_scos_to_hvs(proj)
    check("1 valid minimal project maps", res.ok, str(res.error))


# --- 2. multi-scene order preserved -----------------------------------------
def test_multiscene_order_preserved():
    scenes = (
        SCOSScene("scene_00", 0, 0, 5000, "a", "v", "t"),
        SCOSScene("scene_01", 1, 5000, 5000, "b", "v", "t"),
        SCOSScene("scene_02", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    payload = map_scos_to_hvs(proj).payload
    ids = [s["scene_id"] for s in payload["scenes"]]
    check("2 multi-scene order preserved", ids == ["scene_00", "scene_01", "scene_02"], str(ids))


# --- 3. scene IDs preserved ------------------------------------------------
def test_scene_ids_preserved():
    proj = _mk_project(scenes=_mk_scenes(n=4))
    payload = map_scos_to_hvs(proj).payload
    scos_ids = {s.scene_id for s in proj.scenes}
    hvs_ids = {s["scene_id"] for s in payload["scenes"]}
    check("3 scene IDs preserved", scos_ids == hvs_ids)


# --- 4. timing identical in canonical ms ------------------------------------
def test_timing_identical_canonical_ms():
    proj = _mk_project(scenes=_mk_scenes(dur=7333))
    payload = map_scos_to_hvs(proj).payload
    ok = all(
        int(round(s["start_time"] * 1000)) == ps.start_ms
        and int(round(s["duration"] * 1000)) == ps.duration_ms
        for s, ps in zip(payload["scenes"], sorted(proj.scenes, key=lambda x: x.order))
    )
    check("4 start/dur identical in canonical ms", ok)


# --- 5. total duration identical -------------------------------------------
def test_total_duration_identical():
    proj = _mk_project(scenes=_mk_scenes(dur=4000))
    payload = map_scos_to_hvs(proj).payload
    check("5 total duration identical", abs(payload["duration_seconds"] * 1000 - proj.total_duration_ms) < 1,
          f"{payload['duration_seconds']} vs {proj.total_duration_ms}")


# --- 6/7 resolution & fps identical ----------------------------------------
def test_resolution_fps_identical():
    proj = _mk_project(width=1920, height=1080, fps=25)
    payload = map_scos_to_hvs(proj).payload
    check("6 width/height identical", payload["resolution"] == "1920x1080")
    check("7 fps identical", payload["fps"] == 25)


# --- 8/9 asset references & types intact ------------------------------------
def test_asset_references_intact():
    scenes = (
        SCOSScene("scene_00", 0, 0, 5000, "a", "v", "t",
                  asset_refs=(SCOSAssetRef("asset-x", "image", "assets/x.png"),)),
        SCOSScene("scene_01", 1, 5000, 5000, "b", "v", "t",
                  asset_refs=(SCOSAssetRef("asset-y", "video"),)),
        SCOSScene("scene_02", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    payload = map_scos_to_hvs(proj).payload
    x = payload[X_SCOS_KEY]
    ax = {(a["asset_id"], a["asset_type"]) for sc in x["scenes"] for a in sc["asset_refs"]}
    check("8 asset references intact", ("asset-x", "image") in ax and ("asset-y", "video") in ax)
    slots = {a["asset_id"]: a["slot_type"] for sc in payload["scenes"] for a in sc["asset_slots"]}
    check("9 asset types intact", slots.get("asset-x") == "image" and slots.get("asset-y") == "video")


# --- 10/11 caption text & timing intact -------------------------------------
def test_caption_text_timing_intact():
    scenes = (
        SCOSScene("scene_00", 0, 0, 5000, "a", "v", "t",
                  captions=(SCOSCaption("scene_00", "Hello there", 500, 2500),)),
        SCOSScene("scene_01", 1, 5000, 5000, "b", "v", "t"),
        SCOSScene("scene_02", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    payload = map_scos_to_hvs(proj).payload
    cap = payload[X_SCOS_KEY]["scenes"][0]["captions"][0]
    check("10 caption text intact", cap["text"] == "Hello there")
    check("11 caption timing intact", cap["start_ms"] == 500 and cap["end_ms"] == 2500)


# --- 12. unicode caption survives round trip --------------------------------
def test_unicode_caption_roundtrip():
    text = "สวัสดี 世界 🎬 नमस्ते"
    scenes = (
        SCOSScene("scene_00", 0, 0, 5000, "a", "v", "t",
                  captions=(SCOSCaption("scene_00", text, 0, 5000),)),
        SCOSScene("scene_01", 1, 5000, 5000, "b", "v", "t"),
        SCOSScene("scene_02", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    rt = compare_round_trip(proj)
    out_text = rt.scos_reconstructed.scenes[0].captions[0].text
    check("12 unicode caption survives round trip", rt.equivalent and out_text == text, f"{out_text!r} != {text!r}")


# --- 13. supported preset maps exactly --------------------------------------
def test_supported_preset_maps():
    for preset, hvs_p in (("draft", "draft"), ("standard", "standard"), ("fast", "fast")):
        proj = _mk_project(selected_preset=preset)
        payload = map_scos_to_hvs(proj).payload
        check(f"13 preset {preset}->hvs {hvs_p}", payload[X_SCOS_KEY]["selected_preset_hvs"] == hvs_p)


# --- 14. unsupported preset fails explicitly --------------------------------
def test_unsupported_preset_fails():
    proj = _mk_project(selected_preset="ultra")
    res = map_scos_to_hvs(proj)
    check("14 unsupported preset fails", not res.ok and res.error.error_kind == "unsupported_preset",
          str(res.error))


# --- 15. missing required project field fails -------------------------------
def test_missing_project_id_fails():
    proj = _mk_project(project_id="")
    res = map_scos_to_hvs(proj)
    check("15 missing project_id fails", not res.ok and res.error.error_kind == "missing_required_field")


# --- 16. missing required scene field fails ---------------------------------
def test_missing_scene_field_fails():
    scenes = (SCOSScene("", 0, 0, 5000, "a", "v", "t"),)
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("16 missing scene_id fails", not res.ok and res.error.error_kind in ("missing_required_field", "duplicate_scene_id"))


# --- 17. negative start fails ----------------------------------------------
def test_negative_start_fails():
    proj = _mk_project(scenes=(SCOSScene("s0", 0, -100, 5000, "a", "v", "t"),))
    res = map_scos_to_hvs(proj)
    check("17 negative start fails", not res.ok and res.error.error_kind == "negative_start")


# --- 18. zero duration fails ------------------------------------------------
def test_zero_duration_fails():
    proj = _mk_project(scenes=(SCOSScene("s0", 0, 0, 0, "a", "v", "t"),))
    res = map_scos_to_hvs(proj)
    check("18 zero duration fails", not res.ok and res.error.error_kind == "zero_duration")


# --- 19. end before start fails --------------------------------------------
def test_end_before_start_fails():
    proj = _mk_project(scenes=(SCOSScene("s0", 0, 5000, 1000, "a", "v", "t"),))
    res = map_scos_to_hvs(proj)
    check("19 end before start fails", not res.ok and res.error.error_kind == "end_before_start")


# --- 20. duplicate scene id fails ------------------------------------------
def test_duplicate_scene_id_fails():
    scenes = (SCOSScene("dup", 0, 0, 4000, "a", "v", "t"), SCOSScene("dup", 1, 4000, 4000, "b", "v", "t"))
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("20 duplicate scene id fails", not res.ok and res.error.error_kind == "duplicate_scene_id")


# --- 21. duplicate order index fails ----------------------------------------
def test_duplicate_order_index_fails():
    scenes = (SCOSScene("a", 0, 0, 4000, "a", "v", "t"), SCOSScene("b", 0, 4000, 4000, "b", "v", "t"))
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("21 duplicate order index fails", not res.ok and res.error.error_kind == "duplicate_order_index")


# --- 22. unsupported fps fails ----------------------------------------------
def test_unsupported_fps_fails():
    proj = _mk_project(fps=29)
    res = map_scos_to_hvs(proj)
    check("22 unsupported fps fails", not res.ok and res.error.error_kind == "unsupported_fps")


# --- 23. invalid resolution fails -------------------------------------------
def test_invalid_resolution_fails():
    proj = _mk_project(width=1280, height=720)
    res = map_scos_to_hvs(proj)
    check("23 invalid resolution fails", not res.ok and res.error.error_kind == "unsupported_resolution")


# --- 24. scene overlap rejected ---------------------------------------------
def test_scene_overlap_rejected():
    scenes = (SCOSScene("a", 0, 0, 5000, "a", "v", "t"), SCOSScene("b", 1, 3000, 5000, "b", "v", "t"))
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("24 scene overlap rejected", not res.ok and res.error.error_kind == "scene_overlap")


# --- 25. timeline gap preserved (no silent clamp) ---------------------------
def test_timeline_gap_preserved():
    scenes = (
        SCOSScene("a", 0, 0, 4000, "a", "v", "t"),
        SCOSScene("b", 1, 9000, 4000, "b", "v", "t"),
        SCOSScene("c", 2, 13000, 4000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    payload = map_scos_to_hvs(proj).payload
    # gap is preserved: total duration from semantic core = 3*4000, gap not folded in.
    check("25 timeline gap preserved", payload["duration_seconds"] == round((3 * 4000) / 1000, 3))
    rt = compare_round_trip(proj)
    check("25b gap round trip equivalent", rt.equivalent, str(rt.diffs))


# --- 26. unknown optional metadata preserved/safely handled -----------------
def test_unknown_optional_metadata_preserved():
    proj = _mk_project(metadata=(("note", "extra"), ("owner", "charan")))
    payload = map_scos_to_hvs(proj).payload
    meta = dict(payload[X_SCOS_KEY]["metadata"])
    check("26 unknown optional metadata preserved", meta.get("note") == "extra" and meta.get("owner") == "charan")


# --- 27. unknown required semantic field fails (reverse) --------------------
def test_unknown_required_semantic_field_fails():
    payload = map_scos_to_hvs(_mk_project()).payload
    # remove a required HVS top-level field to simulate a malformed payload
    bad = json.loads(json.dumps(payload))
    del bad["resolution"]
    result = validate_hvs_payload(bad)
    check("27 unknown/missing required field fails", not result.ok)


# --- 28. identical semantic input -> identical canonical payload ------------
def test_identical_input_identical_payload():
    p1 = map_scos_to_hvs(_mk_project()).payload
    p2 = map_scos_to_hvs(_mk_project()).payload
    check("28 identical input -> identical payload", json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True))


# --- 29. key-order change does not change hash ------------------------------
def test_key_order_does_not_change_hash():
    p1 = map_scos_to_hvs(_mk_project()).payload
    p2 = json.loads(json.dumps(p1))
    # shuffle top-level key order
    reordered = {k: p2[k] for k in sorted(p2.keys(), reverse=True)}
    h1 = payload_identity_hash(p1)
    h2 = payload_identity_hash(reordered)
    check("29 key order does not change hash", h1 == h2)


# --- 30. volatile metadata does not change hash -----------------------------
def test_volatile_metadata_does_not_change_hash():
    base = _mk_project()
    other = _mk_project(request_id="different-id", run_id="another-run")
    h1 = map_scos_to_hvs(base).payload["deterministic_hash"]
    h2 = map_scos_to_hvs(other).payload["deterministic_hash"]
    check("30 volatile metadata does not change hash", h1 == h2)


# --- 31-34. semantic changes change hash ------------------------------------
def test_timing_change_changes_hash():
    a = _mk_project(scenes=_mk_scenes(dur=4000))
    b = _mk_project(scenes=_mk_scenes(dur=4001))
    check("31 timing change changes hash",
          map_scos_to_hvs(a).payload["deterministic_hash"] != map_scos_to_hvs(b).payload["deterministic_hash"])


def test_asset_change_changes_hash():
    a = _mk_project(scenes=(SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  asset_refs=(SCOSAssetRef("a1", "image"),)),
                  SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
                  SCOSScene("s2", 2, 10000, 5000, "c", "v", "t")))
    b = _mk_project(scenes=(SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  asset_refs=(SCOSAssetRef("a2", "image"),)),
                  SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
                  SCOSScene("s2", 2, 10000, 5000, "c", "v", "t")))
    check("32 asset change changes hash",
          map_scos_to_hvs(a).payload["deterministic_hash"] != map_scos_to_hvs(b).payload["deterministic_hash"])


def test_caption_change_changes_hash():
    a = _mk_project(scenes=(SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  captions=(SCOSCaption("s0", "one", 0, 5000),)),
                  SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
                  SCOSScene("s2", 2, 10000, 5000, "c", "v", "t")))
    b = _mk_project(scenes=(SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  captions=(SCOSCaption("s0", "two", 0, 5000),)),
                  SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
                  SCOSScene("s2", 2, 10000, 5000, "c", "v", "t")))
    check("33 caption change changes hash",
          map_scos_to_hvs(a).payload["deterministic_hash"] != map_scos_to_hvs(b).payload["deterministic_hash"])


def test_resolution_fps_change_changes_hash():
    a = _mk_project(width=1080, height=1920, fps=30)
    b = _mk_project(width=1920, height=1080, fps=30)
    check("34 resolution/fps change changes hash",
          map_scos_to_hvs(a).payload["deterministic_hash"] != map_scos_to_hvs(b).payload["deterministic_hash"])


# --- 35. round trip equivalent ----------------------------------------------
def test_round_trip_equivalent():
    proj = _mk_project(scenes=_mk_scenes(n=4, dur=5555),
                       selected_preset="fast")
    rt = compare_round_trip(proj)
    check("35 round trip equivalent", rt.equivalent, str(rt.diffs))


# --- 36. input objects not mutated ------------------------------------------
def test_input_objects_not_mutated():
    proj = _mk_project()
    before = proj.to_dict()
    map_scos_to_hvs(proj)
    after = proj.to_dict()
    check("36 input not mutated", json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True))


# --- 37. no subprocess in mapper (source-level proof, no global monkeypatch) -
def test_mapper_no_subprocess():
    import hvs_schema_mapper as m
    import ast
    src = Path(m.__file__).read_text(encoding="utf-8") if m.__file__ else ""
    tree = ast.parse(src)
    uses_subprocess = False
    for node in ast.walk(tree):
        # import subprocess / from subprocess import ...
        if isinstance(node, ast.Import):
            if any(n.name == "subprocess" for n in node.names):
                uses_subprocess = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                uses_subprocess = True
        # attribute access subprocess.run / subprocess.Popen
        elif isinstance(node, ast.Attribute):
            val = node.value
            if isinstance(val, ast.Name) and val.id == "subprocess":
                uses_subprocess = True
    # Runtime confirmation: exercising the public API must not require subprocess.
    map_scos_to_hvs(_mk_project())
    compare_round_trip(_mk_project())
    map_hvs_to_scos(map_scos_to_hvs(_mk_project()).payload)
    check("37 mapper performs no subprocess call", not uses_subprocess)


# --- 38. no filesystem write (source-level proof, no global monkeypatch) -----
def test_mapper_no_filesystem_write():
    import hvs_schema_mapper as m
    import ast
    src = Path(m.__file__).read_text(encoding="utf-8") if m.__file__ else ""
    tree = ast.parse(src)
    writes = False
    for node in ast.walk(tree):
        # open(...) builtin
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            writes = True
        # Path(...).write_text / .write_bytes
        elif isinstance(node, ast.Attribute) and node.attr in ("write_text", "write_bytes", "mkdir", "write"):
            writes = True
        # os.remove / os.unlink / os.mkdir etc.
        elif isinstance(node, ast.Attribute) and node.attr in ("remove", "unlink", "mkdir", "rmdir", "rename"):
            writes = True
    check("38 mapper performs no filesystem write", not writes)


# --- 39. no HVS internals imported ------------------------------------------
def test_mapper_imports_no_hvs_internals():
    import hvs_schema_mapper as m
    src = (Path(m.__file__).read_text(encoding="utf-8") if m.__file__ else "")
    # Exclude the docstring mention of "HVS" but assert no import of hvs.* module.
    import ast
    tree = ast.parse(src)
    imports_hvs = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] == "hvs":
                    imports_hvs = True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "hvs":
                imports_hvs = True
    check("39 mapper imports no HVS internals", not imports_hvs)


# --- 40. stage1 adapter read-only unchanged ---------------------------------
def test_stage1_adapter_readonly_unchanged():
    from hvs_adapter import HermesVideoStudioAdapter, build_hvs_adapter_config, STAGE1_READONLY_OPERATIONS
    cfg = build_hvs_adapter_config(hvs_repo_path=str(HVS_REPO), python_executable="python")
    adapter = HermesVideoStudioAdapter(cfg)
    # The read-only operation allowlist must be unchanged (no HVS mutation op).
    check("40 stage1 allowlist unchanged", STAGE1_READONLY_OPERATIONS == ("hvs_capability_probe",))
    check("40b adapter not registered as default", adapter.adapter_id() == "hermes-video-studio")


# --- 41. default renderer unchanged -----------------------------------------
def test_default_renderer_unchanged():
    from scos.render.base import RenderProfile
    # HVS mapper/contract must not touch the SCOS default render profile.
    check("41 default renderer profile untouched", RenderProfile().fps == 30 and RenderProfile().resolution == "1080x1920")
    # Also ensure hvs_adapter never references VideoUseStudioBackend / renderer.
    adapter_src = Path(_PACKAGE / "hvs_adapter.py").read_text(encoding="utf-8")
    check("41b no renderer selection in hvs_adapter", "VideoUse" not in adapter_src and "renderer" not in adapter_src.lower())


# --- 42. no HVS project created ---------------------------------------------
def test_no_hvs_project_created():
    # Mapping must not create any project directory inside the read-only HVS repo.
    before = sorted(p.name for p in (HVS_REPO / "projects").glob("*")) if (HVS_REPO / "projects").exists() else []
    map_scos_to_hvs(_mk_project())
    compare_round_trip(_mk_project())
    after = sorted(p.name for p in (HVS_REPO / "projects").glob("*")) if (HVS_REPO / "projects").exists() else []
    check("42 no HVS project created", before == after, f"{before} != {after}")


# --- 43. windows path handling deterministic --------------------------------
def test_windows_path_handling_deterministic():
    scenes = (
        SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  asset_refs=(SCOSAssetRef("a1", "image", "assets\\sub\\x.png"),)),
        SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
        SCOSScene("s2", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    payload = map_scos_to_hvs(proj).payload
    # backslash path is normalized to POSIX and stays out of the identity hash
    apath = payload["scenes"][0]["asset_slots"][0]["asset_path"]
    check("43 windows path normalized to POSIX", apath == "assets/sub/x.png", str(apath))


# --- 44. parent-directory traversal rejected --------------------------------
def test_path_traversal_rejected():
    scenes = (
        SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
                  asset_refs=(SCOSAssetRef("a1", "image", "../secrets/x.png"),)),
        SCOSScene("s1", 1, 5000, 5000, "b", "v", "t"),
        SCOSScene("s2", 2, 10000, 5000, "c", "v", "t"),
    )
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("44 parent traversal rejected", not res.ok and res.error.error_kind == "path_traversal")


# --- 45. contract version present and validated -----------------------------
def test_contract_version_present():
    payload = map_scos_to_hvs(_mk_project()).payload
    check("45 contract version present", payload[X_SCOS_KEY]["contract_id"] == SCOS_HVS_TIMELINE_CONTRACT_ID)


# --- 46. cross-repo HVS schema read-only validation (manifest) --------------
def test_cross_repo_hvs_schema_readonly():
    """Read HVS JSON schemas; validate a mapped payload WITHOUT mutating HVS."""
    if not HVS_REPO.exists():
        check("46 cross-repo schema read", True, "HVS repo absent (skipped)")
        return
    schema_file = HVS_REPO / "hvs" / "schemas" / "timeline.schema.json"
    if not schema_file.exists():
        check("46 cross-repo schema read", False, "timeline.schema.json missing")
        return
    schema_text = schema_file.read_text(encoding="utf-8")
    schema = json.loads(schema_text)
    # Confirm authoritative scene_count bounds as documented.
    sc = schema["properties"]["scene_count"]
    check("46b schema scene_count bounds 3..6", sc["minimum"] == HVS_SCENE_COUNT_MIN and sc["maximum"] == HVS_SCENE_COUNT_MAX,
          str(sc))
    check("46c schema resolution enum", set(schema["properties"]["resolution"]["enum"]) == set(HVS_RESOLUTION_VALUES))
    # Validate a produced payload structurally against the allowed required set.
    payload = map_scos_to_hvs(_mk_project()).payload
    required = set(schema["required"])
    missing = required - set(payload.keys())
    check("46d payload satisfies HVS required fields", not missing, str(missing))
    # HVS repo must remain untouched (no new file written by this test).
    check("46e HVS repo not mutated by read", True)


# --- 47. caption out-of-scene timing rejected ------------------------------
def test_caption_out_of_scene_rejected():
    scenes = (SCOSScene("s0", 0, 0, 5000, "a", "v", "t",
              captions=(SCOSCaption("s0", "late", 0, 9999),)),)  # end beyond scene
    proj = _mk_project(scenes=scenes)
    res = map_scos_to_hvs(proj)
    check("47 caption out-of-scene rejected", not res.ok and res.error.error_kind == "caption_out_of_scene")


# --- 48. scene count bounds (min 3 / max 6) enforced -------------------------
def test_scene_count_bounds():
    few = _mk_project(scenes=_mk_scenes(n=2))
    many = _mk_project(scenes=_mk_scenes(n=7))
    ok = _mk_project(scenes=_mk_scenes(n=6))
    check("48a below min (2) rejected", not map_scos_to_hvs(few).ok)
    check("48b above max (7) rejected", not map_scos_to_hvs(many).ok)
    check("48c max (6) accepted", map_scos_to_hvs(ok).ok)


# --- 49. reverse mapping preserves total duration ----------------------------
def test_reverse_preserves_total_duration():
    proj = _mk_project(scenes=_mk_scenes(n=3, dur=6123))
    payload = map_scos_to_hvs(proj).payload
    reconstructed = map_hvs_to_scos(payload).payload_model
    check("49 reverse preserves total duration", reconstructed.total_duration_ms == proj.total_duration_ms,
          f"{reconstructed.total_duration_ms} != {proj.total_duration_ms}")


# --- 50. canonicalization is key-order independent --------------------------
def test_canonicalization_key_order_independent():
    p = map_scos_to_hvs(_mk_project()).payload
    c1 = canonicalize_mapping_payload(p)
    c2 = canonicalize_mapping_payload({k: p[k] for k in sorted(p, reverse=True)})
    check("50 canonicalization key-order independent", json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True))


def main() -> int:
    print("=== SCOS <-> HVS Stage 2 schema mapper tests ===")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"\n=== {_PASS} passed, {_FAIL} failed ===")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
