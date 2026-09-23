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
    assert 'float real2 = sub_1804cdb00(volume);' in body
    assert 'real3 = real2 * 20.0f;' in body
    assert 'this.audioMixer.SetFloat("' + label + '", real3)' in body
    assert 'real2 = 0f * 20.0f' not in body
    assert 'obj14 = sub_1804cdb00(' not in body
    assert '(float)sub_1804cdb00' not in body
