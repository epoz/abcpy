"""Parses a string representing ABC Music Notation into a usable internal structure.

Port of abcjs ``abc_parse.js``.
"""

import re

from ..jsutil import Obj, at, last, parse_int, strip, js_str, substring, obj_copy
from ..data.tune import Tune
from .tokenizer import Tokenizer
from .directive import ParseDirective
from .key_voice import ParseKeyVoice
from .header import ParseHeader
from .music import MusicParser
from .tune_builder import TuneBuilder
from . import wrap_lines


class NormalAbort(Exception):
    pass


def _add_positioning(el, typ, value):
    if el.positioning is None:
        el.positioning = Obj()
    el.positioning[typ] = value


def _add_font(el, typ, value):
    if el.fonts is None:
        el.fonts = Obj()
    el.fonts[typ] = value


class MultilineVars(Obj):
    """The parser state that persists across lines."""

    def reset(self):
        self.clear()
        self.iChar = 0
        self.key = Obj(accidentals=[], root='none', acc='', mode='')
        self.meter = None  # if no meter is specified, free meter is assumed
        self.origMeter = None  # this is for new voices that are created after we set the meter.
        self.hasMainTitle = False
        self.default_length = 0.125
        self.clef = Obj(type='treble', verticalPos=0)
        self.octave = 0
        self.next_note_duration = 0
        self.start_new_line = True
        self.is_in_header = True
        self.partForNextLine = Obj()
        self.tempoForNextLine = []
        self.havent_set_length = True
        self.voices = Obj()
        self.staves = []
        self.macros = Obj()
        self.currBarNumber = 1
        self.barCounter = Obj()
        self.ignoredDecorations = []
        self.score_is_present = False  # Can't have original V: lines when there is the score directive
        self.inEnding = False
        self.inTie = {}
        self.inTieChord = {}
        self.vocalPosition = "auto"
        self.dynamicPosition = "auto"
        self.chordPosition = "auto"
        self.ornamentPosition = "auto"
        self.volumePosition = "auto"
        self.openSlurs = []
        self.freegchord = False
        self.endingHoldOver = Obj()

    def different_font(self, typ, default_fonts):
        a = self[typ]
        b = default_fonts[typ]
        for k in ('decoration', 'face', 'size', 'style', 'weight'):
            if a.get(k) != b.get(k):
                return True
        return False

    def add_formatting_options(self, el, default_fonts, el_type):
        if el_type == 'note':
            for name in ('vocalPosition', 'dynamicPosition', 'chordPosition', 'ornamentPosition', 'volumePosition'):
                if self[name] != 'auto':
                    _add_positioning(el, name, self[name])
            for name in ('annotationfont', 'gchordfont', 'vocalfont', 'tripletfont'):
                if self.different_font(name, default_fonts):
                    _add_font(el, name, self[name])
        elif el_type == 'bar':
            for name in ('dynamicPosition', 'chordPosition', 'ornamentPosition', 'volumePosition'):
                if self[name] != 'auto':
                    _add_positioning(el, name, self[name])
            for name in ('measurefont', 'repeatfont'):
                if self.different_font(name, default_fonts):
                    _add_font(el, name, self[name])

    def duplicate_start_ending_hold_overs(self):
        self.endingHoldOver = Obj(inTie={}, inTieChord={})
        for level, ties in self.inTie.items():
            self.endingHoldOver.inTie[level] = dict(ties) if ties else {}
        for key, value in self.inTieChord.items():
            self.endingHoldOver.inTieChord[key] = value

    def restore_start_ending_hold_overs(self):
        if self.endingHoldOver.inTie is None:
            return
        self.inTie = {}
        self.inTieChord = {}
        for level, ties in self.endingHoldOver.inTie.items():
            self.inTie[level] = dict(ties)
        for key, value in self.endingHoldOver.inTieChord.items():
            self.inTieChord[key] = value


def _encode(s):
    ret = s.replace('\x12', ' ')
    ret = ret.replace('&', '&amp;')
    ret = ret.replace('<', '&lt;')
    return ret.replace('>', '&gt;')


class Parse:
    """The ABC parser.

    Usage::

        parser = Parse()
        parser.parse(abc_string, switches)
        tune = parser.get_tune()
        warnings = parser.get_warnings()
    """

    def __init__(self):
        self.tune = Tune()
        self.tune_builder = TuneBuilder(self.tune)
        self.tokenizer = None
        self.words_continuation = ''
        self.symbol_continuation = ''
        self.multiline_vars = MultilineVars()
        self.directive = ParseDirective()
        self.key_voice = ParseKeyVoice(self.directive)
        self.header = None
        self.music = None

    def get_tune(self):
        return self.tune

    def get_warnings(self):
        return self.multiline_vars.warnings

    def get_warning_objects(self):
        return self.multiline_vars.warningObjects

    # camelCase aliases matching abcjs
    getTune = get_tune
    getWarnings = get_warnings
    getWarningObjects = get_warning_objects

    # -- warnings ------------------------------------------------------------
    def _add_warning(self, s):
        mv = self.multiline_vars
        if not mv.warnings:
            mv.warnings = []
        mv.warnings.append(s)

    def _add_warning_object(self, warning_object):
        mv = self.multiline_vars
        if not mv.warningObjects:
            mv.warningObjects = []
        mv.warningObjects.append(warning_object)

    def warn(self, s, line=None, col_num=None):
        if not line:
            line = " "
        if not isinstance(line, str):
            line = js_str(line)
        bad_char = at(line, col_num) if isinstance(col_num, int) else None
        if bad_char == ' ' or not bad_char:
            bad_char = "SPACE"
        if isinstance(col_num, int):
            before = substring(line, col_num - 64, col_num)
            after = substring(line, col_num + 1)[0:64]
            col_str = js_str(col_num + 1)
            start_char = self.multiline_vars.iChar + col_num
        else:
            before = line
            after = line[0:64]
            col_str = "NaN"
            start_char = float('nan')
        clean_line = _encode(before) + '<span style="text-decoration:underline;font-size:1.3em;font-weight:bold;">' + bad_char + '</span>' + _encode(after)
        line_index = self.tokenizer.line_index if self.tokenizer else 0
        self._add_warning("Music Line:" + js_str(line_index) + ":" + col_str + ': ' + js_str(s) + ":  " + clean_line)
        self._add_warning_object(Obj(message=s, line=line, startChar=start_char, column=col_num))

    # -- lyrics ----------------------------------------------------------------
    def _add_words(self, line, words):
        if '\x12' in words:
            self.words_continuation += words
            return
        words = self.words_continuation + words
        self.words_continuation = ''

        if line is None:
            self.warn("Can't add words before the first line of music", line, 0)
            return
        words = strip(words)
        if at(words, len(words) - 1) != '-':
            words = words + ' '  # Just makes it easier to parse below, since every word has a divider after it.
        word_list = []
        # first make a list of words from the string we are passed. A word is divided on either a space or dash.
        state = Obj(last_divider=0, replace=False)
        tokenizer = self.tokenizer

        def add_word(i):
            word = strip(words[state.last_divider:i])
            word = re.sub(r"\\([-_*|~])", r"\1", word)
            state.last_divider = i + 1
            if len(word) > 0:
                if state.replace:
                    word = word.replace('~', ' ')
                div = words[i]
                if div != '_' and div != '-':
                    div = ' '
                word_list.append(Obj(syllable=tokenizer.translate_string(word), divider=div))
                state.replace = False
                return True
            return False

        esc_next = False
        for i in range(len(words)):
            c = words[i]
            if c == ' ' or c == '\x12':
                add_word(i)
            elif c == '-':
                if not esc_next and not add_word(i) and len(word_list) > 0:
                    last(word_list).divider = '-'
                    word_list.append(Obj(skip=True, to='next'))
            elif c == '_':
                if not esc_next:
                    add_word(i)
                    word_list.append(Obj(skip=True, to='slur'))
            elif c == '*':
                if not esc_next:
                    add_word(i)
                    word_list.append(Obj(skip=True, to='next'))
            elif c == '|':
                if not esc_next:
                    add_word(i)
                    word_list.append(Obj(skip=True, to='bar'))
            elif c == '~':
                if not esc_next:
                    state.replace = True
            esc_next = c == '\\'

        in_slur = False
        for el in line:
            if len(word_list) != 0:
                if word_list[0].skip:
                    to = word_list[0].to
                    if to == 'next':
                        if el.el_type == 'note' and el.pitches is not None and not in_slur:
                            word_list.pop(0)
                    elif to == 'slur':
                        if el.el_type == 'note' and el.pitches is not None:
                            word_list.pop(0)
                    elif to == 'bar':
                        if el.el_type == 'bar':
                            word_list.pop(0)
                    if el.el_type != 'bar':
                        if el.lyric is None:
                            el.lyric = [Obj(syllable="", divider=" ")]
                        else:
                            el.lyric.append(Obj(syllable="", divider=" "))
                else:
                    if el.el_type == 'note' and el.rest is None and not in_slur:
                        lyric = word_list.pop(0)
                        if lyric.syllable:
                            lyric.syllable = re.sub(r" +", '\xA0', lyric.syllable)
                        if el.lyric is None:
                            el.lyric = [lyric]
                        else:
                            el.lyric.append(lyric)

    def _add_symbols(self, line, words):
        if '\x12' in words:
            self.symbol_continuation += words
            return
        words = self.symbol_continuation + words
        self.symbol_continuation = ''

        # TODO-PER: Currently copied from w: line. This needs to be read as symbols instead.
        if line is None:
            self.warn("Can't add symbols before the first line of music", line, 0)
            return
        words = strip(words)
        if at(words, len(words) - 1) != '-':
            words = words + ' '
        word_list = []
        state = Obj(last_divider=0, replace=False)
        tokenizer = self.tokenizer

        def add_word(i):
            word = strip(words[state.last_divider:i])
            state.last_divider = i + 1
            if len(word) > 0:
                if state.replace:
                    word = word.replace('~', ' ')
                div = words[i]
                if div != '_' and div != '-':
                    div = ' '
                word_list.append(Obj(syllable=tokenizer.translate_string(word), divider=div))
                state.replace = False
                return True
            return False

        for i in range(len(words)):
            c = words[i]
            if c == ' ' or c == '\x12':
                add_word(i)
            elif c == '-':
                if not add_word(i) and len(word_list) > 0:
                    last(word_list).divider = '-'
                    word_list.append(Obj(skip=True, to='next'))
            elif c == '_':
                add_word(i)
                word_list.append(Obj(skip=True, to='slur'))
            elif c == '*':
                add_word(i)
                word_list.append(Obj(skip=True, to='next'))
            elif c == '|':
                add_word(i)
                word_list.append(Obj(skip=True, to='bar'))
            elif c == '~':
                state.replace = True

        in_slur = False
        for el in line:
            if len(word_list) != 0:
                if word_list[0].skip:
                    to = word_list[0].to
                    if to == 'next':
                        if el.el_type == 'note' and el.pitches is not None and not in_slur:
                            word_list.pop(0)
                    elif to == 'slur':
                        if el.el_type == 'note' and el.pitches is not None:
                            word_list.pop(0)
                    elif to == 'bar':
                        if el.el_type == 'bar':
                            word_list.pop(0)
                else:
                    if el.el_type == 'note' and el.rest is None and not in_slur:
                        lyric = word_list.pop(0)
                        if el.lyric is None:
                            el.lyric = [lyric]
                        else:
                            el.lyric.append(lyric)

    def _parse_line(self, line):
        if line.startswith('%%'):
            err = self.directive.add_directive(line[2:])
            if err:
                self.warn(err, line, 2)
            return

        i = line.find('%')
        if i >= 0:
            line = line[0:i]
        line = re.sub(r"\s+$", '', line)

        if len(line) == 0:
            return

        if self.words_continuation:
            self._add_words(self.tune_builder.get_current_voice(), line[2:])
            return
        if self.symbol_continuation:
            self._add_symbols(self.tune_builder.get_current_voice(), line[2:])
            return
        if len(line) < 2 or line[1] != ':' or self.music.line_continuation:
            self.music.parse_music(line)
            return

        ret = self.header.parse_header(line)
        if ret.regular:
            self.music.parse_music(line)
        if ret.newline:
            self.music.start_new_line()
        if ret.words:
            self._add_words(self.tune_builder.get_current_voice(), line[2:])
        if ret.symbols:
            self._add_symbols(self.tune_builder.get_current_voice(), line[2:])

    def _add_hint_measures(self):
        tune = self.tune

        def append_last_measure(voice, next_voice):
            voice.append(Obj(el_type='hint'))
            for element in next_voice:
                hint = Obj(element)
                voice.append(hint)
                if element.el_type == 'bar':
                    return

        def add_hint_measure(staff, next_staff):
            for i in range(len(staff)):
                stave = staff[i]
                next_stave = at(next_staff, i)
                if next_stave:  # Be sure there is the same number of staves on the next line.
                    for j in range(len(next_stave.voices)):
                        next_voice = next_stave.voices[j]
                        voice = at(stave.voices, j)
                        if voice is not None:  # Be sure there are the same number of voices on the previous line.
                            append_last_measure(voice, next_voice)

        for i in range(len(tune.lines)):
            line = tune.lines[i].staff
            if line:
                j = i + 1
                while j < len(tune.lines) and tune.lines[j].staff is None:
                    j += 1
                if j < len(tune.lines):
                    next_line = tune.lines[j].staff
                    add_hint_measure(line, next_line)

    def parse(self, str_tune, switches=None, start_pos=None):
        """Parse an abc string.

        ``switches`` are optional and change the way the tune is parsed:
        ``header_only``, ``stop_on_warning``, ``print``, ``format`` (a dict of
        formatting directives), ``hint_measures``, ``visualTranspose``,
        ``lineBreaks``, ``chordGrid``.
        """
        if not switches:
            switches = {}
        if not isinstance(switches, Obj):
            switches = obj_copy(switches)
        if not start_pos:
            start_pos = 0
        tune = self.tune
        tune.reset()
        mv = self.multiline_vars

        # Take care of whatever line endings come our way
        # Tack on newline temporarily to make the last line continuation work
        str_tune = re.sub(r"\r\n?", "\n", str_tune) + '\n'

        # get rid of latex commands. If a line starts with a backslash, then it is replaced by spaces to keep the character count the same.
        arr = str_tune.split("\n\\")
        if len(arr) > 1:
            for i2 in range(1, len(arr)):
                while len(arr[i2]) > 0 and arr[i2][0] != "\n":
                    arr[i2] = arr[i2][1:]
                    arr[i2 - 1] += ' '
            str_tune = "  ".join(arr)  # the split removed two characters, so this puts them back
        # If there is an escaped percent, then temporarily change it so it doesn't affect the processing.
        str_tune = str_tune.replace("\\%", "​％")

        # take care of line continuations right away, but keep the same number of characters
        def repl(m):
            backslash = m.group(1)
            comment = m.group(2)
            padding = ' ' * len(comment) if comment else ""
            return backslash + "\x12" + padding + '\n'

        str_tune = re.sub(r"\\([ \t]*)(%.*)*\n", repl, str_tune)
        lines = str_tune.split('\n')
        if len(last(lines)) == 0:  # remove the blank line we added above.
            lines.pop()
        self.tokenizer = Tokenizer(lines, mv)
        self.header = ParseHeader(self.tokenizer, self.warn, mv, tune, self.tune_builder, self.directive, self.key_voice)
        self.music = MusicParser(self.tokenizer, self.warn, mv, tune, self.tune_builder, self.header, self.key_voice)

        if switches.print:
            tune.media = 'print'
        mv.reset()
        mv.iChar = start_pos
        if switches.visualTranspose:
            mv.globalTranspose = parse_int(switches.visualTranspose)
            if mv.globalTranspose == 0:
                mv.globalTranspose = None
            else:
                self.tune_builder.set_visual_transpose(switches.visualTranspose)
        else:
            mv.globalTranspose = None
        if switches.lineBreaks:
            # The line break numbers are 0-based and they reflect the last measure of the current line.
            mv.lineBreaks = switches.lineBreaks
        self.header.reset(self.tokenizer, self.warn, mv, tune)

        try:
            if switches.format:
                self.directive.global_formatting(switches.format)
            line = self.tokenizer.next_line()
            # Note: an empty string is falsy, so (like abcjs) parsing stops at the first empty line.
            while line:
                if switches.header_only and mv.is_in_header is False:
                    raise NormalAbort()
                if switches.stop_on_warning and mv.warnings:
                    raise NormalAbort()

                was_in_header = mv.is_in_header
                self._parse_line(line)
                if was_in_header and not mv.is_in_header:
                    self.tune_builder.set_running_font("annotationfont", mv.annotationfont)
                    self.tune_builder.set_running_font("gchordfont", mv.gchordfont)
                    self.tune_builder.set_running_font("tripletfont", mv.tripletfont)
                    self.tune_builder.set_running_font("vocalfont", mv.vocalfont)
                line = self.tokenizer.next_line()

            if self.words_continuation:
                self._add_words(self.tune_builder.get_current_voice(), '')
            if self.symbol_continuation:
                self._add_symbols(self.tune_builder.get_current_voice(), '')
            mv.openSlurs = self.tune_builder.clean_up(mv.barsperstaff, mv.staffnonote, mv.openSlurs)
        except NormalAbort:
            pass

        ph = 11 * 72
        pl = 8.5 * 72
        if mv.papersize == "legal":
            ph = 14 * 72
            pl = 8.5 * 72
        elif mv.papersize == "A4":
            ph = 11.7 * 72
            pl = 8.3 * 72
        if mv.landscape:
            ph, pl = pl, ph
        if not tune.formatting.pagewidth:
            tune.formatting.pagewidth = pl
        if not tune.formatting.pageheight:
            tune.formatting.pageheight = ph

        if switches.hint_measures:
            self._add_hint_measures()

        wrap_lines.wrap_lines(tune, mv.lineBreaks, mv.barNumbers)
        if switches.chordGrid:
            from .chord_grid import chord_grid, ChordGridError
            try:
                tune.chordGrid = chord_grid(tune)
            except ChordGridError as err:
                msg = str(err)
                if msg == "notCommonTime":
                    self.warn("Chord grid only works for 2/2 and 4/4 time.", 0, 0)
                elif msg == "noChords":
                    self.warn("No chords are found in the tune.", 0, 0)
                else:
                    self.warn(msg, 0, 0)
