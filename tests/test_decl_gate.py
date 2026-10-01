"""Portable unit tests for the declaration gate (no fixture needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from diff_decls import (
    _mkey,
    _strip_genargs,
    _top_commas,
    canon_member,
    canon_owner,
    canon_short,
    diff_dump_extracted,
)


def test_canon_owner_plain():
    assert canon_owner("System.String") == "System.String"
    assert canon_owner("NS.Outer+Inner") == "NS.Outer.Inner"


def test_canon_owner_generated():
    assert canon_owner("NS.Outer+<Foo>d__13") == "NS.Outer._Foo_d__13"
    assert canon_owner("A.<>c") == "A.__c"


def test_canon_member_plain():
    assert canon_member("Add") == "Add"
    assert canon_member(".ctor") == ".ctor"
    assert canon_member("event") == "event_"


def test_canon_member_explicit():
    assert canon_member("System.IDisposable.Dispose") == \
        "System.IDisposable.Dispose"
    assert canon_member("<.cctor>b__271_0") == "__cctor_b__271_0"


def test_canon_short():
    assert canon_short("System.IntPtr") == "IntPtr"
    assert canon_short("global::System.String") == "String"
    assert canon_short("System.Collections.Generic.List<T>") == "List"
    assert canon_short("ICollection_1") == "ICollection"
    assert canon_short("-") is None


def test_top_commas():
    assert _top_commas("a,b") == ["a", "b"]
    assert _top_commas("Dictionary<K,V>,int") == ["Dictionary<K,V>", "int"]
    assert _top_commas("A<B<C,D>,E>,F") == ["A<B<C,D>,E>", "F"]
    assert _top_commas("") == [""]


def test_strip_genargs():
    assert _strip_genargs("List<T>") == "List"
    assert _strip_genargs("A<B<C>>") == "A"
    assert _strip_genargs("plain") == "plain"


def test_mkey_orders_none_first():
    a = ("M", "Foo", None, 0, 0, 1)
    b = ("M", "Foo", "Bar", 0, 0, 1)
    assert sorted([b, a], key=_mkey)[0] == a


DUMP_BASE = [
    "A mscorlib.dll",
    "T System.Widget kind=class base=- ebase=- ifaces=System.IDisposable",
    "M System.Widget..ctor s=0 g=0 f=0x1886 ()->void",
    "M System.Widget.Dispose s=0 g=0 f=0x1c6 ()->void",
    "F System.Widget._count int",
]


def test_diff_clean():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=IDisposable",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Dispose s=0 g=0 n=0",
        "F System.Widget._count s=0 g=0 n=0",
    ]
    assert diff_dump_extracted(DUMP_BASE, ext) == []


def test_diff_missing_extra():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=-",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Bogus s=1 g=0 n=2",
    ]
    probs = diff_dump_extracted(DUMP_BASE, ext)
    assert any("base mismatch" in p for p in probs)
    assert any("missing emitted member" in p and "Dispose" in p for p in probs)
    assert any("extra emitted member" in p and "Bogus" in p for p in probs)


def test_diff_ifaces_rest():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=System.IDisposable,System.ICloneable",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Dispose s=0 g=0 n=0",
        "F System.Widget._count s=0 g=0 n=0",
    ]
    probs = diff_dump_extracted(DUMP_BASE, ext)
    assert any("ifaces mismatch" in p for p in probs)
    assert not any("missing emitted member" in p for p in probs)
    assert not any("extra emitted member" in p for p in probs)


def test_diff_qualifier_compatible():
    dump = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.IDisposable.Dispose s=0 g=0 f=0x1c6 ()->void",
    ]
    ext = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.Dispose s=0 g=0 n=0",
    ]
    assert diff_dump_extracted(dump, ext) == []


def test_diff_qualifier_mismatch():
    dump = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.IDisposable.Dispose s=0 g=0 f=0x1c6 ()->void",
    ]
    ext = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.ICloneable.Dispose s=0 g=0 n=0",
    ]
    probs = diff_dump_extracted(dump, ext)
    assert any("qualifier mismatch" in p for p in probs)


def test_diff_kind_base_ebase():
    dump = [
        "A m.dll",
        "T N.E kind=enum base=- ebase=uint ifaces=-",
    ]
    ext_ok = [
        "A m.dll",
        "T N.E kind=enum base=- ebase=uint ifaces=-",
    ]
    assert diff_dump_extracted(dump, ext_ok) == []
    ext_bad = [
        "A m.dll",
        "T N.E kind=class base=- ebase=- ifaces=-",
    ]
    probs = diff_dump_extracted(dump, ext_bad)
    assert any("kind mismatch" in p for p in probs)
    assert any("ebase mismatch" in p for p in probs)
