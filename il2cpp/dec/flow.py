from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import LBL, _ELSEIF_CMP_RX, _ITF_CALL_RX, _ITF_SLOT_RX, _ITF_TYPEOF_RX, _LOOP_HDR_RX, _can_fall, _construct_arms, _falls_to, _header_idx, _hoist_point, _match_brace, _split_args
from il2cpp.expr import _recv_fold, _recv_shaped

class _FlowMixin:
    def _resolve_labels(self, lines: List[str]) -> List[str]:
        """Turn provisional label markers into real labels, and drop every label
        (marker or already resolved) that nothing jumps to."""
        used = set()
        for st in lines:
            if 'goto L_' in st:
                used.update(re.findall(r'goto (L_[0-9a-f]+);', st))
        out = []
        for i, st in enumerate(lines):
            s = st.strip()
            lab = None
            if s.startswith(LBL) and s.endswith(':'):
                lab = s[len(LBL):-1]
            elif re.match(r'^L_[0-9a-f]+:$', s):
                lab = s[:-1]
            if lab is not None:
                if lab in used:
                    out.append(lab + ':')
                continue
            out.append(st)
        return out

    def _tidy_gotos(self, lines: List[str]) -> List[str]:
        """Collapse the goto shapes that structuring leaves behind when both
        sides of a branch converge on a block that is about to be emitted."""
        def st(k):
            return lines[k].strip() if 0 <= k < len(lines) else None

        def nxt_real(k):
            while k < len(lines) and not lines[k].strip():
                k += 1
            return k

        for _round in range(8):
            drop = set()
            i = 0
            while i < len(lines):
                s = st(i)
                if not s:
                    i += 1
                    continue
                g = self._GOTO_RX.match(s)
                if g and st(nxt_real(i + 1)) == g.group(1) + ':':
                    drop.add(i)
                    i += 1
                    continue
                # if (c) { goto A; } else { goto B; }
                if s.startswith('if (') and st(i + 1) == '{' and st(i + 3) == '}' \
                        and st(i + 4) == 'else' and st(i + 5) == '{' and st(i + 7) == '}':
                    a = self._GOTO_RX.match(st(i + 2) or '')
                    b = self._GOTO_RX.match(st(i + 6) or '')
                    if a and b:
                        after = st(nxt_real(i + 8))
                        if a.group(1) == b.group(1):
                            lines[i] = 'goto %s;' % a.group(1)
                            drop.update(range(i + 1, i + 8))
                            i += 8
                            continue
                        if after == b.group(1) + ':':
                            drop.update(range(i + 4, i + 8))
                            i += 8
                            continue
                        if after == a.group(1) + ':':
                            lines[i] = 'if (!(%s))' % s[4:-1]
                            lines[i + 2] = 'goto %s;' % b.group(1)
                            drop.update(range(i + 4, i + 8))
                            i += 8
                            continue
                # if (c) { goto L; } directly in front of L:
                if s.startswith('if (') and st(i + 1) == '{' and st(i + 3) == '}':
                    a = self._GOTO_RX.match(st(i + 2) or '')
                    if a and not self._IMPURE.search(s[4:-1]) \
                            and st(nxt_real(i + 4)) == a.group(1) + ':':
                        drop.update(range(i, i + 4))
                        i += 4
                        continue
                # else { goto L; } directly in front of L:
                if s == 'else' and st(i + 1) == '{' and st(i + 3) == '}':
                    a = self._GOTO_RX.match(st(i + 2) or '')
                    if a and st(nxt_real(i + 4)) == a.group(1) + ':':
                        drop.update(range(i, i + 4))
                        i += 4
                        continue
                i += 1
            if not drop:
                break
            lines = [l for k, l in enumerate(lines) if k not in drop]
        return lines

    def _drop_redundant_gotos(self, lines: List[str]) -> List[str]:
        """`goto L_x;` immediately followed by `L_x:` is just fallthrough."""
        out = []
        for i, st in enumerate(lines):
            m = re.match(r'^goto (L_[0-9a-f]+);$', st.strip())
            if m:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip() == m.group(1) + ':':
                    continue
            out.append(st)
        return out

    def _elseif_flatten(self, lines: List[str]) -> List[str]:
        """Flatten a right-nested if/else compare chain into a flat
        else-if chain (todo lead 2). See this patch's module docstring
        for the two cases and why each is a pure boolean identity --
        no data-flow or CFG reasoning needed, unlike lead 1a's hoist/
        duplicate work on the same source shape."""
        NEG = {'!=': '==', '==': '!='}

        def negate(cond):
            if cond.count('!=') + cond.count('==') == 1 \
                    and '&&' not in cond and '||' not in cond:
                m = _ELSEIF_CMP_RX.match(cond)
                if m:
                    lhs, op, rhs = m.groups()
                    if lhs.count('(') == lhs.count(')') \
                            and rhs.count('(') == rhs.count(')'):
                        return '%s %s %s' % (lhs.strip(), NEG[op], rhs.strip())
            if cond.startswith('!(') and cond.endswith(')'):
                return cond[2:-1].strip()
            if cond.startswith('!'):
                return cond[1:].strip()
            return '!(%s)' % cond

        def wholly_empty(lo, hi):
            """No non-blank line at all in lines[lo:hi] -- the
            shape _render's own empty-if/else collapse expects to
            see and handle on its own; declined here rather than
            risk placing our merged 'else if (...)' where that
            logic's exact-text 'else' lookahead doesn't recognize
            it (see this patch's module docstring)."""
            return all(not lines[x].strip() for x in range(lo, hi))

        def lone_if(lo, hi):
            """lines[lo:hi] is exactly one if/else(-if) construct and
            nothing else -> (cond_line_idx, if_open_brace, end_close);
            else None."""
            k = lo
            while k < hi and not lines[k].strip():
                k += 1
            if k >= hi or not lines[k].strip().startswith('if ('):
                return None
            mm = k + 1
            while mm < hi and not lines[mm].strip():
                mm += 1
            if mm >= hi or lines[mm].strip() != '{':
                return None
            arms = _construct_arms(lines, mm)
            if not arms:
                return None
            end = arms[-1][1]
            r = end + 1
            while r < hi and not lines[r].strip():
                r += 1
            if r != hi:
                return None
            return k, mm, end

        for _round in range(400):
            n = len(lines)
            i = 0
            changed = False
            while i < n:
                s = lines[i].strip()
                if not (s.startswith('if (') and s.endswith(')')):
                    i += 1
                    continue
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j >= n or lines[j].strip() != '{':
                    i += 1
                    continue
                arms = _construct_arms(lines, j)
                if len(arms) != 2 or _header_idx(lines, arms[0][0]) != i:
                    i += 1
                    continue
                (t_open, t_close), (f_open, f_close) = arms
                f_hdr = _header_idx(lines, f_open)
                if f_hdr < 0 or lines[f_hdr].strip() != 'else':
                    i += 1
                    continue
                true_lone = lone_if(t_open + 1, t_close)
                false_lone = lone_if(f_open + 1, f_close)
                if false_lone and not true_lone \
                        and not wholly_empty(t_open + 1, t_close):
                    fcond_i, f_if_open, fend = false_lone
                    lines = (lines[:f_hdr]
                             + ['else', lines[fcond_i].strip()]
                             + lines[f_if_open:fend + 1]
                             + lines[f_close + 1:])
                    changed = True
                    break
                if true_lone and not false_lone \
                        and not wholly_empty(f_open + 1, f_close):
                    tcond_i, t_if_open, tend = true_lone
                    newcond = negate(s[4:-1].strip())
                    lines = (lines[:i]
                             + ['if (%s)' % newcond, '{']
                             + lines[f_open + 1:f_close]
                             + ['}', 'else', lines[tcond_i].strip()]
                             + lines[t_if_open:tend + 1]
                             + lines[f_close + 1:])
                    changed = True
                    break
                i += 1
            if not changed:
                break
        # cosmetic-only merge, once all structural rounds are done: an
        # 'else' line immediately followed by an 'if (...)' line (this
        # pass's own output shape -- kept as two lines through the
        # rounds above so _construct_arms/the scanner keep working on
        # a deeper pyramid level) becomes one 'else if (...)' line.
        out = []
        k = 0
        while k < len(lines):
            if lines[k].strip() == 'else' and k + 1 < len(lines) \
                    and lines[k + 1].strip().startswith('if ('):
                out.append('else ' + lines[k + 1].strip())
                k += 2
                continue
            out.append(lines[k])
            k += 1
        return out

    # fix 72e: the case-body emitter for _switch_synth -- verbatim
    # arm body one indent level deeper, a synthetic break unless the
    # body's last statement is itself a flow transfer (an EMPTY body
    # gets one: an empty case block falls through, the if-chain's
    # empty arm did not).
    _SWITCH_FLOW_RX = re.compile(r'^(?:return\b|throw\b|goto\b|break;|continue;)')

    def _emit_case_body(self, out, lines, lo, hi, indent):
        last = None
        for bl in lines[lo:hi]:
            if bl.strip():
                out.append(indent + '    ' + bl)
                last = bl.strip()
            else:
                out.append(bl)
        if not last or not self._SWITCH_FLOW_RX.match(last):
            out.append(indent + '        break;')

    _SWITCH_SUBJ_RX = re.compile(r'^[A-Za-z_@][\w@]*(?:\.[A-Za-z_@][\w@]*)*$')
    _SWITCH_CONST_RX = re.compile(
        r"^(?:-?0[xX][0-9a-fA-F]+[uUlL]*|-?\d+[uUlL]*|'(?:\\.|[^'\\])')$")
    _SWITCH_CMP_RX = re.compile(r'^(.+?)\s*==\s*(.+)$')
    _SWITCH_GOTO_RX = re.compile(r'(?<![\w.])goto\b')
    _SWITCH_LBL_RX = re.compile(r'^L_[0-9a-fA-F]+:')
    _SWITCH_BREAK_RX = re.compile(r'(?<![\w.])break\s*;')

    def _switch_synth(self, lines: List[str]) -> List[str]:
        """Synthesize a real C# `switch` from a flat same-subject
        ==-constant else-if chain (todo lead 2's second half, batch
        50-sized: work/census_b50_switch.py found 314 clean chains at
        the b71 shape, 227 of them 2-arm -- those stay if/else -- and
        ~90 at 3+ arms). Runs right after _elseif_flatten, whose flat
        output shape IS the input, so the census's hazards are the
        actual hazards (new.md section 4: measure a rule against what
        ENTERS the pass). The rewrite is a pure boolean identity:
        the chain tests one subject against distinct constants in
        order with a final default, which is exactly switch
        semantics -- EXCEPT for evaluation count (switch evaluates
        the subject once), which is why the subject must be a pure
        dotted-identifier path (decompiled property reads render as
        getter CALLS, so a dotted path here is a field read). A
        `break;` in an arm would newly bind to the synthesized
        switch (a loop's break changes meaning); goto/label in an
        arm and duplicate case values reject the whole chain; case
        labels must be int/hex/char literals (C# forbids float
        switch). Nothing after this pass re-flattens switches:
        _switch_to_if (the <=2-case inverse) ran earlier, and only
        _drop_dead_lastdef + _render follow."""
        n = len(lines)
        out: List[str] = []
        i = 0
        while i < n:
            s = lines[i].strip()
            if not (s.startswith('if (') and s.endswith(')')):
                out.append(lines[i])
                i += 1
                continue
            cond = s[4:-1].strip()
            cm = self._SWITCH_CMP_RX.match(cond)
            if not cm:
                out.append(lines[i])
                i += 1
                continue
            subj = cm.group(1).strip()
            c0 = cm.group(2).strip()
            if not self._SWITCH_SUBJ_RX.match(subj) \
                    or not self._SWITCH_CONST_RX.match(c0):
                out.append(lines[i])
                i += 1
                continue
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j >= n or lines[j].strip() != '{':
                out.append(lines[i])
                i += 1
                continue
            # parse the flat chain: arms = (const, body_lo, body_hi)
            arms = []
            consts = set()
            els_body = None
            okchain = True
            cur_const = c0
            pos = j
            nxt = j
            while True:
                close = _match_brace(lines, pos)
                if close is None:
                    okchain = False
                    break
                body = lines[pos + 1:close]
                bad = False
                for bl in body:
                    t = bl.strip()
                    if not t:
                        continue
                    if self._SWITCH_BREAK_RX.search(t) \
                            or self._SWITCH_GOTO_RX.search(t) \
                            or self._SWITCH_LBL_RX.match(t):
                        bad = True
                        break
                if bad or cur_const in consts:
                    okchain = False
                    break
                consts.add(cur_const)
                arms.append((cur_const, pos + 1, close))
                nxt = close + 1
                while nxt < n and not lines[nxt].strip():
                    nxt += 1
                if nxt >= n:
                    break
                t = lines[nxt].strip()
                if t == 'else':
                    k = nxt + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k >= n or lines[k].strip() != '{':
                        okchain = False
                        break
                    dclose = _match_brace(lines, k)
                    if dclose is None:
                        okchain = False
                        break
                    els_body = (k + 1, dclose)
                    nxt = dclose + 1
                    break
                if t.startswith('else if (') and t.endswith(')'):
                    cnd = t[9:-1].strip()
                    cmm = self._SWITCH_CMP_RX.match(cnd)
                    if not cmm:
                        okchain = False
                        break
                    s2 = cmm.group(1).strip()
                    if s2 != subj \
                            or not self._SWITCH_CONST_RX.match(cmm.group(2).strip()):
                        okchain = False
                        break
                    k = nxt + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k >= n or lines[k].strip() != '{':
                        okchain = False
                        break
                    cur_const = cmm.group(2).strip()
                    pos = k
                    continue
                break
            if not okchain or len(arms) < 3:
                out.append(lines[i])
                i += 1
                continue
            out.append(indent + 'switch (%s)' % subj)
            out.append(indent + '{')
            for cst, lo, hi in arms:
                out.append(indent + '    case %s:' % cst)
                out.append(indent + '    {')
                self._emit_case_body(out, lines, lo, hi, indent)
                out.append(indent + '    }')
            if els_body is not None:
                out.append(indent + '    default:')
                out.append(indent + '    {')
                self._emit_case_body(out, lines, els_body[0], els_body[1], indent)
                out.append(indent + '    }')
            out.append(indent + '}')
            i = nxt
        return out

    def _name_interface_dispatch(self, lines: List[str]) -> List[str]:
        """todo lead #3: name an interface-dispatch call il2cpp made
        through its runtime interfaceOffsets search (typeof(IFace) +
        a linear scan of klass->interfaceOffsets[] for a matching
        interfaceType, landing on the absolute class-vtable slot
        where that interface's OWN method block begins). Ground
        truth: GameManager.CheckAllReady VA 0x1806DF770 -- three
        back-to-back searches for IEnumerable<PlayerRef>/IEnumerator/
        IEnumerator<PlayerRef> resolve to GetEnumerator/MoveNext/
        get_Current exactly (Il2Cpp.interface_method_by_offset's
        docstring has the offset-arithmetic proof).

        Purely textual, no CFG reasoning: given a call site, walk
        backward for the nearest same-token slot-address assignment,
        then further back for the nearest typeof() decl actually
        referenced inside that span (so an unrelated typeof several
        statements earlier can't be picked up by accident). Declines
        silently -- leaving the honest /*indirect*/ marker -- whenever
        any link in the chain doesn't hold, or the receiver doesn't
        fold cleanly; a wrong name is worse than an honest unknown
        (CLAUDE.md's sub_x/*shared body*/ precedent)."""
        il = self.L.il
        meta = il.meta
        out = list(lines)
        for i, raw in enumerate(out):
            cm = _ITF_CALL_RX.search(raw)
            if not cm:
                continue
            slot_tok, k_txt, args_txt = cm.groups()
            k = int(k_txt, 16)
            if k % 0x10:
                continue
            rel = k // 0x10
            slot_line = None
            for j in range(i - 1, max(-1, i - 60), -1):
                mm = _ITF_SLOT_RX.match(out[j].strip())
                if mm and mm.group(1) == slot_tok:
                    slot_line = j
                    break
            if slot_line is None:
                continue
            iface_text = None
            for j in range(slot_line - 1, max(-1, slot_line - 40), -1):
                tm = _ITF_TYPEOF_RX.match(out[j].strip())
                if not tm:
                    continue
                tok, txt = tm.groups()
                ref = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(tok))
                if any(ref.search(out[k2]) for k2 in range(j + 1, slot_line + 1)):
                    iface_text = txt
                break
            if iface_text is None:
                continue
            mi = il.interface_method_by_offset(iface_text, rel)
            if mi is None or not (0 <= mi < len(meta.methods)):
                continue
            method = meta.methods[mi]
            argl, _ = _split_args('(%s)' % args_txt, 0)
            if not argl or len(argl) < 2:
                continue
            recv_txt = argl[0]
            if not _recv_shaped(recv_txt):
                continue
            mname = method.name[1:] if method.name.startswith('.') else method.name
            mname = mname.replace('|', '_').replace('@', '_')
            real_args = argl[2:2 + method.param_count]
            if mname.startswith('get_') and method.param_count == 0 and not real_args:
                call = '%s.%s;' % (_recv_fold(recv_txt), mname[4:])
            else:
                call = '%s.%s(%s);' % (_recv_fold(recv_txt), mname, ', '.join(real_args))
            out[i] = raw[:cm.start()] + call + raw[cm.end():]
        return out

    def _hoist_shared_tails(self, lines: List[str]) -> List[str]:
        """Kill the `goto` that jumps INTO a sibling/nested block -- illegal
        C# -- by hoisting the label's tail out past the construct it sits in.
        MSVC emits this when a diamond's merge block was inlined into one arm
        and the other arm is left jumping back to it:

            if (!flag1)
            {
                L_181ad286f:
                obj14 = obj1;
            }
            else
            {
                System.Threading.Monitor.Exit(obj7);
                goto L_181ad286f;
            }

        becomes

            if (flag1)
            {
                System.Threading.Monitor.Exit(obj7);
            }
            obj14 = obj1;

        Sound only when every into-block goto to L falls through to the
        hoist point with nothing else executing in between (no statement
        after the goto at any crossed level, no loop/switch/SEH level
        crossed). An emptied label arm collapses into the sibling arm (or a
        bare condition when both arms emptied). Unproven sites are left
        exactly as they are -- an illegal goto is a known, greppable defect;
        a silently wrong hoist is not."""
        for _round in range(200):
            cur_braces: List[int] = []
            stack: List[tuple] = []
            label_of = {}
            gotos = []
            for i, raw in enumerate(lines):
                stack.append(tuple(cur_braces))
                s = raw.strip()
                m = self._LBLDEF_RX.match(s)
                if m:
                    label_of.setdefault(m.group(0)[:-1], i)
                for g in self._GOTO_RX.finditer(s):
                    gotos.append((i, g.group(1)))
                if s == '{':
                    cur_braces.append(i)
                elif s == '}' or s.startswith('} while'):
                    if cur_braces:
                        cur_braces.pop()
            changed = False
            for name, li in sorted(label_of.items()):
                lstack = stack[li]
                if not lstack:
                    continue
                gs = [g for g in gotos if g[1] == name]
                if not gs:
                    continue
                into = []
                same = []
                for gi, _ in gs:
                    gst = stack[gi]
                    if len(lstack) <= len(gst) and gst[:len(lstack)] == lstack:
                        same.append(gi)
                    else:
                        into.append(gi)
                if not into:
                    continue
                arm = lstack[-1]
                ac = _match_brace(lines, arm)
                if ac is None or ac <= 0:
                    continue
                hdr_i = _header_idx(lines, arm)
                hdr = lines[hdr_i].strip() if hdr_i >= 0 else ''
                if _LOOP_HDR_RX.match(hdr) or hdr.startswith('switch') \
                        or hdr in ('try', 'finally') or hdr.startswith('catch') \
                        or hdr.startswith('case') or hdr.startswith('default'):
                    continue
                # another label inside the tail would move with it and its
                # own gotos would dangle; overlapping tails stay put
                if any(self._LBLDEF_RX.match(lines[k].strip())
                       for k in range(li + 1, ac)):
                    continue
                H = _hoist_point(lines, ac)
                dup_ok = False
                if H >= 0 and all(_falls_to(lines, gi, stack[gi], H)
                                  for gi in into):
                    arms_c = _construct_arms(lines, arm)
                    region_start = _header_idx(lines, arms_c[0][0]) \
                        if arms_c else -1
                    # fix 51c: the classic path needs the funnel
                    # just as much as the LCA path (the pass
                    # shipped without classify_into2's
                    # arm_fallthread and a 51-hoist once
                    # unblocked a leaky classic cascade)
                    if region_start >= 0 and not self._funnel_ok(
                            lines, stack, li, ac, region_start, H,
                            into, lstack):
                        # falls_to already proved every into-goto
                        # reaches H cleanly -- only funnel_ok (a
                        # HOISTING-specific concern about OTHER,
                        # non-participant paths leaking into a
                        # MOVED tail) rejected the move; duplication
                        # never touches those paths (todo lead 1a)
                        dup_ok = True
                        region_start = -1
                else:
                    # fix 51: the classic point (from the label's own
                    # arm) is unreachable from some into-goto -- try
                    # the LCA of every participant stack instead
                    H, region_start = self._lca_hoist_plan(lines, stack,
                                                           li, lstack,
                                                           into)
                    if H < 0:
                        dup_ok = self._lca_hoist_plan(
                            lines, stack, li, lstack, into,
                            until_funnel=True)[0] >= 0
                if H < 0 or region_start < 0:
                    # NEW (todo lead 1a): no sound hoist point --
                    # duplicate the tail into each into-goto site
                    # instead of moving it once. `dup_ok` is only
                    # ever set once _falls_to (classic) or
                    # _lca_hoist_plan's own structural+falls_to
                    # checks (LCA) already proved the goto's own
                    # unwind is clean -- the SAME li+1..ac tail
                    # hoisting would have used, at the goto's own
                    # position, is always behaviorally identical to
                    # what the goto already does (nothing else
                    # jumps INTO a goto's own spot); the nested-
                    # label guard above already covers this exact
                    # li+1..ac range. Ground-truthed against
                    # InventoryManager.PickupNewObj, VA
                    # 0x1807018d0 (work/probe_b42_hoist.py).
                    if dup_ok:
                        for k in range(li + 1, ac):
                            if 'goto ' not in lines[k]:
                                continue
                            for g in self._GOTO_RX.finditer(
                                    lines[k].strip()):
                                t = label_of.get(g.group(1))
                                if t is not None and not (li <= t < ac):
                                    dup_ok = False
                    if dup_ok:
                        dtail = [lines[k] for k in range(li + 1, ac)
                                 if lines[k].strip()]
                        # hardening (still fix 56): a tail containing
                        # its OWN try/finally/catch (e.g. a
                        # Monitor.Enter guard region) must not be
                        # duplicated -- a second occurrence of the
                        # guard shape elsewhere in the method
                        # corrupts an UNRELATED dead-arm collapse at
                        # an entirely different position in the SAME
                        # method (live, disasm-confirmed:
                        # XmlDownloadManager's async MoveNext, VA
                        # 0x18235e500 -- a valid `if/else if/else`
                        # guard chain degenerated into a dangling
                        # `else if` with no `if` once a second
                        # Monitor.Enter region existed). Leave these
                        # as an honest goto until that separate
                        # interaction is root-caused.
                        if any(ln.strip() in ('try', 'finally')
                               or ln.strip().startswith('catch')
                               for ln in dtail):
                            continue
                        # fix 56 (todo lead 1a-a): every copy is the
                        # SAME text, so a tail-local decl (`obj4 = ...`)
                        # re-declares the identical token in each copy
                        # -- legal C# (each copy sits in its own block
                        # scope) but it breaks every later single-
                        # assignment-only pass (_singleton_cse,
                        # _value_cse: `assigns[tok] != 1` now sees 2+
                        # and drops the token from folding ENTIRELY,
                        # not partially) -- root cause of the 108->324
                        # InventoryManager.AssignTemplates balloon that
                        # motivated the old 24-line cap this replaces
                        # (VA 0x1806faf40, work/probe_b48_relift.py).
                        # Mint each copy its own fresh number for every
                        # token declared ONLY inside the tail (one
                        # never read outside [li+1, ac) pre-
                        # duplication); a token also read outside the
                        # tail (an outer singleton fetch the tail
                        # merely reads) names one shared value and
                        # stays untouched.
                        outside_toks = set()
                        for oi, ln in enumerate(lines):
                            if li + 1 <= oi < ac:
                                continue
                            outside_toks.update(self._LOC_RX.findall(ln))
                        local_toks = []
                        seen = set()
                        for ln in dtail:
                            for tok in self._LOC_RX.findall(ln):
                                if tok in seen or tok in outside_toks:
                                    continue
                                seen.add(tok)
                                local_toks.append(tok)
                        maxnum = {}
                        for ln in lines:
                            for tok in self._LOC_RX.findall(ln):
                                pre = tok.rstrip('0123456789')
                                n = int(tok[len(pre):])
                                if n > maxnum.get(pre, 0):
                                    maxnum[pre] = n
                        into_set = set(into)
                        out = []
                        for k, raw in enumerate(lines):
                            if k not in into_set:
                                out.append(raw)
                                continue
                            if not local_toks:
                                out.extend(dtail)
                                continue
                            ren = {}
                            for t in local_toks:
                                pre = t.rstrip('0123456789')
                                maxnum[pre] = maxnum.get(pre, 0) + 1
                                ren[t] = '%s%d' % (pre, maxnum[pre])
                            out.extend(
                                self._LOC_RX.sub(
                                    lambda mm: ren.get(mm.group(1),
                                                        mm.group(1)), ln)
                                for ln in dtail)
                        lines = out
                        changed = True
                        break
                    continue
                # fix 51a: a goto inside the tail must not target a
                # label that stays inside the hoisted-over region --
                # the moved goto would jump backward into a block (a
                # newly minted into-block goto)
                tailgoto_bad = False
                for k in range(li + 1, ac):
                    if 'goto ' not in lines[k]:
                        continue
                    for g in self._GOTO_RX.finditer(lines[k].strip()):
                        t = label_of.get(g.group(1))
                        if t is not None and region_start <= t < H \
                                and not li <= t < ac:
                            tailgoto_bad = True
                if tailgoto_bad:
                    continue
                tail = [lines[k] for k in range(li + 1, ac) if lines[k].strip()]
                drop = set(into)
                drop.add(li)
                drop.update(range(li + 1, ac))
                ins_at_h = (['%s:' % name] if same else []) + tail
                ins_at_hdr = []
                drop_hdr = set()
                if all(k in drop or not lines[k].strip()
                       for k in range(arm + 1, ac)):
                    plan = self._collapse_arm(lines, stack, arm, ac, hdr_i, hdr, drop)
                    if plan is not None:
                        ins_at_hdr = plan[0] or []
                        drop_hdr = plan[1]
                out = []
                h_done = hdr_done = False
                for k, raw in enumerate(lines):
                    if k == hdr_i and ins_at_hdr and not hdr_done:
                        out.extend(ins_at_hdr)
                        hdr_done = True
                    if k == H and ins_at_h and not h_done:
                        out.extend(ins_at_h)
                        h_done = True
                    if k in drop or k in drop_hdr:
                        continue
                    out.append(raw)
                if not h_done:
                    out.extend(ins_at_h)
                if not hdr_done:
                    out.extend(ins_at_hdr)
                lines = out
                changed = True
                break
            if not changed:
                break
        return lines

    def _funnel_ok(self, lines, stack, li, ac, region_start, H, into,
                   lstack):
        """Fix 51 funnel (v4, the spine model): after hoisting the tail
        (li, ac) to H, every path that falls out of the hoisted-over
        region must already have executed the tail -- passed the label
        or one of the dropped gotos. The participants are the last
        statement of their chains at every level (_falls_to and the
        label-side checks guarantee it), so inside a participant arm
        everything before the carrying LINK construct funnels into it.
        Only the link's own arms can leak: a non-participant link arm
        that can fall exits the region without the tail; a no-else or
        loop/switch/SEH link bypasses or exits past a participant it
        holds. Arms inside the tail move with it."""
        parts = [li] + list(into)
        # fix 51f: a single `return;` hoisted to the end of the
        # statement list is sound for every path -- falling out of the
        # region and executing it is identical to the implicit
        # fall-off-the-end those paths had before
        tail = [k for k in range(li + 1, ac) if lines[k].strip()]
        if len(tail) == 1 and lines[tail[0]].strip() == 'return;' \
                and all(not lines[k].strip()
                        for k in range(H, len(lines))):
            return True

        def on_lp(pos):
            return (li > pos and pos < H and pos < len(stack)
                    and stack[pos][:len(lstack)] == lstack)

        def container_ok(lo, hi, parts_here):
            k = lo
            while k < hi:
                if lines[k].strip() != '{':
                    k += 1
                    continue
                arms = _construct_arms(lines, k)
                if not arms:
                    return False
                if arms[-1][1] < hi - 1:
                    k = arms[-1][1] + 1     # pre-link: funnels ahead
                    continue
                # the link: the last statement of this arm
                hdr_i = _header_idx(lines, arms[0][0])
                hdr = lines[hdr_i].strip() if hdr_i >= 0 else ''
                holds_part = any(arms[0][0] <= p <= arms[-1][1]
                                 for p in parts_here)
                if holds_part:
                    if _LOOP_HDR_RX.match(hdr) or hdr.startswith('switch') \
                            or hdr in ('try', 'finally') \
                            or hdr.startswith('catch'):
                        return False    # bypass/normal exit skips it
                    ce = arms[-1][1] + 1
                    if hdr.startswith('if') and len(arms) == 1 \
                            and not on_lp(ce):
                        return False    # false path bypasses it
                for a2, c2 in arms:
                    if a2 > li and c2 < ac:
                        continue        # inside the tail: moves with it
                    sub = [p for p in parts_here if a2 <= p <= c2]
                    if sub:
                        if not container_ok(a2 + 1, c2, sub):
                            return False
                    elif _can_fall(lines, a2):
                        return False
                return True
            return True                     # participant line is last

        return container_ok(region_start, H, parts)

    def _lca_hoist_plan(self, lines, stack, li, lstack, into,
                        until_funnel=False):
        """Fix 51: hoist point for the goto-convergence case the
        classic point (the label's own arm) cannot serve -- the end of
        the smallest construct containing the label AND every
        into-goto, with the strict funnel validated. Returns
        (H, region_start) or (-1, -1); region_start bounds the fix-51a
        tail-goto guard. until_funnel=True (todo lead 1a) stops right
        before the funnel_ok call and returns the structurally-clean,
        falls_to-proven H anyway -- funnel_ok is a HOISTING-specific
        check (do OTHER, non-participant paths leak into a MOVED
        tail?) that the tail-duplication fallback doesn't need."""
        n = len(lstack)
        parts = [li] + list(into)
        ac = _match_brace(lines, lstack[-1])
        for lvl in range(n - 1, -1, -1):
            arm = lstack[lvl]
            arms_c = _construct_arms(lines, arm)
            if not arms_c:
                return -1, -1
            E = arms_c[-1][1] + 1
            hdr_i = _header_idx(lines, arms_c[0][0])
            if hdr_i < 0:
                return -1, -1
            if not all(hdr_i < gi < E and any(b in stack[gi]
                                              for b, _ in arms_c)
                       for gi in into):
                continue
            for lv in range(n - 2, lvl - 1, -1):
                inner = _construct_arms(lines, lstack[lv + 1])
                if not inner:
                    return -1, -1
                outer_close = _match_brace(lines, lstack[lv])
                for k in range(inner[-1][1] + 1, outer_close):
                    s = lines[k].strip()
                    if s and s not in ('{', '}', 'else'):
                        return -1, -1
            for lv in range(n - 1, lvl - 1, -1):
                hi = _header_idx(lines, lstack[lv])
                h = lines[hi].strip() if hi >= 0 else ''
                if _LOOP_HDR_RX.match(h) or h.startswith('switch') \
                        or h in ('try', 'finally') or h.startswith('catch'):
                    return -1, -1
            H = E
            if not all(_falls_to(lines, gi, stack[gi], H) for gi in into):
                return -1, -1
            if until_funnel:
                return H, hdr_i
            # fix 51c: region-wide funnel (v2)
            if not self._funnel_ok(lines, stack, li, ac, hdr_i, H,
                                    into, lstack):
                return -1, -1
            return H, hdr_i
        return -1, -1

    def _collapse_arm(self, lines, stack, arm, ac, hdr_i, hdr, drop=()):
        """The label arm emptied; fold the if/else construct it sat in down
        to the arm that kept content, or to a bare condition when both arms
        emptied. Returns (ins_lines, drop_set) or None to leave the (valid
        but empty) shape alone. `drop` is the caller's own drop set (label
        line + hoisted tail + every into-goto) -- an else-arm being copied
        out whole as the new collapsed body must not carry along a goto this
        same round is deleting; its label would already be gone."""
        def cond_of(h):
            return h[4:-1].strip() if h.startswith('if (') and h.endswith(')') \
                else None

        if hdr.startswith('if ('):
            cond = cond_of(hdr)
            if cond is None:
                return None
            j = ac + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip() == 'else':
                k = j + 1
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k < len(lines) and lines[k].strip() == '{':
                    ec = _match_brace(lines, k)
                    if ec is not None and ec > k:
                        ebody = [lines[t] for t in range(k + 1, ec)
                                 if lines[t].strip() and t not in drop]
                        if ebody:
                            if cond.startswith('!(') and cond.endswith(')'):
                                newcond = cond[2:-1].strip()
                            elif cond.startswith('!'):
                                newcond = cond[1:].strip()
                            else:
                                newcond = '!(%s)' % cond
                            if not newcond:
                                return None
                            return (['if (%s)' % newcond, '{'] + ebody + ['}'],
                                    set(range(hdr_i, ec + 1)))
                        return ([] if cond in ('true', 'false') else ['%s;' % cond],
                                set(range(hdr_i, ec + 1)))
                    return None
                return None
            return ([] if cond in ('true', 'false') else ['%s;' % cond],
                    set(range(hdr_i, ac + 1)))
        if hdr == 'else':
            tc = hdr_i - 1
            while tc >= 0 and not lines[tc].strip():
                tc -= 1
            if tc < 0 or lines[tc].strip() != '}':
                return None
            st = stack[tc]
            to = st[-1] if st else -1
            if to < 0 or to >= ac:
                return None
            th_i = _header_idx(lines, to)
            th = lines[th_i].strip() if th_i >= 0 else ''
            cond = cond_of(th)
            if cond is None:
                return None
            tbody = [lines[t] for t in range(to + 1, tc) if lines[t].strip()]
            if tbody:
                return (None, set(range(hdr_i, ac + 1)))
            return ([] if cond in ('true', 'false') else ['%s;' % cond],
                    set(range(th_i, ac + 1)))
        return None

    _IMPURE = re.compile(r'[\w\]\)]\s*\(')
    # klass loads are call-shaped but side-effect free: a dead materialization
    # of a getClass()/typeof() read may drop (receivers may carry `[i - 1]`)
    # fix 72d: typeof(...).member chains (the blob register load,
    # a named static read) are pure too -- a bare typeof was the
    # only accepted spelling, so every dead
    # `objN = typeof(X).__static_fields;` spill survived all three
    # dead-store drops. Member chains only -- no calls, no indexers.
    _PURE_LOAD_RX = re.compile(
        r'^(?:[\w.\[\] +-]+\.getClass\(\)'
        r'|typeof\([^()]*\)(?:\.(?:<>)*[A-Za-z_]\w*)*)$')

    _RHS_TEXT_RX = re.compile(r'=\s*(.*);\s*$')
