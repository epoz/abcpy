"""Splitting a string of ABC into tunes and parsing them (port of ``abc_tunebook.js``)."""

from ..jsutil import Obj, parse_int, obj_copy
from ..parse.parse import Parse
from ..parse.book import book_parser


def number_of_tunes(abc):
    """Return the number of tunes in an abc string (counts the ``X:`` fields)."""
    tunes = abc.split("\nX:")
    num = len(tunes)
    if num == 0:
        num = 1
    return num


class TuneBook:
    """A collection of tunes, split from a single string.

    ``book.header`` contains the file-wide directives and ``book.tunes`` a list
    of dicts with ``abc``, ``pure``, ``startPos``, ``title`` and ``id``.
    """

    def __init__(self, book):
        parsed = book_parser(book)
        self.header = parsed.header
        self.tunes = parsed.tunes

    def get_tune_by_id(self, ident):
        for t in self.tunes:
            if t.id == str(ident):
                return t
        return None

    def get_tune_by_title(self, title):
        for t in self.tunes:
            if t.title == title:
                return t
        return None

    getTuneById = get_tune_by_id
    getTuneByTitle = get_tune_by_title


def render_engine(callback, output, abc, params=None):
    """Parse every requested tune of ``abc`` and pass it to ``callback(target, tune, index, abc)``.

    ``output`` is a list with one entry per tune to process (any non-None value).
    The return value is the list of tunes (or whatever ``callback`` returned).
    """
    ret = []
    if output is None or abc is None:
        return None
    if not isinstance(output, list):
        output = [output]
    params = obj_copy(params) if params is not None else Obj()
    current_tune = parse_int(params.startingTune, 10) if params.startingTune else 0

    # parse the abc string
    book = TuneBook(abc)
    abc_parser = Parse()

    # output each tune, if it exists.
    for i in range(len(output)):
        div = output[i]
        if div:
            if 0 <= current_tune < len(book.tunes):
                abc_parser.parse(book.tunes[current_tune].abc, params, book.tunes[current_tune].startPos - len(book.header))
                tune = abc_parser.get_tune()
                # Init tablatures plugins
                if params.tablature:
                    from ..tablatures.abc_tablatures import prepare_plugins
                    tune.tablatures = prepare_plugins(tune, current_tune, params)
                warnings = abc_parser.get_warnings()
                if warnings:
                    tune.warnings = warnings
                override = callback(div, tune, i, book.tunes[current_tune].abc)
                ret.append(override if override else tune)
                # a fresh parser for the next tune so that tunes don't share objects
                abc_parser = Parse()
        current_tune += 1
    return ret


def parse_only(abc, params=None):
    """Parse all the tunes in ``abc`` and return a list of :class:`abcpy.data.tune.Tune` objects."""
    num_tunes = number_of_tunes(abc)

    # this just needs to be passed in because this tells the engine how many tunes to process.
    output = [1] * num_tunes

    def callback(*args):
        # Don't need to do anything with the parsed tunes.
        return None

    return render_engine(callback, output, abc, params)


def extract_measures(abc):
    """Split each tune into measures.

    Returns a list (one per tune) of ``{'header': str, 'measures': [{'abc': str, ...}], 'hasPickup': bool}``.
    """
    tunes = []
    book = TuneBook(abc)
    for tune in book.tunes:
        arr = tune.abc.split("K:")
        arr2 = arr[1].split("\n")
        header = arr[0] + "K:" + arr2[0] + "\n"
        last_chord = None
        measure_start_chord = None
        frag_start = None
        measures = []
        has_notes = False
        tune_obj = parse_only(tune.abc)[0]
        has_pickup = tune_obj.get_pickup_length() > 0
        for line in tune_obj.lines:
            if line.staff:
                staff = line.staff[0]
                voice = staff.voices[0]
                for elem in voice:
                    if frag_start is None and elem.startChar is not None and elem.startChar >= 0:
                        frag_start = elem.startChar
                        if elem.chord is None:
                            measure_start_chord = last_chord
                        else:
                            measure_start_chord = None
                    if elem.chord:
                        last_chord = elem
                    if elem.el_type == 'bar':
                        if has_notes:
                            from ..jsutil import substring
                            frag = substring(tune.abc, frag_start, elem.endChar)
                            measure = Obj(abc=frag)
                            last_chord = measure_start_chord.chord[0].name if (measure_start_chord and measure_start_chord.chord and len(measure_start_chord.chord) > 0) else None
                            if last_chord:
                                measure.lastChord = last_chord
                            if elem.startEnding:
                                measure.startEnding = elem.startEnding
                            if elem.endEnding:
                                measure.endEnding = elem.endEnding
                            measures.append(measure)
                            frag_start = None
                            has_notes = False
                    elif elem.el_type == 'note':
                        has_notes = True
        tunes.append(Obj(header=header, measures=measures, hasPickup=has_pickup))
    return tunes
