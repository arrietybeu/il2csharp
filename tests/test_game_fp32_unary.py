"""Unregistered pure-FP32-unary leaves keep one float arg and result.

Ground truth: AudioVolumeSliders 23548/23549 call the CRT log10f at
0x1804cdb00. The lift used to spray four stale GPR arguments, bind an
`object` result, and drop the XMM0 float (`real2 = 0f * 20.0f`).
"""
import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


@pytest.mark.parametrize('mi,name,label', [
    (23548, 'SetMusicVolumeInternal', 'Music'),
    (23549, 'SetSFXVolumeInternal', 'SFX'),
])
def test_audio_log10_leaf(game_decompiler, mi, name, label):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'float real2 = (float)sub_1804cdb00(volume);' in body
    assert 'real3 = real2 * 20.0f;' in body
    assert 'this.audioMixer.SetFloat("' + label + '", real3)' in body
    assert 'real2 = 0f * 20.0f' not in body
    assert 'obj14 = sub_1804cdb00(' not in body


@pytest.mark.parametrize('mi,name,count', [
    (26741, 'FixedUpdate', 2),
    (27765, 'Spawned', 1),
])
def test_audio_log10_conditional_consume(game_decompiler, mi, name, count):
    # The float result flows through a flag test + conditional branch
    # before the scalar consume (call; test; je; ...; mulss xmm0).
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert body.count(
        'sub_1804cdb00(UnityEngine.PlayerPrefs.GetFloat(') == count
    assert '0f * 20.0f' not in body
    assert 'obj44 = sub_1804cdb00(' not in body
    assert 'obj29 = sub_1804cdb00(' not in body


def test_slider_log10_conversion_and_copy(game_decompiler):
    # Site 1 fires through cvtss2sd into double/int chains; site 3
    # fires; site 2 honestly declines (its argument carries a bare `?`
    # the output could never spell, so the call keeps today's shape).
    il, dec = game_decompiler
    m = il.meta.methods[15267]
    assert m.name == 'SliderLerpUnclamped'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert body.count('sub_1804cdb00(') == 3
    assert body.count('sub_1804cd9d0(') == 2
    assert 'sub_1804cdb00(real1 & float.NaN)' in body
    assert 'sub_1804cd9d0((double)(real' in body
    assert '(double)(real' in body
    assert '(int)(5.0d - (double)(real' in body
    assert '(float)sub_1804cdb00' in body


def test_binary_op_keeps_honest_spelling(game_decompiler):
    # 0x180001cf0 is `mulss xmm0,xmm1` (binary): the proof declines on
    # the XMM1 input instead of dropping an argument, so the call keeps
    # today's object spray rather than a confidently-wrong unary float.
    import re
    il, dec = game_decompiler
    m = il.meta.methods[104653]
    assert m.name == 'CalculatePathsThreaded'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert re.search(r'object obj\d+ = sub_180001cf0\(', body) is not None
    assert '(float)sub_180001cf0' not in body
