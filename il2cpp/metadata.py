from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import i32, u32

HEADER_TABLES = [
    # (name, struct_size or None)
    ('stringLiteral', 8), ('stringLiteralData', 1), ('string', 1),
    ('events', 24), ('properties', 20), ('methods', 32),
    ('parameterDefaultValues', 12), ('fieldDefaultValues', 12),
    ('fieldAndParameterDefaultValueData', 1), ('fieldMarshaledSizes', 8),
    ('parameters', 12), ('fields', 12), ('genericParameters', 12),
    ('genericParameterConstraints', 4),
    ('genericContainers', 16), ('nestedTypes', 4), ('interfaces', 4),
    ('vtableMethods', 4), ('interfaceOffsets', 8),
    ('typeDefinitions', None),  # version dependent
    ('images', 40), ('assemblies', None),
    ('fieldRefs', 8), ('referencedAssemblies', 4),
    ('attributeData', 1), ('attributeDataRange', 8),
    ('unresolvedVirtualCallParameterTypes', 4),
    ('unresolvedVirtualCallParameterRanges', 8),
    ('windowsRuntimeTypeNames', 8), ('windowsRuntimeStrings', 1),
    ('exportedTypeDefinitions', 4),
]
# tables present per metadata version (all >= 27.2 for our targets)
V_TABLES_MIN = {
    'genericParameterConstraints': 0,
    'fieldRefs': 19, 'referencedAssemblies': 20,
    'unresolvedVirtualCallParameterTypes': 22,
    'unresolvedVirtualCallParameterRanges': 22,
    'windowsRuntimeTypeNames': 23, 'windowsRuntimeStrings': 27,
    'exportedTypeDefinitions': 24,
    'attributeData': 29, 'attributeDataRange': 29,
}


@dataclass
class TypeDef:
    index: int
    name: str
    namespace: str
    byval: int
    declaring: int
    parent: int
    element: int
    generic_container: int
    flags: int
    field_start: int
    method_start: int
    event_start: int
    property_start: int
    nested_start: int
    interfaces_start: int
    vtable_start: int
    iface_offsets_start: int
    method_count: int
    property_count: int
    field_count: int
    event_count: int
    nested_count: int
    vtable_count: int
    interfaces_count: int
    iface_offsets_count: int
    bitfield: int
    token: int

    @property
    def is_valuetype(self): return bool(self.bitfield & 1)
    @property
    def is_enum(self): return bool(self.bitfield & 2)
    @property
    def has_cctor(self): return bool(self.bitfield & 8)


@dataclass
class MethodDef:
    index: int
    name: str
    declaring: int
    return_type: int
    parameter_start: int
    generic_container: int
    token: int
    flags: int
    iflags: int
    slot: int
    param_count: int
    image: int = -1
    addr: int = 0

    @property
    def is_static(self): return bool(self.flags & 0x10)
    @property
    def rid(self): return self.token & 0xFFFFFF


@dataclass
class FieldDef:
    name: str
    type: int
    token: int


@dataclass
class ParamDef:
    name: str
    token: int
    type: int


@dataclass
class ImageDef:
    name: str
    assembly_index: int
    type_start: int
    type_count: int
    entry_point: int
    token: int


class Metadata:
    def __init__(self, path: str):
        self.path = path
        self.d = open(path, 'rb').read()
        self.version = i32(self.d, 4)
        if u32(self.d, 0) != 0xFAB11BAF:
            raise ValueError('not a global-metadata.dat file: %s' % path)
        if not (24 <= self.version <= 31):
            raise ValueError('unsupported metadata version %d' % self.version)
        self.v31 = self.version >= 31
        self._parse_header()
        self._parse_tables()

    # -- header -------------------------------------------------------------
    def _parse_header(self):
        d = self.d
        self.hdr = {}
        self.hdr['sanity'] = u32(d, 0)
        self.hdr['version'] = i32(d, 4)
        off = 8
        for name, _ in HEADER_TABLES:
            lo = V_TABLES_MIN.get(name, 0)
            if self.version < lo:
                continue
            self.hdr[name + 'Offset'] = i32(d, off)
            self.hdr[name + 'Size'] = i32(d, off + 4)
            off += 8
        self.header_ints = off // 4

    def toff(self, table): return self.hdr[table + 'Offset']
    def tsize(self, table): return self.hdr[table + 'Size']

    # -- tables ---------------------------------------------------------------
    def _parse_tables(self):
        d, h = self.d, self.hdr
        self.string_off = h['stringOffset']
        self.string_size = h['stringSize']
        self._str_cache: Dict[int, str] = {}

        # string literals
        so, sc = h['stringLiteralOffset'], h['stringLiteralSize']
        self.string_literals: List[Tuple[int, int]] = [
            (u32(d, so + i * 8), u32(d, so + i * 8 + 4)) for i in range(sc // 8)]

        # images
        io, ic = h['imagesOffset'], h['imagesSize']
        self.images: List[ImageDef] = []
        for i in range(ic // 40):
            b = io + i * 40
            self.images.append(ImageDef(
                self.getstr(u32(d, b)), i32(d, b + 4), i32(d, b + 8),
                u32(d, b + 12), i32(d, b + 24), u32(d, b + 28)))

        # type definitions: v31 adds nothing to typedef; stride 88 for >=24.2
        tdo, tdc = h['typeDefinitionsOffset'], h['typeDefinitionsSize']
        stride = 88 if self.version >= 24.2 else 84
        n = tdc // stride
        self.typedefs: List[TypeDef] = []
        for i in range(n):
            b = tdo + i * stride
            f = struct.unpack_from('<16i', d, b)
            counts = struct.unpack_from('<8H', d, b + 64)
            self.typedefs.append(TypeDef(
                i, self.getstr(f[0]), self.getstr(f[1]), f[2], f[3], f[4], f[5],
                f[6], u32(d, b + 28), f[8], f[9], f[10], f[11], f[12], f[13],
                f[14], f[15], counts[0], counts[1], counts[2], counts[3],
                counts[4], counts[5], counts[6], counts[7],
                u32(d, b + 80), u32(d, b + 84)))

        # methods: v31 adds returnParameterToken
        mo, mc = h['methodsOffset'], h['methodsSize']
        mstride = 36 if self.v31 else 32
        nm = mc // mstride
        self.methods: List[MethodDef] = []
        for i in range(nm):
            b = mo + i * mstride
            if self.v31:
                nameI, decl, rtok, _rp, pstart, gci, token = struct.unpack_from('<7i', d, b)
                tail = struct.unpack_from('<4H', d, b + 28)
            else:
                nameI, decl, rt, pstart, gci, token = struct.unpack_from('<6i', d, b)
                tail = struct.unpack_from('<4H', d, b + 24)
            self.methods.append(MethodDef(
                i, self.getstr(nameI), decl, rtok, pstart, gci,
                u32(d, b + 24 if self.v31 else b + 20), tail[0], tail[1], tail[2], tail[3]))

        # parameters / fields / properties / events
        po, pc = h['parametersOffset'], h['parametersSize']
        self.params: List[ParamDef] = [
            ParamDef(self.getstr(u32(d, po + i * 12)), u32(d, po + i * 12 + 4), i32(d, po + i * 12 + 8))
            for i in range(pc // 12)]
        fo, fc = h['fieldsOffset'], h['fieldsSize']
        self.fields: List[FieldDef] = [
            FieldDef(self.getstr(u32(d, fo + i * 12)), i32(d, fo + i * 12 + 4), u32(d, fo + i * 12 + 8))
            for i in range(fc // 12)]
        pro, prc = h['propertiesOffset'], h['propertiesSize']
        self.properties = [struct.unpack_from('<5i', d, pro + i * 20) for i in range(prc // 20)]
        eo, ec = h['eventsOffset'], h['eventsSize']
        self.events = [struct.unpack_from('<6i', d, eo + i * 24) for i in range(ec // 24)]

        # generic containers / parameters
        gco, gcc = h['genericContainersOffset'], h['genericContainersSize']
        self.generic_containers = [struct.unpack_from('<4i', d, gco + i * 16) for i in range(gcc // 16)]
        gpo, gpc = h['genericParametersOffset'], h['genericParametersSize']
        gp_stride = 16 if self.version >= 24.2 else 12
        self.generic_parameters = []
        for i in range(gpc // gp_stride):
            b = gpo + i * gp_stride
            owner = i32(d, b)
            name = self.getstr(u32(d, b + 4))
            if gp_stride == 16:
                cs, cc, num, flags = struct.unpack_from('<hhHH', d, b + 8)
            else:
                cs, cc, num, flags = struct.unpack_from('<iiHH', d, b + 8)
            self.generic_parameters.append((owner, name, cs, cc, num, flags))

        # misc index tables
        nto, ntc = h['nestedTypesOffset'], h['nestedTypesSize']
        self.nested_types = [i32(d, nto + i * 4) for i in range(ntc // 4)]
        ifo, ifc = h['interfacesOffset'], h['interfacesSize']
        self.interfaces = [i32(d, ifo + i * 4) for i in range(ifc // 4)]
        vto, vtc = h['vtableMethodsOffset'], h['vtableMethodsSize']
        self.vtable_methods = [u32(d, vto + i * 4) for i in range(vtc // 4)]

        # default values
        fdvo, fdvc = h['fieldDefaultValuesOffset'], h['fieldDefaultValuesSize']
        self.field_default_values = {
            i32(d, fdvo + i * 12): (i32(d, fdvo + i * 12 + 4), i32(d, fdvo + i * 12 + 8))
            for i in range(fdvc // 12)}
        pdvo, pdvc = h['parameterDefaultValuesOffset'], h['parameterDefaultValuesSize']
        self.param_default_values = {
            i32(d, pdvo + i * 12): (i32(d, pdvo + i * 12 + 4), i32(d, pdvo + i * 12 + 8))
            for i in range(pdvc // 12)}
        self.dv_off = h['fieldAndParameterDefaultValueDataOffset']

        # per-type method/field lookup accelerators
        self.methods_by_type: Dict[int, List[int]] = {}
        for i, m in enumerate(self.methods):
            if m.declaring >= 0:
                self.methods_by_type.setdefault(m.declaring, []).append(i)

    def getstr(self, idx: int) -> str:
        if idx in self._str_cache:
            return self._str_cache[idx]
        if not (0 <= idx < self.string_size):
            return ''
        e = self.d.index(b'\x00', self.string_off + idx)
        s = self.d[self.string_off + idx:e].decode('utf-8', 'replace')
        self._str_cache[idx] = s
        return s

    def string_literal(self, idx: int) -> str:
        ln, do = self.string_literals[idx]
        return self.d[self.hdr['stringLiteralDataOffset'] + do:
                      self.hdr['stringLiteralDataOffset'] + do + ln].decode('utf-8', 'replace')

    def method_params(self, m: MethodDef) -> List[ParamDef]:
        return self.params[m.parameter_start:m.parameter_start + m.param_count]

    def type_fields(self, t: TypeDef) -> List[int]:
        return list(range(t.field_start, t.field_start + t.field_count))

    def type_methods(self, t: TypeDef) -> List[int]:
        return list(range(t.method_start, t.method_start + t.method_count))


# ----------------------------------------------------------------------------
# executable binaries
# ----------------------------------------------------------------------------
