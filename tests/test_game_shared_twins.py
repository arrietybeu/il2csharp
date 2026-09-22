"""Array receivers resolve their shared Clone; same-typedef twins stay shared.

Ground truth: `sub_181c07770` folds 9 instance Clone() bodies. A byte[]
field home (275/326) or Delegate[] home (4047) can only dispatch to
System.Array.Clone -- arrays have no subclasses. The 2-candidate
string twins (144, Equals/op_Equality over one typedef) can never
split and keep their markers.
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


def test_byte_array_field_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 275, 'get_Value', '0x181ad0920')
    assert 'object obj4 = this.m_aValue.Clone();' in text
    assert 'shared body' not in text


def test_second_byte_array_owner_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 326, 'HashFinal', '0x181ad61f0')
    assert 'object obj8 = this.state.Clone();' in text
    assert 'shared body' not in text


def test_delegate_array_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 4047, 'GetInvocationList',
                     '0x181cff280')
    assert 'System.Delegate[] delegateArray1 = this.delegates.Clone();' \
        in text
    assert 'shared body' not in text


def test_same_typedef_string_twins_stay_shared(game_decompiler):
    text = lift_text(game_decompiler, 144, 'ReadReference', '0x181ae3120')
    assert text.count('sub_181af7520/*shared body, 2 candidates*/') == 5
