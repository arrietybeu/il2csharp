"""Dead-`unknown`-store elimination pinned on LagCompensationUtils 63027
(`vector32 = unknown;` + `vector32 = 0;` twins) and RaycastModifier
105455 (`object obj87 = unknown;` + `obj87 = 0;` strip, plus a use-site
that must survive).
"""
import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


def test_lagcomp_twins_drop_first_store(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[63027]
    assert m.name == 'ClosestDistanceBetweenLines'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert body.count('vector32 = unknown;') == 3
    assert 'vector32 = 0;' in body
    # non-twins keep their honest spelling (different next LHS, use of
    # the value, typed decl without a same-name overwrite)
    assert 'vector31 = unknown;' in body
    assert 'float real8 = unknown;' in body


def test_raycast_decl_strips_and_use_survives(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[105455]
    assert m.name == 'ValidateLine'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert body.count('obj87 = unknown;') == 2
    assert 'object obj87;' in body
    assert 'Vector3 vector35 = obj87.normalized;' in body
