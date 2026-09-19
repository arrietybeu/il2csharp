"""Byte-range provenance for stack copies of metadata-proven value types."""
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.expr import Expr
from il2cpp.text import sdisp, reg_name, _int_lit
from il2cpp.names import repr_f32, repr_f64


_COLOR_NAMES = {
    (1.0, 0.0, 0.0, 1.0): 'UnityEngine.Color.red',
    (0.0, 1.0, 0.0, 1.0): 'UnityEngine.Color.green',
    (0.0, 0.0, 1.0, 1.0): 'UnityEngine.Color.blue',
    (0.0, 1.0, 1.0, 1.0): 'UnityEngine.Color.cyan',
    (1.0, 1.0, 1.0, 1.0): 'UnityEngine.Color.white',
    (0.0, 0.0, 0.0, 1.0): 'UnityEngine.Color.black',
}


def _color_text(raw16):
    if len(raw16) != 16:
        return None
    vals = struct.unpack('<4f', raw16)
    name = _COLOR_NAMES.get(vals)
    if name is not None:
        return name
    return 'new UnityEngine.Color(%s, %s, %s, %s)' % tuple(repr_f32(v) for v in vals)


class _AggregatesMixin:
    def _stack_address(self, ins):
        if ins.memory_index != IReg.NONE:
            return None
        base = reg_name(ins.memory_base)
        if base == 'RSP':
            return self.rsp_delta + sdisp(ins.memory_displacement)
        value = dict.get(self.regs, base)
        offset = getattr(value, '_stack_offset', None)
        return None if offset is None else offset + sdisp(ins.memory_displacement)

    def _fragment(self, origin, offset, width):
        # Preserve all bytes of a SIMD copy even when its display text names
        # the first scalar field. Only exact scalar consumers may use that text.
        scalar = self._piece_value(origin, offset, width, None)
        result = Expr(scalar.text if scalar is not None else origin.text,
                      scalar.ty if scalar is not None else None,
                      scalar.kind if scalar is not None else 'bits')
        result._slice = (origin, offset, width)
        return result

    def _piece_value(self, origin, offset, width, expected, depth=0):
        if depth > 8:
            return None
        data = getattr(origin, '_bytes', None)
        if data is not None:
            if offset + width > len(data) or expected is None:
                return None
            raw = data[offset:offset + width]
            te = self.il._type_enum(expected)
            if te == 0x11:
                td = self._td_of(expected)
                if td is not None and self.meta.typedefs[td].is_valuetype and self.il.type_name(expected) == 'UnityEngine.Color':
                    if offset == 0 and width == 16:
                        return Expr(_color_text(raw), expected, self._ty_kind(expected))
                    return None
            if te == 0x0c and width == 4:
                text = repr_f32(struct.unpack('<f', raw)[0])
            elif te == 0x0d and width == 8:
                text = repr_f64(struct.unpack('<d', raw)[0])
            else:
                text = self._fimm(str(int.from_bytes(raw, 'little')), expected)
            return Expr(text, expected, self._ty_kind(expected))
        parts = getattr(origin, '_parts', None)
        if parts is not None:
            for tlo, po, poff, pw in parts:
                if tlo <= offset and offset + width <= tlo + pw:
                    return self._piece_value(po, poff + (offset - tlo), width, expected, depth + 1)
            return None
        ty = origin.ty
        if ty is None:
            if offset == 0 and expected is not None and _int_lit(origin.text) is not None:
                return Expr(self._fimm(origin.text, expected), expected, self._ty_kind(expected))
            return None
        size = self.il._sf_field_size(ty, 0)
        if offset == 0 and size == width:
            if expected is None or self.il._closed_type_key(ty) == self.il._closed_type_key(expected):
                return origin
            if _int_lit(origin.text) is not None:
                return Expr(self._fimm(origin.text, expected), expected, self._ty_kind(expected))
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        chain = self.il.instance_field_chain(td) or {}
        for field_offset, (name, ti) in sorted(chain.items()):
            start = field_offset - 0x10
            ft = self.il.types[ti]
            size = self.il._sf_field_size(ft, 0)
            if size is not None and start <= offset and offset + width <= start + size:
                value = Expr(origin.text + '.' + name, ft, self._ty_kind(ft))
                return self._piece_value(value, offset - start, width, expected, depth + 1)
        return None

    def _stack_store(self, start, width, value):
        # Memory facts live with register facts, so CFG merges cannot reuse
        # another path's packed bytes. Overlapping stores retain only the
        # unaffected ranges of the previous value.
        for key, old in list(self.regs.items()):
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            hi = lo + n
            if lo >= start + width or hi <= start:
                continue
            del self.regs[key]
            part = getattr(old, '_slice', None)
            if part is None:
                continue
            origin, offset, _ = part
            if lo < start:
                self.regs[f'!mem:{lo}:{start-lo}'] = self._fragment(origin, offset, start-lo)
            if hi > start + width:
                cut = start + width - lo
                self.regs[f'!mem:{start+width}:{hi-start-width}'] = self._fragment(origin, offset+cut, hi-start-width)
        if value is not None:
            part = getattr(value, '_slice', None)
            if part is None:
                part = (value, 0, width)
            take = part[2] if part[2] < width else width
            if take > 0:
                self.regs[f'!mem:{start}:{take}'] = self._fragment(value, 0, take)

    def _stack_piece(self, start, width, expected=None):
        for key, value in self.regs.items():
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            part = getattr(value, '_slice', None)
            if part is not None and lo <= start and start + width <= lo + n:
                origin, offset, _ = part
                if expected is not None:
                    return self._piece_value(origin, offset + start - lo, width, expected)
                return self._fragment(origin, offset + start - lo, width)
        tiles = []
        for key, value in self.regs.items():
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            if n <= 0:
                continue
            part = getattr(value, '_slice', None)
            if part is None:
                continue
            tiles.append((lo, part[0], part[1], n))
        tiles.sort()
        cur, acc = start, []
        for lo, origin, off, n in tiles:
            if lo + n <= cur:
                continue
            if lo != cur:
                return None
            take = min(n, start + width - cur)
            acc.append((cur - start, origin, off + (cur - lo), take))
            cur += take
            if cur >= start + width:
                break
        if cur < start + width or not acc:
            return None
        result = Expr('', None, 'bits')
        result._parts = acc
        return result

    def _stack_struct(self, address, ty):
        size = self.il._sf_field_size(ty, 0)
        if size is None:
            return None
        whole = self._stack_piece(address, size, ty)
        if whole is not None and whole.text:
            return whole.text
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        chain = self.il.instance_field_chain(td) or {}
        fields = []
        for off, (name, ti) in sorted(chain.items()):
            ft = self.il.types[ti]
            width = self.il._sf_field_size(ft, 0)
            if width is None or off < 0x10 or off - 0x10 + width > size:
                return None
            value = self._stack_piece(address + off - 0x10, width, ft)
            if value is None:
                return None
            fields.append(name + ' = ' + value.text)
        return ('new ' + self.il.type_name(ty) + ' { ' + ', '.join(fields) + ' }') if fields else None

    def _copied_struct_arg(self, text, ty):
        if not text.startswith('&') or not self._byval_struct(ty):
            return None
        addresses = [key for key, name in self.stack_map.items() if name == text[1:]]
        return self._stack_struct(addresses[0], ty) if len(addresses) == 1 else None

    def _aggregate_load(self, ins):
        width = MemorySizeExt.size(ins.memory_size)
        address = self._stack_address(ins)
        if address is not None:
            frag = self._stack_piece(address, width)
            if frag is not None and not frag.text:
                frag.text = self.slot_var(ins.memory_displacement)
            return frag
        if ins.memory_base == IReg.RIP or ins.memory_index != IReg.NONE:
            return None
        base = dict.get(self.regs, reg_name(ins.memory_base))
        if base is None:
            return None
        td = self._td_of(base.ty)
        if td is None:
            return None
        offset = sdisp(ins.memory_displacement)
        if self.meta.typedefs[td].is_valuetype:
            frag = self._fragment(base, offset, width)
            if frag.text != base.text:
                return frag
            return None
        chain = self.il.instance_field_chain(td) or {}
        if offset in chain:
            return None
        for off, (name, ti) in chain.items():
            ft = self.il.types[ti]
            ftd = self._td_of(ft)
            if ftd is None or not self.meta.typedefs[ftd].is_valuetype:
                continue
            size = self.il._sf_field_size(ft, 0)
            if size is not None and off <= offset and offset + width <= off + size:
                container = Expr(base.text + '.' + name, ft, 'obj')
                frag = self._fragment(container, offset - off, width)
                if frag.text != container.text or frag.ty is not None:
                    return frag
        return None
