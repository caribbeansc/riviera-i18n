# SPEC-001: `data*.bin` containers and `.pck` packages

The game keeps its files in a few containers (`data.bin`, `data_en.bin`, ...). They use the same format on Switch, Android and
PC. Inside them, pictures are grouped in `.pck` packages.

```
container   u32 header_size, u32 data_size, header (obfuscated  u32 size + zlib(index)), file data
index       u32 names_off, u32 names_size, 12-byte entries (name_off, info, value), names
            info bit 31: a directory of (info & 0x3fffffff) children whose first one is `value` bytes into the entries
            otherwise: a file of (info & 0x3fffffff) bytes at 8 + header_size + value; bit 30: wrapped as u32 size + zlib
package     u32 count, u32 start of data, count x (64-byte name, u32 size, u32 offset), data
```

## Requirements

- **R-1** A file is obfuscated by XOR with 32-bit words of `MD5(rot13(name))`, word *i* using key word `i & 3`; the index uses the
  name `InfoData`. The operation is its own inverse, and the key depends on the file name.
- **R-2** `Archive` lists every path of a container and reads each file, whether it is stored plain or wrapped in zlib.
- **R-3** `pack` replaces only the files it is given. Every other file is copied byte for byte, still obfuscated, and the result
  is again a valid container. It returns how many files it replaced.
- **R-4** The replacements of `pack` may be a mapping `{path: bytes}`, a folder, or a list of folders (the first one that has a file
  wins), with paths laid out like the container (`data/event/e_00.pck`).
- **R-5** `extract` writes the tree of a container (or the files a filter accepts) under a folder.
- **R-6** The container header declares its sizes: `8 + header_size + data_size` is the length of the file.
- **R-7** `read_pck` and `write_pck` are inverse; an entry may change size, because the engine draws every picture at its own size.
  A package whose entry table does not fit its start of data is refused.
- **R-8** `write_pck(..., align=4)` pads every entry to a multiple of 4 and the result still reads back (the Android build wants it).
