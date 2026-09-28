from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import _has_arrow, _in_string
from il2cpp.stmt_text import _fix_cond_line, _rsplit_op, _split_top

def _needs_unsafe_block(lines):
    """True when any rendered line uses unsafe pointer syntax: a raw
    `*(...)` deref, a `(T*)` pointer cast of any primitive spelling (fix
    102 renders width-preserving casts, not only byte), or `->`."""
    for ln in lines:
        if '*(' in ln or '*))' in ln or _has_arrow(ln):
            return True
        if re.search(r'\(\([A-Za-z_][\w$]*\*\)', ln):
            return True
    return False
class _TextPassMixin:
    @classmethod
    def _simplify_cond(cls, c: str) -> str:
        c = c.strip()
        m = re.match(r'^!\((.*)\)$', c)
        if m and cls._negation_spans_whole(c):
            inner = m.group(1).strip()
            for op, neg in cls.NEG.items():
                # try split at last occurrence of ' op ' outside quotes
                idx = _rsplit_op(inner, op)
                if idx is not None:
                    lhs = inner[:idx].strip()
                    rhs = inner[idx + len(op):].strip()
                    if lhs and rhs:
                        return '%s %s %s' % (lhs, neg, rhs)
            return '!(%s)' % inner
        return c

    @staticmethod
    def _negation_spans_whole(c: str) -> bool:
        """True when the `!(` of `!(...)` closes at the final `)`.
        A regex alone cannot tell `!((A) & (B))` (whole negation,
        De Morgan applies) from `!(A) & (B)` (negated first operand
        only); simplifying the latter drops the `!` and strands the
        `&` arm outside the head -- unparseable (MinMaxAABB). String
        literals never affect paren depth."""
        if not c.startswith('!(') or not c.endswith(')'):
            return False
        depth = 0
        for k in range(1, len(c)):
            if _in_string(c, k):
                continue
            ch = c[k]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return k == len(c) - 1
        return False

    # callee-adjacent guard (mirrors SUB_CMP_RE): folding inside a call's
    # own parens (`s_28.ctor(0 + 1)` -> `s_28.ctor1`) deletes the argument
    # list itself (XmlNodeConverter). Grouping parens (after space, open
    # paren or operator) still fold.
    FOLD_RE = re.compile(r'(?<![\w.>\]\)])\((-?(?:0[xX][0-9a-fA-F]+|\d+)) ([+*/&|^-]|<<|>>) '
                         r'(-?(?:0[xX][0-9a-fA-F]+|\d+))\)')
    ZEXT_RE = re.compile(r'\((-?(?:0[xX][0-9a-fA-F]+|\d+)) & (0[xX][0-9a-fA-F]+)/\*z\*/\)')

    # X - C ==/!= D  ->  X ==/!= D+C   (one or more ` - C` terms).
    # X must start at an operand boundary and begin with a letter/underscore,
    # so `(num1 + 2) - 1 != 0` gets no fold and `0 == 0` can never match.
    SUB_CMP_RE = re.compile(
        r'(?<![\w.>\]\)])([A-Za-z_][\w.<>\[\]]*)'               # X
        r'((?: - (?:-?(?:0[xX][0-9a-fA-F]+|\d+)))+)'             # one or more ` - C`
        r' (==|!=) '
        r'(-?(?:0[xX][0-9a-fA-F]+|\d+))')                       # D
    _SUB_CMP_TERM_RE = re.compile(r' - (-?(?:0[xX][0-9a-fA-F]+|\d+))')

    _STR_LIT_RX = re.compile(r'^"(?:[^"\\]|\\.)*"$')
    _TOSTRING_RX = re.compile(r'^(.*)\.ToString\("([^"{}]*)"\)$')

    @classmethod
    def _interp_parts(cls, parts):
        """$"...": interpolation when a concat mixes string literals with
        expressions; None when the shape doesn't fit (all-literal, or a part
        that can't live inside a hole -- nested quotes)."""
        lit = [p for p in parts if cls._STR_LIT_RX.match(p.strip())]
        if not lit or len(lit) == len(parts):
            return None
        out = ['$"']
        for p in parts:
            p = p.strip()
            if cls._STR_LIT_RX.match(p):
                body = p[1:-1]
                if '{' in body or '}' in body:
                    body = body.replace('{', '{{').replace('}', '}}')
                out.append(body)
                continue
            if '"' in p or '\n' in p:
                return None
            m = cls._TOSTRING_RX.match(p)
            if m and m.group(1):
                out.append('{%s:%s}' % (m.group(1), m.group(2)))
            else:
                out.append('{%s}' % p)
        out.append('"')
        return ''.join(out)

    _FMT_HOLE_RX = re.compile(r'\{(\d+)([:,][^{}]*)?\}')

    def _format_interp(self, text: str) -> str:
        """System.String.Format("{0} x {1}", a, b) -> $" {a} x {b} " when
        every hole resolves to an argument that can live inside one."""
        idx = 0
        while True:
            idx = text.find('System.String.Format(', idx)
            if idx < 0:
                return text
            start = idx + len('System.String.Format(')
            depth = 1
            i = start
            while i < len(text) and depth > 0:
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                i += 1
            if depth != 0:
                return text
            parts = _split_top(text[start:i - 1])
            if len(parts) < 2 or not all(p.strip() for p in parts):
                idx = i
                continue
            lit = parts[0].strip()
            if not self._STR_LIT_RX.match(lit):
                idx = i
                continue
            args = [p.strip() for p in parts[1:]]

            def hole_text(a, suffix=''):
                tm = self._TOSTRING_RX.match(a)
                if tm and tm.group(1):
                    return '{%s:%s}' % (tm.group(1), tm.group(2))
                return '{%s%s}' % (a, suffix)

            if any('"' in hole_text(a) or '\n' in hole_text(a) for a in args):
                idx = i
                continue
            body = lit[1:-1].replace('{{', '\x01').replace('}}', '\x02')

            def hole(mo):
                n = int(mo.group(1))
                if n >= len(args):
                    return mo.group(0)
                return hole_text(args[n], mo.group(2) or '')

            body = self._FMT_HOLE_RX.sub(hole, body)
            if re.search(r'\{\d', body):
                idx = i
                continue
            rep = '$"' + body.replace('\x01', '{{').replace('\x02', '}}') + '"'
            text = text[:idx] + rep + text[i:]
            idx += len(rep)

    @classmethod
    def _fold_concat(cls, text: str) -> str:
        # System.String.Concat(a, b, c) -> (a + b + c), or $"..." when the
        # args mix string literals with expressions
        idx = 0
        while True:
            idx = text.find('System.String.Concat(', idx)
            if idx < 0:
                break
            start = idx + len('System.String.Concat(')
            depth = 1
            i = start
            while i < len(text) and depth > 0:
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                i += 1
            if depth != 0:
                break
            inner = text[start:i - 1]
            parts = _split_top(inner)
            if len(parts) >= 2 and all(p.strip() for p in parts):
                inter = cls._interp_parts(parts)
                if inter is not None:
                    text = text[:idx] + inter + text[i:]
                    idx += len(inter)
                else:
                    text = text[:idx] + '(' + ' + '.join(p.strip() for p in parts) + ')' + text[i:]
                    idx += 2
            else:
                idx = i
        return text

    @classmethod
    def _fold_consts(cls, text: str) -> str:
        def zrep(m):
            try:
                return str(int(m.group(1), 0) & int(m.group(2), 0))
            except Exception:
                return m.group(0)
        text = cls.ZEXT_RE.sub(zrep, text)

        def rep(m):
            try:
                a, op, b = int(m.group(1), 0), m.group(2), int(m.group(3), 0)
                if op == '+':
                    return str(a + b)
                if op == '-':
                    return str(a - b)
                if op == '*' and abs(a) < 4096 and abs(b) < 4096:
                    return str(a * b)
                if op == '/' and b != 0 and a % b == 0:
                    return str(a // b)
                if op == '&':
                    return str(a & b)
                if op == '|':
                    return str(a | b)
                if op == '^':
                    return str(a ^ b)
                if op == '<<' and 0 <= b < 64:
                    return str(a << b)
                if op == '>>' and 0 <= b < 64:
                    return str(a >> b)
            except Exception:
                pass
            return m.group(0)
        def sub_cmp_rep(m):
            try:
                cs = sum(int(c, 0) for c in cls._SUB_CMP_TERM_RE.findall(m.group(2)))
                d = int(m.group(4), 0)
                return '%s %s %d' % (m.group(1), m.group(3), d + cs)
            except Exception:
                return m.group(0)
        prev = None
        while prev != text:
            prev = text
            text = cls.FOLD_RE.sub(rep, text)
            text = cls.SUB_CMP_RE.sub(sub_cmp_rep, text)
        return text

    _DEREF_OFF = re.compile(r'([+-])\s*(0x[0-9a-fA-F]+|\d+)\s*$')
    _ADDR_LOCAL_RX = re.compile(
        r'(?<=[\\(,])(?<!\*)\&((?:obj|s|t|v)\d+|this\.[A-Za-z_$][\w$]*)')
    _DSTAR_RX = re.compile(
        r'(?<!\*)\*((?:obj|s|t|v)\d+|this)(?:\.[A-Za-z_$][\w$]*)*')
    _NCONST_RX = re.compile(
        r'(?<![\w)])(?<!\w\s)(?<!\)\s)\*(0x[0-9a-fA-F]+|\d+)')
    # a cast-prefixed constant deref (`(uint*)*16`, from a folded
    # null-base address) is not a multiplication: the paren group is
    # type-shaped (ends in `*`), so the inner `*` is a redundant
    # deref -- the cast already provides pointerhood. `(a+b)*16`
    # (operand, not cast) never matches and stays untouched.
    _CAST_NCONST_RX = re.compile(
        r'\(([A-Za-z_.<>\,\[\]\*? ]+\*)\)\*(0x[0-9a-fA-F]+|\d+)')
    _RCONST_RX = re.compile(r'\breturn\s+\*(0x[0-9a-fA-F]+|\d+)\s*;')
    _TYPEOF_KSTORE_RX = re.compile(
        r'^(\s*)typeof\(([^()]*)\)\s*\.\s*[A-Za-z_][\w$]*\s*=\s*[^=].*;')
    _LVAL_OFF_RX = re.compile(
        r'^((?:[A-Za-z_$][\w$]*|typeof\([^()]*\))(?:\.[A-Za-z_$][\w$]*)*)'
        r'\s*\+\s*((?:\([^=]*?\)|[^=;])+?)\s*=')
    _DATA_ADDR_RX = re.compile(r'&(data_[0-9a-fA-F]+)')
    _TYPEOF_STORE_0_RX = re.compile(r'^(\s*)typeof\([^)]*\)\s*=\s*[^=].*;')
    _DEFAULT_OP_RX = re.compile(r'(?<![:\w])\bdefault(?=\s*[><=!&|+*/%]|\s*\.)')
    _DEFAULT_DEQUE_RX = re.compile(r'\bdefault(?:\s+default)+\b|\(\s*\w+\s+default\s*\)')
    _FLAG_SENTINEL_RX = re.compile(r'\x01[^;\r\n]*;')

    def _fix_select(self, ln: str) -> str:
        """`(c ? Y)` (lifter select with no false branch) -> `(c ? Y : default)`.
        Only `?` marks inside paren groups that contain no `:` are touched;
        full `? :` ternaries and unknown-value `default`s already passed."""
        if '?' not in ln:
            return ln
        # NOTE: no whole-line `':' in ln` fast-reject here -- a `:` can sit
        # inside an unrelated string literal (`string.IndexOf(";/?:@&=+_,",
        # c)`) or in a real ternary elsewhere on the same line, and either
        # one used to skip this whole line, select mark and all. The loop
        # below already re-checks `:` per paren GROUP (`ln[k:j]`), which is
        # the actually-correct, narrower rule this docstring describes.
        n = len(ln)
        i = 0
        while i < n:
            qi = ln.find('?', i)
            if qi < 0:
                break
            if _in_string(ln, qi):
                # a `?` inside a string/char literal is text, not a select
                # mark (`obj17.ctor("Touch Touch Contact?")` was getting
                # ` : default` appended after the literal)
                i = qi + 1
                continue
            nxt1 = ln[qi + 1] if qi + 1 < n else ''
            prv1 = ln[qi - 1] if qi > 0 else ''
            if nxt1 == '?':
                # `??` -- the second `?` is part of the operator too
                i = qi + 2
                continue
            if nxt1 in ('.', '[') or prv1 == '?':
                # `?.`/`?[`/`??` are null operators, not the lifter's
                # no-false-arm select mark (the same guard
                # `_strip_dangling_default` uses); appending a false arm
                # inside the parens corrupts the expression.
                i = qi + 1
                continue
            k = qi - 1
            depth = 0
            while k >= 0:
                c2 = ln[k]
                if c2 == ')':
                    depth += 1
                elif c2 == '(':
                    if depth == 0:
                        break
                    depth -= 1
                k -= 1
            if k < 0:
                break
            # the select's expression ends at the first statement-level `;`
            # AFTER the mark (for-headers: the `;` between cond and incr), or
            # at the group's `)` when no `;` intervenes (while/if/assignment,
            # including parenthesized selects before a comma/`;`)
            j = qi + 1
            depth = 0
            while j < n:
                c2 = ln[j]
                if c2 == '(':
                    depth += 1
                elif c2 == ')':
                    if depth == 0:
                        break
                    depth -= 1
                elif c2 == ';' and depth == 0:
                    break
                j += 1
            if any(ln[_m] == ':' and not _in_string(ln, _m) for _m in range(k, j)):
                # the group is already a ternary; never re-process this `?`
                # (j can sit BEFORE the `?` inside a `for` header, so a bare
                # `i = j` would re-find the same mark forever). A `:` inside a
                # STRING literal in this span (`string.IndexOf(";/?:@&", c)`)
                # is not a real ternary colon and must not count here.
                i = qi + 1
                continue
            ln = ln[:j] + ' : default' + ln[j:]
            n = len(ln)
            i = j + len(' : default')
        return ln

    def _unsafify(self, text: str) -> str:
        """Rewrite residual native pointer syntax into parseable unsafe C#.
        `*(E + N)` (a deref of a pointer-arithmetic base) becomes
        `((byte*)E + N)[0]`; a bare-pointer deref `*E` becomes
        `((byte*)E)[0]`; a raw-offset STORE lvalue `E + N = v` becomes
        `((byte*)E + N)[0] = v`. Only the outermost offset is peeled per
        pass; nested derefs re-enter through the loop. `&objN` argument
        residues become `ref objN`."""
        for _ in range(16):
            m = text
            text = self._CAST_NCONST_RX.sub(r'(\1)\2', text)
            text = self._DSTAR_RX.sub(r'((byte*)\1)[0]', text)
            text = self._NCONST_RX.sub(r'((byte*)\1)[0]', text)
            if text == m:
                m2 = self._LVAL_OFF_RX.match(text)
                if m2:
                    text = '((byte*)%s + %s)[0] = %s' % (m2.group(1), m2.group(2),
                                             text[m2.end():].lstrip())
                else:
                    mm = re.search(r'\*\x28', text)
                    if mm:
                        i = mm.start() + 1
                        depth = 0
                        j = i
                        while j < len(text):
                            ch = text[j]
                            if ch == '(':
                                depth += 1
                            elif ch == ')':
                                depth -= 1
                                if depth == 0:
                                    break
                            j += 1
                        if j < len(text):
                            inner = text[i + 1:j]
                            om = self._DEREF_OFF.search(inner)
                            if om:
                                off = om.group(2)
                                sign = om.group(1)
                                base = inner[:om.start()].rstrip('+- ')
                                repl = '((byte*)%s %s %s)[0]' % (base, sign, off)
                                text = text[:mm.start()] + repl + text[j + 1:]
                            # a bare `=` guards against converting an
                            # inner that's actually an assignment/
                            # statement blob, not a real dereference
                            # target -- but `[=;]` also matches the `=`
                            # inside `==`/`!=`/`<=`/`>=`, so any deref
                            # target containing a plain COMPARISON (a
                            # CMOV-derived ternary's condition, e.g.
                            # `*(obj6 + 0x0) == obj7 ? obj6 : 0`, batch
                            # 27) silently skipped conversion, leaving the
                            # raw `*(...)` form -- not just imprecise
                            # output, that raw form is a genuine parse
                            # error whenever the paren-matched inner isn't
                            # a bare identifier (ground-truthed:
                            # `XmlWriterSettings.cs`). Only a real
                            # assignment operator -- `=` not part of one
                            # of those four comparison operators -- or a
                            # statement-terminating `;` should still
                            # block the conversion.
                            elif not re.search(r';|(?<![=!<>])=(?!=)', inner):
                                text = text[:mm.start()] + '((byte*)%s)[0]' % inner + text[j + 1:]
                    if text == m:
                        break
        return text

    @staticmethod
    def _sanitize_dollar(ln: str) -> str:
        """Replace `$` in code only; C# identifiers cannot carry it.

        Metadata names can (Burst's `$BurstManaged`), so the char is
        sanitized -- but a blanket line replace corrupted every string
        literal it touched: JSON.NET's wire names became `_type`/`_id`/
        `_values`, the UTF7 direct-character set lost its `$`, and a
        money template became `MONEY: _`. Strings, chars and comments
        keep their bytes.
        """
        out = []
        n = len(ln)
        i = 0
        while i < n:
            if ln.startswith('//', i):
                out.append(ln[i:])
                break
            if ln.startswith('/*', i):
                j = ln.find('*/', i + 2)
                if j < 0:
                    out.append(ln[i:])
                    break
                out.append(ln[i:j + 2])
                i = j + 2
                continue
            if ln.startswith('$@"', i):
                j = i + 3
                while j < n:
                    if ln.startswith('""', j):
                        j += 2
                        continue
                    if ln[j] == '"':
                        j += 1
                        break
                    j += 1
                out.append(ln[i:j])
                i = j
                continue
            if ln.startswith('$"', i):
                j = i + 2
                while j < n:
                    if ln[j] == '\\':
                        j += 2
                        continue
                    if ln[j] == '"':
                        j += 1
                        break
                    j += 1
                out.append(ln[i:j])
                i = j
                continue
            if ln.startswith('@"', i):
                j = i + 2
                while j < n:
                    if ln.startswith('""', j):
                        j += 2
                        continue
                    if ln[j] == '"':
                        j += 1
                        break
                    j += 1
                out.append(ln[i:j])
                i = j
                continue
            c = ln[i]
            if c in ('"', "'"):
                j = i + 1
                while j < n:
                    if ln[j] == '\\':
                        j += 2
                        continue
                    if ln[j] == c:
                        j += 1
                        break
                    j += 1
                out.append(ln[i:j])
                i = j
                continue
            out.append('_' if c == '$' else c)
            i += 1
        return ''.join(out)

    def _render(self, raw: List[str]) -> List[str]:
        # residual pointer syntax: `*(E + N)` -> `((byte*)E + N)[0]`,
        # `&objN` args -> `ref objN`; files with any of it get wrapped
        # in an unsafe block below (C# permits pointer ops only there)
        raw = [self._sanitize_dollar(ln) for ln in raw]
        raw = [self._DATA_ADDR_RX.sub(r'\1', ln) for ln in raw]
        # `typeof(X) = 0;` (a static-field blob store whose offset 0 has no
        # field name to attach) cannot be an lvalue; keep the fact as a
        # comment. A bare `default` that got rewritten into an operator
        # context (`default > x`) is an unknown value, not the keyword.
        # Trailing `;` on the replacement keeps the line a real (if empty)
        # statement -- a bare `/* comment */` with nothing after it is not
        # a statement, so a label with no other tail collapsed to just one
        # of these (e.g. after `case`/`else` funneled into a single elided
        # store) left a MISSING-node parse error: `L_x: /* ... */` needs a
        # statement after the label, and a comment alone doesn't count.
        raw = [self._TYPEOF_STORE_0_RX.sub(r'\1/* typeof(X) blob store at offset 0 */;', ln) for ln in raw]
        raw = [self._TYPEOF_KSTORE_RX.sub(
            lambda m: m.group(0).replace('typeof(' + m.group(2) + ')', m.group(2), 1),
            ln) for ln in raw]
        raw = [self._RCONST_RX.sub(r'return ((byte*)\1)[0];', ln) for ln in raw]
        raw = [self._DEFAULT_OP_RX.sub('0', ln) for ln in raw]
        for _ in range(3):
            raw = [self._DEFAULT_DEQUE_RX.sub('default', ln) for ln in raw]
        # fix 54b: the `&X` -> `ref X` rewrite that used to wrap this
        # call is gone. Its lookbehind (`(?<=[(,])`) could only ever
        # reach the argument immediately after `(`, because args join
        # with ', ' -- so it spelled `ref` by comma position, not by
        # signature. fix 54 (il2csharp.py `_hint_arg_types`) now does it
        # from the callee's declared parameter type; anything it cannot
        # resolve keeps the honest raw `&`.
        # lone `?` marks an undecodable native value; the lifter's ternary
        # renders are protected: a `?` followed by a real operand
        # (`(c ? X)` no-colon select form and the full `? :` form) stays
        raw = [ln.replace('?addr', 'default') for ln in raw]
        # lone `?` marks an undecodable native value. Rewrite ONLY operand
        # positions into the parseable `unknown` name: a `?` preceded by an
        # expression (`(c ? Y)` no-false-arm select, `? 1 : 0` ternary,
        # `int?` nullable) is the lifter's select mark and stays for
        # _fix_select; `??` coalesces are already valid C#. The `?`-as-
        # unknown-op vs operand ambiguity resolves textually: select marks
        # sit AFTER a value (letter/digit/)/]/>) and unknown operands sit
        # after whitespace/opening chars.
        # (documentation form of the scanner below; the scanner is the
        # implementation - it is string-aware and skips whitespace behind
        # the `?` before deciding head-is-a-value)
        _UK_RX = re.compile(r'(?<![A-Za-z0-9_)\]>])\?(?=\s*(?:[<>=|+*/%^\[\].&:-]|!(?==))|[.,);]|\s*$|\s*\?)')

        # keywords that OPEN an expression: a `?` after one is an unknown
        # operand, never a select mark (`return ? - x;`). `this`/`base`/
        # `true`/`false`/`null`/`default`/`unknown` END a value and are
        # deliberately absent.
        _OPENS_EXPR = frozenset((
            'return', 'case', 'goto', 'new', 'throw', 'ref', 'out', 'in',
            'is', 'as', 'yield', 'await', 'else', 'do', 'while', 'if',
            'stackalloc', 'checked', 'unchecked',
        ))

        def _rewrite_unknowns(ln: str) -> str:
            out = []
            n = len(ln)
            i = 0
            s = ln
            while i < n:
                c = s[i]
                if c in ('"', "'"):
                    delim = c
                    j = i + 1
                    while j < n:
                        if s[j] == '\\':
                            j += 2
                            continue
                        if s[j] == delim:
                            break
                        j += 1
                    out.append(s[i:j + 1])
                    i = j + 1
                    continue
                if c == '?':
                    if i + 1 < n and s[i + 1] == '?':
                        out.append('??')
                        i += 2
                        continue
                    # a select mark sits after a VALUE, an unknown operand
                    # after an operator/opening char. Look PAST whitespace
                    # for that value: `0 ? &obj5` and `real1 ? -inff` are
                    # selects whose adjacent char is a space. `>` counts
                    # only when adjacent (a generic close, `Foo<T>?`) --
                    # separated by a space it is the comparison operator
                    # (`? > ?`). With the head test whitespace-aware, the
                    # tail set can carry a bare `-`.
                    prev = s[i - 1] if i else ''
                    k = i - 1
                    while k >= 0 and s[k] in ' \t':
                        k -= 1
                    back = s[k] if k >= 0 else ''
                    if back.isalnum() or back == '_':
                        w = re.search(r'[A-Za-z_]\w*$', s[:k + 1])
                        if w and w.group(0) in _OPENS_EXPR:
                            back = ''
                    # `?` is deliberately NOT a back-value: a `? ?` chain
                    # must rewrite BOTH marks so the `unknown unknown`
                    # collapse below folds it to one `unknown`.
                    if not (re.match(r'[A-Za-z0-9_)\]>]', prev)
                            or re.match(r'[A-Za-z0-9_)\]]', back)):
                        tail = s[i + 1:]
                        if re.match(r'\s*(?:[<>=|+*/%^\[\].&:-]|!(?==))|[.,);]|\s*$|\s*\?', tail):
                            out.append('unknown')
                            i += 1
                            continue
                out.append(c)
                i += 1
            return ''.join(out)

        # Repair unknown operands before pointer casts can turn their
        # closing ')' into false evidence of a ternary condition.
        raw = [_rewrite_unknowns(ln) for ln in raw]
        raw = [self._unsafify(ln) for ln in raw]
        raw = [_rewrite_unknowns(ln) for ln in raw]
        # a chain of two unknown operands with an unknown operator between
        # them (`? ? ?` -> `unknown unknown unknown`) collapses to one.
        for _ in range(3):
            raw = [re.sub(r'\bunknown\s+unknown\b', 'unknown', ln) for ln in raw]
        # `?.NAME : default` is the selective-shock `?` receiver: the rewrite
        # above already produced `unknown.NAME`; drop the dangling ` : default`
        # ternary tail that would leave an unparseable `expr : default` in an
        # argument list (RuntimeHelpers.InitializeArray family). A real
        # ternary keeps its `?` outside strings, so a `: default` whose
        # enclosing statement region has none is a dangling tail.
        raw = [re.sub(r'\bunknown\.([A-Za-z_]\w*)\s*:\s*default\b', 'unknown.\\1', ln) for ln in raw]

        def _strip_dangling_default(ln: str) -> str:
            out = []
            n = len(ln)
            i = 0
            s = ln
            # Depths of the paren groups holding a live ternary/select
            # `?` mark. A `?` governs a later `: default` only while
            # its own group stays open, so a call's parens inside the
            # true arm (`c ? Foo(x) : default`, synthesized en masse by
            # fix 97b whenever a zero-literal else-arm takes a
            # non-numeric declaration) no longer read as a region
            # boundary orphaning the tail into `? Foo(x) ;`. fix 97e.
            live_q = []
            depth = 0
            while i < n:
                c = s[i]
                if c in ('"', "'"):
                    j = i + 1
                    while j < n:
                        if s[j] == '\\':
                            j += 2
                            continue
                        if s[j] == c:
                            break
                        j += 1
                    out.append(s[i:j + 1])
                    i = j + 1
                    continue
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth = depth - 1 if depth else 0
                    live_q = [qd for qd in live_q if qd <= depth]
                if c == '?':
                    nxt1 = s[i + 1] if i + 1 < n else ''
                    prv1 = s[i - 1] if i > 0 else ''
                    if nxt1 != '?' and nxt1 != '.' and prv1 != '?':
                        # `??`/`?.` never open a ternary arm, and
                        # neither does a nullable `?` (`T?`, `(T?)`,
                        # `Foo<T?>`): its follower closes the type
                        # instead of starting a value.
                        k = i + 1
                        while k < n and s[k] in ' \t':
                            k += 1
                        nxt = s[k] if k < n else ''
                        if nxt != '>' and nxt != ',' and nxt != ')' and nxt != ';' and nxt != '=' and nxt != '[' and nxt != '.' and nxt != '?' and nxt != ':' and nxt != '':
                            live_q.append(depth)
                if c == ',':
                    # a comma only closes sibling groups at its own
                    # depth: one inside a call's arguments
                    # (`c ? Foo(a, b) : default`) must not forget the `?`.
                    live_q = [qd for qd in live_q if qd < depth]
                elif c in ';{' or (c == '=' and i > 0 and s[i - 1] not in '!<>'):
                    live_q = []
                if c == ':':
                    m = re.match(r':\s*default\b', s[i:])
                    if m:
                        nxt = i + len(m.group(0))
                        if nxt >= n or s[nxt] in ');,':
                            if not live_q:
                                i = nxt
                                continue
                out.append(c)
                i += 1
            return ''.join(out)

        raw = [_strip_dangling_default(ln) for ln in raw]
        # the lifter's select form `(c ? Y)` carries no false branch; the
        # grammar needs one, and C# needs a real value: unknown -> default
        raw = [self._fix_select(ln) for ln in raw]
        # a store INTO an untracked address (`?addr = v;`) cannot be
        # re-expressed; keep the fact as a comment, drop the impossible line
        raw = [re.sub(r'^(\s*)default\s*=.*;$',
                      r'\1/* store into untracked ?addr elided */', ln) for ln in raw]
        needs_unsafe = _needs_unsafe_block(raw)
        # drop pure value-discard statements: a line that IS only a
        # pointer cast/index with no assignment or call has no effect
        cleaned = []
        for ln in raw:
            if re.match(r'^\(\(byte\*\)[^()=]*\)(?:\[0\])?;', ln):
                continue
            cleaned.append(ln)
        # drop duplicate call statements followed by var tN = <same call>
        dup = []
        i = 0
        while i < len(cleaned):
            line = cleaned[i].rstrip()
            if line.endswith(';') and i + 1 < len(cleaned):
                nxt = cleaned[i + 1].strip()
                if nxt.startswith('var ') and '=' in nxt:
                    rhs = nxt.split('=', 1)[1].strip().rstrip(';')
                    if rhs == line.rstrip(';') and '(' in line:
                        i += 1
                        dup.append(nxt)
                        i += 1
                        continue
            dup.append(line)
            i += 1
        cleaned = dup
        out = []
        depth = 0
        j = 0
        # simplify conditions
        while j < len(cleaned):
            line = cleaned[j].strip()
            if line.startswith('if (') or line.startswith('while (') or line.startswith('} while'):
                line = _fix_cond_line(line, self)
            if line == '{':
                out.append('    ' * depth + '{')
                depth += 1
                j += 1
                continue
            if line == '}' or line.startswith('} while'):
                if line == '}':
                    depth = max(0, depth - 1)
                    out.append('    ' * depth + '}')
                    j += 1
                    # drop empty if/else blocks: pattern 'if (...)' '{' '}' -> drop all three
                    if len(out) >= 2 and out[-1].strip() == '}' and out[-2].strip() == '{':
                        k = len(out) - 3
                        head = out[k].strip() if k >= 0 else ''
                        if head == 'else':
                            out = out[:k]
                            continue
                        if head.startswith('if ('):
                            # empty then-branch: if an else follows, invert the test and
                            # keep that branch -- purely structural, the condition still
                            # evaluates exactly once, so an IMPURE (call) cond inverts
                            # just as soundly as a bare token (fix 44b; _flag_inline's
                            # inlined call conds relied on the old guard refusing them).
                            # The no-else DROP arm is the one that must stay pure-guarded:
                            # dropping `if (call()) { }` would erase the side effect.
                            if j < len(cleaned) and cleaned[j].strip() == 'else':
                                j += 1
                                out = out[:k]
                                inner = head[4:-1]
                                for _ in range(4):
                                    if inner[:1] == '(' and inner[-1:] == ')' and self._paren_wraps_whole(inner):
                                        inner = inner[1:-1]
                                    else:
                                        break
                                out.append('    ' * depth
                                           + _fix_cond_line('if (!(%s))' % inner, self))
                            elif not self._IMPURE.search(head[4:-1]):
                                out = out[:k]
                            continue
                    continue
                else:
                    depth = max(0, depth - 1)
                    out.append('    ' * depth + line)
                    j += 1
                    continue
            if line == 'else':
                out.append('    ' * depth + 'else')
                j += 1
                continue
            if line:
                line = self._fold_concat(line)
                line = self._format_interp(line)
                line = self._fold_consts(line)
                out.append('    ' * depth + line)
            j += 1
        if needs_unsafe:
            # the writer owns the method's outer braces, so the unsafe
            # block must be self-contained: `unsafe { ... }` pairs inside.
            out = ['unsafe', '{'] + out + ['}']
        return out


    # ------------------------------------------------------------------
