# SPEC-002: The script in the executable, and the IPS patch

The script is one table of relocated pointers to UTF-8 strings in the NSO `main`; see [PIPELINE.md](../PIPELINE.md).

## Requirements

- **R-1** `lz4_block` decodes a raw LZ4 block, including literals, matches and **overlapping** matches (offset smaller than the
  length), and checks the decoded size.
- **R-2** `load_nso` returns the decompressed image (with its 0x100-byte header) and the build id, and refuses a file that is not an
  NSO.
- **R-3** The text table and its blocks are found **by content**, with no fixed addresses: the longest run of consecutive pointers
  to valid UTF-8 is the table; descriptors outside it say where each block starts, with or without a header of four empty strings.
- **R-4** The rows line up across languages: the English, Japanese, Korean and Chinese row *k* of a block are the same sentence.
- **R-5** The slot of a row is a relocated pointer: it has a RELA entry whose addend is the address of its string.
- **R-6** A string splits into segments: every ASCII comma and every `V(id)` opens one, and joining separator + prefix + text gives
  the string back. A `cN` colour tag is a prefix.
- **R-7** `disp` makes a string readable: full-width to ASCII, no line breaks.
- **R-8** `wanted` says which rows are narrative (dialogue, narration, descriptions, choices; items only if they are descriptions),
  and the groups of blocks cover all 41.
- **R-9** `encode` follows the engine's conventions: the ASCII comma of the text goes full-width (the ASCII one separates
  segments), `…` becomes `＿`, quotes and apostrophes become the curly ones, a `%` that is not a format of the engine goes full-width,
  because the engine runs printf on every string.
- **R-10** `Writes` refuses overlapping writes. `to_ips` merges writes that are close, never emits the offset `0x454F46` (it spells
  `EOF`), and `apply_ips` of the result gives the same image as applying the writes; something that is not IPS is refused.
- **R-11** `place` rewrites a string in place when the new one fits and nobody else uses those bytes (freeing the tail), moves it
  into free memory and updates its relocation when it does not, and reports the strings that have no room.
- **R-12** A string that the code uses directly (found by scanning for `adrp` + `add`/`ldr`) is never overwritten or reused as free
  space, even when a row of the table has the same bytes.
