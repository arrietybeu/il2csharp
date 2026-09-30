"""Parameterized interface dispatch renders the managed call.

Ground truth: GraphUpdateProcessor.ProcessRegularUpdates (mi 104498)
calls CanUpdateAsync (slot 3) through 0x180006590 with (slot, iface,
receiver, R9 arg). The R9 value is live on entry and typed, so the
site renders the one-argument managed call. Untyped-R9 sites
(mi 104027), multi-parameter targets (mi 6160) and the writes-first
impostor keep the honest marker.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_can_update_async_resolves(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[104498]
    assert m.name == 'ProcessRegularUpdates'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'guoSingle1.graph.CanUpdateAsync(guoSingle1.obj)' in text


def test_untyped_r9_keeps_the_marker(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[104027]
    assert m.name == 'OnEnable'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180006020(26, typeof(Pathfinding.IAstarAI), this.ai, action1)' in text


def test_multi_param_target_keeps_the_marker(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[6160]
    assert m.name == 'FlushFinalBlock'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180003a40(4, typeof(System.Security.Cryptography.ICryptoTransform)' in text


def test_writes_first_impostor_scores_zero(game_decompiler):
    il, dec = game_decompiler
    lif = dec.L if hasattr(dec, 'L') else None
    assert lif is not None
    assert lif._iface_dispatch_arity(0x180540f50) == 0
    assert lif._iface_dispatch_arity(0x180006020) == 1
    assert lif._iface_dispatch_arity(0x180002210) == 0
