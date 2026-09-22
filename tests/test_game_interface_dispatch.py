"""Interface-offset dispatch naming (mi 25368 CheckAllReady).

Ground truth: three back-to-back interfaceOffsets searches for
IEnumerable<PlayerRef>/IEnumerator/IEnumerator<PlayerRef> resolve to
GetEnumerator/MoveNext/get_Current. They missed on three crisp gates
(slot decl prefix, typeof-ref span ending at the slot, _N arity key);
all three now resolve with every decline preserved.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_check_all_ready_names_all_dispatches(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25368]
    assert m.name == 'CheckAllReady'
    assert hex(m.addr) == '0x1806df770'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'object obj25 = enumerable12.GetEnumerator();' in text
    assert 'bool obj32 = obj5.MoveNext();' in text
    assert 'Fusion.PlayerRef playerRef1 = obj5.Current;' in text
    assert '/*indirect*/' not in text


def test_boxed_bool_folds_and_unbox_declines(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25368]
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'if (!obj32)' in text
    m2 = il.meta.methods[25872]
    assert m2.name == 'Update'
    assert hex(m2.addr) == '0x180547380'
    text2 = '\n'.join(dec.lift_method(m2, il.meta.typedefs[m2.declaring]))
    assert 'bool obj35 = enumerator3.MoveNext();' in text2
    assert 'object obj52 = enumerator8.MoveNext();' in text2
