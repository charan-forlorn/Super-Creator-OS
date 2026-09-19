import pytest

from scos.premium_media.motion import (
    AnimatedNumber, Camera2D, EffectStack, Keyframe, MotionLayer,
    PremiumMotionGraph, PremiumShot, ShotTransition, Transform2D, with_fingerprint,
)


def motion_graph():
    transform = Transform2D(
        x=AnimatedNumber(0, (Keyframe(0, 0), Keyframe(1.0, 120, 'ease_out'))),
        scale=AnimatedNumber(1.0, (Keyframe(0, 1.0), Keyframe(1.0, 1.08, 'ease_in_out'))),
    )
    shot = PremiumShot(
        shot_id='shot-01', start_s=0, end_s=3, purpose='hook', pacing='fast',
        camera=Camera2D(zoom=AnimatedNumber(1.0, (Keyframe(0, 1.0), Keyframe(3.0, 1.15, 'ease_in_out')))),
        layers=(
            MotionLayer('bg', 'media', 0, 0, 3, asset_id='asset-bg'),
            MotionLayer('headline', 'text', 1, 0, 3, text='One idea', transform=transform,
                        effects=EffectStack(glow=AnimatedNumber(0, (Keyframe(0,0), Keyframe(1,0.25,'ease_out'))))),
        ),
        transition_out=ShotTransition('crossfade', 0.35),
    )
    return PremiumMotionGraph((shot,), fps=30)


def test_valid_graph_fingerprints_deterministically():
    a = motion_graph(); b = motion_graph()
    assert a.validate() == ()
    assert a.fingerprint() == b.fingerprint()
    props = with_fingerprint(a)
    assert props['fingerprint'] == a.fingerprint()
    assert props['shots'][0]['layers'][1]['transform']['scale']['keyframes'][1]['easing'] == 'ease_in_out'


def test_rejects_non_contiguous_keyframes():
    shot = PremiumShot(
        shot_id='bad', start_s=0, end_s=2,
        layers=(MotionLayer('t', 'text', 1, 0, 2, text='x',
            transform=Transform2D(x=AnimatedNumber(0, (Keyframe(0.5, 1),)))),),
    )
    g = PremiumMotionGraph((shot,))
    assert any('first keyframe must start' in e for e in g.validate())


def test_rejects_shot_overlap_and_layer_escape():
    first = PremiumShot('a', 0, 2, layers=(MotionLayer('x','text',0,0,2,text='a'),))
    second = PremiumShot('b', 1.5, 3, layers=(MotionLayer('y','text',0,1.4,3,text='b'),))
    g = PremiumMotionGraph((first, second))
    errors = g.validate()
    assert any('shot overlap' in e for e in errors)
    assert any('escapes shot bounds' in e for e in errors)


def test_transition_and_effect_bounds_are_fail_closed():
    shot = PremiumShot('x', 0, 1, layers=(MotionLayer('l','text',0,0,1,text='x',
        transform=Transform2D(scale=AnimatedNumber(0), opacity=AnimatedNumber(2)),),),
        transition_out=ShotTransition('slide', 3),
    )
    errors = shot.validate()
    assert any('scale must be > 0' in e for e in errors)
    assert any('opacity must be in' in e for e in errors)
    assert any('duration must be within' in e for e in errors)