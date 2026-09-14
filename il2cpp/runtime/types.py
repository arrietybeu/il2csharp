from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import compressed_int, csharp_type_name, i32, read_compressed_uint, u32, u64
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs

class _TypesMixin:
    def typedef_full(self, ti: int) -> str:
        if not (0 <= ti < len(self.meta.typedefs)):
            return '?'
        td = self.meta.typedefs[ti]
        parts = [td.name]
        d = td.declaring
        seen = 0
        while 0 <= d < len(self.meta.typedefs) and seen < 8:
            dt = self.meta.typedefs[d]
            parts.append(dt.name)
            d = dt.declaring
            seen += 1
        ns = td.namespace
        base = '.'.join(reversed(parts))
        return (ns + '.' + base) if ns else base

    def type_from_ptr(self, ptr) -> Optional[Tuple[int, int]]:
        """Parse an Il2CppType struct at a native VA."""
        t = self._type_by_ptr.get(ptr)
        if t is not None:
            return t
        o = self.bin.va2off(ptr)
        if o is None:
            return None
        t = (u64(self.bin.d, o), u32(self.bin.d, o + 8))
        self._type_by_ptr[ptr] = t
        return t

    _tn_cache: Dict[int, str] = {}

    def type_name(self, type_tuple, depth=0) -> str:
        """C# name for an Il2CppType tuple (data, bits)."""
        if type_tuple is None or depth > 6:
            return 'object'
        data, bits = type_tuple
        te = (bits >> 16) & 0xFF
        byref = (bits >> 29) & 1
        name = self._tn_cache.get((data, bits, depth))
        if name:
            return name
        if te in self.PRIM and te != 0x12:
            nm = self.PRIM[te]
        elif te in (0x11, 0x12):  # valuetype / class
            if te == 0x12 and data == 0 and not byref:
                nm = 'object'
            else:
                td = self.meta.typedefs[data] if 0 <= data < len(self.meta.typedefs) else None
                if td is None:
                    nm = 'object'
                else:
                    nm = csharp_type_name(self.typedef_full(data))
                if nm.startswith('__StaticArrayInitTypeSize='):
                    # IL2CPP spells these compiler-generated size types with
                    # `=N`; the decls are emitted sanitized as `_N`, so match
                    nm = '__StaticArrayInitTypeSize_' + nm[len('__StaticArrayInitTypeSize='):]
                elif nm.startswith('$ArrayType='):
                    # Mono emits the same blob structs as `$ArrayType=N`
                    # (sanitized decl spelling `_ArrayType_N`)
                    nm = '_ArrayType_' + nm[len('$ArrayType='):]
        elif te == 0x0f:  # ptr
            inner = self.type_from_ptr(data)
            nm = self.type_name(inner, depth + 1) + '*'
        elif te == 0x10:  # byref (enum)
            inner = self.type_from_ptr(data)
            nm = 'ref ' + self.type_name(inner, depth + 1)
        elif te == 0x1d:  # szarray
            inner = self.type_from_ptr(data)
            nm = self.type_name(inner, depth + 1) + '[]'
        elif te == 0x15:  # genericinst
            nm = self._generic_inst_name(data, depth)
        elif te in (0x13, 0x1e):  # var / mvar
            gp = self.meta.generic_parameters[data] if 0 <= data < len(self.meta.generic_parameters) else None
            nm = gp[1] if gp else ('T' if te == 0x13 else 'TArg')
        elif te == 0x14:  # multidim array
            inner = self.type_from_ptr(data)
            nm = self.type_name(inner, depth + 1) + '[,]'
        else:
            nm = 'object'
        nm = nm.replace('@', '_')
        self._tn_cache[(data, bits, depth)] = nm
        return nm

    @staticmethod
    def _type_enum(t):
        return (t[1] >> 16) & 0xFF if t else 0

    def _generic_inst_name(self, gc_ptr, depth) -> str:
        b = self.bin
        o = b.va2off(gc_ptr)
        if o is None:
            return 'object'
        type_ptr = u64(b.d, o)
        class_inst = u64(b.d, o + 8)
        t = self.type_from_ptr(type_ptr)
        te = self._type_enum(t)
        d = t[0] if t else 0
        if te in (0x11, 0x12) and 0 <= d < len(self.meta.typedefs):
            base = csharp_type_name(self.typedef_full(d))
            if base.startswith('__StaticArrayInitTypeSize='):
                base = '__StaticArrayInitTypeSize_' + base[len('__StaticArrayInitTypeSize='):]
            base = base.split('.')[-1] if depth > 0 else base
        else:
            base = 'object'
        args = self._inst_args(class_inst, depth)
        if args is None:
            return base
        return '%s<%s>' % (base, ', '.join(args))

    def _inst_args(self, inst_ptr, depth):
        if not inst_ptr:
            return None
        b = self.bin
        o = b.va2off(inst_ptr)
        if o is None:
            return None
        argc = u64(b.d, o)
        argv = u64(b.d, o + 8)
        return self._argv_names(argv, argc, depth)

    def _argv_names(self, argv, argc, depth):
        b = self.bin
        out = []
        for k in range(min(argc, 8)):
            tp = b.qword(argv + k * 8) if argv else None
            t = self.type_from_ptr(tp) if tp else None
            out.append(self.type_name(t, depth + 1) if t else 'object')
        return out

    _str_slots = None

    def string_slots(self):
        """[(slot VA, literal text)] for every StringLiteral usage slot in the binary."""
        if self._str_slots is not None:
            return self._str_slots
        out = []
        nlit = len(self.meta.string_literals)
        b = self.bin
        for sec in b.sections:
            if not sec.is_data or not sec.rawsize:
                continue
            o, n = sec.offset, sec.rawsize // 8
            for j in range(n):
                q = u64(b.d, o + j * 8)
                if (q & 1) and 0 < q < 0x20000000 and ((q >> 29) & 7) == 5:
                    idx = (q & 0x1FFFFFFE) >> 1
                    if 0 <= idx < nlit:
                        out.append((sec.addr + j * 8, self.meta.string_literal(idx)))
        self._str_slots = out
        return out

    def vtable_method(self, td_index, slot) -> Optional[int]:
        """global method index for virtual slot of typedef, or None."""
        td = self.meta.typedefs[td_index]
        if 0 <= slot < td.vtable_count:
            v = self.meta.vtable_methods[td.vtable_start + slot]
            idx = (v & 0x1FFFFFFE) >> 1
            if idx < len(self.meta.methods):
                return idx
        return None

    def enum_members(self, td_idx):
        """value -> 'Member' name map for an enum typedef, or None when
        td_idx is not an enum. Detection is structural: an enum is a
        valuetype whose field list carries the `value__` instance slot;
        members are its static-literal fields, whose constants live in
        the fieldDefaultValues table and its shared data blob. The blob
        entry is decoded through the enum's OWN underlying type
        (`td.element`), exactly as `parse_default` does, because v29+
        metadata stores i4/u4 constants WriteCompressedUInt32-encoded."""
        cache = getattr(self, '_enum_members_cache', None)
        if cache is None:
            cache = self._enum_members_cache = {}
        if td_idx in cache:
            return cache[td_idx]
        cache[td_idx] = None   # pessimistic; survives malformed rows
        td = self.meta.typedefs[td_idx]
        if not td.is_valuetype:
            return None
        fidx = self.meta.type_fields(td)
        rows = [self.meta.fields[i] for i in fidx]
        if not any(r.name == 'value__' for r in rows):
            return None
        out = {}
        d = self.meta.d
        v29 = self.meta.version >= 29
        te_u = None
        if 0 <= td.element < len(self.types):
            te_u = self._type_enum(self.types[td.element])
        for i2, r in zip(fidx, rows):
            a = field_attrs(self, r)
            if not (a & FA_STATIC and a & FA_LITERAL):
                continue
            dv = self.meta.field_default_values.get(i2)
            if dv is None:
                continue
            off = self.meta.dv_off + dv[1]
            if off < 0 or off + 8 > len(self.meta.d):
                continue
            # fix 86: decode with the SAME authority `parse_default` uses.
            # The old code read the blob raw at four widths and kept every
            # result. That is wrong twice over on v29+ metadata: i4/u4
            # constants are WriteCompressedUInt32-encoded, so a raw read
            # returns the zigzag image (FileMode.Open=3 read as 6,
            # DateTimeKind.Utc=1 read as 2), and the extra widths invent
            # keys no member ever had. Non-zero members therefore never
            # matched, and worse, a literal could collide with another
            # member's zigzag image and fold to the WRONG name -- a bare
            # 2 naming FileMode.CreateNew when 2 means Create. Only 0 was
            # ever safe, because zigzag(0) == 0. An underlying type this
            # decoder does not know declines instead of guessing.
            try:
                if te_u == 0x08:
                    v = compressed_int(d, off)[0] if v29 else i32(d, off)
                elif te_u == 0x09:
                    v = read_compressed_uint(d, off)[0] if v29 else u32(d, off)
                elif te_u in (0x04, 0x06, 0x0a):
                    w = {0x04: 1, 0x06: 2, 0x0a: 8}[te_u]
                    v = int.from_bytes(d[off:off + w], 'little', signed=True)
                elif te_u in (0x05, 0x07, 0x0b):
                    w = {0x05: 1, 0x07: 2, 0x0b: 8}[te_u]
                    v = int.from_bytes(d[off:off + w], 'little', signed=False)
                else:
                    continue
            except Exception:
                continue
            out.setdefault(v, r.name.replace('@', '_'))
        if out:
            cache[td_idx] = out
        return cache[td_idx]

    def slot_max_arity(self, slot):
        """Largest declared arity (receiver included) of any
        instance method occupying this vtable slot across ALL
        typedefs -- a provable upper bound for trimming an
        unresolved VIRT_CALL's argument list (batch 21j's proof,
        applied to slot-indexed candidates). Lazy one-time scan."""
        cache = self.__dict__.setdefault('_slot_arity_cache', {})
        if not cache:
            mx = {}
            vt = self.meta.vtable_methods
            nm = len(self.meta.methods)
            for td in self.meta.typedefs:
                for s in range(td.vtable_count):
                    idx = (vt[td.vtable_start + s] & 0x1FFFFFFE) >> 1
                    if idx < nm:
                        m = self.meta.methods[idx]
                        a = m.param_count + (0 if m.is_static else 1)
                        if a > mx.get(s, -1):
                            mx[s] = a
            cache.update(mx)
        return cache.get(slot)

    def interface_method_by_offset(self, type_text, rel_slot):
        """Resolve an interface-offset-search dispatch (todo lead
        #3): `type_text` is the interface's rendered typeof() display
        text (may be a closed generic, e.g. 'System.Collections.
        Generic.IEnumerator<Fusion.PlayerRef>'); `rel_slot` is the
        0-based index into THAT interface's own metadata method
        table. Ground truth (GameManager.CheckAllReady VA
        0x1806DF770): the runtime's linear scan of
        klass->interfaceOffsets[] lands on `offset` -- an ABSOLUTE
        slot in the receiver's class vtable where the interface's
        OWN method block begins -- and a call's further `+ K` bytes
        into that address reads the K/16'th method of the block.
        Interface typedefs carry no runtime vtable of their own
        (vtable_start is -1 -- interfaces are never instantiated), so
        metadata's method_start/method_count IS the authority for
        block order, not any BCL declaration-order assumption --
        verified against ground truth that IEnumerator's method[0]
        is MoveNext, not get_Current. Returns a global method index,
        or None when the type text or slot don't resolve."""
        idx = self.__dict__.setdefault('_td_by_full_name', None)
        if idx is None:
            idx = {}
            for i, td in enumerate(self.meta.typedefs):
                key = ('%s.%s' % (td.namespace, td.name)) if td.namespace else td.name
                idx[key] = i
            self._td_by_full_name = idx
        base, _, rest = type_text.partition('<')
        if rest:
            inner = rest[:-1] if rest.endswith('>') else rest
            depth = 0
            arity = 1
            for ch in inner:
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    arity += 1
            key = '%s`%d' % (base, arity)
        else:
            key = base
        td_idx = idx.get(key)
        if td_idx is None:
            return None
        td = self.meta.typedefs[td_idx]
        if not (0 <= rel_slot < td.method_count):
            return None
        return td.method_start + rel_slot

    def method_simple_name(self, method_index) -> str:
        m = self.meta.methods[method_index]
        td = self.meta.typedefs[m.declaring] if 0 <= m.declaring < len(self.meta.typedefs) else None
        return '%s.%s' % (td.name if td else '?', m.name.lstrip('.'))

    def generic_method_name(self, spec_index, short=True) -> str:
        """methodSpecs[i] = (methodDefinitionIndex, classIndexIndex, methodIndexIndex).
        Memoized: the address-collision disambiguation in `_call` calls this
        once per candidate at every ambiguous shared-generic-body call site,
        and some addresses carry thousands of candidates (MSVC/IL2CPP body
        sharing) -- unmemoized this made a subset build hang for 10+ minutes
        on mscorlib."""
        cache = self.__dict__.setdefault('_gmn_cache', {})
        ck = (spec_index, short)
        if ck in cache:
            return cache[ck]
        if not (0 <= spec_index < len(self.method_specs)):
            r = 'GenericMethod#%d' % spec_index
            cache[ck] = r
            return r
        md, ci, mi = self.method_specs[spec_index]
        m = self.meta.methods[md] if 0 <= md < len(self.meta.methods) else None
        if not m:
            r = 'GenericMethod#%d' % spec_index
            cache[ck] = r
            return r
        td = self.meta.typedefs[m.declaring]
        ns = (td.namespace + '.') if td.namespace else ''
        # `_info_name` sanitizes the non-generic branch; this one renders the
        # method name straight from metadata, so local-function (`|`),
        # marshalling (`@`) and leading-dot (`.cctor`) names reached the tree
        # unmangled -- the def side is covered by `sanitize()`, only the
        # CALL-TARGET render came through here. Do it before `<margs>` is
        # appended: generic args legitimately contain `<`, `>`, `.` and `,`.
        name = m.name.lstrip('.').replace('|', '_').replace('@', '_')
        # method instantiation.  MethodSpec stores ZERO-based GenericInst
        # indices and spells "no instantiation" as -1, never as 0: across
        # all 175736 specs the zero-based read matches the declared generic
        # arity 100% of the time (32671 method rows, 144977 class rows, no
        # exceptions), while the former one-based read left 2749 rows whose
        # argument count contradicted the declaration it belongs to -- see
        # work/review89_spec_arity_census.py.  A row is None when its
        # registration data was unreadable; unpacking that would raise.
        margs = None
        mrow = self.generic_insts_list[mi] \
            if 0 <= mi < len(self.generic_insts_list) else None
        if mrow is not None:
            argc, argv = mrow
            margs = self._argv_names(argv, argc, 0)
        # class instantiation (only if declaring type is generic)
        cargs = None
        crow = self.generic_insts_list[ci] \
            if 0 <= ci < len(self.generic_insts_list) else None
        if crow is not None:
            argc, argv = crow
            cargs = self._argv_names(argv, argc, 0)
        if cargs:
            base = '%s%s<%s>' % (ns, td.name, ', '.join(cargs))
        else:
            base = ns + td.name
        if margs:
            name += '<%s>' % ', '.join(margs)
        r = '%s.%s' % (csharp_type_name(base), name)
        cache[ck] = r
        return r

    def _argv_type_tuples(self, argc, argv):
        """Closed type arguments stored in one Il2CppGenericInst.

        Return ``None`` rather than a partial tuple when registration data is
        unreadable.  Return-type consensus is an all-candidates proof; one
        missing argument must therefore make it decline.
        """
        cache = self.__dict__.setdefault('_argv_type_tuple_cache', {})
        ck = (argc, argv)
        if ck in cache:
            return cache[ck]
        result = None
        if isinstance(argc, int) and 0 <= argc <= 64 and (argv or argc == 0):
            values = []
            for k in range(argc):
                tp = self.bin.qword(argv + k * 8)
                ty = self.type_from_ptr(tp) if tp else None
                if ty is None:
                    break
                values.append(ty)
            else:
                result = tuple(values)
        cache[ck] = result
        return result

    def _method_spec_type_args(self, inst_index):
        """Type tuples for a method-spec class/method instantiation.

        MethodSpec stores zero-based GenericInst indices; -1 means that the
        corresponding class or method has no instantiation.  The base is not
        an assumption: it is the only one of the two that agrees with every
        declared generic arity in the corpus (work/review89_spec_arity_census.py).
        """
        if not (0 <= inst_index < len(self.generic_insts_list)):
            return None
        row = self.generic_insts_list[inst_index]
        return self._argv_type_tuples(*row) if row is not None else None

    def _closed_type_key(self, ty):
        """Structural identity for a fully closed managed type.

        Parameter/field attributes in the low bits do not change type
        identity, but byref does change both meaning and ABI.  VAR/MVAR at
        any depth makes the key unavailable: printing an open ``T`` as a
        concrete call result would only replace one unknown with another.
        """
        cache = self.__dict__.setdefault('_closed_type_key_cache', {})
        if ty in cache:
            return cache[ty]

        def walk(cur, depth, seen):
            if cur is None or depth > 16:
                return None
            data, bits = cur
            te = (bits >> 16) & 0xFF
            byref = (bits >> 29) & 1
            marker = (data, te)
            if marker in seen:
                return None
            if te in (0x13, 0x1e):       # VAR / MVAR
                return None
            if 0x01 <= te <= 0x0e or te in (0x16, 0x18, 0x19, 0x1c):
                return (te, byref)
            if te in (0x11, 0x12, 0x55):
                return (te, data, byref)
            if te in (0x0f, 0x10, 0x1d):  # pointer / byref / szarray
                inner = self.type_from_ptr(data)
                ik = walk(inner, depth + 1, seen | {marker})
                return (te, ik, byref) if ik is not None else None
            if te == 0x14:               # Il2CppArrayType (multidim)
                o = self.bin.va2off(data)
                if o is None:
                    return None
                ep = u64(self.bin.d, o)
                ik = walk(self.type_from_ptr(ep) if ep else None,
                          depth + 1, seen | {marker})
                return (te, ik, self.bin.d[o + 8], byref) \
                    if ik is not None and o + 8 < len(self.bin.d) else None
            if te == 0x15:               # GENERICINST
                o = self.bin.va2off(data)
                if o is None:
                    return None
                basep, instp = u64(self.bin.d, o), u64(self.bin.d, o + 8)
                bk = walk(self.type_from_ptr(basep) if basep else None,
                          depth + 1, seen | {marker})
                io = self.bin.va2off(instp) if instp else None
                if bk is None or io is None:
                    return None
                args = self._argv_type_tuples(u64(self.bin.d, io),
                                              u64(self.bin.d, io + 8))
                if args is None:
                    return None
                keys = tuple(walk(a, depth + 1, seen | {marker}) for a in args)
                return (te, bk, keys, byref) \
                    if all(k is not None for k in keys) else None
            # Unsupported/rare compound classes may hide type parameters;
            # declining is safer than treating an opaque pointer as closed.
            return None

        result = walk(ty, 0, set())
        cache[ty] = result
        return result

    def candidate_return_type(self, candidate):
        """Closed return type for one address candidate, if provable."""
        cache = self.__dict__.setdefault('_candidate_return_type_cache', {})
        if candidate in cache:
            return cache[candidate]
        result = None
        kind, index = candidate
        spec = None
        if kind == 'method':
            mi = index
        elif kind == 'generic' and 0 <= index < len(self.method_specs):
            spec = self.method_specs[index]
            mi = spec[0]
        else:
            mi = -1
        if 0 <= mi < len(self.meta.methods):
            ri = self.meta.methods[mi].return_type
            ty = self.types[ri] if 0 <= ri < len(self.types) else None
            te = self._type_enum(ty)
            if spec is not None and te in (0x13, 0x1e) \
                    and 0 <= ty[0] < len(self.meta.generic_parameters):
                ordinal = self.meta.generic_parameters[ty[0]][4]
                inst = spec[1] if te == 0x13 else spec[2]
                args = self._method_spec_type_args(inst)
                actual = args[ordinal] \
                    if args is not None and 0 <= ordinal < len(args) else None
                if actual is not None:
                    # Type arguments cannot themselves be byref.  The return
                    # signature owns that bit; the argument owns enum/data.
                    ty = (actual[0], (actual[1] & ~(1 << 29))
                          | (ty[1] & (1 << 29)))
            if self._closed_type_key(ty) is not None:
                result = ty
        cache[candidate] = result
        return result

    def _return_abi_is_known(self, ty):
        """Whether ``ty`` has an exact Win64 managed return ABI."""
        if ty is None:
            return False
        bits = ty[1]
        if (bits >> 29) & 1:
            return False                # ref-return syntax is not modelled
        te = (bits >> 16) & 0xFF
        if te == 0x11:
            size = self.value_type_size(ty[0])
            return size is not None and size > 0
        if te == 0x15:
            td = self.td_of_ty(ty)
            return td is not None and not self.meta.typedefs[td].is_valuetype
        # TypedReference and opaque runtime/modifier classes need their own
        # ABI model.  Everything below is scalar, pointer, or managed ref.
        return te in set(range(0x01, 0x10)) | {
            0x0f, 0x12, 0x14, 0x18, 0x19, 0x1c, 0x1d}

    def shared_return_type(self, target):
        """Return type agreed by every metadata owner of ``target``.

        Identity may remain ambiguous after receiver/rgctx argument proofs,
        yet its result ABI and managed type need not be.  Consensus reveals
        only what every possible owner states; a missing, open-generic, or
        disagreeing candidate keeps the old unknown result.
        """
        cache = self.__dict__.setdefault('_shared_return_type_cache', {})
        if target in cache:
            return cache[target]
        cands = self.addr_candidates.get(target)
        result = None
        if cands and len(cands) > 1:
            first_key = None
            first_type = None
            for candidate in cands:
                ty = self.candidate_return_type(candidate)
                key = self._closed_type_key(ty)
                if key is None or not self._return_abi_is_known(ty):
                    break
                if first_key is None:
                    first_key, first_type = key, ty
                elif key != first_key:
                    break
            else:
                result = first_type
        cache[target] = result
        return result

    # ==================================================================
    # usage slots (v27.1+ lazy handles)
    # ==================================================================

    USG_KINDS = {1: 'TypeInfo', 2: 'Il2CppType', 3: 'MethodDef',
                 4: 'FieldInfo', 5: 'StringLiteral', 6: 'MethodRef'}
    _slot_cache: Dict[int, Optional[dict]] = {}
