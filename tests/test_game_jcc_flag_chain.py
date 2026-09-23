"""Two Jcc instructions after one UCOMISS retain the comparison operands."""

import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


@pytest.mark.parametrize('mi,name,label', [
    (23548, 'SetMusicVolumeInternal', 'Music'),
    (23549, 'SetSFXVolumeInternal', 'SFX'),
])
def test_audio_volume_parity_then_not_equal(game_decompiler, mi, name, label):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'if (float.IsNaN(volume))' in body
    assert 'else if (volume != 0f)' in body
    assert 'unknown != unknown' not in body
    assert 'this.audioMixer.SetFloat("' + label + '", real1)' in body
