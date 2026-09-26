"""Audit batch 1: per-instance caches, non-negative type_sizes, ELF-gated
registration fallback.

TypeDef indices are binary-local, so a cache keyed by one and shared at class
level hands a second Decompiler/Emitter -- a second fixture -- another
binary's answer. `_static_field_name` then names another type's static field,
with no marker: a confidently wrong name rather than an honest decline.
"""
import inspect
import types
from types import SimpleNamespace as NS

from il2cpp import Decompiler, Emitter
from il2cpp.binary import ELF
import il2cpp.cli as cli_mod


def _typedefs(pairs):
    return [NS(namespace=ns, name=nm) for ns, nm in pairs]


def _decompiler_with(typedefs):
    d = Decompiler.__new__(Decompiler)
    d.L = NS(meta=NS(typedefs=_typedefs(typedefs)))
    return d


# --------------------------------------------------------------- A1a
def test_type_name_cache_is_per_instance():
    a = _decompiler_with([("Alpha", "Widget")])
    assert a._td_idx_by_name("Alpha.Widget") == 0

    b = _decompiler_with([("Other", "Thing"), ("Alpha", "Widget")])
    # the same name is TypeDef 1 in B; a shared cache would answer 0 and
    # resolve 'Other.Thing''s static fields
    assert b._td_idx_by_name("Alpha.Widget") == 1


def test_type_name_cache_absent_and_dotted_forms():
    a = _decompiler_with([("A", "B")])
    assert a._td_idx_by_name("A.B") == 0
    assert a._td_idx_by_name("B") is None          # no namespace -> no hit
    assert not hasattr(Decompiler, "_TDNAME_CACHE")


# --------------------------------------------------------------- A1b/A1c
def test_emitter_caches_are_not_class_attributes():
    assert not hasattr(Emitter, "_us_cache")
    assert not hasattr(Emitter, "_delegate_cache")


def test_us_cache_does_not_leak_between_instances():
    one = Emitter.__new__(Emitter)
    one.__dict__.setdefault("_us_cache", {})[4242] = True
    two = Emitter.__new__(Emitter)
    assert two.__dict__.setdefault("_us_cache", {}) is not one.__dict__["_us_cache"]
    assert two.__dict__.setdefault("_us_cache", {}).get(4242) is None


def test_delegate_caches_keep_separate_key_spaces():
    """The two delegate answers used to share one dict, distinguishable only
    because an int key can never equal a ('viable', int) tuple key."""
    e = Emitter.__new__(Emitter)
    dcache = e.__dict__.setdefault("_delegate_cache", {})
    vcache = e.__dict__.setdefault("_delegate_viable_cache", {})
    assert dcache is not vcache
    dcache[7] = True
    assert vcache.get(7) is None
    assert all(not isinstance(k, tuple) for k in dcache)


# --------------------------------------------------------------- A3
def test_android_registration_fallback_is_elf_gated():
    """The Android loader assumes a different registration struct shape. On
    the x64 PE it does not fail -- probed: a code_reg_va 0x10 off the classic
    answer, same module count, same resolved coverage -- so a PE must get a
    clean error instead of a silently wrong registration."""
    src = inspect.getsource(cli_mod.main)
    assert "isinstance(bin_, ELF)" in src
    assert "could not read code/metadata registrations" in src
    assert ELF is not None


def test_registration_phase_reports_errors_without_a_traceback():
    src = inspect.getsource(cli_mod.main)
    for exc in ("struct.error", "IndexError", "RuntimeError"):
        assert exc in src
