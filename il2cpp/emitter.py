from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.arm64 import Arm64Lifter, is_arm64_binary
from il2cpp.common import compressed_int, csharp_type_name, i32, i64, read_compressed_uint, u16, u32, u64
from il2cpp.csharp import FA_INITONLY, FA_LITERAL, FA_STATIC, FIELD_VIS, METH_VIS, TYPE_VIS, UsingTracker, field_attrs, nameof_sugar, strip_namespaces
from il2cpp.lifter import Lifter
from il2cpp.metadata import ImageDef, MethodDef, TypeDef
from il2cpp.names import repr_f32, repr_f64, safe_ident, sanitize
from il2cpp.runtime.core import Il2Cpp
from il2cpp.runtime.meta import meta_lit_repr
from il2cpp.text import MANGLED_IDENT_RX, reindent

class Emitter:
    def __init__(self, il2: Il2Cpp, out_dir: str, asm_comments=False,
                 with_bodies=True, max_methods=None, verbose=False, type_filter=None):
        self.il = il2
        self.meta = il2.meta
        self.out_dir = out_dir
        self.asm_comments = asm_comments
        self.with_bodies = with_bodies
        self.max_methods = max_methods
        self.verbose = verbose
        self.type_filter = type_filter.casefold() if type_filter else None
        self.decompiler_error = None
        _a64 = with_bodies and HAVE_CAPSTONE and is_arm64_binary(il2.bin)
        if _a64:
            self.lifter = Arm64Lifter(il2, asm_comments=asm_comments)
        elif with_bodies and HAVE_ICED and not is_arm64_binary(il2.bin):
            self.lifter = Lifter(il2, asm_comments=asm_comments)
        else:
            self.lifter = None
        self.decompiler = None
        if self.lifter:
            try:
                from il2cpp.dec import Decompiler
                from il2cpp.arm64_dec import Arm64Decompiler
                self.decompiler = (Arm64Decompiler(self.lifter) if _a64
                                   else Decompiler(self.lifter))
            except Exception as ex:
                self.decompiler_error = str(ex)
                self.decompiler = None
        self.lifted = 0
        self.failed = 0
        self.fallbacks = 0
        self.emit_failed = 0

    # -- type header ------------------------------------------------------
    def type_decl_line(self, td: TypeDef) -> List[str]:
        f = td.flags
        vis = TYPE_VIS.get((f >> 0) & 7, '')
        if td.declaring < 0 and (f & 7) > 1:
            vis = 'internal '  # a nested form on a top-level row: unreadable
        lines = []
        if (f & 0x20) and not (f & 0x80):  # interface, not abstract-class
            kw = vis + 'partial interface'
        elif td.is_enum:
            kw = vis + 'enum'
        elif td.is_valuetype:
            kw = vis + 'partial struct'
        else:
            kw = vis + 'abstract sealed partial class'
            if not (f & 0x80):
                kw = kw.replace('abstract ', '')
            if not (f & 0x100):
                kw = kw.replace('sealed ', '')
        name = td.name
        gparams = ''
        if td.generic_container != -1 and not td.is_enum:
            gc = self.meta.generic_containers[td.generic_container]
            gp = []
            for k in range(gc[1]):
                gi = gc[3] + k
                if gi < len(self.meta.generic_parameters):
                    gp.append(self.meta.generic_parameters[gi][1])
            gparams = '<%s>' % ', '.join(gp) if gp else ''
        base = []
        if td.parent >= 0 and not td.is_enum and not td.is_valuetype:
            pt = self.il.types[td.parent] if td.parent < len(self.il.types) else None
            pn = self.il.type_name(pt) if pt else None
            if pn and pn != 'object':
                base.append(pn)
        if td.interfaces_count:
            for k in range(td.interfaces_count):
                ii = self.meta.interfaces[td.interfaces_start + k]
                t = self.il.types[ii] if ii < len(self.il.types) else None
                if t:
                    base.append(self.il.type_name(t))
        if td.is_valuetype and not td.is_enum and not base:
            pass
        hdr = '%s %s%s' % (kw, sanitize(name), gparams)
        if base:
            hdr += ' : ' + ', '.join(base)
        lines.append(hdr)
        return lines

    def enum_body(self, td: TypeDef) -> List[str]:
        out = []
        for k, fi in enumerate(self.meta.type_fields(td)):
            if k == 0:
                continue  # value__
            f = self.meta.fields[fi]
            v = self.default_value_of(fi)
            out.append('        %s = %s,' % (sanitize(f.name), v if v is not None else '?'))
        return out

    def default_value_of(self, field_row) -> Optional[str]:
        dv = self.meta.field_default_values.get(field_row)
        if not dv:
            return None
        ti, di = dv
        return self.parse_default(ti, di)

    def parse_default(self, type_idx, data_idx, param=False) -> Optional[str]:
        if data_idx is None or data_idx < 0:
            return None
        t = self.il.types[type_idx] if 0 <= type_idx < len(self.il.types) else None
        if t is None:
            return None
        te = self.il._type_enum(t)
        d = self.meta.d
        off = self.meta.dv_off + data_idx
        # v29+ stores i4/u4/string (and enums over those underlyings) in the
        # WriteCompressedUInt32 format; everything else stays raw fixed-size.
        v29 = self.meta.version >= 29
        try:
            if te in (0x55, 0x11):  # enum: encode via the underlying type
                td = self.meta.typedefs[t[0]] if t[0] < len(self.meta.typedefs) else None
                if not td or td.element < 0:
                    return None
                te = self.il._type_enum(self.il.types[td.element])
            if te == 0x02:
                return 'true' if d[off] else 'false'
            if te in (0x04, 0x05):
                v = d[off]
                return str(v - 0x100 if te == 0x04 and v >= 0x80 else v)
            if te == 0x03:
                c = chr(u16(d, off))
                if c.isprintable():
                    return "'%s'" % c
                return "'\\u%04x'" % u16(d, off)
            if te in (0x06, 0x07):
                v = u16(d, off)
                return str(v - 0x10000 if te == 0x06 and v >= 0x8000 else v)
            if te == 0x08:
                return str(compressed_int(d, off)[0] if v29 else i32(d, off))
            if te == 0x09:
                return str(read_compressed_uint(d, off)[0] if v29 else u32(d, off))
            if te == 0x0a:
                return str(i64(d, off))
            if te == 0x0b:
                return str(u64(d, off))
            if te in (0x18, 0x19):
                return str(i32(d, off))
            if te == 0x0c:
                return repr_f32(struct.unpack_from('<f', d, off)[0])
            if te == 0x0d:
                return repr_f64(struct.unpack_from('<d', d, off)[0])
            if te == 0x0e:
                if v29:
                    ln, lnlen = compressed_int(d, off)
                else:
                    ln, lnlen = i32(d, off), 4
                s = d[off + lnlen:off + lnlen + max(0, min(ln, 512))].decode('utf-8', 'replace')
                return meta_lit_repr(s)
        except Exception:
            return None
        return None

    # -- members ------------------------------------------------------------
    def method_sig(self, m: MethodDef, td: TypeDef) -> str:
        parts = []
        f = m.flags
        vis = METH_VIS.get((f >> 0) & 7, '')
        if (f & 0x400) and (td.flags & 0x80):
            pass
        mods = vis
        if m.is_static:
            mods += 'static '
        if f & 0x400:
            mods += 'virtual '
            if f & 0x40:
                pass
            if (td.flags & 0x80) and (f & 0x400) and not (f & 0x40):
                mods = mods.replace('virtual ', 'override ') if not (f & 0x100) else mods
            if f & 0x40 and not (f & 0x80):
                pass
        if f & 0x400 and (f & 0x100):
            mods += 'sealed '
        if (td.flags & 0x80) and (f & 0x400) and not (f & 0x40):
            mods = vis + ('static ' if m.is_static else '') + 'override '
            if f & 0x100:
                mods += 'sealed '
        if (f & 0x400) and (td.flags & 0x80) == 0 and (f & 0x40) == 0:
            mods = mods  # virtual new
        # abstract
        if (td.flags & 0x80) and (f & 0x400) and not (f & 0x40) and (f & 0x400):
            if f & 0x400 and not (f & 0x40) and (td.flags & 0x80):
                pass
        if f & 0x400 and not (f & 0xFC) and False:
            pass
        # final cleanup for abstract
        if (f & 0x400) and (f & 0x40) and (td.flags & 0x80):
            mods = vis + 'abstract ' if m.flags & 0x400 else mods
        rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
        rtname = self.il.type_name(rt) if rt else 'void'
        if rtname == 'void':
            pass
        name = sanitize(csharp_type_name(m.name))
        gp = ''
        if m.generic_container != -1:
            gc = self.meta.generic_containers[m.generic_container]
            gplist = []
            for k in range(gc[1]):
                gi = gc[3] + k
                if gi < len(self.meta.generic_parameters):
                    gplist.append(self.meta.generic_parameters[gi][1])
            gp = '<%s>' % ', '.join(gplist) if gplist else ''
        ps = []
        params = self.meta.method_params(m)
        for k, p in enumerate(params):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            tn = self.il.type_name(pt) if pt else 'object'
            byref = (pt[1] >> 29) & 1 if pt else 0
            pmod = 'ref ' if byref else ''
            dv = self.parse_default(*self.meta.param_default_values[m.parameter_start + k],
                                    param=True) if (m.parameter_start + k) in self.meta.param_default_values else None
            ps.append('%s%s %s%s' % (pmod, tn, safe_ident(p.name), (' = %s' % dv) if dv else ''))
        return '%s%s %s%s(%s)' % (mods, rtname, name, gp, ', '.join(ps))

    _us_cache: Dict[int, bool] = {}

    def _unity_serialized(self, td: TypeDef, field_name: str) -> bool:
        """[SerializeField]: a MonoBehaviour / ScriptableObject descendant.
        The caller has already established that this is a non-public
        instance field (public fields serialize without the attribute);
        whether Unity really serializes this one is not knowable without
        the custom-attribute blob, so it stays a well-scoped guess."""
        if not field_name:
            return False
        cached = self._us_cache.get(td.index)
        if cached is None:
            cached = False
            cur = td.index
            hops = 0
            while 0 <= cur < len(self.meta.typedefs) and hops < 12:
                t = self.meta.typedefs[cur]
                if t.parent < 0 or t.parent >= len(self.il.types):
                    break
                pt = self.il.types[t.parent]
                pn = self.il.type_name(pt).split('<')[0]
                if pn in ('UnityEngine.MonoBehaviour', 'UnityEngine.ScriptableObject'):
                    cached = True
                    break
                if self.il._type_enum(pt) not in (0x11, 0x12) \
                        or not (0 <= pt[0] < len(self.meta.typedefs)):
                    break
                if pt[0] == cur:
                    break
                cur = pt[0]
                hops += 1
            self._us_cache[td.index] = cached
        return cached

    def emit_type(self, td: TypeDef, out: List[str], indent='    ') -> bool:
        pre = indent
        hdr = self.type_decl_line(td)
        out.append('')
        comment = []
        if td.generic_container != -1:
            pass
        if (td.flags & 0x2000) and not td.is_enum and not td.is_valuetype:
            out.append(pre + '[Serializable]')
        out.append(pre + hdr[0])
        out.append(pre + '{')
        if td.is_enum:
            out.extend(self.enum_body(td))
            out.append(pre + '}')
            return True
        # fields
        prop_names = {self.meta.getstr(self.meta.properties[td.property_start + k][0])
                      for k in range(td.property_count)}
        bk_offs = {}
        _BKF = re.compile(r'^<(.+)>k__BackingField$')
        fmax = self.meta.type_fields(td)
        for fi in fmax:
            f = self.meta.fields[fi]
            ft = self.il.types[f.type] if 0 <= f.type < len(self.il.types) else None
            if ft is None:
                continue
            fn = sanitize(f.name)
            fa = field_attrs(self.il, f)
            is_static_field = bool(fa & FA_STATIC)
            off_note = self.field_off_note(td, fi, is_static_field)
            bk = _BKF.match(f.name)
            if bk and bk.group(1) in prop_names:
                # auto-property backing field: the property already
                # declares the member; the fake `_X_k__BackingField`
                # line reads as a real public API member that doesn't
                # exist (1,080 files tree-wide). Carry its offset
                # comment onto the property instead.
                bk_offs[bk.group(1)] = off_note
                continue
            vis = FIELD_VIS.get(fa & 7, 'public ')
            # const is FieldAttributes.Literal, NOT `has a decodable
            # default value` -- RVA data blobs carry a dv row too, and 14
            # of them decoded to an int and printed as const.
            if fa & FA_LITERAL:
                dv = self.default_value_of(fi)
                if dv is not None:
                    out.append(pre + '    %sconst %s %s = %s;' % (
                        vis, self.il.type_name(ft), fn, dv))
                    continue
                # a literal we cannot decode: `const T X;` does not compile
                is_static_field = True
                fa |= FA_INITONLY
            mods = vis
            if is_static_field:
                mods += 'static '
            if fa & FA_INITONLY:
                mods += 'readonly '
            # [SerializeField] only means something on a field Unity would
            # not serialize by itself, i.e. a non-public instance field
            attr = ''
            if not is_static_field and (fa & 7) != 6 \
                    and self._unity_serialized(td, f.name):
                attr = '[SerializeField] '
            out.append(pre + '    %s%s%s %s;%s' % (
                attr, mods, self.il.type_name(ft), fn, off_note))
        # properties: accessors render inside the property, not as methods
        accessor_idxs = set()
        for k in range(td.property_count):
            pr = self.meta.properties[td.property_start + k]
            for x in (pr[1], pr[2]):
                if x is not None and x >= 0 and 0 <= td.method_start + x < len(self.meta.methods):
                    accessor_idxs.add(td.method_start + x)
            self.emit_property(td, out, pre, pr, bk_offs)
        # events: add_/remove_ accessors are represented by the event itself
        for k in range(td.event_count):
            ev = self.meta.events[td.event_start + k]
            for x in ev[2:5]:
                if x is not None and x >= 0 and 0 <= td.method_start + x < len(self.meta.methods):
                    accessor_idxs.add(td.method_start + x)
            out.append(pre + '    public event %s %s;' % (
                self.il.type_name(self.il.types[ev[1]]) if ev[1] < len(self.il.types) else 'Action',
                sanitize(csharp_type_name(self.meta.getstr(ev[0])))))
        # methods
        for mi in self.meta.type_methods(td):
            if mi in accessor_idxs:
                continue
            m = self.meta.methods[mi]
            self.emit_method(m, td, out, pre + '    ')
        # nested types
        for k in range(td.nested_count):
            ni = self.meta.nested_types[td.nested_start + k]
            if 0 <= ni < len(self.meta.typedefs):
                self.emit_type(self.meta.typedefs[ni], out, pre + '    ')
        out.append(pre + '}')
        return True

    def field_off_note(self, td, fi, is_static):
        """Trailing `// 0x..` comment for a field declaration. Generic type
        definitions have no field-offset table (offsets live per
        instantiation), so every lookup there returns 0 -- print nothing
        rather than a fake `0x0`."""
        fo = self.il.field_offsets[td.index] \
            if td.index < len(self.il.field_offsets) else None
        if fo is None or td.generic_container != -1:
            return ''
        off = self.field_off_display(td, fi)
        if not off and not is_static:
            return ''  # no instance field can sit in the object header
        return ' // static @0x%x' % off if is_static else ' // 0x%x' % off

    def field_off_display(self, td, fi):
        fo = self.il.field_offsets[td.index] if td.index < len(self.il.field_offsets) else None
        if fo is None:
            return 0
        for k, off in enumerate(fo):
            if td.field_start + k == fi:
                return off
        return 0

    def prop_type(self, getter):
        if getter is None:
            return 'object'
        t = self.il.types[getter.return_type] if 0 <= getter.return_type < len(self.il.types) else None
        return self.il.type_name(t) if t else 'object'

    def render_params(self, m: MethodDef) -> str:
        ps = []
        params = self.meta.method_params(m)
        for k, p in enumerate(params):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            tn = self.il.type_name(pt) if pt else 'object'
            byref = (pt[1] >> 29) & 1 if pt else 0
            pmod = 'ref ' if byref else ''
            dv = self.parse_default(*self.meta.param_default_values[m.parameter_start + k],
                                    param=True) if (m.parameter_start + k) in self.meta.param_default_values else None
            ps.append('%s%s %s%s' % (pmod, tn, safe_ident(p.name), (' = %s' % dv) if dv else ''))
        return ', '.join(ps)

    def ctor_sig(self, m: MethodDef, td: TypeDef) -> str:
        """Instance/static constructor signature: public ClassName() /
        static ClassName() -- no return type, no .ctor name."""
        cname = sanitize(re.sub(r'`\d+$', '', td.name))
        if m.name == '.cctor':
            return 'static %s()' % cname
        vis = METH_VIS.get((m.flags >> 0) & 7, 'public ')
        return '%s%s(%s)' % (vis, cname, self.render_params(m))

    def ctor_base_initializer(self, td: TypeDef) -> Optional[str]:
        """: base() when the parent is a real class (not object/valuetype)."""
        if td.is_valuetype or td.is_enum or td.parent < 0:
            return None
        if td.parent >= len(self.il.types):
            return None
        pn = self.il.type_name(self.il.types[td.parent])
        if not pn or pn.split('<')[0] in ('object', 'System.Object',
                                          'System.ValueType', 'System.Enum'):
            return None
        return 'base()'

    _CTORCALL_RX = re.compile(r'^(this|base)\.\.ctor\s*\((.*?)\)\s*;(?:\s*return\s*;)?\s*$')

    def _ctor_body(self, lines: List[str]):
        """Pull base..ctor()/this..ctor() calls out of a constructor body:
        returns (initializer-or-None, body). Trailing bare returns on an
        otherwise finished ctor disappear with the promoted call."""
        init = None
        out = []
        for st in lines:
            m = self._CTORCALL_RX.match(st.strip())
            if m:
                init = '%s(%s)' % (m.group(1), m.group(2).strip())
                continue
            out.append(st)
        while out and out[-1].strip() == 'return;':
            out.pop()
        return init, out

    def _void_tail_strip(self, body, m):
        rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
        if rt is not None and ((rt[1] >> 16) & 0xFF) == 0x01:
            while body and body[-1].strip() == 'return;':
                body.pop()
        return body

    def _lift_body(self, m: MethodDef, td: TypeDef, abstract=False):
        """Lift one method body (decompiler first, linear fallback); None when
        there is nothing to lift. Counts toward lifted/failed."""
        has_body = m.addr and self.with_bodies and self.lifter and not abstract
        if self.max_methods is not None and self.lifted >= self.max_methods:
            has_body = False
        if not has_body:
            return None
        structured_error = None
        if self.decompiler is not None:
            try:
                body = self.decompiler.lift_method(m, td)
                self.lifted += 1
                return self._void_tail_strip(body, m)
            except Exception as ex:
                structured_error = ex
        self.fallbacks += 1
        if self.verbose:
            print('warning: structured lift fallback mi=%d VA=%#x %s.%s: %s' % (
                m.index, m.addr, td.name, m.name,
                structured_error or getattr(self, 'decompiler_error', None) or
                'structured backend unavailable'), file=sys.stderr)
        try:
            body = self.lifter.lift(m, td)
            self.lifted += 1
            # The linear fallback has no type analysis: object, not var.
            body = [re.sub(r'^(\s*)var (\w+)( = )', r'\1object \2\3', l)
                    for l in body]
            return self._void_tail_strip(body, m)
        except Exception as ex:
            self.failed += 1
            return ['/* lift failed: %s */' % ex]

    def _rel_method(self, td: TypeDef, rel: int) -> Optional[MethodDef]:
        """Property/event accessor rows store method indices RELATIVE to the
        type's method range (metadata v27+); -1 means the accessor is absent."""
        if rel is None or rel < 0:
            return None
        mi = td.method_start + rel
        return self.meta.methods[mi] if 0 <= mi < len(self.meta.methods) else None

    def emit_property(self, td: TypeDef, out: List[str], pre: str, pr,
                     bk_offs=None):
        """public T P { get { ... } set { ... } } -- accessor bodies move
        inside the property; auto-accessors when no body is available."""
        getter = self._rel_method(td, pr[1])
        setter = self._rel_method(td, pr[2])
        gbody = self._lift_body(getter, td) if getter else None
        sbody = self._lift_body(setter, td) if setter else None
        pname = sanitize(csharp_type_name(self.meta.getstr(pr[0])))
        ptype = self.prop_type(getter)
        acc = '' if '.' in pname else 'public '
        off = (bk_offs or {}).get(self.meta.getstr(pr[0]), '')
        if gbody is None and sbody is None:
            out.append('%s    %s%s %s { %s%s }%s' % (
                pre, acc, ptype, pname,
                'get; ' if getter else '', 'set; ' if setter else '', off))
            return
        out.append('%s    %s%s %s%s' % (pre, acc, ptype, pname, off))
        out.append('%s    {' % pre)
        for kind, body in (('get', gbody), ('set', sbody)):
            if (getter if kind == 'get' else setter) is None:
                continue
            if body is None or not body:
                out.append('%s        %s;' % (pre, kind))
                continue
            out.append('%s        %s' % (pre, kind))
            out.append('%s        {' % pre)
            for l in body:
                out.append(('%s            %s' % (pre, l.rstrip())) if l.strip() else '')
            out.append('%s        }' % pre)
        out.append('%s    }' % pre)

    def emit_method(self, m: MethodDef, td: TypeDef, out: List[str], pre: str):
        is_ctor = m.name in ('.ctor', '.cctor')
        sig = self.ctor_sig(m, td) if is_ctor else self.method_sig(m, td)
        abstract = (td.flags & 0x80) and (m.flags & 0x400) and not (m.flags & 0x40)
        body = self._lift_body(m, td, abstract)
        ctor_init = None
        if is_ctor:
            if body:
                ctor_init, body = self._ctor_body(body)
            if m.name == '.ctor' and not ctor_init:
                ctor_init = self.ctor_base_initializer(td)
        if abstract or not m.addr:
            out.append('%s%s; // RVA: 0x%x VA: 0x%x' % (pre, sig, m.addr or 0, m.addr or 0)
                       if m.addr else '%s%s;' % (pre, sig))
            return
        slot_note = ' Slot: %d' % m.slot if m.slot != 0xFFFF else ''
        rva = m.addr - self.il.bin.image_base if hasattr(self.il.bin, 'image_base') else m.addr
        out.append('%s// RVA: 0x%X VA: 0x%X%s' % (pre, rva, m.addr, slot_note))
        out.append('%s%s%s' % (pre, sig, (' : ' + ctor_init) if ctor_init else ''))
        out.append('%s{' % pre)
        if body:
            for l in body:
                if not l.strip():
                    out.append('')
                elif l.startswith(' '):
                    # structured output already carries relative indentation
                    out.append(pre + l.rstrip())
                else:
                    out.append(pre + l.rstrip())
        out.append('%s}' % pre)

    # -- assembly: one .cs file per top-level type --------------------------
    def file_name_for(self, td: TypeDef) -> str:
        m = re.match(r'^(.*?)(?:`(?:\d+))?$', td.name)
        base = re.sub(r'[^A-Za-z0-9_.-]', '_', m.group(1)).strip('._-') or 'Type'
        return base

    def seg(self, part: str) -> str:
        segm = re.sub(r'[^A-Za-z0-9_.-]', '_', part).strip('.')
        return segm or '_'

    def _matches_type_filter(self, td):
        """A nested match retains its entire top-level owner file."""
        if not self.type_filter:
            return True
        pending = [(td.index, td.namespace)]
        visited = set()
        while pending:
            ti, prefix = pending.pop()
            if ti in visited or not 0 <= ti < len(self.meta.typedefs):
                continue
            visited.add(ti)
            child = self.meta.typedefs[ti]
            full = (prefix + '.' if prefix else '') + child.name
            if self.type_filter in full.casefold():
                return True
            for k in range(child.nested_start, child.nested_start + child.nested_count):
                if 0 <= k < len(self.meta.nested_types):
                    pending.append((self.meta.nested_types[k], full))
        return False

    def write_assembly_split(self, img: ImageDef) -> int:
        asm_name = self.seg(img.name[:-4] if img.name.lower().endswith('.dll') else img.name)
        asm_dir = os.path.join(self.out_dir, asm_name)
        os.makedirs(asm_dir, exist_ok=True)
        top_types = []
        for ti in range(img.type_start, min(img.type_start + img.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            if td.declaring < 0:
                top_types.append(td)
        written = 0
        used = {}
        for td in top_types:
            if td.name == '<Module>' or not self._matches_type_filter(td):
                continue
            ns = td.namespace
            rel = [self.seg(x) for x in ns.split('.')] if ns else []
            dirp = os.path.join(asm_dir, *rel)
            base = self.file_name_for(td)
            key = (dirp, base.lower())
            used[key] = used.get(key, 0) + 1
            if used[key] > 1:
                base += '_%d' % used[key]
            buf = []
            try:
                indent = '    ' if ns else ''
                self.emit_type(td, buf, indent)
            except Exception as ex:
                self.emit_failed += 1
                if self.verbose:
                    print('warning: type emission failed %s: %s' % (td.name, ex), file=sys.stderr)
                buf = ['// emit failed for %s: %s' % (td.name, ex)]
            tr = UsingTracker(self.il)
            for l in buf:
                tr.add_text(l)
            uses_set = set(tr.used)   # own ns too: in scope inside its block
            if uses_set:
                buf = strip_namespaces(buf, uses_set)
            members = self._nameof_members(uses_set)
            if members:
                # the enum must be referenced elsewhere in the file too:
                # nameof's argument does not survive compilation, so a file
                # that never names the enum almost surely had a plain string
                toks = set(re.findall(r'[A-Za-z_]\w*', '\n'.join(buf)))
                members = {mn: en for mn, en in members.items() if en in toks}
                if members:
                    buf = nameof_sugar(buf, members)
            hdr = ['// Decompiled by il2csharp | %s | TypeDefIndex: %d' % (img.name, td.index)]
            uses = tr.render(skip=[ns] if ns else [])
            if uses:
                hdr.append('')
                hdr.extend(uses)
            if ns:
                hdr.append('')
                hdr.append('namespace %s' % ns)
                hdr.append('{')
                content = '\n'.join(hdr) + '\n' + '\n'.join(buf) + '\n}\n'
            else:
                content = '\n'.join(hdr) + '\n' + '\n'.join(buf) + '\n'
            # lay every line at its real brace depth (see `reindent`): the
            # threaded-`indent` emitters drift a level and bodies read as
            # sitting outside their own braces. No-op on correct files.
            if os.environ.get('IL2CSHARP_NO_REINDENT') != '1':
                content = reindent(content)
            # a label in front of `}`/EOF needs a statement after it
            # (C# rule; tree-sitter MISSING). The structured path
            # fixes this in `_final_text`; the legacy flat lift never
            # runs it, so do it at the file boundary.
            _fl = content.split('\n')
            for _li in range(len(_fl)):
                if not re.match(r'^\s*L_[0-9a-fA-F]+:$', _fl[_li]):
                    continue
                _lj = _li + 1
                while _lj < len(_fl) and not _fl[_lj].strip():
                    _lj += 1
                if _lj >= len(_fl) or _fl[_lj].lstrip().startswith('}'):
                    _fl[_li] = _fl[_li] + ' ;'
            content = '\n'.join(_fl)
            # generated identifiers carry IL-only characters (`<>c`,
            # `<Foo>d__13`, `<>9__0_0`) that no C# grammar accepts; mangle
            # them deterministically at the file boundary so declarations
            # and every reference move together
            content = MANGLED_IDENT_RX.sub(
                lambda m: m.group(0).replace('<', '_').replace('>', '_')
                .replace('.', '_').replace('|', '_'), content)
            os.makedirs(dirp, exist_ok=True)
            with open(os.path.join(dirp, base + '.cs'), 'w', encoding='utf-8') as fh:
                fh.write(content)
            written += 1
        with open(os.path.join(asm_dir, asm_name + '.csproj'), 'w', encoding='utf-8') as fh:
            fh.write('<Project Sdk="Microsoft.NET.Sdk">\n'
                     '  <PropertyGroup>\n'
                     '    <TargetFramework>netstandard2.1</TargetFramework>\n'
                     '    <AssemblyName>%s</AssemblyName>\n'
                     '    <EnableDefaultCompileItems>true</EnableDefaultCompileItems>\n'
                     '    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>\n'
                     '    <NoWarn>CS0169;CS0649;CS0108;CS0114;CS8019</NoWarn>\n'
                     '  </PropertyGroup>\n'
                     '</Project>\n' % asm_name)
        return written

    def _nameof_members(self, ns_set) -> dict:
        """member name -> enum short name for top-level enums in the given
        namespaces. A short name shared by two enums in scope is dropped
        (the qualified member would not resolve)."""
        if getattr(self, '_enum_ns_idx', None) is None:
            idx = {}
            for td in self.meta.typedefs:
                if td.is_enum and td.declaring < 0:
                    idx.setdefault(td.namespace, []).append(td)
            self._enum_ns_idx = idx
        short_count = {}
        for ns in ns_set:
            for td in self._enum_ns_idx.get(ns, ()):
                short_count[td.name] = short_count.get(td.name, 0) + 1
        members = {}
        for ns in ns_set:
            for td in self._enum_ns_idx.get(ns, ()):
                if short_count[td.name] > 1:
                    continue
                for fi in self.meta.type_fields(td)[1:]:
                    name = sanitize(self.meta.fields[fi].name)
                    if name not in members:
                        members[name] = td.name
        return members

    def write_script_json(self, path):
        import json
        methods = []
        for m in self.meta.methods:
            if not m.addr or m.image < 0:
                continue
            td = self.meta.typedefs[m.declaring] if 0 <= m.declaring < len(self.meta.typedefs) else None
            if td is None:
                continue
            ns = (td.namespace + '.') if td.namespace else ''
            params = ', '.join(
                self.il.type_name(self.il.types[p.type]) if 0 <= p.type < len(self.il.types) else 'object'
                for p in self.meta.method_params(m))
            methods.append({'Name': '%s%s.%s(%s)' % (ns, td.name, m.name, params),
                            'Address': m.addr})
        strings = [{'Address': sva, 'Value': lit} for sva, lit in self.il.string_slots()]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'ScriptMethod': methods, 'ScriptString': strings}, fh, indent=1)

    def write_string_literals(self, path):
        import json
        lits = [{'index': i, 'value': self.meta.string_literal(i)}
                for i in range(len(self.meta.string_literals))]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(lits, fh, indent=1, ensure_ascii=False)

