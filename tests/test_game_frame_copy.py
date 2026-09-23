"""Frame-copy homes (mi 117615) and same-owner shared twins (mi 23900).

Ground truth: NetBitBuffer.WriteInt32AtOffset parks the frame base with
`mov r11,rsp`, so [r11+8] and later [rsp+0x50] are one home -- previously
`mem[8]`/`mem_8`/raw twins. ActorSpawner.Update calls same-typedef
Transform twins (get_parent triple, set_parent pair) that no receiver
proof can ever split -- the markers must stay.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def lift_text(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_frame_copy_homes_are_slots_not_raw(game_decompiler):
    text = lift_text(game_decompiler, 117615, 'WriteInt32AtOffset',
                     '0x180932790')
    assert 'mem[8' not in text
    assert 'mem_8' not in text
    assert 'this._offsetBits = offset;' in text
    assert 'this.WriteSlow(value, bits);' in text


def test_same_typedef_twins_stay_shared(game_decompiler):
    text = lift_text(game_decompiler, 23900, 'Update', '0x180513740')
    assert 'sub_182bf5c10/*shared body, 3 candidates*/' in text
    assert 'sub_182bf76f0/*shared body, 2 candidates*/' in text


def test_last_qaddr_sites_are_extinct(game_decompiler):
    # The promoted tree's only two `?addr` hits were `store into
    # untracked ?addr` elisions in copy-heavy methods (native
    # `mov r64,rsp` + indexed traffic); the homes resolve now.
    line = lift_text(game_decompiler, 104380,
                     'LineCircleIntersectionFactor', '0x180723720')
    assert '?addr' not in line
    assert 'mem[' not in line
    rest = lift_text(game_decompiler, 82799, 'RestBendingConstraint',
                     '0x181e79af0')
    assert '?addr' not in rest
    assert 'mem[' not in rest


def test_indexed_home_store_keeps_home(game_decompiler):
    # The final `?addr` (mi 65244): `lea rcx,[rcx+r12*4]` over named
    # home &s_1d0 keeps the home (honest composite) instead of ?addr;
    # only anonymous copies decline. The store uses the home's
    # address, so stale home values elsewhere don't alias it.
    text = lift_text(game_decompiler, 65244, 'UpdateGpuData',
                     '0x1829f2810')
    assert '?addr' not in text
    assert 'elided' not in text
    assert '((byte*)obj44 + num55 * 4)[0] = 4294967295;' in text
