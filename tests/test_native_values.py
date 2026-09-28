"""Small real-x64 instruction regressions for Review 78's TODO fixes."""
from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp import Expr, Lifter

BOOL = (0, 0x02 << 16)
SHORT = (0, 0x06 << 16)
INT = (0, 0x08 << 16)
FLOAT = (0, 0x0C << 16)
ARRAY = (0x9000, 0x1D << 16)
OBJECT = (0, 0x12 << 16)


def lifter(regs=None, fields=None, field_types=None):
    types = field_types or [BOOL, BOOL]
    chain = fields if fields is not None else {0x10: ('first', 0), 0x11: ('second', 1)}
    il = NS(types=types, _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            instance_field_chain=lambda td: chain,
            type_from_ptr=lambda ptr: INT if ptr == ARRAY[0] else None,
            # array element stride: references are 8 bytes
            _sf_field_size=lambda fty, depth: 8 if fty is not None else None)
    meta = NS(typedefs=[NS(is_valuetype=False)])
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS()
    lift.regs = dict(regs or {'RCX': Expr('this', OBJECT, 'obj')})
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.addr_of = {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    return lift


def execute(lift, hex_bytes):
    insns = list(Decoder(64, bytes.fromhex(hex_bytes), ip=0x1000))
    for index, ins in enumerate(insns):
        lift._insn(ins, insns, index, None, insns[-1].next_ip)
    return [text for _, text, _ in lift.out]


@pytest.mark.parametrize('value,expected', [
    ('0101', ['this.first = true;', 'this.second = true;']),
    ('0100', ['this.first = true;', 'this.second = false;']),
    ('0001', ['this.first = false;', 'this.second = true;']),
    ('0000', ['this.first = false;', 'this.second = false;']),
])
def test_packed_boolean_word_store_preserves_both_fields(value, expected):
    assert execute(lifter(), '66c74110' + value) == expected


def test_packed_boolean_dword_store_preserves_all_four_bytes():
    lift = lifter(fields={0x10+i: (f'b{i}', i) for i in range(4)}, field_types=[BOOL]*4)
    assert execute(lift, 'c7411001000100') == [
        'this.b0 = true;', 'this.b1 = false;', 'this.b2 = true;', 'this.b3 = false;']


def test_single_byte_boolean_store_is_unchanged():
    assert execute(lifter(), 'c6411001') == ['this.first = true;']


def test_word_integer_immediate_is_not_an_unknown():
    lift = lifter(fields={0x10: ('value', 0)}, field_types=[SHORT])
    assert execute(lift, '66c741103412') == ['this.value = 4660;']


def test_signed_short_immediate_is_interpreted_at_field_width():
    lift = lifter(fields={0x10: ('value', 0)}, field_types=[SHORT])
    assert execute(lift, '66c74110ffff') == ['this.value = -1;']


@pytest.mark.parametrize('opcode,operator', [('03','+'), ('2b','-'), ('23','&'), ('0b','|'), ('33','^')])
def test_register_arithmetic_reads_its_memory_source(opcode, operator):
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    execute(lift, '41' + opcode + '4c8020')  # op ecx,[r8+rax*4+20h]
    assert lift.regs['RCX'].text == f'30 {operator} ammo[slot]'
    assert '?' not in lift.regs['RCX'].text


def test_unresolved_memory_source_stays_visible_not_a_zero_default():
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'RAX': Expr('slot', INT, 'int')})
    execute(lift, '412b4c8020')
    assert '?' in lift.regs['RCX'].text or 'mem_' in lift.regs['RCX'].text
    assert lift.regs['RCX'].text != '30'


def test_integer_address_math_does_not_hint_an_array_as_int():
    lift = lifter({'R8': Expr('t0', ARRAY, 'arr')})
    execute(lift, '4983c020')  # add r8,20h (skip array header)
    assert lift._type_hints.get('t0') != INT
    assert lift.regs['R8'].ty == ARRAY
    assert lift.regs['R8'].kind == 'arr'


def test_unknown_scalar_arithmetic_still_receives_integer_hint():
    lift = lifter({'R8': Expr('t0', None, '?')})
    execute(lift, '4983c002')
    assert lift._type_hints['t0'] == INT


def test_three_operand_imul_reads_its_memory_source():
    lift = lifter({'R8': Expr('ammo', ARRAY, 'arr'), 'RAX': Expr('slot', INT, 'int')})
    execute(lift, '416b4c802003')
    assert lift.regs['RCX'].text == 'ammo[slot] * 3'


@pytest.mark.parametrize('fields,types,value', [
    ({0x10: ('first', 0)}, [BOOL], '0101'),                 # unknown second byte
    ({0x10: ('first', 0), 0x12: ('second', 1)}, [BOOL]*2, '0101'),  # padding
    ({0x10: ('first', 0), 0x11: ('second', 1)}, [BOOL,INT], '0101'),
    ({0x10: ('first', 0), 0x11: ('first', 1)}, [BOOL]*2, '0101'),  # duplicate identity
    ({0x10: ('first', 0), 0x11: ('second', 1)}, [BOOL]*2, '0102'),  # noncanonical bool
])
def test_unproven_wide_boolean_store_is_not_split_or_narrowed(fields, types, value):
    lift = lifter(fields=fields, field_types=types)
    output = execute(lift, '66c74110' + value)
    assert len(output) == 1
    assert 'ushort*' in output[0] and '.first =' not in output[0]
    assert str(int.from_bytes(bytes.fromhex(value), 'little')) in output[0]
    from il2cpp import Decompiler
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp
    rendered = '\n'.join(Decompiler.__new__(Decompiler)._render(output))
    parser = Parser(Language(tree_sitter_c_sharp.language()))
    assert not parser.parse(('class C { void M() {' + rendered + '} }').encode()).root_node.has_error


def test_explicit_layout_is_not_assumed_nonoverlapping():
    lift = lifter()
    lift.meta.typedefs[0].flags = 0x10
    output = execute(lift, '66c741100101')
    assert len(output) == 1 and 'ushort*' in output[0]


def test_packed_store_materializes_old_field_values_before_both_writes():
    lift = lifter({'RCX': Expr('this', OBJECT, 'obj'),
                   'R8': Expr('this.first', BOOL, 'int'),
                   'R9': Expr('this.second', BOOL, 'int')})
    output = execute(lift, '66c741100101')
    assert output[:2] == ['var t0 = this.first;', 'var t1 = this.second;']
    assert output[2:] == ['this.first = true;', 'this.second = true;']
    assert lift.regs['R8'].text == 't0' and lift.regs['R9'].text == 't1'


def test_register_memory_arithmetic_does_not_invent_a_second_store():
    lift = lifter({'RCX': Expr('capacity', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    assert execute(lift, '412b4c8020') == []
    assert lift.regs['RCX'].text == 'capacity - ammo[slot]'


def test_unsplit_wide_store_preserves_known_first_field_old_value():
    lift = lifter({'RCX': Expr('this', OBJECT, 'obj'),
                   'R8': Expr('this.first', BOOL, 'int')},
                  fields={0x10: ('first', 0)}, field_types=[BOOL])
    output = execute(lift, '66c741100101')
    assert output[0] == 'var t0 = this.first;'
    assert 'ushort*' in output[1]
    assert lift.regs['R8'].text == 't0'


@pytest.mark.parametrize('encoding,guarded', [
    ('b801000000c3', False),  # straight-line
    ('750190c3', False),     # forward-only branch
    ('9075fd', False),       # direct loop: structured header replay is safe
    ('75fe', False),         # direct self-loop
    ('ffe0', True),          # unresolved/table/indirect dispatch
    ('e9fbefffff', False),   # tail to code outside the current extent
])
def test_memory_rhs_guard_is_reserved_for_unmodelled_control_flow(encoding, guarded):
    from il2cpp import Decompiler
    insns = list(Decoder(64, bytes.fromhex(encoding), ip=0x1000))
    assert Decompiler._memory_rhs_needs_loop_guard(insns) is guarded


@pytest.mark.parametrize('encoding', ['412b4c8020', '416b4c802003'])
def test_forced_indirect_dispatch_guard_keeps_memory_operand_honest(encoding):
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    lift._memory_rhs_loop_guard = True
    execute(lift, encoding)
    assert 'ammo[slot]' not in lift.regs['RCX'].text
    assert '?' in lift.regs['RCX'].text


def test_direct_loop_can_recover_memory_operand_after_header_replay():
    from il2cpp import Decompiler

    loop = list(Decoder(64, bytes.fromhex('412b4c802075fa'), ip=0x1000))
    assert Decompiler._memory_rhs_needs_loop_guard(loop) is False

    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    lift._memory_rhs_loop_guard = False
    execute(lift, '412b4c8020')
    assert lift.regs['RCX'].text == '30 - ammo[slot]'
