"""Extract structural declarations from emitted C# files (side A check).

Parses every .cs file under an image directory (except
__SharedBodyStubs.cs, whose stub methods have no metadata owners)
with tree-sitter-c-sharp and emits the same T/M/F grammar as
tools/dump_decls.py, so the two can be structurally compared:
type existence + kind, base/interface short names, member
existence + name + staticness + generic arity + parameter count.
Property/event/indexer declarations are skipped (their accessors
are folded; the metadata dump excludes accessor methods too).
Any other unhandled declaration shape fails loudly -- a gate that
silently skips is dishonest.
"""
import argparse
import os
import re
import sys

import tree_sitter_c_sharp as tscs
from tree_sitter import Language, Parser

CS = Language(tscs.language())

OP_TABLE = {
    "+": "op_Addition", "-": "op_Subtraction", "*": "op_Multiply",
    "/": "op_Division", "%": "op_Modulus", "&": "op_BitwiseAnd",
    "|": "op_BitwiseOr", "^": "op_ExclusiveOr", "!": "op_LogicalNot",
    "<<": "op_LeftShift", ">>": "op_RightShift",
    "==": "op_Equality", "!=": "op_Inequality",
    "<": "op_LessThan", ">": "op_GreaterThan",
    "<=": "op_LessThanOrEqual", ">=": "op_GreaterThanOrEqual",
    "~": "op_OnesComplement", "++": "op_Increment", "--": "op_Decrement",
    "true": "op_True", "false": "op_False",
}

TYPE_KW = {"class": "class", "struct": "struct", "interface": "interface",
           "enum": "enum", "record": "class"}


def text(src, node):
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


class Extractor:
    def __init__(self):
        self.parser = Parser(CS)
        self.types = {}
        self.unhandled = []
        self.skipped_props = 0

    def emit_type(self, path, kind):
        self.types.setdefault(path, {"kind": kind, "base": None, "ebase": None,
                                     "ifaces": [], "members": []})

    def walk(self, src, node, ns, owners):
        if len(node.children) == 0:
            return
        t = node.type
        if t in ("namespace_declaration", "file_scoped_namespace_declaration"):
            name = ns
            for c in node.children:
                if c.type in ("qualified_name", "identifier"):
                    name = text(src, c).strip()
                    break
            for c in node.children:
                if c.type == "declaration_list":
                    for d in c.children:
                        self.walk(src, d, name, owners)
            return
        if t in ("class_declaration", "struct_declaration",
                 "interface_declaration", "record_declaration",
                 "enum_declaration"):
            kw = ("class" if t == "class_declaration"
                  else "struct" if t == "struct_declaration"
                  else "interface" if t == "interface_declaration"
                  else "enum" if t == "enum_declaration" else "class")
            name = None
            garity = 0
            base = None
            ifaces = []
            static = False
            for c in node.children:
                if c.type == "modifier" and text(src, c).strip() == "static":
                    static = True
                elif c.type == "identifier" and name is None:
                    name = text(src, c).strip()
                elif c.type == "type_parameter_list":
                    garity = sum(1 for g in c.children
                                 if g.type == "type_parameter")
                elif c.type == "base_list":
                    items = [x.strip() for x in
                             text(src, c).strip().lstrip(":").split(",")]
                    items = [x for x in items if x]
                    if items:
                        base = items[0]
                        ifaces = items[1:]
            if name is None:
                self.unhandled.append("nameless-type:" + text(src, node)[:60])
                return
            path = (ns + "." if ns else "") + "+".join(owners + [name])
            self.emit_type(path, "enum" if kw == "enum" else kw)
            rec = self.types[path]
            if kw == "enum":
                rec["ebase"] = base
            else:
                if base:
                    rec["base"] = base
            rec["ifaces"] = ifaces
            rec["garity"] = garity
            rec["static"] = static
            for c in node.children:
                if c.type in ("declaration_list", "enum_member_declaration_list"):
                    for d in c.children:
                        self.walk(src, d, ns, owners + [name])
            return
        if t == "delegate_declaration":
            name = None
            kids = node.children
            anchor = len(kids)
            for k in range(len(kids)):
                if kids[k].type == "parameter_list":
                    anchor = k
                    break
            for k in range(anchor - 1, -1, -1):
                if kids[k].type == "identifier":
                    name = text(src, kids[k]).strip()
                    break
            if name is None:
                self.unhandled.append("nameless-delegate")
                return
            path = (ns + "." if ns else "") + "+".join(owners + [name])
            self.emit_type(path, "delegate")
            return
        if t in ("method_declaration", "constructor_declaration",
                 "destructor_declaration", "operator_declaration",
                 "conversion_operator_declaration"):
            if not owners:
                self.unhandled.append("ownerless-member:" + text(src, node)[:60])
                return
            static = any(c.type == "modifier" and text(src, c).strip() == "static"
                         for c in node.children)
            garity = 0
            pname = None
            nargs = 0
            if t == "constructor_declaration":
                pname = ".ctor" if not static else ".cctor"
                for c in node.children:
                    if c.type == "parameter_list":
                        nargs = sum(1 for g in c.children
                                    if g.type == "parameter")
            elif t == "destructor_declaration":
                pname = "Finalize"
            elif t == "operator_declaration":
                op = None
                for c in node.children:
                    if c.type in ("+", "-", "*", "/", "%", "&", "|", "^", "!",
                                  "<<", ">>", "==", "!=", "<", ">", "<=", ">=",
                                  "~", "++", "--", "true", "false"):
                        op = text(src, c).strip()
                        break
                    if c.type == "operator":
                        pass
                pname = OP_TABLE.get(op or "", None)
                if pname is None:
                    self.unhandled.append("unknown-operator:" + text(src, node)[:80])
                    return
            elif t == "conversion_operator_declaration":
                key = "implicit"
                for c in node.children:
                    if c.type in ("implicit", "explicit"):
                        key = text(src, c).strip()
                        break
                pname = "op_Implicit" if key == "implicit" else "op_Explicit"
            else:
                pname = None
                kids = node.children
                anchor = len(kids)
                for k in range(len(kids)):
                    if kids[k].type in ("parameter_list", "type_parameter_list"):
                        anchor = k
                        break
                for k in range(anchor - 1, -1, -1):
                    c = kids[k]
                    if c.type == "identifier":
                        pname = text(src, c).strip()
                        if k > 0 and kids[k - 1].type == "explicit_interface_specifier":
                            spec = kids[k - 1]
                            parts = []

                            def _ids(n):
                                for g in n.children:
                                    if g.type == "type_argument_list":
                                        continue
                                    if g.type == "identifier":
                                        parts.append(text(src, g).strip())
                                    else:
                                        _ids(g)

                            _ids(spec)
                            q = ".".join(parts)
                            if q:
                                pname = q + "." + pname
                        break
                    if c.type in ("qualified_name", "dotted_name",
                                  "member_access_expression"):
                        pname = text(src, c).strip()
                        break
                if pname is None:
                    self.unhandled.append("nameless-method:" + text(src, node)[:80])
                    return
            for c in node.children:
                if c.type == "type_parameter_list":
                    garity = sum(1 for g in c.children
                                 if g.type == "type_parameter")
                if c.type == "parameter_list":
                    nargs = sum(1 for g in c.children if g.type == "parameter")
            path = (ns + "." if ns else "") + "+".join(owners)
            self.types.setdefault(path, {"kind": "?", "base": None,
                                         "ifaces": [], "members": []})
            self.types[path]["members"].append(
                ("M", pname, 1 if static else 0, garity, nargs))
            return
        if t == "enum_member_declaration":
            if not owners:
                self.unhandled.append("ownerless-enum-member")
                return
            name = None
            for c in node.children:
                if c.type == "identifier" and name is None:
                    name = text(src, c).strip()
            if name is None:
                self.unhandled.append("nameless-enum-member")
                return
            path = (ns + "." if ns else "") + "+".join(owners)
            self.types.setdefault(path, {"kind": "?", "base": None,
                                         "ifaces": [], "members": []})
            self.types[path]["members"].append(("F", name, 0, 0, 0))
            return
        if t == "field_declaration":
            if not owners:
                self.unhandled.append("ownerless-field")
                return
            static = any(c.type == "modifier" and text(src, c).strip() in ("static", "const")
                         for c in node.children)
            path = (ns + "." if ns else "") + "+".join(owners)
            self.types.setdefault(path, {"kind": "?", "base": None,
                                         "ifaces": [], "members": []})
            for c in node.children:
                if c.type == "variable_declaration":
                    for v in c.children:
                        if v.type == "variable_declarator":
                            for w in v.children:
                                if w.type == "identifier":
                                    self.types[path]["members"].append(
                                        ("F", text(src, w).strip(),
                                         1 if static else 0, 0, 0))
            return
        if t in ("property_declaration", "event_declaration",
                 "indexer_declaration", "accessor_list", "accessor_declaration"):
            self.skipped_props += 1
            return
        if t in ("declaration_list", "compilation_unit", "{", "}", ";",
                 "comment", "using_directive", "attribute_list", "attribute",
                 "nullable_directive", "pragma_directive", "region_directive",
                 "checked_statement", "block"):
            for c in node.children:
                self.walk(src, c, ns, owners)
            return
        if t in ("class", "struct", "interface", "enum", "namespace",
                 "identifier", "qualified_name", "modifier", "type_parameter",
                 "type_parameter_list", "parameter", "parameter_list",
                 "base_list", "block", "arrow_expression_clause",
                 "explicit_interface_specifier"):
            return
        self.unhandled.append(t + ":" + text(src, node)[:60])

    def lines(self, assembly):
        out = ["A " + assembly]
        for path in sorted(self.types):
            r = self.types[path]
            eb = r.get("ebase")
            out.append("T %s kind=%s base=%s ebase=%s ifaces=%s" % (
                path, r["kind"],
                re.sub(r"\s+", " ", r["base"]).strip() if r["base"] else "-",
                eb if eb else "-",
                ",".join(re.sub(r"\s+", " ", x).strip() for x in r["ifaces"])
                if r["ifaces"] else "-"))
            for kind, name, static, garity, nargs in sorted(r["members"]):
                out.append("%s %s.%s s=%d g=%d n=%d" % (
                    kind, path, name, static, garity, nargs))
        return out


def extract_tree(root, assembly):
    ex = Extractor()
    nfiles = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".cs"):
                continue
            if f == "__SharedBodyStubs.cs":
                continue
            p = os.path.join(dirpath, f)
            src = open(p, "rb").read()
            tree = ex.parser.parse(src)
            ex.walk(src, tree.root_node, "", [])
            nfiles += 1
    if ex.unhandled:
        raise SystemExit("unhandled declaration shapes:\n" +
                         "\n".join(ex.unhandled[:20]))
    return ex.lines(assembly), nfiles, ex.skipped_props


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--assembly", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    lines, nfiles, nskip = extract_tree(args.tree, args.assembly)
    text = "\n".join(lines) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print("extracted %d lines from %d files (%d props skipped)" %
          (len(lines), nfiles, nskip), file=sys.stderr)


if __name__ == "__main__":
    main()
