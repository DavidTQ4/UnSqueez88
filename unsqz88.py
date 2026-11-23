#!/usr/bin/env python3
"""
unsqz88.py - unsqueeze Cambridge Z88 "Squeez88" (.ZSQ) files and list
Z88 BBC BASIC programs.

Squeez88 uses the classic CP/M "SQ" format (Huffman coding over a
run-length layer). This tool:

  * decompresses one or more squeezed files,
  * verifies each result against the checksum stored in the file,
  * names the output after the original filename stored inside,
  * with --list, also writes a plain-text LISTing of BBC BASIC programs,
  * detects files damaged by a text-mode transfer (EazyLink / PC-Link
    ISO->IBM character translation and CR->CRLF conversion) and says so.

Python 3.6+ standard library only.  Run with -h for usage.
"""
import argparse
import os
import sys

__version__ = "1.1"

SQ_MAGIC = 0x76, 0xFF
DLE = 0x90          # run-length escape byte in the SQ format
EOF_SYMBOL = 256    # Huffman end-of-stream symbol


class SqueezeError(Exception):
    pass


# --------------------------------------------------------------------------
# Decompression
# --------------------------------------------------------------------------

def parse_header(data):
    """Return (stored_checksum, original_name, tree, offset_of_bitstream)."""
    if len(data) < 7:
        raise SqueezeError("file too short to be a squeezed file")
    if (data[0], data[1]) != SQ_MAGIC:
        hint = ""
        if data[0] == 0x76 and data[1] == 0x98:
            hint = (" - the magic bytes are 76 98 instead of 76 FF, which is the "
                    "signature of an ISO->IBM character-translated transfer "
                    "(re-transfer in binary mode)")
        raise SqueezeError("not a squeezed file (magic %02X %02X)%s"
                           % (data[0], data[1], hint))
    checksum = data[2] | data[3] << 8
    try:
        end = data.index(0, 4)
    except ValueError:
        raise SqueezeError("no terminator after the stored filename")
    name = data[4:end].decode("latin-1")
    p = end + 1
    count = data[p] | data[p + 1] << 8
    p += 2
    if count > 257 or p + 4 * count > len(data):
        raise SqueezeError("corrupt Huffman tree header (%d nodes)" % count)

    def s16(i):
        v = data[i] | data[i + 1] << 8
        return v - 0x10000 if v & 0x8000 else v

    tree = [(s16(p + 4 * i), s16(p + 4 * i + 2)) for i in range(count)]
    for a, b in tree:
        for child in (a, b):
            if child >= count or child < -(EOF_SYMBOL + 1):
                raise SqueezeError("corrupt Huffman tree (bad node %d)" % child)
    return checksum, name, tree, p + 4 * count


def unsqueeze(data):
    """Decompress squeezed bytes. Returns (name, stored_checksum, output)."""
    checksum, name, tree, p = parse_header(data)
    out = bytearray()
    node = 0
    in_run = False
    prev = None
    if not tree:                       # empty original file
        return name, checksum, bytes(out)
    for byte in data[p:]:
        for bit in range(8):           # bits are read least-significant first
            node = tree[node][(byte >> bit) & 1]
            if node >= 0:
                continue
            symbol = -(node + 1)
            node = 0
            if symbol == EOF_SYMBOL:
                return name, checksum, bytes(out)
            if in_run:                 # byte after DLE is a repeat count
                in_run = False
                if symbol == 0:        # DLE 0 = a literal 0x90 byte
                    out.append(DLE)
                    prev = DLE
                else:
                    if prev is None:
                        raise SqueezeError("run-length code before any data")
                    out += bytes([prev]) * (symbol - 1)
            elif symbol == DLE:
                in_run = True
            else:
                out.append(symbol)
                prev = symbol
    raise SqueezeError("compressed data ended without an end-of-file code "
                       "(file truncated or damaged)")


def damage_report(data):
    """Heuristic signs of a text-mode (translated) transfer."""
    signs = []
    if len(data) > 1 and data[1] == 0x98:
        signs.append("magic byte 0xFF has become 0x98 (ISO->IBM translation)")
    crs = data.count(b"\r")
    if crs and data.count(b"\r\n") == crs:
        signs.append("every CR is followed by LF (%d CR+LF pairs: CR->CRLF "
                     "conversion)" % crs)
    missing = 256 - len(set(data))
    if len(data) > 2000 and missing > 20:
        signs.append("%d byte values never occur (a character-set translation "
                     "removes some values)" % missing)
    return signs


# --------------------------------------------------------------------------
# BBC BASIC (Z80) / Z88 detokeniser
# --------------------------------------------------------------------------

TOKENS = (
    "AND DIV EOR MOD OR ERROR LINE OFF STEP SPC TAB( ELSE THEN <line> OPENIN PTR "
    "PAGE TIME LOMEM HIMEM ABS ACS ADVAL ASC ASN ATN BGET COS COUNT DEG ERL ERR "
    "EVAL EXP EXT FALSE FN GET INKEY INSTR( INT LEN LN LOG NOT OPENUP OPENOUT PI "
    "POINT( POS RAD RND SGN SIN SQR TAN TO TRUE USR VAL VPOS CHR$ GET$ INKEY$ "
    "LEFT$( MID$( RIGHT$( STR$ STRING$( EOF AUTO DELETE LOAD LIST NEW OLD RENUMBER "
    "SAVE PUT PTR PAGE TIME LOMEM HIMEM SOUND BPUT CALL CHAIN CLEAR CLOSE CLG CLS "
    "DATA DEF DIM DRAW END ENDPROC ENVELOPE FOR GOSUB GOTO GCOL IF INPUT LET LOCAL "
    "MODE MOVE NEXT ON VDU PLOT PRINT PROC READ REM REPEAT REPORT RESTORE RETURN RUN "
    "STOP COLOUR TRACE UNTIL WIDTH OSCLI"
).split()
assert len(TOKENS) == 128
TOK_LINENUM, TOK_REM, TOK_DATA = 0x8D, 0xF4, 0xDC


def looks_like_basic(prog):
    """True if prog is a well-formed tokenised BBC BASIC (Z80) program."""
    p, last = 0, -1
    while p < len(prog):
        length = prog[p]
        if length == 0:
            return p + 2 < len(prog) and prog[p + 1] == 0xFF and prog[p + 2] == 0xFF
        if length < 4 or p + length > len(prog) or prog[p + length - 1] != 0x0D:
            return False
        num = prog[p + 1] | prog[p + 2] << 8
        if num <= last:
            return False
        last = num
        p += length
    return False


def _char(c, escape_high):
    if 0x20 <= c < 0x7F:
        return chr(c)
    if c >= 0xA0 and not escape_high:
        return bytes([c]).decode("latin-1")
    return "\\x%02X" % c


def detokenise(prog, escape_high=False):
    """Return (listing_text, end_offset) for a tokenised program."""
    lines = []
    p = 0
    while p < len(prog) and prog[p] != 0:
        length = prog[p]
        num = prog[p + 1] | prog[p + 2] << 8
        body = prog[p + 3:p + length - 1]
        text = []
        in_string = literal = False
        i = 0
        while i < len(body):
            c = body[i]
            if literal:                           # rest of a REM / DATA line
                text.append(_char(c, escape_high))
            elif in_string:
                if c == 0x22:
                    in_string = False
                text.append(_char(c, escape_high))
            elif c == 0x22:
                in_string = True
                text.append('"')
            elif c == TOK_LINENUM and i + 3 < len(body):
                b1 = body[i + 1] ^ 0x54
                lo = (body[i + 2] & 0x3F) | ((b1 << 2) & 0xC0)
                hi = (body[i + 3] & 0x3F) | ((b1 << 4) & 0xC0)
                text.append(str(lo | hi << 8))
                i += 3
            elif c >= 0x80:
                text.append(TOKENS[c - 0x80])
                if c in (TOK_REM, TOK_DATA):
                    literal = True
            else:
                text.append(_char(c, escape_high))
            i += 1
        lines.append("%5d %s" % (num, "".join(text)))
        p += length
    return "\n".join(lines) + "\n", p


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def unique_path(path):
    if not os.path.exists(path):
        return path
    base, n = path, 1
    while os.path.exists("%s.%d" % (base, n)):
        n += 1
    return "%s.%d" % (base, n)


def process(path, args):
    data = open(path, "rb").read()
    try:
        name, stored, out = unsqueeze(data)
    except SqueezeError as e:
        print("%s: ERROR: %s" % (path, e), file=sys.stderr)
        for s in damage_report(data):
            print("    possible transfer damage: %s" % s, file=sys.stderr)
        return False
    actual = sum(out) & 0xFFFF
    ok = actual == stored
    is_basic = looks_like_basic(out)
    status = "checksum OK" if ok else "CHECKSUM MISMATCH (stored %04X, got %04X)" % (stored, actual)
    kind = "BBC BASIC program" if is_basic else "data file"
    print("%s: %s, %d bytes, %s, %s" % (path, name or "(no name)", len(out), kind, status))
    if not ok:
        for s in damage_report(data):
            print("    possible transfer damage: %s" % s)
        if not args.force:
            print("    not written (use --force to write anyway)")
            return False
    if args.info:
        return ok
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name) or \
        os.path.splitext(os.path.basename(path))[0]
    target = os.path.join(args.outdir, safe)
    if not args.overwrite:
        target = unique_path(target)
    with open(target, "wb") as f:
        f.write(out)
    print("    wrote %s" % target)
    if is_basic and args.list:
        listing, end = detokenise(out, args.escape_high)
        lpath = target + ".txt"
        with open(lpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(listing)
        print("    wrote %s (%d lines)" % (lpath, listing.count("\n")))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Unsqueeze Cambridge Z88 Squeez88 (.ZSQ) files and, with "
                    "--list, list BBC BASIC programs.")
    ap.add_argument("files", nargs="+", help="squeezed file(s) to process")
    ap.add_argument("-o", "--outdir", default=".", help="output directory (default: current)")
    ap.add_argument("-i", "--info", action="store_true",
                    help="only report name, size and checksum; write nothing")
    ap.add_argument("-f", "--force", action="store_true",
                    help="write output even if the checksum does not match")
    ap.add_argument("-l", "--list", action="store_true",
                    help="also write a plain-text .txt listing for each BBC BASIC "
                         "program (default: straight decompression only)")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing output files instead of adding .1, .2 ...")
    ap.add_argument("--escape-high", action="store_true",
                    help="with --list, show bytes >= 0x80 in strings as \\xNN "
                         "instead of Latin-1")
    ap.add_argument("-V", "--version", action="version", version="%(prog)s " + __version__)
    args = ap.parse_args(argv)
    if not args.info:
        os.makedirs(args.outdir, exist_ok=True)
    results = [process(f, args) for f in args.files]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
