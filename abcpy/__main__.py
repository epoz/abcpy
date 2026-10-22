"""Command line interface: ``python -m abcpy FILE.abc [options]``."""

import argparse
import json
import sys

from . import parse_only, render_svg, get_midi_file, transpose, number_of_tunes, TuneBook
from .data.tune import _strip_engraver_refs


def main(argv=None):
    p = argparse.ArgumentParser(prog="abcpy", description="Parse, transpose and convert ABC music notation.")
    p.add_argument("file", help="the abc file to read ('-' for stdin)")
    p.add_argument("--transpose", type=int, metavar="STEPS", help="transpose the abc text by STEPS half steps")
    p.add_argument("--abc", metavar="OUT", help="write the (transposed) abc text to OUT")
    p.add_argument("--svg", metavar="OUT", help="write SVG; use {n} in the name for tune numbers when there are several tunes")
    p.add_argument("--midi", metavar="OUT", help="write a MIDI file; use {n} in the name for tune numbers")
    p.add_argument("--json", metavar="OUT", help="write the parsed tunes as JSON ('-' for stdout)")
    p.add_argument("--list", action="store_true", help="list the tunes in the file")
    p.add_argument("--staffwidth", type=float, help="staff width in pixels for the SVG")
    p.add_argument("--responsive", action="store_true", help="make the SVG resize to its container (viewBox)")
    p.add_argument("--classes", action="store_true", help="add CSS classes to the SVG elements")
    p.add_argument("--warnings", action="store_true", help="print the parser warnings")
    args = p.parse_args(argv)

    if args.file == "-":
        abc = sys.stdin.read()
    else:
        with open(args.file, encoding="utf-8") as f:
            abc = f.read()

    if args.transpose:
        abc = transpose(abc, args.transpose)
    if args.abc:
        with open(args.abc, "w", encoding="utf-8") as f:
            f.write(abc)

    if args.list:
        book = TuneBook(abc)
        for t in book.tunes:
            print("%s\t%s" % (t.id, t.title))

    params = {}
    if args.staffwidth:
        params["staffwidth"] = args.staffwidth
    if args.responsive:
        params["responsive"] = "resize"
    if args.classes:
        params["add_classes"] = True

    if args.json or args.warnings:
        tunes = parse_only(abc)
        if args.warnings:
            for i, t in enumerate(tunes):
                for w in t.warnings or []:
                    print("tune %d: %s" % (i, w), file=sys.stderr)
        if args.json:
            data = [_strip_engraver_refs(t.to_dict()) for t in tunes]
            text = json.dumps(data, ensure_ascii=False, indent=1, default=lambda o: None)
            if args.json == "-":
                print(text)
            else:
                with open(args.json, "w", encoding="utf-8") as f:
                    f.write(text)

    n = number_of_tunes(abc)

    def name(pattern, i):
        if "{n}" in pattern:
            return pattern.replace("{n}", str(i))
        if n > 1 and i > 0:
            base, dot, ext = pattern.rpartition(".")
            return "%s-%d.%s" % (base, i, ext) if dot else "%s-%d" % (pattern, i)
        return pattern

    if args.svg:
        for i, svg in enumerate(render_svg(abc, params)):
            if svg is None:
                continue
            with open(name(args.svg, i), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg)
    if args.midi:
        for i, data in enumerate(get_midi_file(abc, {"midiOutputType": "binary"})):
            with open(name(args.midi, i), "wb") as f:
                f.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
