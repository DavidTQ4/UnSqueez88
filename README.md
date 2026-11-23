# unsqz88 — Squeez88 (.ZSQ) unsqueezer for Cambridge Z88 files

`unsqz88.py` decompresses files made with the Z88 **Squeez88** utility and,
on request, turns Z88 BBC BASIC programs into readable text listings. It needs only
Python 3.6 or later and its standard library, with nothing to install.

## Quick start

```
python3 unsqz88.py APP1.ZSQ
```

Output:

```
APP1.ZSQ: APP1, 7047 bytes, BBC BASIC program, checksum OK
    wrote ./APP1
```

`APP1` is the original file, byte for byte. For a BBC BASIC program that
means tokenised BASIC that the Z88 (or an emulator such as OZvm) can `LOAD`
directly. By default the tool does straight decompression only.

To also get a plain-text listing of BBC BASIC programs, add `-l`/`--list`:

```
python3 unsqz88.py --list APP1.ZSQ
```

```
APP1.ZSQ: APP1, 7047 bytes, BBC BASIC program, checksum OK
    wrote ./APP1
    wrote ./APP1.txt (286 lines)
```

`APP1.txt` is a `LIST` of the program for reading or editing on a PC.

The output filename comes from the original name stored inside the
squeezed file, not from the `.ZSQ` filename.

## Usage

```
python3 unsqz88.py [options] FILE [FILE ...]
```

| Option | Meaning |
|---|---|
| `-o DIR`, `--outdir DIR` | Write output into `DIR` (created if needed). Default: current directory. |
| `-i`, `--info` | Check only: report name, size, type and checksum; write nothing. |
| `-f`, `--force` | Write the output even if the checksum does not match. |
| `-l`, `--list` | Also write a plain-text `.txt` listing for each BBC BASIC program. Off by default. |
| `--overwrite` | Replace existing output files. Otherwise a clash gets `.1`, `.2` … added. |
| `--escape-high` | With `--list`, show bytes ≥ 0x80 inside strings as `\xNN` instead of Latin-1 characters. |
| `-V`, `--version` | Print the version. |
| `-h`, `--help` | Show help. |

Examples:

```
# Everything in a folder, results into ./restored
python3 unsqz88.py -o restored *.ZSQ

# Same, plus readable listings of any BBC BASIC programs
python3 unsqz88.py --list -o restored *.ZSQ

# Just check a batch of transfers are sound
python3 unsqz88.py --info *.ZSQ

# Windows
py unsqz88.py -o restored APP1.ZSQ clishell.ZSQ
```

The exit status is `0` if every file decoded with a matching checksum and
`1` otherwise, so the script can be used in batch jobs.

## Checksums: how you know it's right

Every squeezed file stores a 16-bit checksum of the original data. The tool
recomputes it after decompressing:

* **`checksum OK`**: the output is a byte-exact copy of the original.
* **`CHECKSUM MISMATCH`**: the squeezed file is damaged. Nothing is written
  unless you add `--force`.

Non-BASIC files (text, data, other squeezed content) are unsqueezed in the
same way; only BBC BASIC programs get a listing, and only with `--list`.

## Transferring files from the Z88

Squeezed files are **binary**. When copying them off the Z88 with EazyLink /
PC-Link over serial:

* turn **character translation** (ISO ↔ IBM) **off**, and
* turn **CR/LF conversion** (line-ending translation) **off**.

With either setting on, the files are silently altered and won't decode.
The tool recognises the symptoms and reports them, for example:

```
APP1.ZSQ: ERROR: not a squeezed file (magic 76 98) - the magic bytes are
76 98 instead of 76 FF, which is the signature of an ISO->IBM
character-translated transfer (re-transfer in binary mode)
    possible transfer damage: magic byte 0xFF has become 0x98 ...
    possible transfer damage: every CR is followed by LF ...
```

A good squeezed file always starts with the bytes `76 FF`. If you see
`76 98`, re-transfer in binary mode. (Damaged files *can* sometimes be
reconstructed, but it's slow, specialised work. A clean transfer is far
better.)

## About the listings

Listings are only written when you pass `-l`/`--list`. The format follows the Z88's own `LIST` output:

* BBC BASIC keywords are expanded from their one-byte tokens.
* Line numbers after `GOTO`, `GOSUB`, `THEN`, `ELSE` and `RESTORE` are
  decoded from their packed form.
* Text after `REM` and `DATA`, and inside strings, is shown as stored.
* Control characters are shown as `\xNN`.

The listing is for reading only. To put a program back on the Z88, use the
unsqueezed binary file, not the `.txt`.

## The format, briefly

For anyone maintaining this later:

```
offset  size  content
0       2     magic 76 FF
2       2     checksum (16-bit sum of original bytes, little-endian)
4       n     original filename, NUL-terminated
..      2     number of Huffman tree nodes N
..      4*N   nodes: two signed 16-bit children each;
              >= 0 is another node, < 0 is a leaf for symbol -(value+1)
..      ...   Huffman bit stream, least-significant bit first
```

Decoded symbols 0–255 are bytes and 256 marks end of file. Byte `0x90` is a
run-length escape: `90 00` means a literal `0x90`, and `90 nn` means repeat
the previous byte until it has appeared `nn` times in total. This is the
CP/M "SQ" format that Squeez88 uses.

BBC BASIC (Z80) programs are stored as lines of
`[length][line-number lo][hi][tokenised text][0D]` and end with `00 FF FF`.
