from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.names import safe_ident

MEMBER_VIS = {0: '', 1: 'private ', 2: 'private protected ', 3: 'internal ',
              4: 'protected ', 5: 'protected internal ', 6: 'public ',
              7: 'public '}
METH_VIS = MEMBER_VIS
FIELD_VIS = MEMBER_VIS
# TypeAttributes visibility is a DIFFERENT table (ECMA-335 II.23.1.15):
# 0 NotPublic, 1 Public, then the six nested forms.
TYPE_VIS = {0: 'internal ', 1: 'public ', 2: 'public ', 3: 'private ',
            4: 'protected ', 5: 'internal ', 6: 'private protected ',
            7: 'protected internal '}
# CLI FieldAttributes (ECMA-335 II.23.1.5), as IL2CPP stores them
FA_STATIC = 0x0010
FA_INITONLY = 0x0020
FA_LITERAL = 0x0040
FA_HASRVA = 0x0100


def field_attrs(il, f) -> int:
    """FieldAttributes of a field row. IL2CPP does not carry field flags
    in the field table -- they live in the low 16 bits of the field's
    Il2CppType (`attrs:16`, below the type enum at bits 16-23 and the
    byref bit at 29). static/readonly/const/visibility all come from
    here; the offset-threshold and has-a-default-value heuristics this
    replaced misread 7,085 fields on the reference corpus."""
    t = il.types[f.type] if 0 <= f.type < len(il.types) else None
    return (t[1] & 0xFFFF) if t else 0


class UsingTracker:
    """Namespace references used by one emitted file, rendered as sorted,
    de-duplicated using statements. Sources are the file's rendered text --
    field types, parameter and return types, base and interface types, and
    dotted call targets inside bodies. Only namespaces that actually exist
    in the game metadata are emitted, so string literals and member paths
    can't smuggle in fake ones."""
    _DOTID_RX = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+')
    _STR_RX = re.compile(r'"(?:[^"\\]|\\.)*"')

    def __init__(self, il2: 'Il2Cpp' = None):
        self._valid = il2.all_namespaces if il2 is not None else None
        self.used: set = set()

    def add_name(self, dotted: str):
        """Collect the namespace prefix of one dotted identifier: the longest
        prefix that is a real namespace (System.Collections.Generic for
        System.Collections.Generic.List`1, never the type itself)."""
        name = dotted.strip()
        if '.' not in name:
            return
        for chunk in re.split(r'[<>\[\],*]', name):
            chunk = chunk.strip()
            if '.' not in chunk:
                continue
            parts = chunk.split('.')
            for k in range(len(parts) - 1, 0, -1):
                cand = '.'.join(parts[:k])
                if self._valid is None or cand in self._valid:
                    self.used.add(cand)
                    break

    def add_text(self, text: str):
        """Collect every dotted identifier in a chunk of rendered source;
        string literals are masked out first."""
        for m in self._DOTID_RX.finditer(self._STR_RX.sub('', text)):
            self.add_name(m.group(0))

    def render(self, skip=()) -> List[str]:
        skip = set(skip or ())
        return ['using %s;' % n for n in sorted(self.used - skip)]


_NS_CHAIN_RX = re.compile(r'(?<![\w.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)')


def strip_namespaces(lines: List[str], uses: set) -> List[str]:
    """Drop the namespace prefix of every dotted reference the file's own
    using set imports (longest imported prefix wins), so a body carrying
    `UnityEngine.Transform` under `using UnityEngine;` reads `Transform`.
    String literals and // comments are left untouched."""
    order = sorted(uses, key=lambda u: (-len(u), u))

    def rewrite(s: str) -> str:
        out = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch in ('"', "'"):
                j = i + 1
                while j < n and s[j] != ch:
                    j += 2 if s[j] == '\\' else 1
                out.append(s[i:min(j + 1, n)])
                i = j + 1
                continue
            if ch == '/' and i + 1 < n and s[i + 1] == '/':
                out.append(s[i:])
                break
            j = i
            while j < n and s[j] not in '"\'':
                if s[j] == '/' and j + 1 < n and s[j + 1] == '/':
                    break
                j += 1
            code = s[i:j]

            def rep(m):
                chain = m.group(0)
                for u in order:
                    if chain.startswith(u + '.'):
                        rest = chain[len(u) + 1:]
                        # Self-shadow: the stripped prefix ends where the
                        # remainder begins (`HID.HIDDeviceDescriptor` from
                        # `...HID.HID...`). Shortening rebinds the head to
                        # the namespace instead of the nested owner, so the
                        # full chain stays.
                        if rest.split('.')[0] == u.split('.')[-1]:
                            return chain
                        return rest
                return chain

            out.append(_NS_CHAIN_RX.sub(rep, code))
            i = j
        return ''.join(out)

    return [rewrite(l) for l in lines]


_NAMEOF_DENY = {
    'None', 'All', 'Default', 'Name', 'Value', 'True', 'False', 'Auto',
    'Other', 'Unknown', 'Normal', 'Custom', 'Left', 'Right', 'Center',
    'Top', 'Bottom', 'Start', 'End', 'None1', 'First', 'Last', 'Empty',
}
_NAMEOF_LIT_RX = re.compile(r'"([A-Za-z_]\w{2,})"')


def nameof_sugar(lines: List[str], members) -> List[str]:
    """Rewrite string literals that name an enum member (of an enum the
    file imports) into nameof(Enum.Member). `nameof` always evaluates to
    the identifier text, so the runtime value is unchanged; the denylist
    keeps common-word members out. Only whole arguments convert (the
    literal is preceded by '(' or ',' and followed by ')' or ',')."""
    out = []
    for raw in lines:
        i = 0
        n = len(raw)
        res = []
        while i < n:
            ch = raw[i]
            if ch in ('"', "'"):
                j = i + 1
                while j < n and raw[j] != ch:
                    j += 2 if raw[j] == '\\' else 1
                lit = raw[i:min(j + 1, n)]
                if ch == '"' and i > 0 and raw[i - 1] in '(,' \
                        and min(j + 1, n) < n and raw[j + 1] in '),':
                    m = _NAMEOF_LIT_RX.match(lit)
                    if m and m.group(1) in members and m.group(1) not in _NAMEOF_DENY:
                        # the enum member declaration escapes keywords
                        # (safe_ident), so the nameof text must match it.
                        res.append('nameof(%s.%s)' % (members[m.group(1)], safe_ident(m.group(1))))
                        i = j + 1
                        continue
                res.append(lit)
                i = j + 1
                continue
            if ch == '/' and i + 1 < n and raw[i + 1] == '/':
                res.append(raw[i:])
                i = n
                break
            j = i
            while j < n and raw[j] not in '"\'':
                if raw[j] == '/' and j + 1 < n and raw[j + 1] == '/':
                    break
                j += 1
            res.append(raw[i:j])
            i = j
        out.append(''.join(res))
    return out

