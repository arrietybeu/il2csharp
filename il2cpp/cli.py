from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.arm64 import is_arm64_binary
from il2cpp.binary import ELF, load_binary
from il2cpp.emitter import Emitter
from il2cpp.headers import HeaderEmitter
from il2cpp.metadata import Metadata
from il2cpp.runtime.core import Il2Cpp

def find_game_files(path=None, *, metadata=None, binary=None):
    """Discover one unambiguous pair; explicit files always take priority.

    Directory targets are a boundary: never pair them with a parent game's
    binary. Direct metadata files may use the standard Unity ancestor layout.
    Discovery reads directories only and never executes the native binary.
    """
    def explicit(value, label):
        if value is None:
            return None
        value = os.path.abspath(os.fspath(value))
        if not os.path.isfile(value):
            raise ValueError('%s file does not exist: %s' % (label, value))
        return value

    def pick(paths, label, flag):
        paths = sorted(set(paths))
        if len(paths) > 1:
            raise ValueError('multiple %s files found; select one with %s: %s' % (
                label, flag, ', '.join(paths)))
        return paths[0] if paths else None

    def scan(root, names):
        found = []
        for directory, dirs, files in os.walk(root):
            dirs.sort()
            for name in sorted(files):
                if name.casefold() in names:
                    found.append(os.path.join(directory, name))
        return found

    gmd, bp = explicit(metadata, 'metadata'), explicit(binary, 'binary')
    root = None
    if path is not None:
        target = os.path.abspath(os.fspath(path))
        if os.path.isdir(target):
            root = target
        elif os.path.isfile(target):
            if os.path.basename(target).casefold() == 'global-metadata.dat' or target == gmd:
                gmd = gmd or target
            else:
                bp = bp or target
        elif not (gmd or bp):
            return None, None
    if gmd and bp:
        return gmd, bp
    if root is None:
        root = os.path.dirname(bp or gmd) if bp or gmd else None
        if root and gmd and not bp:
            # .../<Game>_Data/il2cpp_data/Metadata/global-metadata.dat
            parent = os.path.dirname(root)
            data_dir = os.path.dirname(parent)
            if os.path.basename(root).casefold() == 'metadata' and \
                    os.path.basename(parent).casefold() == 'il2cpp_data' and \
                    os.path.basename(data_dir).casefold().endswith('_data'):
                root = os.path.dirname(data_dir)
    if root is None:
        return gmd, bp
    if gmd is None:
        gmd = pick(scan(root, {'global-metadata.dat'}), 'metadata', '--metadata')
    if bp is None:
        bp = pick(scan(root, {'gameassembly.dll', 'libil2cpp.so'}), 'binary', '--binary')
    return gmd, bp


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog='il2csharp',
        description='IL2CPP -> C# recovery with real (lifted) method bodies.')
    ap.add_argument('target', nargs='?', help='game dir, metadata file, or binary file')
    ap.add_argument('--metadata', help='explicit global-metadata.dat path (renamed files supported)')
    ap.add_argument('--binary', help='explicit GameAssembly.dll / libil2cpp.so path')
    ap.add_argument('-o', '--out', default='il2csharp_out', help='output directory')
    ap.add_argument('--only', default=None, help='comma-separated assembly name filters (substring match)')
    ap.add_argument('--types', default=None, help='case-insensitive full type-name substring; nested matches retain the owner file')
    ap.add_argument('--strict', action='store_true', help='return nonzero on body-lifting fallback or missing backend')
    ap.add_argument('--decls-only', action='store_true', help='skip method body lifting')
    ap.add_argument('--asm', action='store_true', help='include native asm comments in bodies')
    ap.add_argument('--max-methods', type=int, default=None, help='cap lifted bodies (debug)')
    ap.add_argument('--probe', action='store_true', help='diagnostics only')
    ap.add_argument('--emit-h', action='store_true',
                    help='also emit an il2cpp.h-style C header (Il2CppDumper format)')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args(argv[1:])

    if args.max_methods is not None and args.max_methods < 0:
        ap.error('--max-methods must be nonnegative')
    if not args.target and not (args.metadata and args.binary):
        ap.error('provide a target or both --metadata and --binary')
    try:
        gmd, bp = find_game_files(args.target, metadata=args.metadata, binary=args.binary)
    except (OSError, ValueError) as ex:
        print('error:', ex)
        return 1
    if not gmd:
        print('error: could not locate global-metadata.dat under', args.target)
        return 1
    print('metadata:', gmd)
    print('binary  :', bp)
    try:
        meta = Metadata(gmd)
    except (OSError, ValueError, struct.error) as ex:
        print('error: could not read metadata:', ex)
        return 1
    print('metadata v%d | %d types | %d methods | %d images | %d string literals' % (
        meta.version, len(meta.typedefs), len(meta.methods), len(meta.images),
        len(meta.string_literals)))
    if not bp:
        print('error: no binary found (need GameAssembly.dll / libil2cpp.so)')
        return 1
    try:
        bin_ = load_binary(bp)
    except (OSError, ValueError, struct.error) as ex:
        print('error: could not read binary:', ex)
        return 1
    if bin_ is None:
        print('error: unsupported binary format')
        return 1
    print('binary loaded: %d sections, %d exports%s' % (len(bin_.sections), len(bin_.exports), (' | relocs: %d' % bin_.reloc_applied) if getattr(bin_, 'reloc_applied', 0) else ''))
    il = Il2Cpp(meta, bin_)
    il.verbose = args.verbose
    t0 = time_ms()
    try:
        il.assign_images()
        try:
            il.find_registrations()
        except RuntimeError:
            # The Android loader assumes a different registration struct
            # shape. Probed on the x64 PE it does not fail: it lands on a
            # code_reg_va 0x10 off the classic answer with the same module
            # count and the same resolved method coverage, so trying it on
            # a PE trades a clean error for a silently wrong registration.
            if not isinstance(bin_, ELF):
                raise
            il.find_registrations_android()
        il.load_function_bounds()
        il.resolve_method_addrs()
    except (OSError, ValueError, IndexError, KeyError, struct.error,
            RuntimeError) as ex:
        print('error: could not read code/metadata registrations:', ex)
        return 1
    il._mod_ptr_cache.clear()  # free raw pointer arrays
    n_addr = sum(1 for m in meta.methods if m.addr)
    print('registrations ok | %d/%d methods have native code | %d ms' % (
        n_addr, len(meta.methods), time_ms() - t0))

    if args.probe:
        for name, mod in sorted(il.modules.items()):
            print('  %-50s methods=%d' % (name, mod.method_pointer_count))
        return 0

    if not args.decls_only:
        if is_arm64_binary(bin_) and not HAVE_CAPSTONE:
            print('warning: Capstone not installed; ARM64 bodies disabled (pip install capstone)')
        elif not is_arm64_binary(bin_) and not HAVE_ICED:
            print('warning: iced-x86 not installed; x64 bodies disabled (pip install iced-x86)')

    os.makedirs(args.out, exist_ok=True)
    if args.emit_h:
        t0 = time_ms()
        hpath = os.path.join(args.out, 'il2cpp.h')
        n_types = HeaderEmitter(il, hpath).write()
        print('il2cpp.h: %d types in %d ms -> %s' % (n_types, time_ms() - t0, hpath))
    em = Emitter(il, args.out, asm_comments=args.asm, with_bodies=not args.decls_only,
                 max_methods=args.max_methods, verbose=args.verbose, type_filter=args.types)

    only = [t.strip().lower() for t in args.only.split(',')] if args.only else None
    t0 = time_ms()
    total_files = 0
    for img in meta.images:
        if only and not any(t in img.name.lower() for t in only):
            continue
        n = em.write_assembly_split(img)
        total_files += n
        print('  %-52s %5d types  (%d bodies, %d failed)' % (
            img.name, n, em.lifted, em.failed))
    em.write_script_json(os.path.join(args.out, 'script.json'))
    em.write_string_literals(os.path.join(args.out, 'stringliteral.json'))
    print('done: %d type files in %d ms | bodies lifted: %d, failed: %d | '
          'structured fallbacks: %d, type emit failures: %d' % (
        total_files, time_ms() - t0, em.lifted, em.failed, em.fallbacks, em.emit_failed))
    failed = bool(em.failed or em.emit_failed)
    if args.strict and not args.decls_only:
        failed = failed or bool(em.fallbacks) or em.lifter is None
    return 1 if failed else 0


def time_ms():
    import time
    return int(time.time() * 1000)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
