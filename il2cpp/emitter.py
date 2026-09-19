from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.arm64 import Arm64Lifter, is_arm64_binary
from il2cpp.common import compressed_int, csharp_type_name, i32, i64, read_compressed_uint, u16, u32, u64
from il2cpp.csharp import FA_INITONLY, FA_LITERAL, FA_STATIC, FIELD_VIS, METH_VIS, TYPE_VIS, UsingTracker, field_attrs, nameof_sugar, strip_namespaces, collision_heads, source_field_name
from il2cpp.lifter import Lifter
from il2cpp.metadata import ImageDef, MethodDef, TypeDef
from il2cpp.names import repr_f32, repr_f64, safe_ident, sanitize, sanitize_qualifier
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
    def _type_generic_params(self, td: TypeDef) -> str:
        """`<T, ...>` from the typedef's generic container, else ''."""
        # A nested container holds mirrored owner parameters plus its
        # own trailing ones: declare only the own suffix (possibly none).
        # Unprovable splits keep the legacy full-container rendering.
        try:
            if self.il._nested_owner(td.index) is not None:
                own = self.il._nested_own_params(td)
                if own is not None:
                    return '<%s>' % ', '.join(own) if own else ''
        except Exception:
            pass
        gparams = ''
        if td.generic_container != -1 and not td.is_enum:
            gc = self.meta.generic_containers[td.generic_container]
            gp = []
            for k in range(gc[1]):
                gi = gc[3] + k
                if gi < len(self.meta.generic_parameters):
                    gp.append(self.meta.generic_parameters[gi][1])
            gparams = '<%s>' % ', '.join(gp) if gp else ''
        return gparams

    _arity_qualifier_cache = None

    def _arity_qualifier(self, dotted, td=None):
        """Append the metadata arity suffix to an explicit-interface qualifier
        (`NS.IFoo<T>` -> `NS.IFoo_1<T>`) so it spells the same identifier the
        interface declaration does. Qualifiers come from metadata name strings
        that never record arity, so arity is proved by matching (namespace,
        dotted path, top-level argument count) against exactly one typedef
        row; anything else declines unchanged."""
        if '<' not in dotted or '>' not in dotted:
            return dotted
        try:
            exact = self._iface_qualifier(dotted, td)
            if exact is not None:
                return exact
            cache = self._arity_qualifier_cache
            if cache is None:
                cache = {}
                for td in self.meta.typedefs:
                    try:
                        nm = td.name or ''
                    except Exception:
                        continue
                    if '`' not in nm:
                        continue
                    m = re.match(r'^(.*)`(\d+)$', nm)
                    if not m:
                        continue
                    short, arity = m.group(1), int(m.group(2))
                    parts = [short]
                    seen = 0
                    ns = getattr(td, 'namespace', '')
                    try:
                        dd = self.il._nested_owner(td.index)
                        while dd is not None and seen < 8:
                            dt = self.meta.typedefs[dd]
                            parts.append((dt.name or '').split('`')[0])
                            seen += 1
                            # the namespace lives on the outermost owner;
                            # nested rows carry none of their own.
                            if getattr(dt, 'namespace', ''):
                                ns = dt.namespace
                            dd = self.il._nested_owner(dd)
                    except Exception:
                        pass
                    path = '.'.join(reversed(parts))
                    cache.setdefault((ns, path), []).append(arity)
                self._arity_qualifier_cache = cache
            head, rest = dotted.split('<', 1)
            args = '<' + rest
            depth = commas = 0
            has_arg = False
            for ch in args[1:]:
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ',' and depth == 0:
                    commas += 1
                elif ch not in ', ':
                    has_arg = True
            if not has_arg:
                return dotted
            argc = commas + 1
            # a nested qualifier (`N.Outer.Inner<X>`) may split namespace
            # from path at any dot; accept only a globally unique proof.
            segs = head.split('.')
            proofs = []
            for k in range(len(segs)):
                ns = '.'.join(segs[:k])
                path = '.'.join(segs[k:])
                cands = [a for a in cache.get((ns, path), []) if a == argc]
                if len(cands) == 1:
                    proofs.append('%s%s_%d%s' % (ns + '.' if ns else '', path, argc, args))
            if len(proofs) != 1:
                return dotted
            return proofs[0]
        except Exception:
            return dotted

    def _iface_qualifier(self, dotted, td=None):
        """Render an explicit-interface qualifier from the declaring type's
        own interface list (binary truth) instead of the arity-less metadata
        name string. Matches (namespace, short name, top-level argument
        count) against each implemented interface tuple and, on exactly one
        match, returns that tuple's rendered spelling — identical to the
        base-list spelling, nested arguments included. Returns None to let
        the typedef-name proof below decide, or to decline unchanged."""
        if td is None:
            return None
        try:
            head, rest = dotted.split('<', 1)
            args = '<' + rest
            if '.' in head:
                qns, _, qpath = head.rpartition('.')
            else:
                qns, qpath = '', head
            depth = commas = 0
            has_arg = False
            for ch in args[1:]:
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ',' and depth == 0:
                    commas += 1
                elif ch not in ', ':
                    has_arg = True
            if not has_arg:
                return None
            qargc = commas + 1
            hits = []
            for k in range(getattr(td, 'interfaces_count', 0)):
                ii = self.meta.interfaces[td.interfaces_start + k]
                tup = self.il.types[ii] if 0 <= ii < len(self.il.types) else None
                if tup is None:
                    continue
                rendered = self.il.type_name(tup)
                if '<' not in rendered or '>' not in rendered:
                    continue
                rhead, rrest = rendered.split('<', 1)
                if '.' in rhead:
                    rns, _, rpath = rhead.rpartition('.')
                else:
                    rns, rpath = '', rhead
                rpath = re.sub(r'_\d+$', '', rpath)
                rdepth = rcommas = 0
                rhas = False
                for ch in ('<' + rrest)[1:]:
                    if ch == '<':
                        rdepth += 1
                    elif ch == '>':
                        if rdepth == 0:
                            break
                        rdepth -= 1
                    elif ch == ',' and rdepth == 0:
                        rcommas += 1
                    elif ch not in ', ':
                        rhas = True
                if not rhas:
                    continue
                if rpath == qpath and (not qns or rns == qns) and rcommas + 1 == qargc:
                    hits.append(rendered)
            if len(hits) != 1:
                return None
            return hits[0]
        except Exception:
            return None

    def type_decl_line(self, td: TypeDef) -> List[str]:
        f = td.flags
        vis = TYPE_VIS.get((f >> 0) & 7, '')
        if td.declaring < 0 and (f & 7) > 1:
            vis = 'internal '  # a nested form on a top-level row: unreadable
        lines = []
        if f & 0x20:
            # interfaces are implicitly abstract: 0x80 is always set
            # alongside 0x20, so excluding abstract here misread nearly
            # every interface as a class (fix 113).
            kw = vis + 'partial interface'
        elif td.is_enum:
            kw = vis + 'enum'
        elif td.is_valuetype:
            kw = vis + 'partial struct'
        elif (f & 0x80) and (f & 0x100):
            # abstract + sealed with no instance content anywhere
            # (census over the fixture) is a static utility class.
            kw = vis + 'static partial class'
        else:
            kw = vis + 'partial class'
            if f & 0x80:
                kw = vis + 'abstract ' + kw[len(vis):]
            if f & 0x100:
                kw = vis + 'sealed ' + kw[len(vis):]
        name = td.name
        gparams = self._type_generic_params(td)
        base = []
        if td.parent >= 0 and not td.is_enum and not td.is_valuetype \
                and not (td.flags & 0x20):
            # interfaces inherit interfaces only (via interfaces[]
            # below); a class-typed parent slot on one is malformed.
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
        hdr = '%s %s%s' % (kw, safe_ident(sanitize(name)), gparams)
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
            out.append('        %s = %s,' % (safe_ident(sanitize(f.name)), v if v is not None else '?'))
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
        f = m.flags
        vis = METH_VIS.get(f & 7, '')
        # CLI MethodAttributes: Final=0x20, Virtual=0x40,
        # NewSlot=0x100, Abstract=0x400. TypeAttributes use different bits.
        explicit = '.' in m.name
        mods = '' if explicit else vis
        if m.is_static:
            mods += 'static '
        if td.flags & 0x20:
            mods = 'static ' if m.is_static else ''
            if m.is_static and f & 0x400:
                mods += 'abstract '
        elif not explicit:
            if f & 0x400:
                mods += 'abstract '
                if f & 0x40 and not f & 0x100:
                    mods += 'override '
            elif f & 0x40 and not m.is_static:
                if not f & 0x100:
                    mods += 'sealed override ' if f & 0x20 else 'override '
                elif not f & 0x20:
                    mods += 'virtual '
                # Final+NewSlot implements an interface without exposing
                # an overridable C# member; it is not a sealed override.
        rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
        rtname = self.il.type_name(rt) if rt else 'void'
        if rtname == 'void':
            pass
        # explicit-interface `IFoo.Bar`: escape the member component only.
        # The qualifier keeps its generic structure: a blanket sanitize()
        # here would eat the commas (`IDictionary<TKey, TValue>`), so split
        # first and sanitize each half through its own rule.
        raw = csharp_type_name(m.name)
        if '.' in raw:
            head, _, tail = raw.rpartition('.')
            name = sanitize_qualifier(self._arity_qualifier(head, td)) + '.' + safe_ident(tail)
        else:
            name = safe_ident(raw)
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
        if '*' in rtname or any('*' in s for s in ps):
            mods += 'unsafe '
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

    _delegate_cache: Dict[int, bool] = {}

    def _is_delegate_td(self, td: TypeDef) -> bool:
        """True for user delegate types (MulticastDelegate subclasses).

        System.Delegate/MulticastDelegate themselves stay classes.
        Cached: base chains are binary-global.
        """
        try:
            hit = self._delegate_cache.get(td.index)
            if hit is not None:
                return hit
            res = False
            if (td.namespace, td.name) not in (
                    ('System', 'Delegate'),
                    ('System', 'MulticastDelegate')):
                try:
                    chain = self.il.base_chain_tds(td.index)
                except Exception:
                    chain = ()
                for ti in chain[1:]:
                    t2 = self.meta.typedefs[ti] \
                        if 0 <= ti < len(self.meta.typedefs) else None
                    if t2 is not None and t2.name in (
                            'MulticastDelegate', 'Delegate'):
                        res = True
                        break
            self._delegate_cache[td.index] = res
            return res
        except Exception:
            return False

    def _delegate_invoke(self, td: TypeDef):
        """The instance Invoke MethodDef of a delegate typedef, else None."""
        try:
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if m.name == 'Invoke' and not m.is_static:
                    return m
            return None
        except Exception:
            return None

    def _delegate_viable(self, td: TypeDef) -> bool:
        """True when the typedef can render as a delegate declaration.

        Needs the instance Invoke (the signature source) and no
        fields, properties, events, or nested types (a `delegate`
        declaration cannot carry them). Cached per emitter.
        """
        try:
            hit = self._delegate_cache.get(('viable', td.index))
            if hit is not None:
                return hit
            res = self._delegate_invoke(td) is not None \
                and not list(self.meta.type_fields(td)) \
                and not td.property_count and not td.event_count \
                and not td.nested_count
            self._delegate_cache[('viable', td.index)] = res
            return res
        except Exception:
            return False

    def emit_delegate(self, td: TypeDef, out: List[str], pre: str) -> bool:
        """`delegate R Name(params);` for a user delegate type.

        The runtime-provided .ctor/Invoke/BeginInvoke/EndInvoke
        members are covered by the declaration itself.
        """
        try:
            inv = self._delegate_invoke(td)
            vis = TYPE_VIS.get((td.flags >> 0) & 7, '')
            if td.declaring < 0 and (td.flags & 7) > 1:
                vis = 'internal '
            rt = self.il.types[inv.return_type] \
                if 0 <= inv.return_type < len(self.il.types) else None
            rtname = self.il.type_name(rt) if rt else 'void'
            ps = []
            for p in self.meta.method_params(inv):
                pt = self.il.types[p.type] \
                    if 0 <= p.type < len(self.il.types) else None
                tn = self.il.type_name(pt) if pt else 'object'
                byref = (pt[1] >> 29) & 1 if pt else 0
                ps.append('%s%s %s' % ('ref ' if byref else '', tn,
                                       safe_ident(p.name)))
            nm = safe_ident(sanitize(td.name)) + \
                self._type_generic_params(td)
            unsafe = 'unsafe ' if '*' in rtname or any(
                '*' in p for p in ps) else ''
            out.append('')
            if (td.flags & 0x2000) and not td.is_enum \
                    and not td.is_valuetype:
                # qualified so the using tracker imports System; the file
                # boundary strips it back when unambiguous.
                out.append(pre + '[System.Serializable]')
            out.append('%s%s%sdelegate %s %s(%s);' % (
                pre, vis, unsafe, rtname, nm, ', '.join(ps)))
            return True
        except Exception:
            return False

    def emit_type(self, td: TypeDef, out: List[str], indent='    ') -> bool:
        pre = indent
        if self._is_delegate_td(td) and self._delegate_viable(td):
            self.emit_delegate(td, out, pre)
            return True
        hdr = self.type_decl_line(td)
        out.append('')
        comment = []
        if td.generic_container != -1:
            pass
        if (td.flags & 0x2000) and not td.is_enum and not td.is_valuetype:
            out.append(pre + '[System.Serializable]')
        out.append(pre + hdr[0])
        out.append(pre + '{')
        if td.is_enum:
            out.extend(self.enum_body(td))
            out.append(pre + '}')
            return True
        # Preserve real storage; accessors must not recursively read themselves.
        fmax = self.meta.type_fields(td)
        for fi in fmax:
            f = self.meta.fields[fi]
            ft = self.il.types[f.type] if 0 <= f.type < len(self.il.types) else None
            if ft is None:
                continue
            fn = safe_ident(sanitize(source_field_name(self.il, fi)))
            fa = field_attrs(self.il, f)
            ftname = self.il.type_name(ft)
            is_static_field = bool(fa & FA_STATIC)
            off_note = self.field_off_note(td, fi, is_static_field)
            vis = FIELD_VIS.get(fa & 7, 'public ')
            # const is FieldAttributes.Literal, NOT `has a decodable
            # default value` -- RVA data blobs carry a dv row too, and 14
            # of them decoded to an int and printed as const.
            if fa & FA_LITERAL:
                dv = self.default_value_of(fi)
                if dv is not None:
                    out.append(pre + '    %sconst %s %s = %s;' % (
                        vis, ftname, fn, dv))
                    continue
                # a literal we cannot decode: `const T X;` does not compile
                is_static_field = True
                fa |= FA_INITONLY
            mods = vis
            if is_static_field:
                mods += 'static '
            if fa & FA_INITONLY:
                mods += 'readonly '
            if '*' in ftname:
                mods += 'unsafe '
            # [SerializeField] only means something on a field Unity would
            # not serialize by itself, i.e. a non-public instance field
            attr = ''
            if not is_static_field and (fa & 7) != 6 \
                    and self._unity_serialized(td, f.name):
                attr = '[UnityEngine.SerializeField] '
            out.append(pre + '    %s%s%s %s;%s' % (
                attr, mods, ftname, fn, off_note))
        # properties: accessors render inside the property, not as methods
        accessor_idxs = set()
        for k in range(td.property_count):
            pr = self.meta.properties[td.property_start + k]
            for x in (pr[1], pr[2]):
                if x is not None and x >= 0 and 0 <= td.method_start + x < len(self.meta.methods):
                    accessor_idxs.add(td.method_start + x)
            self.emit_property(td, out, pre, pr)
        # C# has add/remove syntax but no raise accessor: keep raise as a
        # normal method instead of silently dropping its native body.
        for k in range(td.event_count):
            ev = self.meta.events[td.event_start + k]
            if self.emit_event(td, out, pre, ev):
                for x in ev[2:4]:
                    if self._rel_method(td, x) is not None:
                        accessor_idxs.add(td.method_start + x)
        # methods
        skip_delegate = self._is_delegate_td(td) \
            and self._delegate_viable(td)
        for mi in self.meta.type_methods(td):
            if mi in accessor_idxs:
                continue
            m = self.meta.methods[mi]
            if skip_delegate and (m.name in ('.ctor', '.cctor', 'Invoke')
                                  or m.name.startswith(
                                      ('BeginInvoke', 'EndInvoke'))):
                # covered by the delegate declaration itself
                continue
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
        # Match the emitted type identifier, including its arity suffix.
        # C# constructors omit <T>, but must retain Box_1 in Box_1<T>.
        cname = safe_ident(sanitize(td.name))
        if m.name == '.cctor':
            return 'static %s()' % cname
        vis = METH_VIS.get((m.flags >> 0) & 7, 'public ')
        params = self.render_params(m)
        if '*' in params:
            return '%sunsafe %s(%s)' % (vis, cname, params)
        return '%s%s(%s)' % (vis, cname, params)

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
        """Lift a body or emit an explicit unavailable-body throw.

        Only abstract declarations return None; only actual lifts are counted.
        """
        if abstract:
            return None
        has_body = m.addr and self.with_bodies and self.lifter
        if self.max_methods is not None and self.lifted >= self.max_methods:
            has_body = False
        if not has_body:
            return ['throw new global::System.NotImplementedException("Method body was not recovered.");']
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

    def _member_name(self, raw, td):
        raw = csharp_type_name(raw)
        if '.' in raw:
            head, _, tail = raw.rpartition('.')
            return sanitize_qualifier(self._arity_qualifier(head, td)) + '.' + safe_ident(tail)
        return safe_ident(sanitize(raw))

    def _accessor_modifiers(self, td, present, explicit=False):
        """Use the most accessible accessor, preserving method dispatch flags."""
        if not present:
            return '' if td.flags & 0x20 or explicit else 'public '
        # Accessibility is a lattice: protected + internal has their union.
        vis = {getattr(a, 'flags', 6) & 7 for a in present}
        access = 6 if 6 in vis else 5 if 5 in vis or {3, 4} <= vis else max(vis)
        chosen = next((a for a in present if getattr(a, 'flags', 6) & 7 == access), present[0])
        f = getattr(chosen, 'flags', 6)
        mods = '' if explicit or td.flags & 0x20 else METH_VIS.get(access, '')
        if all(a.is_static for a in present):
            mods += 'static '
        abstract = all(getattr(a, 'flags', 0) & 0x400 for a in present)
        if td.flags & 0x20:
            if all(a.is_static for a in present) and abstract:
                mods += 'abstract '
        elif not explicit:
            if abstract:
                mods += 'abstract '
                if f & 0x40 and not f & 0x100:
                    mods += 'override '
            elif f & 0x40 and not chosen.is_static:
                if not f & 0x100:
                    mods += 'sealed override ' if f & 0x20 else 'override '
                elif not f & 0x20:
                    mods += 'virtual '
        return mods

    def _accessor_lines(self, m, td, aliases=None):
        if getattr(m, 'flags', 0) & 0x400:
            return None
        body = self._lift_body(m, td)
        if body is None or not aliases:
            return body
        # Only parameter tokens, never member names or literal/comment text.
        from il2cpp.dec.highlevel import _HighLevelMixin
        mapping = {safe_ident(k): v for k, v in aliases.items() if safe_ident(k) != v}
        if not mapping:
            return body
        comment = False
        result = []
        for line in body:
            # Temporarily protect qualified member tokens from parameter rename.
            protected = {}
            def protect(match):
                key = '__accessor_member_%d__' % len(protected)
                protected[key] = match.group(0)
                return key
            text = re.sub(r'\.\s*(?:' + '|'.join(re.escape(k) for k in mapping) + r')\b', protect, line)
            text, comment = _HighLevelMixin._replace_semantic_names(text, mapping, comment)
            for key, value in protected.items():
                text = text.replace(key, value)
            result.append(text)
        return result

    def _emit_accessor(self, out, pre, kind, m, body, visibility=''):
        if getattr(m, 'addr', 0):
            base = getattr(self.il.bin, 'image_base', 0)
            out.append('%s// RVA: 0x%X VA: 0x%X' % (pre, m.addr - base, m.addr))
        if body is None:
            out.append(pre + visibility + kind + ';')
            return
        out.append(pre + visibility + kind)
        out.append(pre + '{')
        out.extend(pre + '    ' + line.rstrip() if line.strip() else '' for line in body)
        out.append(pre + '}')

    def emit_property(self, td: TypeDef, out: List[str], pre: str, pr,
                      bk_offs=None):
        getter = self._rel_method(td, pr[1])
        setter = self._rel_method(td, pr[2])
        present = [a for a in (getter, setter) if a is not None]
        raw = self.meta.getstr(pr[0])
        pname = self._member_name(raw, td)
        explicit = '.' in raw
        gparams = list(self.meta.method_params(getter)) if getter else []
        sparams = list(self.meta.method_params(setter)) if setter else []
        ptype = self.prop_type(getter)
        if not getter and sparams:
            pt = sparams[-1].type
            ptype = self.il.type_name(self.il.types[pt]) if 0 <= pt < len(self.il.types) else 'object'
        index_params = gparams if getter else sparams[:-1]
        if index_params:
            prefix = pname.rpartition('.')[0] + '.' if explicit else ''
            params = ', '.join('%s %s' % (self.il.type_name(self.il.types[p.type]), safe_ident(p.name)) for p in index_params)
            pname = prefix + 'this[' + params + ']'
        mods = self._accessor_modifiers(td, present, explicit)
        if '*' in ptype or any('*' in self.il.type_name(self.il.types[p.type]) for p in index_params):
            mods += 'unsafe '
        aliases = {p.name: safe_ident(q.name) for p, q in zip(sparams[:-1], index_params)}
        if sparams:
            aliases[sparams[-1].name] = 'value'
        gbody = self._accessor_lines(getter, td) if getter else None
        sbody = self._accessor_lines(setter, td, aliases) if setter else None
        off = (bk_offs or {}).get(raw, '')
        header = '%s    %s%s %s' % (pre, mods, ptype, pname)
        # Keep compact bodyless declarations (abstract/interface/signatures).
        vis = {getattr(a, 'flags', 6) & 7 for a in present}
        unequal = len(present) == 2 and len(vis) > 1 and not explicit and not td.flags & 0x20
        def access(a):
            if not unequal:
                return ''
            v = METH_VIS.get(getattr(a, 'flags', 6) & 7, '')
            return '' if mods.startswith(v) else v
        if gbody is None and sbody is None:
            out.append(header + ' { ' + (access(getter) + 'get; ' if getter else '') + (access(setter) + 'set; ' if setter else '') + '}' + off)
            return
        out.extend([header + off, pre + '    {'])
        for kind, m, body in (('get', getter, gbody), ('set', setter, sbody)):
            if m is not None:
                self._emit_accessor(out, pre + '        ', kind, m, body, access(m))
        out.append(pre + '    }')

    def emit_event(self, td, out, pre, ev):
        add = self._rel_method(td, ev[2])
        remove = self._rel_method(td, ev[3])
        if add is None or remove is None:
            # Malformed/unrepresentable event: retain its ordinary methods.
            out.append(pre + '    // Event has no complete add/remove pair: ' + safe_ident(sanitize(self.meta.getstr(ev[0]))))
            return False
        raw = self.meta.getstr(ev[0])
        name = self._member_name(raw, td)
        mods = self._accessor_modifiers(td, [add, remove], '.' in raw)
        ty = self.il.type_name(self.il.types[ev[1]]) if 0 <= ev[1] < len(self.il.types) else 'System.Action'
        header = pre + '    ' + mods + 'event ' + ty + ' ' + name
        bodies = []
        for m in (add, remove):
            params = list(self.meta.method_params(m))
            aliases = {params[-1].name: 'value'} if params else {}
            bodies.append(self._accessor_lines(m, td, aliases))
        if all(getattr(a, 'flags', 0) & 0x400 for a in (add, remove)):
            out.append(header + ';')
            return True
        out.extend([header, pre + '    {'])
        for kind, m, body in zip(('add', 'remove'), (add, remove), bodies):
            self._emit_accessor(out, pre + '        ', kind, m, body)
        out.append(pre + '    }')
        return True

    def emit_method(self, m: MethodDef, td: TypeDef, out: List[str], pre: str):
        is_ctor = m.name in ('.ctor', '.cctor')
        sig = self.ctor_sig(m, td) if is_ctor else self.method_sig(m, td)
        abstract = bool(m.flags & 0x400) and not is_ctor
        body = self._lift_body(m, td, abstract)
        ctor_init = None
        if is_ctor:
            if body:
                ctor_init, body = self._ctor_body(body)
            if m.name == '.ctor' and not ctor_init:
                ctor_init = self.ctor_base_initializer(td)
        if abstract:
            out.append('%s%s; // RVA: 0x%x VA: 0x%x' % (pre, sig, m.addr or 0, m.addr or 0)
                       if m.addr else '%s%s;' % (pre, sig))
            return
        if m.addr:
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

    _SUB_REF_RX = re.compile(r'(?<![\w@.])sub_([0-9a-f]+)(?![\w])')

    @classmethod
    def _stub_collect(cls, text):
        """All `sub_<hex>` VAs referenced as calls in emitted text."""
        if not text:
            return set()
        return set(m.group(1) for m in cls._SUB_REF_RX.finditer(text))

    @classmethod
    def _real_sub_names(cls, meta):
        """`sub_<hex>` spellings that are REAL metadata method names."""
        try:
            return frozenset(
                md.name[4:] for md in meta.methods
                if (md.name or '').startswith('sub_')
                and re.fullmatch(r'sub_[0-9a-f]+', md.name or ''))
        except Exception:
            return frozenset()

    def _stub_owners(self, va):
        """Short honesty note per VA: owner count/names, or unregistered."""
        try:
            cands = self.il.addr_candidates.get(int(va, 16)) or []
            if not cands:
                return 'unregistered native target'
            names = []
            for c in cands[:4]:
                try:
                    if c[0] == 'method':
                        m = self.meta.methods[c[1]]
                        td = self.meta.typedefs[m.declaring]
                        names.append('%s.%s' % (td.name, m.name))
                    elif c[0] == 'generic':
                        names.append(str(self.il.generic_method_name(c[1]))[:70])
                    else:
                        names.append(str(c[0]))
                except Exception:
                    names.append('?')
            more = '' if len(cands) <= 4 else ' +%d more' % (len(cands) - 4)
            return '%d owners: %s%s' % (len(cands), ', '.join(names), more)
        except Exception:
            return 'unresolved target'

    def _stub_file_text(self, vas):
        """One global stub class for an assembly's referenced VAs."""
        head = [
            '// <auto-generated>',
            '// Unresolved shared/unregistered native call targets referenced',
            '// by the recovered bodies of this assembly. Each `sub_VA` names',
            '// one native address: either compiled bodies shared by the',
            '// listed metadata owners, or an unregistered native helper.',
            '// Signatures are unknown, so every stub takes any arguments',
            '// and returns object, throwing on invocation; call sites carry',
            '// caller-proven `(T)` casts where the need is proven.',
            '// Generated by il2csharp; never hand-edit.',
            'internal static class __SharedBodyStubs',
            '{',
        ]
        tail = ['}']
        body = []
        for va in sorted(vas):
            body.append('    // 0x%s: %s' % (va, self._stub_owners(va)))
            body.append('    internal static object sub_%s(params object[] args)'
                        ' { throw new System.NotImplementedException('
                        '"unresolved shared native body 0x%s"); }' % (va, va))
        return '\n'.join(head + body + tail) + '\n'

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
        all_sub = set()
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
            all_sub |= self._stub_collect('\n'.join(buf))
            tr = UsingTracker(self.il)
            for l in buf:
                tr.add_text(l)
            uses_set = set(tr.used)   # own ns too: in scope inside its block
            if uses_set:
                dup = collision_heads("\n".join(buf), ns, uses_set, self._short_ns_index())
                buf = strip_namespaces(buf, uses_set, ns, dup)
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
            if self._stub_collect('\n'.join(buf)):
                hdr.append('')
                hdr.append('using static __SharedBodyStubs;')
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
        all_sub = set(v for v in all_sub if v not in self._real_sub_names(self.meta))
        if all_sub:
            with open(os.path.join(asm_dir, '__SharedBodyStubs.cs'), 'w', encoding='utf-8') as fh:
                fh.write(self._stub_file_text(all_sub))
            written += 1
        with open(os.path.join(asm_dir, asm_name + '.csproj'), 'w', encoding='utf-8') as fh:
            fh.write('<Project Sdk="Microsoft.NET.Sdk">\n'
                     '  <PropertyGroup>\n'
                     '    <TargetFramework>netstandard2.1</TargetFramework>\n'
                     '    <AssemblyName>%s</AssemblyName>\n'
                     '    <EnableDefaultCompileItems>true</EnableDefaultCompileItems>\n'
                     '    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>\n'
                     '    <LangVersion>latest</LangVersion>\n'
                     '    <NoWarn>CS0169;CS0649;CS0108;CS0114;CS8019</NoWarn>\n'
                     '  </PropertyGroup>\n'
                     '</Project>\n' % asm_name)
        return written

    def _short_ns_index(self):
        """short typedef name (sans arity) -> namespaces. Built once per
        emitter; metadata does not change during a build."""
        idx = getattr(self, "_short_ns_idx", None)
        if idx is None:
            idx = {}
            for td in self.meta.typedefs:
                try:
                    nm = (td.name or "").split("`")[0]
                except Exception:
                    continue
                if nm:
                    idx.setdefault(nm, set()).add(getattr(td, "namespace", ""))
            self._short_ns_idx = idx
        return idx

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

