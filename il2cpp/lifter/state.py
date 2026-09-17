from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.expr import Expr, _BINDABLE_KINDS, _RegState, _USE_BIND_MIN, _is_unresolved_gp, _mentions
from il2cpp.metadata import MethodDef, TypeDef
from il2cpp.names import safe_ident
from il2cpp.runtime.core import Il2Cpp
from il2cpp.text import imm_of, reg_name, strip_outer
from il2cpp.x64 import ARG_REGS, ARG_XMM, GPRS, GPR_ALIAS, VOLATILE

class _StateMixin:
    """Lift one native method body to pseudo-C# statements."""

    def __init__(self, il2: Il2Cpp, asm_comments=False):
        self.il = il2
        self.bin = il2.bin
        self.meta = il2.meta
        self.asm_comments = asm_comments
        self.dry = False       # decompiler pass 1 suppresses use-binding
        self._cur_ip = 0
        self._copying = False  # a reg-reg move re-homes a value; not a use
        self._init_runtime_ids()

    # Runtime-helper arity: the Win64 register spray pads a call with the
    # leftover GPR/XMM residues, and these helpers legitimately read only
    # the first couple arguments. arity is keyed by the rt_names string,
    # so `_call_name` wiring (which follows jmp thunks too) carries it.
    RT_ARITY = {
        'il2cpp_codegen_initialize_runtime_metadata': 1,
        'il2cpp_object_new': 1,
        'il2cpp_codegen_write_barrier': 2,
        'il2cpp_runtime_class_init': 1,
    }

    @staticmethod
    def _return_value_register(rty):
        """Win64 register carrying a scalar managed return value.

        Single and Double values use XMM0.  Their by-reference forms return
        an address and therefore use RAX despite retaining the R4/R8 element
        enum in metadata.  Other value/reference returns also use RAX; large
        structs are handled separately by the hidden sret-buffer path.
        """
        if isinstance(rty, tuple) and len(rty) >= 2:
            bits = rty[1]
            if ((bits >> 16) & 0xFF) in (0x0c, 0x0d) \
                    and not ((bits >> 29) & 1):
                return 'XMM0'
        return 'RAX'

    def _is_scalar_sqrt_helper(self, target):
        """Recognize the unregistered double sqrt/domain wrapper by proof.

        Unity's Windows player calls a CRT-style helper on the negative/NaN
        arm of an inlined sqrt diamond.  It has no MethodDef or export, so an
        address/name guess would be target-specific.  Require the helper's
        complete local signature instead: XMM0 double spill/return, a scalar
        SQRTSD path, and the RIP-relative error-name literal ``sqrt``.  A
        different runtime stays unrecognized and therefore keeps the honest
        fallback.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or not 0 < finish - target <= 0x400:
            return False
        code = self.bin.read(target, finish - target)
        if not code:
            return False
        try:
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            insns = list(dec)
        except Exception:
            return False
        spilled = rooted = named = returned = loaded = False
        for ins in insns:
            if (ins.mnemonic == Mnemonic.MOVSD
                    and ins.op0_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RSP
                    and ins.op1_kind == OpKind.REGISTER
                    and reg_name(ins.op1_register) == 'XMM0'):
                spilled = True
            elif ins.mnemonic == Mnemonic.SQRTSD:
                rooted = True
            elif (ins.mnemonic == Mnemonic.LEA
                    and ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == 'RCX'
                    and ins.op1_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RIP):
                named = self.bin.cstr(ins.ip_rel_memory_address, 32) == 'sqrt' or named
            elif (ins.mnemonic == Mnemonic.MOVSD
                    and ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == 'XMM0'
                    and ins.op1_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RSP):
                loaded = True
            elif ins.mnemonic == Mnemonic.RET:
                returned = True
        return spilled and rooted and named and loaded and returned

    def _is_fence_body(self, target):
        """Recognize the unregistered full-fence helper by proof. -- fix 107

        Exactly `lock or dword ptr [rsp],0; ret`: a locked RMW of its own
        stack slot (the full barrier MSVC emits where the source calls
        `Thread.MemoryBarrier`) then return. The store preserves the
        slot (`x|0 == x`), no register is read or written, and the
        immediate must be zero (anything else would corrupt the return
        address slot it touches); `ret` terminates the extent, so no
        bounds analysis is needed. Registered/exported owners decline,
        as does anything unreadable. Ground truth:
        `System.Threading.Thread.MemoryBarrier`'s own recovered body is
        one call to 0x1804429c0 (RVA 0x1D1F380). Results are memoized;
        never hardcode an address.
        """
        cache = getattr(self, "_fence_cache", None)
        if cache is None:
            cache = self._fence_cache = {}
        if target in cache:
            return cache[target]
        res = self._is_fence_body_inner(target)
        cache[target] = res
        return res

    def _is_fence_body_inner(self, target):
        try:
            if not HAVE_ICED or not target:
                return False
            if self.il.addr_candidates.get(target):
                return False
            if target in self.bin.exports:
                return False
            if not self.bin.is_exec_va(target):
                return False
            code = self.bin.read(target, 16)
            if not code:
                return False
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            ii = [next(iter(dec)) for _ in range(2)]
        except Exception:
            return False
        try:
            i0 = ii[0]
            if i0.mnemonic != Mnemonic.OR or not i0.has_lock_prefix:
                return False
            if i0.op0_kind != OpKind.MEMORY or i0.memory_base != IReg.RSP:
                return False
            if i0.memory_displacement != 0:
                return False
            if MemorySizeExt.size(i0.memory_size) != 4:
                return False
            if i0.op1_kind in (OpKind.IMMEDIATE8,
                               OpKind.IMMEDIATE8TO32):
                if getattr(i0, "immediate8", 1) != 0:
                    return False
            elif i0.op1_kind == OpKind.IMMEDIATE32:
                if getattr(i0, "immediate32", 1) != 0:
                    return False
            else:
                return False
            return ii[1].mnemonic == Mnemonic.RET
        except Exception:
            return False

    def _fence_target(self, va):
        """Fence VA reached from `va` (itself or <=3 jmp hops), else None."""
        try:
            if not va:
                return None
            if self._is_fence_body(va):
                return va
            cur = va
            for _ in range(3):
                if not self.bin.is_exec_va(cur):
                    return None
                code = self.bin.read(cur, 8)
                if not code:
                    return None
                try:
                    dec = Decoder(64, code, DecoderOptions.NONE)
                    dec.ip = cur
                    ins = next(iter(dec))
                except Exception:
                    return None
                if ins.mnemonic != Mnemonic.JMP \
                        or ins.op0_kind != OpKind.NEAR_BRANCH64 \
                        or ins.len > 6:
                    return None
                cur = ins.near_branch_target
                if self._is_fence_body(cur):
                    return cur
            return None
        except Exception:
            return None

    def _init_runtime_ids(self):
        """Identify il2cpp runtime helper functions by structural signature."""
        self.rt_init_meta = None
        b = self.bin
        # find the dominant callee of (lea rcx,[rip] ; call) across a sample of methods
        from collections import Counter
        cnt = Counter()
        img = next((i for i, im in enumerate(self.meta.images)
                    if im.name == 'Assembly-CSharp.dll'), 0)
        im = self.meta.images[img]
        dec_ip_base = []
        for ti in range(im.type_start, min(im.type_start + im.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if not m.addr:
                    continue
                code = b.read(m.addr, 512)
                if not code:
                    continue
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = m.addr
                last_lea = False
                for ins in dec:
                    if ins.mnemonic == Mnemonic.LEA and ins.op0_register == IReg.RCX \
                            and ins.memory_base == IReg.RIP:
                        last_lea = True
                    elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                        if last_lea:
                            cnt[ins.near_branch_target] += 1
                        last_lea = False
                    elif ins.mnemonic == Mnemonic.RET:
                        break
                if sum(cnt.values()) > 4000:
                    break
        self.rt_init_meta = cnt.most_common(1)[0][0] if cnt else None
        # box helper: identified by export name, not hardcoded address
        self.rt_value_box = next(
            (va for va, nm in b.exports.items() if nm == 'il2cpp_value_box'), None)

        # classify hot unknown helpers by the instruction feeding rcx at the call:
        #   mov rcx,[slot->TypeInfo]   -> alloc family (object/array new)
        #   lea rcx,[obj+disp]         -> GC write barrier store
        stats = {}  # target -> [total, arg_klass, arg_addr, sample_type_name]
        img = next((i for i, im in enumerate(self.meta.images)
                    if im.name == 'Assembly-CSharp.dll'), 0)
        im = self.meta.images[img]
        budget = 6000
        for ti in range(im.type_start, min(im.type_start + im.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if not m.addr:
                    continue
                code = b.read(m.addr, 512)
                if not code:
                    continue
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = m.addr
                pend = []  # (ip, kind, sample) rcx writers pending
                for ins in dec:
                    if (ins.mnemonic == Mnemonic.MOV or ins.mnemonic == Mnemonic.MOVZX)                             and ins.op0_kind == OpKind.REGISTER                             and reg_name(ins.op0_register) == 'RCX':
                        if ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                            usg = self.il.decode_slot(ins.ip_rel_memory_address)
                            if usg and usg.get('kind') in (1, 2):
                                pend.append(('klass', usg.get('text')))
                            else:
                                pend.append((None, None))
                        else:
                            pend.append((None, None))
                    elif ins.mnemonic == Mnemonic.LEA and ins.op0_register == IReg.RCX:
                        pend.append(('addr' if ins.memory_base != IReg.RIP else None, None))
                    elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                        t = ins.near_branch_target
                        if t not in self.il.addr_to_method and t not in self.il.bin.exports:
                            argk = pend[-1] if pend else (None, None)
                            st = stats.setdefault(t, [0, 0, 0, argk[1]])
                            st[0] += 1
                            if argk[0] == 'klass':
                                st[1] += 1
                            elif argk[0] == 'addr':
                                st[2] += 1
                            if st[3] is None and argk[1]:
                                st[3] = argk[1]
                        pend = []
                    elif ins.mnemonic == Mnemonic.RET:
                        break
                budget -= 1
                if budget <= 0:
                    break
            if budget <= 0:
                break
        self.rt_alloc = None
        self.rt_arrnew = set()
        self.rt_wbarrier = set()
        self.rt_names = {}
        if self.rt_init_meta:
            self.rt_names[self.rt_init_meta] = 'il2cpp_codegen_initialize_runtime_metadata'
            # the wrapper's own callee is the same routine (and the 86k-site
            # jmp-thunk band points at that inner address too): name it the
            # same instead of leaving it `sub_...`.
            code = b.read(self.rt_init_meta, 32)
            if code:
                try:
                    dec4 = Decoder(64, code, DecoderOptions.NONE)
                    dec4.ip = self.rt_init_meta
                    for ins in dec4:
                        if ins.mnemonic in (Mnemonic.CALL, Mnemonic.JMP) \
                                and ins.op0_kind == OpKind.NEAR_BRANCH64:
                            self.rt_names[ins.near_branch_target] = \
                                'il2cpp_codegen_initialize_runtime_metadata'
                            break
                        if ins.ip - self.rt_init_meta > 24:
                            break
                except Exception:
                    pass
        for t, (total, nkl, naddr, sample) in sorted(stats.items(), key=lambda kv: -kv[1][0])[:40]:
            if t == self.rt_init_meta or total < 8:
                continue
            if nkl >= total * 0.6:
                if sample and '[' in sample:
                    self.rt_arrnew.add(t)
                    self.rt_names[t] = 'il2cpp_array_new'
                else:
                    if self.rt_alloc is None:
                        self.rt_alloc = t
                        self.rt_names[t] = 'il2cpp_object_new'
            elif naddr >= total * 0.6:
                self.rt_wbarrier.add(t)
                self.rt_names[t] = 'il2cpp_codegen_write_barrier'
        self._helper_stats = stats
        sqrt_helpers = [target for target in stats
                        if self._is_scalar_sqrt_helper(target)]
        self.rt_sqrt = sqrt_helpers[0] if len(sqrt_helpers) == 1 else None
        self._thunk_cache = {}
        self._twin_cache = {}
        self._cls_init_export = next(
            (va for va, nm0 in b.exports.items()
             if nm0 == 'il2cpp_runtime_class_init'), None)

        # noreturn raiser family: MSVC thunks `sub rsp,X; call T; int3` that
        # unconditionally build one specific managed exception (the chain
        # lea's its class name into the exception ctor) and raise it. Name
        # the thunk by that exception -- it is the codegen-level
        # "throw new <Exc>()" word, parameterless by construction. Also the
        # class-init inline twin: `cmp dword [rcx+0E4h],0; je <export>` is
        # the out-of-line copy of the fast path the compiler usually
        # inlines; it returns the klass itself.
        try:
            cls_init_export = next(
                (va for va, nm0 in b.exports.items()
                 if nm0 == 'il2cpp_runtime_class_init'), None)
            for t in sorted(set(cnt) | set(stats)):
                if t in self.rt_names or t in b.exports:
                    continue
                if t in self.il.addr_to_method:
                    continue
                if cnt.get(t, 0) < 2 and t not in stats:
                    continue
                code = b.read(t, 16)
                if not code:
                    continue
                try:
                    dec5 = Decoder(64, code, DecoderOptions.NONE)
                    dec5.ip = t
                    ins0 = next(iter(dec5))
                    if ins0.mnemonic == Mnemonic.CMP \
                            and ins0.op0_kind == OpKind.MEMORY \
                            and ins0.memory_base == IReg.RCX \
                            and ins0.memory_displacement == 0xE4 \
                            and ins0.op1_kind in (OpKind.IMMEDIATE8,
                                                  OpKind.IMMEDIATE8TO16,
                                                  OpKind.IMMEDIATE8TO32,
                                                  OpKind.IMMEDIATE8TO64,
                                                  OpKind.IMMEDIATE16,
                                                  OpKind.IMMEDIATE32,
                                                  OpKind.IMMEDIATE64):
                        ins1 = next(iter(dec5))
                        if cls_init_export and ins1.mnemonic in (Mnemonic.JE, Mnemonic.JNE) \
                                and ins1.op0_kind == OpKind.NEAR_BRANCH64 \
                                and ins1.near_branch_target == cls_init_export:
                            self.rt_names[t] = 'il2cpp_runtime_class_init'
                            continue
                except Exception:
                    pass
                exc = None
                if t != self.rt_init_meta:
                    hops, cur = 0, t
                    while hops < 4:
                        code = b.read(cur, 32)
                        if not code:
                            break
                        try:
                            dec5 = Decoder(64, code, DecoderOptions.NONE)
                            dec5.ip = cur
                            ii = [next(iter(dec5)) for _ in range(2)]
                        except Exception:
                            break
                        if ii[0].mnemonic != Mnemonic.SUB \
                                or ii[0].op0_kind != OpKind.REGISTER \
                                or reg_name(ii[0].op0_register) != 'RSP' \
                                or ii[1].mnemonic != Mnemonic.CALL \
                                or ii[1].op0_kind != OpKind.NEAR_BRANCH64:
                            break
                        nxt = ii[1].near_branch_target
                        if exc is None:
                            exc = self._scan_exc_refs(nxt, 2)
                        cur = nxt
                        hops += 1
                if exc:
                    self.RT_ARITY = dict(self.RT_ARITY)
                    self.rt_names[t] = 'raise_%s' % exc
                    self.RT_ARITY['raise_%s' % exc] = 0
        except Exception:
            pass

    def _scan_exc_refs(self, va, depth):
        """Best-effort name scan for the noreturn raise helpers: any
        RIP-relative lea in the wrapper chain referencing a C string ending
        in 'Exception' is the managed exception that chain raises."""
        if depth < 0:
            return None
        code = self.bin.read(va, 256)
        if not code:
            return None
        try:
            dec5 = Decoder(64, code, DecoderOptions.NONE)
            dec5.ip = va
            found = None
            calls = []
            for i, ins in enumerate(dec5):
                if i >= 40:
                    break
                if ins.mnemonic == Mnemonic.LEA and ins.memory_base == IReg.RIP \
                        and ins.op0_kind == OpKind.REGISTER:
                    o = self.bin.va2off(ins.ip_rel_memory_address)
                    if o is not None:
                        s = self.bin.d[o:o + 64].split(b'\x00')[0]
                        try:
                            s = s.decode('utf-8')
                        except Exception:
                            s = ''
                        if s.endswith('Exception'):
                            found = s
                elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                    calls.append(ins.near_branch_target)
                elif ins.mnemonic == Mnemonic.RET:
                    break
            if found:
                return found.rsplit('.', 1)[-1]
            for c in calls:
                f2 = self._scan_exc_refs(c, depth - 1)
                if f2:
                    return f2
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    def lift(self, m: MethodDef, td: TypeDef) -> List[str]:
        b = self.bin
        va = m.addr
        nxt = self.il.next_method_start(va) if hasattr(self.il, 'next_method_start') else None
        end = min(nxt or (va + 0x10000), va + 0x10000)
        code = b.read(va, end - va)
        if not code:
            return ['/* no code */']
        self.cur_va = va
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = va
        fmt = None
        if self.asm_comments:
            fmt = Formatter(FormatterSyntax.NASM)
            fmt.digit_separator = ''

        self.regs = self._new_regs()
        self.dry = False   # a mid-lift_method exception can leave this set
        self._memory_rhs_loop_guard = False  # flat lift preserves native labels
        self._array_allocation_loop_guard = False
        self._cur_ip = 0
        self.rsp_delta = 0
        self.stack_map: Dict[int, str] = {}   # slot offset from entry rsp -> var name
        self.slot_types: Dict[str, tuple] = {}  # stack var -> il2cpp type (sret buffers)
        self.stack_values: Dict[str, Expr] = {}  # current simple value parked in a stack slot
        self.vt_recv_slot = None
        self.vt_recv = None
        self.addr_of = {}
        self.var_n = 0
        self.flags = None                      # (lhs, rhs, cmpop)
        self.out: List[Tuple[int, str, Optional[str]]] = []  # (ip, code, asm)
        self.targets = set()

        # decode everything, then find logical end: first ret / unconditional
        # indirect jump; direct jmp-out handled at emission
        raw = []
        for ins in dec:
            raw.append(ins)
            if len(raw) >= 20000:
                break
        term_idx = len(raw)
        for i, ins in enumerate(raw):
            fc = ins.flow_control
            if fc == FlowControl.RETURN:
                term_idx = i + 1
                break
            if fc == FlowControl.UNCONDITIONAL_BRANCH and ins.op0_kind != OpKind.NEAR_BRANCH64:
                term_idx = i + 1
                break
        insns = raw[:term_idx]
        last_ip = insns[-1].next_ip if insns else va
        for ins in insns:
            fc = ins.flow_control
            if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH)                     and ins.op0_kind == OpKind.NEAR_BRANCH64:
                t = ins.near_branch_target
                if va <= t < last_ip:
                    self.targets.add(t)

        # peephole: swallow metadata-init guards
        #   cmp byte [rip+X],0 ; <benign movs> ; jcc T ; <lea/call init... + movs> ;
        #   mov byte [rip+X],1 ; T:
        # only the cmp/jcc/lea+call-init/mov-flag-store are skipped; other movs run.
        self.skip_ips = set()
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.CMP and ins.op0_kind == OpKind.MEMORY                     and ins.memory_base == IReg.RIP and ins.memory_size == 1:
                if imm_of(ins, 1) != 0:
                    continue
                slotA = ins.ip_rel_memory_address
                # find the guard jcc within the next 4 instructions (movs may interleave)
                j_idx = None
                for k in range(i + 1, min(i + 5, len(insns))):
                    w = insns[k]
                    if w.flow_control == FlowControl.CONDITIONAL_BRANCH and w.op0_kind == OpKind.NEAR_BRANCH64:
                        j_idx = k
                        break
                    if w.mnemonic not in (Mnemonic.MOV, Mnemonic.MOVZX):
                        break
                if j_idx is None:
                    continue
                T = insns[j_idx].near_branch_target
                # scan forward for mov byte [rip+slotA],1 landing at/before T
                found = False
                for k in range(j_idx + 1, min(j_idx + 24, len(insns))):
                    w = insns[k]
                    if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY                             and w.memory_base == IReg.RIP and w.memory_size == 1                             and w.ip_rel_memory_address == slotA and imm_of(w, 1) == 1:
                        if w.next_ip == T or (k + 1 < len(insns) and insns[k + 1].ip == T):
                            found = True
                        break
                    if w.mnemonic not in (Mnemonic.LEA, Mnemonic.MOV, Mnemonic.CALL,
                                          Mnemonic.MOVZX, Mnemonic.XOR, Mnemonic.PUSH, Mnemonic.SUB):
                        break
                    if w.ip >= T:
                        break
                if not found:
                    continue
                # skip: cmp, jcc, the flag store, and every (lea rcx,[rip]; call) pair between
                self.skip_ips.add(ins.ip)
                self.skip_ips.add(insns[j_idx].ip)
                for k in range(j_idx + 1, len(insns)):
                    w = insns[k]
                    if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY                             and w.memory_base == IReg.RIP and w.memory_size == 1                             and w.ip_rel_memory_address == slotA:
                        self.skip_ips.add(w.ip)
                        break
                    if w.mnemonic == Mnemonic.LEA and w.op0_register == IReg.RCX                             and w.memory_base == IReg.RIP:
                        self.skip_ips.add(w.ip)
                    elif w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64                             and w.near_branch_target == self.rt_init_meta:
                        self.skip_ips.add(w.ip)
        # peephole: swallow class-init guards
        #   mov rA,[rip slot->TypeInfo] ; cmp dword [rA+E4],0 ; jne T ;
        #   mov rcx,rA ; call class_init ; mov rA,[rip slot] ; T:
        _ci_ip_idx = {x.ip: xi for xi, x in enumerate(insns)}
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER                     and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = self.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') in (1, 2)):
                    continue
                regA = reg_name(ins.op0_register)
                k = i + 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if not (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.MEMORY
                        and reg_name(w.memory_base) == regA and w.memory_displacement == 0xE4):
                    continue
                k += 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                k += 1
                # T is the guard's own merge point (the fast `jne T` path
                # jumps straight past the call, whatever the slow path does
                # before reaching it) -- a provable bound, unlike a fixed
                # instruction-count lookahead, which can run past T and
                # swallow real code when no slot-reload mov exists to stop
                # it early (batch 21: `mov rcx,rA` direct reuse instead of
                # a second `mov rA,[slot]`, e.g. AmbientMusicSystem.Awake).
                t_idx = _ci_ip_idx.get(T)
                if t_idx is None or t_idx < k:
                    continue
                # find the class-init call within the guard body (i+1..t_idx)
                ok2 = False
                for m3 in range(k, t_idx):
                    w3 = insns[m3]
                    if w3.mnemonic == Mnemonic.CALL and w3.op0_kind == OpKind.NEAR_BRANCH64:
                        tgt = w3.near_branch_target
                        nm3 = self._call_name(tgt)
                        if 'class_init' in nm3 or 'ClassInit' in nm3 or tgt not in self.il.addr_to_method:
                            # the whole guard body is bounded by T; nothing
                            # in [i+1, t_idx) can be real code (see above)
                            for q in range(i + 1, t_idx):
                                self.skip_ips.add(insns[q].ip)
                            ok2 = True
                        break
                if ok2:
                    continue
        # peephole: swallow icall thunk-cache guards
        #   mov rA,[rel CELL->method] ; test rA,rA ; jne T ;
        #   lea rcx,[rel sig] ; call helper ; mov [rel CELL],rax ; T:
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = self.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') == 3):
                    continue
                k = i + 1
                regA = reg_name(ins.op0_register)
                # the test may sit a few instructions out (thunk prologues
                # park register saves between the load and the test); nothing
                # in between may overwrite regA
                t_idx = None
                for k2 in range(k, min(k + 7, len(insns))):
                    w = insns[k2]
                    if (w.mnemonic == Mnemonic.TEST and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA):
                        t_idx = k2
                        break
                    if (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA and imm_of(w, 1) == 0):
                        t_idx = k2
                        break
                    if w.flow_control != FlowControl.NEXT or \
                            (w.op0_kind == OpKind.REGISTER
                             and reg_name(w.op0_register) == regA):
                        break
                if t_idx is None:
                    continue
                k = t_idx + 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                range_ips = []
                saw_store = False
                for q in range(k, min(k + 10, len(insns))):
                    wq = insns[q]
                    if wq.ip >= T:
                        break
                    range_ips.append(wq.ip)
                    if wq.mnemonic == Mnemonic.MOV and wq.op0_kind == OpKind.MEMORY \
                            and wq.memory_base == IReg.RIP \
                            and wq.ip_rel_memory_address == ins.ip_rel_memory_address:
                        saw_store = True
                        break
                if saw_store:
                    self.skip_ips.update(range_ips)

        self.targets -= self.skip_ips

        self._u = 0
        for _r in GPRS + ['XMM%d' % _k for _k in range(16)]:
            if _r == 'RSP':
                continue
            self._u += 1
            _e = Expr('v%d' % self._u, None, '?')
            _e._unk = True            # fix 58: never written yet
            self.regs[_r] = _e
        self._setup_entry(m, td)

        for i, ins in enumerate(insns):
            if ins.ip in self.skip_ips:
                continue
            if ins.ip in self.targets and self.out:
                self.emit(ins.ip, '', None)  # label marker
            self._insn(ins, insns, i, fmt, end)
        return self._render()

    # ------------------------------------------------------------------
    def _setup_entry(self, m: MethodDef, td: TypeDef):
        # Constructor call rendering needs the caller identity: `this` plus a
        # same-type target is `: this(...)`; an ancestor target is `: base(...)`.
        self._current_method = m
        self._current_td = td
        # reset per method/pass: t-names repeat across methods and v-names
        # differ between the two analysis passes, so leftovers mis-type
        self._var_types = {}
        if not hasattr(self, 'stack_map'):
            self.stack_map = {}
        if not hasattr(self, 'slot_types'):
            self.slot_types = {}
        if not hasattr(self, 'rsp_delta'):
            self.rsp_delta = 0
        # per-method (per-pass) type evidence: token -> Il2CppType tuple,
        # gathered at calls/stores/returns and consumed live by _field_expr
        self._type_hints = {}
        # tokens whose _bind-time type was withheld specifically because it
        # was an unresolved generic parameter (fix 21f) -- a later type hint
        # for one of these means the token's DECLARATION text was rescued
        # from a bare `T`, so the RHS call/index that produced it lost its
        # own `<T>` too and is worth re-annotating (_rename_locals).
        self._gp_blocked = set()
        self._last_tabread = None
        self.stack_values = {}
        byval_bits = (0x12 << 16)
        this_ty = (td.index, byval_bits)
        args = self.meta.method_params(m)
        # fix 57: ONE shared Win64 positional counter, the same walk
        # _positional_args (fix 42b) and _hint_arg_types (fix 53) do on
        # the caller side -- argument N takes register slot N, as RCX/
        # RDX/R8/R9 when integral and XMM0-3 when float, never a
        # per-class ordinal. `this` is argument 0 of an instance method,
        # so `double DateTime.AddDays(double)` reads its parameter from
        # XMM1 (disasm-proven at 0x181c94c40 and three more, see
        # work/probe_b50_entryfloat.py). Two independent counters seated
        # it in XMM0 and left every read of the real register rendering
        # as an undefined temp.
        # fix 59b (todo lead 5b): a valuetype return that does not fit a
        # register takes a hidden buffer in the FIRST slot, so `this` is
        # RDX and every parameter moves one register right. This is the
        # CALLEE side of the shift `_hint_arg_types` has always modelled
        # on the caller side; batch 50 deliberately left it alone for
        # want of an exact size, which `returns_sret` now is. 11,046
        # methods return sret, 7,633 of them with parameters
        # (work/probe_b51_sretsize.py).
        rt0 = self.il.types[m.return_type] \
            if 0 <= m.return_type < len(self.il.types) else None
        self._return_reg = self._return_value_register(rt0)
        base = 1 if self.il.returns_sret(rt0) else 0
        if not m.is_static:
            self.regs[ARG_REGS[base]] = Expr(
                'this', (td.index, 0x12 << 16), 'obj')
            base += 1
        for pi, p in enumerate(args):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            bits = pt[1] if pt else 0
            te = (bits >> 16) & 0xFF
            # byref is pointer-class even when the pointee is float: the
            # machine passes an address in a GPR (mirrors _hint_arg_types)
            is_float = te in (0x0c, 0x0d) and not ((bits >> 29) & 1)
            slot = base + pi
            pname = safe_ident(p.name)
            if slot > 3:
                # Win64 stack parameters begin above the return address and
                # the 32-byte shadow space. Track them by their real source
                # names/types so later [rsp+disp] reads do not degrade to
                # anonymous `s_N` locals once rsp_delta follows frame allocs.
                off = 0x28 + 8 * (slot - 4)
                self.stack_map.setdefault(off, pname)
                if pt is not None:
                    self.slot_types.setdefault(pname, pt)
                    self._type_hints.setdefault(pname, pt)
                self.stack_values.setdefault(pname, Expr(pname, pt,
                    'float' if is_float else ('obj' if te >= 0x10 else 'int')))
                continue
            if is_float:
                self.regs[ARG_XMM[slot]] = Expr(pname, pt, 'float')
            else:
                self.regs[ARG_REGS[slot]] = Expr(
                    pname, pt, 'obj' if te >= 0x10 else 'int')
        if m.generic_container != -1:
            self.hidden_method_info = True
        else:
            self.hidden_method_info = False

    # fix 60: `flags` records WHICH instruction wrote it. The six
    # flag-specific jumps have no comparison operator to splice, but
    # their meaning follows from the setter (arithmetic parks its
    # result in the lhs slot; `test a,a` puts the tested value there;
    # an SSE compare's parity flag means an unordered/NaN operand).
    # A property keeps this impossible to desync: every existing
    # `self.flags = ...` site stamps the mnemonic `_insn` is running.
    @property
    def flags(self):
        return self._flags

    @flags.setter
    def flags(self, v):
        self._flags = v
        self._flags_mn = getattr(self, '_cur_mn', None) if v else None

    def reg(self, name) -> Optional[Expr]:
        base = GPR_ALIAS.get(name, name)
        if base.startswith('XMM'):
            return self.regs.get(base)
        return self.regs.get(base)

    def set_reg(self, name, expr):
        base = GPR_ALIAS.get(name, name)
        if base in ('RSP',):
            return
        self.regs[base] = expr

    # ------------------------------------------------------------------
    def _new_regs(self, init=None) -> _RegState:
        return _RegState(self, init)

    def _stamp(self, e):
        """Record where a register value was defined, so a later use-bind
        inserts `var tN = ...;` right after the defining instruction instead
        of at the (later) point the second use happened. First stamp wins:
        a copy re-stamping the same expression would move the declaration
        past uses that already rendered."""
        if e._defpos is not None:
            return
        t = e.text
        if not t or len(t) < _USE_BIND_MIN:
            return
        o = self.out
        if o is None:
            return
        blk = getattr(o, 'block', None)
        if blk is not None:
            e._defpos = (blk, len(blk.stmts))
        else:
            e._defpos = (None, len(o))

    def _note_use(self, e):
        """Count one rendering of a register value. Registers hold text that
        re-renders at each use, so the second rendering of an expensive
        expression binds it to a temp: the value prints once at its
        definition and every use -- including the statement being composed
        right now -- reads the temp. Counting is per expression object, not
        per text: two calls with identical text are two values, and each
        binds on its own uses."""
        if self.dry or self._copying or e is None or e._no_bind:
            return
        t = e.text
        if len(t) < _USE_BIND_MIN or t[0] == '&':
            return
        if e.kind not in _BINDABLE_KINDS:
            return
        # calls/typeof/arithmetic bind from 16 chars; a bare member chain
        # (this.doorCollider) re-renders cheaply, so only long ones pay
        if '(' not in t and ('.' not in t or len(t) < 24):
            return
        if e._use_ip == self._cur_ip:
            return   # same instruction already counted (test r,r / add r,r)
        e._use_ip = self._cur_ip
        u = e._uses
        e._uses = 1 if u is None else u + 1
        # batch 38: remember where this rendering lands so _bind can
        # rewrite CROSS-block uses (the def-block window alone leaves
        # a use in a later block as the full text -- backlog #4's
        # duplicate impure render). A cond/ret/switch render records
        # len(stmts), which no later stmt occupies (those renders are
        # terminal in their block), so it cannot collide with a twin
        # text from another expression object.
        blk = getattr(self.out, 'block', None)
        st = e._sites
        if st is None:
            st = e._sites = []
        st.append((blk, len(blk.stmts) if blk is not None else len(self.out)))
        if e._uses == 2:
            self._bind(e)

    def _stmt_sink(self, blk):
        return blk.stmts if blk is not None else self.out

    def _last_stmt_text(self):
        st = self._stmt_sink(getattr(self.out, 'block', None))
        if not st:
            return None
        s = st[-1]
        return s if type(s) is str else (s[1] if type(s) is tuple else None)

    def _bind(self, e):
        """Materialize `e` to a temp declared at its definition (or, when no
        definition site was recorded, immediately before the first rendered
        use), then rename the expression so every later rendering -- and
        every register still holding it -- reads the temp. Earlier renderings
        in the declaration's block are found by content, not position:
        positional anchors go stale the moment a declaration shifts lines.
        Renderings in blocks that precede the declaration are left as the
        full text: rewriting them would use the temp before it exists. A
        materialization line whose whole RHS is the old text (`var k =
        old;`, e.g. a kill-on-write temp) freezes the value at its own point
        and keeps it."""
        old = e.text
        v = self.new_var()
        # an address-of expression carries its pointee's type; the temp it
        # binds to holds the ADDRESS, so the type must not rename it
        if isinstance(e.ty, tuple) and e.kind != 'ptr' and not old.startswith('&'):
            if _is_unresolved_gp(e.ty):
                self._gp_blocked.add(v)
            else:
                vt = getattr(self, '_var_types', None)
                if vt is None:
                    vt = self._var_types = {}
                vt.setdefault(v, e.ty)
        line = 'var %s = %s;' % (v, strip_outer(old))
        dp = e._defpos
        if dp is not None:
            dblk, didx = dp
            sink = self._stmt_sink(dblk)
            # several expressions can share one definition slot (defined
            # between the same two statements): skip past declarations
            # already parked there, but stop before one that reads us --
            # either through our old text or through the temp we just chose
            while didx < len(sink):
                s = sink[didx]
                c = s if type(s) is str else (s[1] if type(s) is tuple else None)
                if c is None or not c.startswith('var '):
                    break
                if old in c or _mentions(c, v):
                    break
                didx += 1
            if dblk is not None:
                dblk.stmts.insert(didx, line)
            else:
                self.out.insert(didx, (self._cur_ip, line, None))
        else:
            # no definition site: declare right before the first statement
            # that renders the text
            dblk = getattr(self.out, 'block', None)
            st = self._stmt_sink(dblk)
            didx = len(st)
            for i in range(len(st)):
                s = st[i]
                c = s if type(s) is str else (s[1] if type(s) is tuple else '')
                if old in c and not (c.startswith('var ')
                                     and c.rstrip().endswith('= %s;' % old)):
                    didx = i
                    break
            if dblk is not None:
                dblk.stmts.insert(didx, line)
            else:
                self.out.insert(didx, (self._cur_ip, line, None))
        st = self._stmt_sink(dblk)
        # the rewrite window is bounded: uses that render far below the
        # declaration are rare, and skipping them only leaves the full text
        # in place (which re-renders correctly) -- while scanning an unbounded
        # tail costs quadratically on the wide blocks of flat-lifted methods
        # fix 58b: a statement that is EXACTLY `old;` is a standalone
        # side-effecting emission -- a distinct instruction's own call,
        # not a re-render of this value. Rewriting it yields `objN;`
        # (not a C# expression statement) and collapses several separate
        # allocations into one identity. The cross-block pass below
        # already reasons per-object for exactly this reason; this window
        # was still per-text. Ground truth: SaveManager 0x1805AA260, five
        # `new List<int>();` at five IPs (work/probe_b58b_bindbare.py).
        bare = '%s;' % old
        # fix 58c: indices of THIS expression object's own render sites in
        # the declaration's block, shifted past the declaration just
        # inserted at didx. A bare `old;` at one of these is this value's
        # own emission -- subsumed by `var v = old;` -- so it is dropped;
        # a bare `old;` anywhere else belongs to a different instruction
        # and is left untouched (fix 58b).
        own = set()
        for _sb, _si in (e._sites or ()):
            if _sb is dblk:
                own.add(_si + 1 if _si >= didx else _si)
        for i in range(didx, min(len(st), didx + 64)):
            s = st[i]
            if type(s) is str:
                if s == line or old not in s:
                    continue
                if s.strip() == bare:
                    if i in own:
                        st[i] = ''
                    continue
                if s.startswith('var ') and s.rstrip().endswith('= %s;' % old):
                    continue
                st[i] = s.replace(old, v)
            elif type(s) is tuple:
                c = s[1]
                if old not in c or c == line:
                    continue
                if c.strip() == bare:
                    if i in own:
                        st[i] = (s[0], '', s[2])
                    continue
                if c.startswith('var ') and c.rstrip().endswith('= %s;' % old):
                    continue
                st[i] = (s[0], c.replace(old, v), s[2])
        # a use #1 may have rendered into the block's condition / return /
        # switch index rather than a statement: those are plain strings on
        # the block, rewritten the same way
        if dblk is not None:
            if dblk.cond and old in dblk.cond:
                dblk.cond = dblk.cond.replace(old, v)
            if dblk.ret and old in dblk.ret:
                dblk.ret = dblk.ret.replace(old, v)
            if dblk.switch_idx and old in dblk.switch_idx:
                dblk.switch_idx = dblk.switch_idx.replace(old, v)
        # cross-block render sites (batch 38): the window above covers
        # only the declaration's own block, so a use that rendered in a
        # LATER block kept the full text -- the duplicate impure render
        # (`obj10 = Allocate(...)` decl plus the same call inline one
        # block down). Rewrite the recorded sites of THIS expression
        # object -- per object, not per text, so a real second identical
        # call is never touched -- and only in blocks reachable from
        # the declaration's (a path around the declaration must keep
        # the full text: the temp would not exist there). A site whose
        # index no longer holds our text (shifted by another bind's
        # inserted declaration) is skipped -- the full text re-renders
        # correctly, which is the pre-batch-38 behavior.
        sites = e._sites
        blocks = getattr(self, '_blocks', None)
        reach = None
        if sites and blocks is not None and dblk is not None:
            reach = set()
            stk = list(dblk.succs or ())
            while stk:
                x = stk.pop()
                if x in reach or not (0 <= x < len(blocks)):
                    continue
                reach.add(x)
                stk.extend(blocks[x].succs or ())
        for sblk, sidx in sites or ():
            if sblk is None:
                continue
            si = sidx
            if sblk is dblk:
                # window covered [didx, didx+64); before didx renders
                # before the declaration; past the window, shift +1
                if sidx < didx or didx <= sidx < didx + 64:
                    continue
                si = sidx + 1
            elif reach is None or sblk.bid not in reach:
                continue
            stt = sblk.stmts
            if 0 <= si < len(stt):
                s = stt[si]
                c = s if type(s) is str else (s[1] if type(s) is tuple else None)
                # fix 58c: this list is per-OBJECT, so a bare `old;` here
                # is this value's own emission -- the declaration already
                # performs it, and rewriting it would render `objN;`
                if c is not None and c.strip() == bare:
                    stt[si] = '' if type(s) is str else (s[0], '', s[2])
                    continue
                if c and old in c and not (c.startswith('var ')
                                           and c.rstrip().endswith('= %s;' % old)):
                    if type(s) is str:
                        stt[si] = c.replace(old, v)
                    else:
                        stt[si] = (s[0], c.replace(old, v), s[2])
            if sblk.cond and old in sblk.cond:
                sblk.cond = sblk.cond.replace(old, v)
            if sblk.ret and old in sblk.ret:
                sblk.ret = sblk.ret.replace(old, v)
            if sblk.switch_idx and old in sblk.switch_idx:
                sblk.switch_idx = sblk.switch_idx.replace(old, v)
        e._sites = None
        e.text = v
        e._prec = None   # the temp name is an atom

    # ------------------------------------------------------------------
    def emit(self, ip, code, asm):
        if getattr(self, 'dry', False):
            return
        self.out.append((ip, code, asm))

    def new_var(self):
        v = 't%d' % self.var_n
        self.var_n += 1
        return v

    def _fresh_unknowns(self):
        """give clobbered volatile regs fresh unknown names so later reads
        render as vN instead of '?'"""
        if getattr(self, '_u', 0) > 200000:
            return
        for r in VOLATILE:
            if r in self.regs:
                continue
            self._u = getattr(self, '_u', 0) + 1
            e = Expr('v%d' % self._u, None, '?')
            e._unk = True             # fix 58: clobbered, not re-written
            self.regs[r] = e

    def _mk(self, text, ty=None, kind='?', cap=240):
        """Build an Expr, materializing oversized expressions into a temp var
        to prevent exponential text growth from self-referential folds."""
        if len(text) > cap:
            v = self.new_var()
            if getattr(self, 'dry', False):
                return Expr(v, ty, kind)
            self.emit(0, 'var %s = 0; // %s' % (v, text[:cap] + ('...' if len(text) > cap else '')), None)
            return Expr(v, ty, kind)
        return Expr(text, ty, kind)

    def slot_var(self, off):
        key = off + self.rsp_delta
        if key not in self.stack_map:
            self.stack_map[key] = 's_%x' % abs(off)
        return self.stack_map[key]

    @staticmethod
    def _copy_expr(e):
        if e is None:
            return None
        c = Expr(e.text, e.ty, e.kind, e.recv)
        for name in ('_prec', '_unk', '_usg_idx', '_mi', '_td',
                     '_no_bind', '_alloc'):
            val = getattr(e, name, None)
            if val is not None and not (name == '_unk' and not val):
                setattr(c, name, val)
        return c
