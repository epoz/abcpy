"""Parses a line of music (port of ``abc_parse_music.js``).

This is a stream of <(bar-marking|header|note-group)...> in any order, with
optional spaces between each element.  See the abcjs source for the detailed
grammar notes.
"""

import re

from ..jsutil import Obj, at, substring, substr, js_set, truthy, js_str
from . import transpose
from . import key_voice as key_voice_mod
from .settings import (legal_accents, volume_decorations, dynamic_decorations, accent_pseudonyms,
                       accent_dynamic_pseudonyms, non_decorations, durations, pitches, rests, acc_map,
                       triplet_q)
from .tokenizer import is_white_space


def _is_in_tie(mv, overlay_level, el):
    level = mv.inTie.get(overlay_level)
    if level is None:
        return False
    # If this is single voice music then the voice index isn't set, so we use the first voice.
    voice_index = mv.currentVoice.staffNum * 100 + mv.currentVoice.index if mv.currentVoice else 0
    if level.get(voice_index):
        if el.pitches is not None or el.rest.type != 'spacer':
            return True
    return False


def _set_is_in_tie(mv, overlay_level, value):
    # If this is single voice music then the voice index isn't set, so we use the first voice.
    voice_index = mv.currentVoice.staffNum * 100 + mv.currentVoice.index if mv.currentVoice else 0
    if mv.inTie.get(overlay_level) is None:
        mv.inTie[overlay_level] = {}
    mv.inTie[overlay_level][voice_index] = value


def _add_end_beam(el):
    if el.duration is not None and el.duration < 0.25:
        el.end_beam = True
    return el


def _get_broken_rhythm(line, index):
    c = at(line, index)
    if c == '>':
        if index < len(line) - 2 and at(line, index + 1) == '>' and at(line, index + 2) == '>':  # triple >>>
            return [3, 1.875, 0.125]
        elif index < len(line) - 1 and at(line, index + 1) == '>':  # double >>
            return [2, 1.75, 0.25]
        return [1, 1.5, 0.5]
    if c == '<':
        if index < len(line) - 2 and at(line, index + 1) == '<' and at(line, index + 2) == '<':  # triple <<<
            return [3, 0.125, 1.875]
        elif index < len(line) - 1 and at(line, index + 1) == '<':  # double <<
            return [2, 0.25, 1.75]
        return [1, 0.5, 1.5]
    return None


def _duration_of_measure(mv):
    # TODO-PER: This could be more complicated if one of the unusual measures is used.
    from ..jsutil import parse_int
    meter = mv.origMeter
    if not meter or meter.type != 'specified':
        return 1
    if not meter.value or len(meter.value) == 0:
        return 1
    num = parse_int(meter.value[0].num, 10)
    den = parse_int(meter.value[0].den, 10)
    try:
        return num / den
    except (ZeroDivisionError, TypeError):
        return float('nan')


def _letter_to_spacer(line, i):
    start = i
    while is_white_space(at(line, i)):
        i += 1
    return [i - start]


def _letter_to_overlay(line, i):
    if at(line, i) == '&':
        start = i
        while at(line, i) and at(line, i) != ':' and at(line, i) != '|':
            i += 1
        return [i - start, line[start + 1:i]]
    return [0]


def _is_digit_1_9(c):
    return c is not None and '1' <= c <= '9'


class MusicParser:
    def __init__(self, tokenizer, warn, multiline_vars, tune, tune_builder, header, key_voice):
        self.tokenizer = tokenizer
        self.warn = warn
        self.multiline_vars = multiline_vars
        self.tune = tune
        self.tune_builder = tune_builder
        self.header = header
        self.key_voice = key_voice
        self.line_continuation = False
        self.el = Obj()

    def _is_first_voice(self):
        mv = self.multiline_vars
        return mv.currentVoice is None or (mv.currentVoice.staffNum == 0 and mv.currentVoice.index == 0)

    def parse_music(self, line):
        mv = self.multiline_vars
        tokenizer = self.tokenizer
        tune_builder = self.tune_builder
        tune = self.tune
        warn = self.warn
        header = self.header

        header.resolve_tempo()
        mv.is_in_header = False  # We should have gotten a key header by now, but just in case, this is definitely out of the header.
        i = 0
        start_of_line = mv.iChar
        # see if there is nothing but a comment on this line. If so, just ignore it. A full line comment is optional white space followed by %
        while is_white_space(at(line, i)) and i < len(line):
            i += 1
        if i == len(line) or at(line, i) == '%':
            return

        # Start with the standard staff, clef and key symbols on each line
        delay_start_new_line = mv.start_new_line
        if mv.continueall is None:
            mv.start_new_line = True
        else:
            mv.start_new_line = False
        triplet_notes_left = 0

        # See if the line starts with a header field
        ret_header = header.letter_to_body_header(line, i)
        if ret_header[0] > 0:
            i += ret_header[0]
            # fixes bug on this: c[V:2]d
            if at(ret_header, 1) == 'V':
                self.start_new_line()

        overlay_level = 0
        while i < len(line):
            start_i = i
            if line[i] == '%':
                break

            ret_inline_header = header.letter_to_inline_header(line, i, delay_start_new_line)
            if ret_inline_header[0] > 0:
                i += ret_inline_header[0]
                if at(ret_inline_header, 1) == 'V':
                    delay_start_new_line = True  # fixes bug on this: c[V:2]d
            else:
                # Wait until here to actually start the line because we know we're past the inline statements.
                if not tune_builder.has_begin_music() or (delay_start_new_line and not self.line_continuation):
                    self.start_new_line()
                    delay_start_new_line = False

                # We need to decide if the following characters are a bar-marking or a note-group.
                # Unfortunately, that is ambiguous. Both can contain chord symbols and decorations.
                while True:
                    ret = tokenizer.eat_white_space(line, i)
                    if ret > 0:
                        i += ret
                    if i > 0 and at(line, i - 1) == '\x12':
                        # there is one case where a line continuation isn't the same as being on the same line, and that is if the next character after it is a header.
                        ret = header.letter_to_body_header(line, i)
                        if ret[0] > 0:
                            if at(ret, 1) == 'V':
                                self.start_new_line()  # fixes bug on this: c\\nV:2]\\nd
                            i = ret[0]
                            mv.start_new_line = False
                    # gather all the grace notes, chord symbols and decorations
                    ret = _letter_to_spacer(line, i)
                    if ret[0] > 0:
                        i += ret[0]

                    ret = self._letter_to_chord(line, i)
                    if ret[0] > 0:
                        # There could be more than one chord here if they have different positions.
                        # If two chords have the same position, then connect them with newline.
                        if not self.el.chord:
                            self.el.chord = []
                        chord_name = tokenizer.translate_string(ret[1])
                        chord_name = chord_name.replace(";", "\n")
                        added_chord = False
                        for c in self.el.chord:
                            if c.position == at(ret, 2):
                                added_chord = True
                                c.name += "\n" + chord_name
                        if added_chord is False:
                            if at(ret, 2) is None and at(ret, 3):
                                self.el.chord.append(Obj(name=chord_name, rel_position=ret[3]))
                            else:
                                self.el.chord.append(Obj(name=chord_name, position=ret[2]))

                        i += ret[0]
                        ii = tokenizer.skip_white_space(line[i:])
                        if ii > 0:
                            self.el.force_end_beam_last = True
                        i += ii
                    else:
                        c = at(line, i)
                        if c is None or c not in non_decorations:
                            ret = self._letter_to_accent(line, i)
                        else:
                            ret = [0]
                        if ret[0] > 0:
                            if ret[1] is None:
                                if i + 1 < len(line):
                                    self.start_new_line()  # There was a ! in the middle of the line. Start a new line if there is anything after it.
                            elif len(ret[1]) > 0:
                                if ret[1].find("style=") == 0:
                                    self.el.style = ret[1][6:]
                                elif ret[1].find("class=") == 0:
                                    self.el.extraClass = ret[1][6:]
                                else:
                                    if self.el.decoration is None:
                                        self.el.decoration = []
                                    if ret[1] == 'beambr1':
                                        self.el.beambr = 1
                                    elif ret[1] == "beambr2":
                                        self.el.beambr = 2
                                    else:
                                        self.el.decoration.append(ret[1])
                            i += ret[0]
                        else:
                            ret = self._letter_to_grace(line, i)
                            # TODO-PER: Be sure there aren't already grace notes defined. That is an error.
                            if ret[0] > 0:
                                self.el.gracenotes = ret[1]
                                i += ret[0]
                            else:
                                break

                ret = self._letter_to_bar(line, i)
                if ret[0] > 0:
                    # This is definitely a bar
                    overlay_level = 0
                    if self.el.gracenotes is not None:
                        # Attach the grace note to an invisible note
                        self.el.rest = Obj(type='spacer')
                        self.el.duration = 0.125  # TODO-PER: I don't think the duration of this matters much, but figure out if it does.
                        mv.add_formatting_options(self.el, tune.formatting, 'note')
                        tune_builder.append_element('note', start_of_line + i, start_of_line + i + ret[0], self.el)
                        mv.measureNotEmpty = True
                        self.el = Obj()
                    bar = Obj(type=ret[1])
                    if len(bar.type) == 0:
                        warn("Unknown bar type", line, i)
                    else:
                        if mv.inEnding and bar.type != 'bar_thin':
                            bar.endEnding = True
                            mv.inEnding = False
                        if at(ret, 2):
                            bar.startEnding = ret[2]
                            if mv.inEnding:
                                bar.endEnding = True
                            mv.inEnding = True
                            if ret[1] == "bar_right_repeat":
                                # restore the tie and slur state from the start repeat
                                mv.restore_start_ending_hold_overs()
                            else:
                                # save inTie, inTieChord
                                mv.duplicate_start_ending_hold_overs()
                        if self.el.decoration is not None:
                            bar.decoration = self.el.decoration
                        if self.el.chord is not None:
                            bar.chord = self.el.chord
                        if bar.startEnding and mv.barFirstEndingNum is None:
                            mv.barFirstEndingNum = mv.currBarNumber
                        elif bar.startEnding and bar.endEnding and mv.barFirstEndingNum:
                            mv.currBarNumber = mv.barFirstEndingNum
                        elif bar.endEnding:
                            mv.barFirstEndingNum = None
                        if bar.type != 'bar_invisible' and mv.measureNotEmpty:
                            if self._is_first_voice():
                                mv.currBarNumber += 1
                                if mv.barNumbers and mv.currBarNumber % mv.barNumbers == 0:
                                    bar.barNumber = mv.currBarNumber
                        mv.add_formatting_options(self.el, tune.formatting, 'bar')
                        tune_builder.append_element('bar', start_of_line + start_i, start_of_line + i + ret[0], bar)
                        mv.measureNotEmpty = False
                        self.el = Obj()
                    i += ret[0]
                elif at(line, i) == '&':  # backtrack to beginning of measure
                    ret = _letter_to_overlay(line, i)
                    if ret[0] > 0:
                        tune_builder.append_element('overlay', start_of_line, start_of_line + 1, Obj())
                        i += 1
                        overlay_level += 1
                else:
                    # This is definitely a note group
                    #
                    # Look for as many open slurs and triplets as there are. (Note: only the first triplet is valid.)
                    ret = self._letter_to_open_slurs_and_triplets(line, i)
                    if ret.consumed > 0:
                        if ret.startSlur is not None:
                            self.el.startSlur = ret.startSlur
                        if ret.dottedSlur:
                            self.el.dottedSlur = True
                        if ret.triplet is not None:
                            if triplet_notes_left > 0:
                                warn("Can't nest triplets", line, i)
                            else:
                                self.el.startTriplet = ret.triplet
                                self.el.tripletMultiplier = ret.tripletQ / ret.triplet
                                self.el.tripletR = ret.num_notes
                                triplet_notes_left = ret.triplet if ret.num_notes is None else ret.num_notes
                        i += ret.consumed

                    # handle chords.
                    if at(line, i) == '[':
                        i += 1
                        chord_duration = None
                        remember_end_beam = False

                        done = False
                        while not done:
                            accent = self._letter_to_accent(line, i)
                            if accent[0] > 0:
                                i += accent[0]

                            chord_note = self._get_core_note(line, i, Obj(), False)
                            if chord_note is not None and chord_note.pitch is not None:
                                if accent[0] > 0:  # If we found a decoration above, it modifies the entire chord. "style" is handled below.
                                    if (accent[1] or "").find("style=") != 0:
                                        if self.el.decoration is None:
                                            self.el.decoration = []
                                        self.el.decoration.append(accent[1])
                                if chord_note.end_beam:
                                    self.el.end_beam = True
                                    del chord_note.end_beam
                                if self.el.pitches is None:
                                    self.el.duration = chord_note.duration
                                    self.el.pitches = [chord_note]
                                else:  # Just ignore the note lengths of all but the first note.
                                    self.el.pitches.append(chord_note)
                                chord_note.pop('duration', None)
                                if accent[0] > 0:  # If we found a style above, it modifies the individual pitch, not the entire chord.
                                    if (accent[1] or "").find("style=") == 0:
                                        self.el.pitches[-1].style = substr(accent[1], 6)

                                n = len(self.el.pitches)
                                if mv.inTieChord.get(n):
                                    chord_note.endTie = True
                                    mv.inTieChord[n] = None
                                if chord_note.startTie:
                                    mv.inTieChord[n] = True

                                i = chord_note.endChar
                                del chord_note.endChar
                            elif at(line, i) == ' ':
                                # Spaces are not allowed in chords, but we can recover from it by ignoring it.
                                warn("Spaces are not allowed in chords", line, i)
                                i += 1
                            else:
                                if i < len(line) and line[i] == ']':
                                    # consume the close bracket
                                    i += 1

                                    if mv.next_note_duration != 0:
                                        self.el.duration = self.el.duration * mv.next_note_duration if self.el.duration is not None else float('nan')
                                        mv.next_note_duration = 0

                                    if _is_in_tie(mv, overlay_level, self.el):
                                        for pitch in self.el.pitches:
                                            pitch.endTie = True
                                        _set_is_in_tie(mv, overlay_level, False)

                                    if triplet_notes_left > 0 and not (self.el.rest and self.el.rest.type == "spacer"):
                                        triplet_notes_left -= 1
                                        if triplet_notes_left == 0:
                                            self.el.endTriplet = True

                                    post_chord_done = False
                                    while i < len(line) and not post_chord_done:
                                        c = line[i]
                                        if c == ' ' or c == '\t':
                                            _add_end_beam(self.el)
                                        elif c == ')':
                                            if self.el.endSlur is None:
                                                self.el.endSlur = 1
                                            else:
                                                self.el.endSlur += 1
                                        elif c == '-':
                                            for pitch in self.el.pitches:
                                                pitch.startTie = Obj()
                                            _set_is_in_tie(mv, overlay_level, True)
                                        elif c == '>' or c == '<':
                                            br2 = _get_broken_rhythm(line, i)
                                            i += br2[0] - 1  # index gets incremented below, so we'll let that happen
                                            mv.next_note_duration = br2[2]
                                            if truthy(chord_duration):
                                                chord_duration = chord_duration * br2[1]
                                            else:
                                                chord_duration = br2[1]
                                        elif c in '123456789/':
                                            fraction = tokenizer.get_fraction(line, i)
                                            chord_duration = fraction.value
                                            i = fraction.index
                                            ch = at(line, i)
                                            if ch == ' ':
                                                remember_end_beam = True
                                            if ch == '-' or ch == ')' or ch == ' ' or ch == '<' or ch == '>':
                                                i -= 1  # Subtracting one because one is automatically added below
                                            else:
                                                post_chord_done = True
                                        elif c == '0':
                                            chord_duration = 0
                                        else:
                                            post_chord_done = True
                                        if not post_chord_done:
                                            i += 1
                                else:
                                    warn("Expected ']' to end the chords", line, i)

                                if self.el.pitches is not None:
                                    if chord_duration is not None:
                                        self.el.duration = self.el.duration * chord_duration
                                        if remember_end_beam:
                                            _add_end_beam(self.el)

                                    mv.add_formatting_options(self.el, tune.formatting, 'note')
                                    tune_builder.append_element('note', start_of_line + start_i, start_of_line + i, self.el)
                                    mv.measureNotEmpty = True
                                    self.el = Obj()
                                done = True
                    else:
                        # Single pitch
                        el2 = Obj()
                        core = self._get_core_note(line, i, el2, True)
                        if el2.endTie is not None:
                            _set_is_in_tie(mv, overlay_level, True)
                        if core is not None:
                            el = self.el
                            if core.pitch is not None:
                                el.pitches = [Obj()]
                                # TODO-PER: straighten this out so there is not so much copying: getCoreNote shouldn't change e'
                                if core.accidental is not None:
                                    el.pitches[0].accidental = core.accidental
                                el.pitches[0].pitch = core.pitch
                                el.pitches[0].name = core.name
                                if core.midipitch or core.midipitch == 0:
                                    if 'midipitch' in core:
                                        el.pitches[0].midipitch = core.midipitch
                                if core.endSlur is not None:
                                    el.pitches[0].endSlur = core.endSlur
                                if core.endTie is not None:
                                    el.pitches[0].endTie = core.endTie
                                if core.startSlur is not None:
                                    el.pitches[0].startSlur = core.startSlur
                                if el.startSlur is not None:
                                    el.pitches[0].startSlur = el.startSlur
                                if el.dottedSlur is not None:
                                    el.pitches[0].dottedSlur = True
                                if core.startTie is not None:
                                    el.pitches[0].startTie = core.startTie
                                if el.startTie is not None:
                                    el.pitches[0].startTie = el.startTie
                            else:
                                el.rest = core.rest
                                if core.rest.type == 'multimeasure' and self._is_first_voice():
                                    mv.currBarNumber += core.rest.text - 1  # The minus one is because the measure with the rest is already counted once normally.
                                if core.endSlur is not None:
                                    el.endSlur = core.endSlur
                                if core.endTie is not None:
                                    el.rest.endTie = core.endTie
                                if core.startSlur is not None:
                                    el.startSlur = core.startSlur
                                if core.startTie is not None:
                                    el.rest.startTie = core.startTie
                                if el.startTie is not None:
                                    el.rest.startTie = el.startTie

                            if core.chord is not None:
                                el.chord = core.chord
                            if core.duration is not None:
                                el.duration = core.duration
                            if core.decoration is not None:
                                el.decoration = core.decoration
                            if core.graceNotes is not None:
                                el.graceNotes = core.graceNotes
                            el.pop('startSlur', None)
                            el.pop('dottedSlur', None)
                            if _is_in_tie(mv, overlay_level, el):
                                if el.pitches is not None:
                                    el.pitches[0].endTie = True
                                elif el.rest.type != 'spacer':
                                    el.rest.endTie = True
                                _set_is_in_tie(mv, overlay_level, False)
                            if core.startTie or el.startTie:
                                _set_is_in_tie(mv, overlay_level, True)
                            i = core.endChar

                            if triplet_notes_left > 0 and not (core.rest and core.rest.type == "spacer"):
                                triplet_notes_left -= 1
                                if triplet_notes_left == 0:
                                    el.endTriplet = True

                            if core.end_beam:
                                _add_end_beam(el)

                            # If there is a whole rest, then it should be the duration of the measure, not it's own duration. We need to special case it.
                            # If the time signature length is greater than 4/4, though, then a whole rest has no special treatment.
                            if el.rest and el.rest.type == 'rest' and el.duration == 1 and _duration_of_measure(mv) <= 1:
                                el.rest.type = 'whole'
                                el.duration = _duration_of_measure(mv)

                            # Create a warning if this is not a displayable duration.
                            # The first item on a line is a regular note value, each item after that represents a dot placed after the previous note.
                            # Only durations less than a whole note are tested because whole note durations have some tricky rules.
                            if el.duration is not None and el.duration < 1 and el.duration not in durations and el.duration != 0:
                                if not el.rest or el.rest.type != 'spacer':
                                    warn("Duration not representable: " + substring(line, start_i, i), line, i)

                            mv.add_formatting_options(el, tune.formatting, 'note')
                            succeeded = tune_builder.append_element('note', start_of_line + start_i, start_of_line + i, el)
                            if not succeeded:
                                self.start_new_line()
                                tune_builder.append_element('note', start_of_line + start_i, start_of_line + i, el)
                            mv.measureNotEmpty = True
                            self.el = Obj()

                if i == start_i:  # don't know what this is, so ignore it.
                    if at(line, i) != ' ' and at(line, i) != '`':
                        warn("Unknown character ignored", line, i)
                    i += 1
        self.line_continuation = line.find('\x12') >= 0 or (ret_header[0] > 0)
        if not self.line_continuation:
            self.el = Obj()

    # -- pieces of a note group -----------------------------------------------
    def _letter_to_chord(self, line, i):
        mv = self.multiline_vars
        warn = self.warn
        tokenizer = self.tokenizer
        if at(line, i) == '"':
            chord = tokenizer.get_bracketted_substring(line, i, 5)
            if not chord[2]:
                warn("Missing the closing quote while parsing the chord symbol", line, i)
            # If it starts with ^, then the chord appears above.
            # If it starts with _ then the chord appears below.
            # (note that the 2.0 draft standard defines them as not chords, but annotations and also defines @.)
            first = at(chord[1], 0)
            if chord[0] > 0 and len(chord[1]) > 0 and first == '^':
                chord[1] = chord[1][1:]
                chord[2] = 'above'
            elif chord[0] > 0 and len(chord[1]) > 0 and first == '_':
                chord[1] = chord[1][1:]
                chord[2] = 'below'
            elif chord[0] > 0 and len(chord[1]) > 0 and first == '<':
                chord[1] = chord[1][1:]
                chord[2] = 'left'
            elif chord[0] > 0 and len(chord[1]) > 0 and first == '>':
                chord[1] = chord[1][1:]
                chord[2] = 'right'
            elif chord[0] > 0 and len(chord[1]) > 0 and first == '@':
                # @-15,5.7
                chord[1] = chord[1][1:]
                x = tokenizer.get_float(chord[1])
                if x.digits == 0:
                    warn("Missing first position in absolutely positioned annotation.", line, i)
                    chord[1] = chord[1].replace("@", "", 1)
                    chord[2] = 'above'
                    return chord
                chord[1] = chord[1][x.digits:]
                if at(chord[1], 0) != ',':
                    warn("Missing comma absolutely positioned annotation.", line, i)
                    chord[1] = chord[1].replace("@", "", 1)
                    chord[2] = 'above'
                    return chord
                chord[1] = chord[1][1:]
                y = tokenizer.get_float(chord[1])
                if y.digits == 0:
                    warn("Missing second position in absolutely positioned annotation.", line, i)
                    chord[1] = chord[1].replace("@", "", 1)
                    chord[2] = 'above'
                    return chord
                chord[1] = chord[1][y.digits:]
                ws = tokenizer.skip_white_space(chord[1])
                chord[1] = chord[1][ws:]
                chord[2] = None
                chord.append(Obj(x=x.value, y=y.value))
            else:
                if mv.freegchord is not True:
                    s = chord[1]
                    s = re.sub(r"([ABCDEFG0-9])b", r"\1♭", s)
                    s = re.sub(r"([ABCDEFG0-9])#", r"\1♯", s)
                    s = re.sub(r"^([ABCDEFG])([♯♭]?)o([^A-Za-z])", r"\1\2°\3", s)
                    s = re.sub(r"^([ABCDEFG])([♯♭]?)o$", r"\1\2°", s)
                    s = re.sub(r"^([ABCDEFG])([♯♭]?)0([^A-Za-z])", r"\1\2ø\3", s)
                    s = re.sub(r"^([ABCDEFG])([♯♭]?)\^([^A-Za-z])", r"\1\2∆\3", s)
                    chord[1] = s
                chord[2] = 'default'
                chord[1] = transpose.chord_name(mv, chord[1])
            return chord
        return [0, ""]

    def _letter_to_grace(self, line, i):
        mv = self.multiline_vars
        warn = self.warn
        # Grace notes are an array of: startslur, note, endslur, space; where note is accidental, pitch, duration
        if at(line, i) == '{':
            # fetch the gracenotes string and consume that into the array
            gra = self.tokenizer.get_bracketted_substring(line, i, 1, '}')
            if not gra[2]:
                warn("Missing the closing '}' while parsing grace note", line, i)
            # If there is a slur after the grace construction, then move it to the last note inside the grace construction
            if at(line, i + gra[0]) == ')':
                gra[0] += 1
                gra[1] += ')'

            gracenotes = []
            ii = 0
            in_tie = False
            while ii < len(gra[1]):
                acciaccatura = False
                if gra[1][ii] == '/':
                    acciaccatura = True
                    ii += 1
                note = self._get_core_note(gra[1], ii, Obj(), False)
                if note is not None:
                    # The grace note durations should not be affected by the default length: they should be based on 1/16, so if that isn't the default, then multiply here.
                    note.duration = note.duration / (mv.default_length * 8)
                    if acciaccatura:
                        note.acciaccatura = True
                    if note.rest:
                        # don't allow rests inside gracenotes
                        warn("Rests not allowed as grace notes '" + js_str(at(gra[1], ii)) + "' while parsing grace note", line, i)
                    else:
                        gracenotes.append(note)

                    if in_tie:
                        note.endTie = True
                        in_tie = False
                    if note.startTie:
                        in_tie = True

                    ii = note.endChar
                    del note.endChar

                    if note.end_beam:
                        note.endBeam = True
                        del note.end_beam
                else:
                    # We shouldn't get anything but notes or a space here, so report an error
                    if at(gra[1], ii) == ' ':
                        if len(gracenotes) > 0:
                            gracenotes[-1].endBeam = True
                    else:
                        warn("Unknown character '" + js_str(at(gra[1], ii)) + "' while parsing grace note", line, i)
                    ii += 1
            if len(gracenotes):
                return [gra[0], gracenotes]
        return [0]

    def _letter_to_accent(self, line, i):
        mv = self.multiline_vars
        warn = self.warn
        c = at(line, i)
        macro = mv.macros.get(c) if c is not None else None

        if macro is not None:
            if at(macro, 0) == '!' or at(macro, 0) == '+':
                macro = macro[1:]
            if at(macro, len(macro) - 1) == '!' or at(macro, len(macro) - 1) == '+':
                macro = macro[0:len(macro) - 1]
            if macro in legal_accents:
                return [1, macro]
            elif macro in volume_decorations:
                if mv.volumePosition == 'hidden':
                    macro = ""
                return [1, macro]
            elif macro in dynamic_decorations:
                if mv.dynamicPosition == 'hidden':
                    macro = ""
                return [1, macro]
            else:
                if macro not in mv.ignoredDecorations:
                    warn("Unknown macro: " + macro, line, i)
                return [1, '']
        if c == '.':
            if at(line, i + 1) == '(' or at(line, i + 1) == '-':  # a dot then open paren is a dotted slur; likewise dot dash is dotted tie.
                return [0, 0]
            return [1, 'staccato']
        if c == 'u':
            return [1, 'upbow']
        if c == 'v':
            return [1, 'downbow']
        if c == '~':
            return [1, 'irishroll']
        if c == '!' or c == '+':
            ret = self.tokenizer.get_bracketted_substring(line, i, 5)
            # Be sure that the accent is recognizable.
            if len(ret[1]) > 1 and (ret[1][0] == '^' or ret[1][0] == '_'):
                ret[1] = ret[1][1:]  # The test files have indicators forcing the ornament to the top or bottom, but that isn't in the standard. We'll just ignore them.
            if ret[1] in legal_accents or ret[1].find('class=') == 0:
                return ret
            if ret[1] in volume_decorations:
                if mv.volumePosition == 'hidden':
                    ret[1] = ''
                return ret
            if ret[1] in dynamic_decorations:
                if mv.dynamicPosition == 'hidden':
                    ret[1] = ''
                return ret

            for acc in accent_pseudonyms:
                if ret[1] == acc[0]:
                    ret[1] = acc[1]
                    return ret

            for acc in accent_dynamic_pseudonyms:
                if ret[1] == acc[0]:
                    ret[1] = acc[1]
                    if mv.dynamicPosition == 'hidden':
                        ret[1] = ''
                    return ret

            # We didn't find the accent in the list, so consume the space, but don't return an accent.
            # Although it is possible that ! was used as a line break, so accept that.
            if c == '!' and (ret[0] == 1 or at(line, i + ret[0] - 1) != '!'):
                return [1, None]
            warn("Unknown decoration: " + ret[1], line, i)
            ret[1] = ""
            return ret
        simple = {'H': 'fermata', 'J': 'slide', 'L': 'accent', 'M': 'mordent', 'O': 'coda',
                  'P': 'pralltriller', 'R': 'roll', 'S': 'segno', 'T': 'trill', 't': 'trillh'}
        if c is not None and c in simple:
            return [1, simple[c]]
        return [0, 0]

    def _letter_to_bar(self, line, curr_pos):
        # returns the class of the bar line
        # the number of the repeat
        # and the number of characters used up
        # if 0 is returned, then the next element was not a bar line
        tokenizer = self.tokenizer
        ret = tokenizer.get_bar_line(line, curr_pos)
        if ret.len == 0:
            return [0, ""]
        if ret.warn:
            self.warn(ret.warn, line, curr_pos)
            return [ret.len, ""]

        # Now see if this is a repeated ending
        # A repeated ending is all of the characters 1,2,3,4,5,6,7,8,9,0,-, and comma
        # It can also optionally start with '[', which is ignored.
        # Also, it can have white space before the '['.
        ws = 0
        while ws < len(line):
            if at(line, curr_pos + ret.len + ws) != ' ':
                break
            ws += 1
        orig_bar_len = ret.len
        if at(line, curr_pos + ret.len + ws) == '[':
            ret.len += ws + 1

        # It can also be a quoted string. It is unclear whether that construct requires '[', but it seems like it would. otherwise it would be confused with a regular chord.
        if at(line, curr_pos + ret.len) == '"' and at(line, curr_pos + ret.len - 1) == '[':
            ending = tokenizer.get_bracketted_substring(line, curr_pos + ret.len, 5)
            return [ret.len + ending[0], ret.token, ending[1]]
        ret_rep = tokenizer.get_token_of(line[curr_pos + ret.len:], "1234567890-,")
        if ret_rep.len == 0 or ret_rep.token[0] == '-':
            return [orig_bar_len, ret.token]

        return [ret.len + ret_rep.len, ret.token, ret_rep.token]

    def _letter_to_open_slurs_and_triplets(self, line, i):
        # consume spaces, and look for all the open parens. If there is a number after the open paren,
        # that is a triplet. Otherwise that is a slur. Collect all the slurs and the first triplet.
        warn = self.warn
        ret = Obj()
        start = i
        if at(line, i) == '.' and at(line, i + 1) == '(':
            ret.dottedSlur = True
            i += 1
        while at(line, i) == '(' or is_white_space(at(line, i)):
            if at(line, i) == '(':
                if i + 1 < len(line) and (at(line, i + 1) is not None and '2' <= line[i + 1] <= '9'):
                    if ret.triplet is not None:
                        warn("Can't nest triplets", line, i)
                    else:
                        ret.triplet = ord(line[i + 1]) - 48
                        ret.tripletQ = triplet_q.get(ret.triplet)
                        ret.num_notes = ret.triplet
                        if i + 2 < len(line) and line[i + 2] == ':':
                            # We are expecting "(p:q:r" or "(p:q" or "(p::r"
                            # That is: "put p notes into the time of q for the next r notes"
                            # if r is missing, then it is equal to p.
                            # if q is missing, it is determined from the tripletQ table
                            if i + 3 < len(line) and line[i + 3] == ':':
                                # The second number, 'q', is not present.
                                if i + 4 < len(line) and _is_digit_1_9(line[i + 4]):
                                    ret.num_notes = ord(line[i + 4]) - 48
                                    i += 3
                                else:
                                    warn("expected number after the two colons after the triplet to mark the duration", line, i)
                            elif i + 3 < len(line) and _is_digit_1_9(line[i + 3]):
                                ret.tripletQ = ord(line[i + 3]) - 48
                                if i + 4 < len(line) and line[i + 4] == ':':
                                    if i + 5 < len(line) and _is_digit_1_9(line[i + 5]):
                                        ret.num_notes = ord(line[i + 5]) - 48
                                        i += 4
                                else:
                                    i += 2
                            else:
                                warn("expected number after the triplet to mark the duration", line, i)
                    i += 1
                else:
                    if ret.startSlur is None:
                        ret.startSlur = 1
                    else:
                        ret.startSlur += 1
            i += 1
        ret.consumed = i - start
        return ret

    def start_new_line(self):
        mv = self.multiline_vars
        key_voice = self.key_voice
        params = Obj(startChar=-1, endChar=-1)
        if mv.partForNextLine.title:
            params.part = mv.partForNextLine
        if mv.currentVoice and mv.staves[mv.currentVoice.staffNum].clef is not None:
            params.clef = Obj(mv.staves[mv.currentVoice.staffNum].clef)
        else:
            params.clef = Obj(mv.clef)
        score_transpose = mv.currentVoice.scoreTranspose if mv.currentVoice else 0
        params.key = key_voice.standard_key(mv.key.root + mv.key.acc + mv.key.mode, mv.key.root, mv.key.acc, score_transpose)
        params.key.mode = mv.key.mode
        if mv.key.impliedNaturals is not None:
            params.key.impliedNaturals = mv.key.impliedNaturals
        if mv.key.explicitAccidentals is not None:
            for ea in mv.key.explicitAccidentals:
                found = False
                for a in params.key.accidentals:
                    if a.note == ea.note:
                        # If the note is already in the list, override it with the new value
                        a.acc = ea.acc
                        found = True
                if not found:
                    params.key.accidentals.append(ea)
        mv.targetKey = params.key
        if params.key.explicitAccidentals:
            del params.key.explicitAccidentals
        key_voice_mod.add_pos_to_key(params.clef, params.key)
        if mv.meter is not None:
            if mv.currentVoice:
                for st in mv.staves:
                    st.meter = mv.meter
                params.meter = mv.staves[mv.currentVoice.staffNum].meter
                mv.staves[mv.currentVoice.staffNum].meter = None
            else:
                params.meter = mv.meter
            mv.meter = None
        elif mv.currentVoice and mv.staves[mv.currentVoice.staffNum].meter:
            # Make sure that each voice gets the meter marking.
            params.meter = mv.staves[mv.currentVoice.staffNum].meter
            mv.staves[mv.currentVoice.staffNum].meter = None
        if mv.currentVoice and mv.currentVoice.name:
            params.name = mv.currentVoice.name
        if mv.vocalfont:
            params.vocalfont = mv.vocalfont
        if mv.tripletfont:
            params.tripletfont = mv.tripletfont
        if mv.gchordfont:
            params.gchordfont = mv.gchordfont
        if mv.style:
            params.style = mv.style
        if mv.currentVoice:
            staff = mv.staves[mv.currentVoice.staffNum]
            if staff.brace:
                params.brace = staff.brace
            if staff.bracket:
                params.bracket = staff.bracket
            if staff.connectBarLines:
                params.connectBarLines = staff.connectBarLines
            if staff.name:
                v = at(staff.name, mv.currentVoice.index)
                if v is not None:
                    params.name = v
                else:
                    params.pop('name', None)
            if staff.subname:
                v = at(staff.subname, mv.currentVoice.index)
                if v is not None:
                    params.subname = v
            if mv.currentVoice.stem:
                params.stem = mv.currentVoice.stem
            if truthy(mv.currentVoice.stafflines):
                params.stafflines = mv.currentVoice.stafflines
            if truthy(mv.currentVoice.staffscale):
                params.staffscale = mv.currentVoice.staffscale
            if truthy(mv.currentVoice.scale):
                params.scale = mv.currentVoice.scale
            if mv.currentVoice.color:
                params.color = mv.currentVoice.color
            if mv.currentVoice.style:
                params.style = mv.currentVoice.style
            if truthy(mv.currentVoice.transpose):
                params.clef.transpose = mv.currentVoice.transpose
            params.currentVoice = mv.currentVoice
            for vname in mv.voices:
                if params.currentVoice.staffNum == mv.voices[vname].staffNum and params.currentVoice.index == mv.voices[vname].index:
                    params.currentVoiceName = vname
        if mv.barNumbers == 0 and self._is_first_voice() and mv.currBarNumber != 1:
            params.barNumber = mv.currBarNumber
        self.tune_builder.start_new_line(params)
        if mv.key.impliedNaturals is not None:
            del mv.key.impliedNaturals

        mv.partForNextLine = Obj()
        if len(mv.tempoForNextLine) == 4:
            self.tune_builder.append_element(mv.tempoForNextLine[0], mv.tempoForNextLine[1], mv.tempoForNextLine[2], mv.tempoForNextLine[3])
        mv.tempoForNextLine = []

    def _get_core_note(self, line, index, el, can_have_broken_rhythm):
        mv = self.multiline_vars
        tokenizer = self.tokenizer
        tune = self.tune

        def is_complete(state):
            return state in ('octave', 'duration', 'Zduration', 'broken_rhythm', 'end_slur')

        dotted_tie = None
        if at(line, index) == '.' and at(line, index + 1) == '-':
            dotted_tie = True
            index += 1
        state = 'startSlur'
        duration_set_by_previous_note = False
        while True:
            c = at(line, index)
            if c == '(':
                if state == 'startSlur':
                    if el.startSlur is None:
                        el.startSlur = 1
                    else:
                        el.startSlur += 1
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == ')':
                if is_complete(state):
                    if el.endSlur is None:
                        el.endSlur = 1
                    else:
                        el.endSlur += 1
                else:
                    return None
            elif c == '^':
                if state == 'startSlur':
                    el.accidental = 'sharp'
                    state = 'sharp2'
                elif state == 'sharp2':
                    el.accidental = 'dblsharp'
                    state = 'pitch'
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == '_':
                if state == 'startSlur':
                    el.accidental = 'flat'
                    state = 'flat2'
                elif state == 'flat2':
                    el.accidental = 'dblflat'
                    state = 'pitch'
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == '=':
                if state == 'startSlur':
                    el.accidental = 'natural'
                    state = 'pitch'
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c is not None and c in 'ABCDEFGabcdefg':
                if state in ('startSlur', 'sharp2', 'flat2', 'pitch'):
                    el.pitch = pitches[c]
                    octave = mv.currentVoice.octave if (mv.currentVoice and mv.currentVoice.octave is not None) else mv.octave
                    el.pitch += 7 * octave
                    if isinstance(el.pitch, float) and el.pitch == int(el.pitch):
                        el.pitch = int(el.pitch)
                    el.name = c
                    if el.accidental:
                        el.name = acc_map[el.accidental] + el.name
                    transpose.note(mv, el)
                    state = 'octave'
                    # At this point we have a valid note. The rest is optional. Set the duration in case we don't get one below
                    if can_have_broken_rhythm and mv.next_note_duration != 0:
                        el.duration = mv.default_length * mv.next_note_duration
                        mv.next_note_duration = 0
                        duration_set_by_previous_note = True
                    else:
                        el.duration = mv.default_length
                    # If the clef is percussion, there is probably some translation of the pitch to a particular drum kit item.
                    if (mv.clef and mv.clef.type == "perc") or (mv.currentVoice and mv.currentVoice.clef == "perc"):
                        key = c
                        if el.accidental:
                            key = acc_map[el.accidental] + key
                        if tune.formatting and tune.formatting.midi and tune.formatting.midi.drummap:
                            el.midipitch = tune.formatting.midi.drummap.get(key)
                            if el.midipitch is None:
                                del el.midipitch
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == ',':
                if state == 'octave':
                    el.pitch -= 7
                    el.name += ','
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == "'":
                if state == 'octave':
                    el.pitch += 7
                    el.name += "'"
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c is not None and c in 'xXyzZ':
                if state == 'startSlur':
                    el.rest = Obj(type=rests[c])
                    # There shouldn't be some of the properties that notes have. If some sneak in due to bad syntax in the abc file,
                    # just nix them here.
                    for k in ('accidental', 'startSlur', 'startTie', 'endSlur', 'endTie', 'end_beam', 'grace_notes'):
                        el.pop(k, None)
                    # At this point we have a valid note. The rest is optional. Set the duration in case we don't get one below
                    if 'multimeasure' in el.rest.type:
                        el.duration = tune.get_bar_length()
                        el.rest.text = 1
                        state = 'Zduration'
                    else:
                        if can_have_broken_rhythm and mv.next_note_duration != 0:
                            el.duration = mv.default_length * mv.next_note_duration
                            mv.next_note_duration = 0
                            duration_set_by_previous_note = True
                        else:
                            el.duration = mv.default_length
                        state = 'duration'
                elif is_complete(state):
                    el.endChar = index
                    return el
                else:
                    return None
            elif c is not None and c in '1234567890/':
                if state == 'octave' or state == 'duration':
                    fraction = tokenizer.get_fraction(line, index)
                    el.duration = el.duration * fraction.value
                    # TODO-PER: We can test the returned duration here and give a warning if it isn't the one expected.
                    el.endChar = fraction.index
                    while fraction.index < len(line) and (is_white_space(line[fraction.index]) or line[fraction.index] == '-'):
                        if line[fraction.index] == '-':
                            el.startTie = Obj()
                        else:
                            el = _add_end_beam(el)
                        fraction.index += 1
                    index = fraction.index - 1
                    state = 'broken_rhythm'
                elif state == 'sharp2':
                    el.accidental = 'quartersharp'
                    state = 'pitch'
                elif state == 'flat2':
                    el.accidental = 'quarterflat'
                    state = 'pitch'
                elif state == 'Zduration':
                    num = tokenizer.get_number(line, index)
                    el.duration = num.num * tune.get_bar_length()
                    el.rest.text = num.num
                    el.endChar = num.index
                    return el
                else:
                    return None
            elif c == '-':
                if state == 'startSlur':
                    # This is the first character, so it must have been meant for the previous note. Correct that here.
                    self.tune_builder.add_tie_to_last_note(dotted_tie)
                    el.endTie = True
                elif state in ('octave', 'duration', 'end_slur'):
                    el.startTie = Obj()
                    if not duration_set_by_previous_note and can_have_broken_rhythm:
                        state = 'broken_rhythm'
                    else:
                        # Peek ahead to the next character. If it is a space, then we have an end beam.
                        if is_white_space(at(line, index + 1)):
                            _add_end_beam(el)
                        el.endChar = index + 1
                        return el
                elif state == 'broken_rhythm':
                    el.endChar = index
                    return el
                else:
                    return None
            elif c == ' ' or c == '\t':
                if is_complete(state):
                    el.end_beam = True
                    # look ahead to see if there is a tie
                    dotted_tie = False
                    while True:
                        if at(line, index) == '.' and at(line, index + 1) == '-':
                            dotted_tie = True
                            index += 1
                        if at(line, index) == '-':
                            el.startTie = Obj()
                            if dotted_tie:
                                el.startTie.style = "dotted"
                        index += 1
                        if not ((index < len(line) and (is_white_space(at(line, index)) or at(line, index) == '-')) or
                                (at(line, index) == '.' and at(line, index + 1) == '-')):
                            break
                    el.endChar = index
                    if not duration_set_by_previous_note and can_have_broken_rhythm and (at(line, index) == '<' or at(line, index) == '>'):
                        index -= 1
                        state = 'broken_rhythm'
                    else:
                        return el
                else:
                    return None
            elif c == '>' or c == '<':
                if is_complete(state):
                    if can_have_broken_rhythm:
                        br2 = _get_broken_rhythm(line, index)
                        index += br2[0] - 1  # index gets incremented below, so we'll let that happen
                        mv.next_note_duration = br2[2]
                        el.duration = br2[1] * el.duration
                        state = 'end_slur'
                    else:
                        el.endChar = index
                        return el
                else:
                    return None
            else:
                if is_complete(state):
                    el.endChar = index
                    return el
                return None
            index += 1
            if index == len(line):
                if is_complete(state):
                    el.endChar = index
                    return el
                return None
