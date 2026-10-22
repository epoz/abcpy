"""Tablature for string instruments (port of abcjs ``src/tablatures``).

Pass ``tablature=[{'instrument': 'guitar', ...}]`` in the render parameters to
get a tablature staff under each staff (``violin``, ``fiddle``, ``mandolin``,
``guitar`` and ``fiveString`` are known).
"""

import re

from ..jsutil import Obj, at, js_str, js_round, js_max, parse_int, truthy
from ..synth.midi_tables import note_to_midi, midi_to_note
from ..write.creation.elements import AbsoluteElement, RelativeElement, VoiceElement
from ..write.helpers import spacing

# Existing tab classes
plugin_tab = {
    'violin': Obj(name='StringTab', defaultTuning=['G,', 'D', 'A', 'e'], isTabBig=False, tabSymbolOffset=0),
    'fiddle': Obj(name='StringTab', defaultTuning=['G,', 'D', 'A', 'e'], isTabBig=False, tabSymbolOffset=0),
    'mandolin': Obj(name='StringTab', defaultTuning=['G,', 'D', 'A', 'e'], isTabBig=False, tabSymbolOffset=0),
    'guitar': Obj(name='StringTab', defaultTuning=['E,', 'A,', 'D', 'G', 'B', 'e'], isTabBig=True, tabSymbolOffset=0),
    'fiveString': Obj(name='StringTab', defaultTuning=['C,', 'G,', 'D', 'A', 'e'], isTabBig=False, tabSymbolOffset=-.95),
}


def _set_error(tune, msg):
    if tune.warnings:
        tune.warnings.append(msg)
    else:
        tune.warnings = [msg]


def prepare_plugins(tune, tune_number, params):
    """Called after parsing a tune and before engraving it."""
    returned = None
    if params.tablature:
        # validate requested plugins
        tabs = params.tablature
        returned = []
        for args in tabs:
            instrument = args.get('instrument')
            if instrument is None:
                _set_error(tune, "tablature 'instrument' is missing")
                return returned
            tab_name = plugin_tab.get(instrument)
            plugin = StringTabPlugin if tab_name else None
            if plugin:
                if params.visualTranspose != 0:
                    # populate transposition request to tabs
                    args['visualTranspose'] = params.visualTranspose
                args['abcSrc'] = None
                returned.append(Obj(classz=plugin, tuneNumber=tune_number, params=args, instance=None, tabType=tab_name))
            elif instrument == '':
                # create a placeholder - there is no tab for this staff
                returned.append(None)
            else:
                # unknown tab plugin
                _set_error(tune, 'Undefined tablature plugin: ' + js_str(instrument))
                return returned
    return returned


def layout_tablatures(renderer, abc_tune):
    tabs = abc_tune.tablatures

    # check tabs request for each staffs
    staff_line_count = 0

    # Clear the suppression flag
    if tabs and len(tabs) > 0:
        for t in tabs:
            if t and t.params.get('firstStaffOnly'):
                t.params['suppress'] = False

    for line in abc_tune.lines:
        if line.staff:
            staff_line_count += 1

        # If tab param "firstStaffOnly", remove the tab label after the first staff
        if staff_line_count > 1:
            if tabs and len(tabs) > 0:
                for t in tabs:
                    if t.params.get('firstStaffOnly'):
                        # Set the staff draw suppression flag
                        t.params['suppress'] = True

        cur_staff = line.staff
        if cur_staff:
            max_staves = len(cur_staff)
            jj = 0
            while jj < len(cur_staff):
                if at(tabs, jj) and jj < max_staves:
                    # tablature requested for staff
                    tab_plugin = tabs[jj]
                    if tab_plugin.instance is None:
                        tab_plugin.instance = tab_plugin.classz()
                        tab_plugin.instance.init(abc_tune, tab_plugin.tuneNumber, tab_plugin.params, tab_plugin.tabType)
                    # render next
                    tab_plugin.instance.render(renderer, line, jj)
                jj += 1


# -- tab-note.js --------------------------------------------------------------------------

class TabNote:
    def __init__(self, note, clef_transpose=None):
        pitch = note_to_midi(note)
        if clef_transpose:
            pitch += clef_transpose
        new_note = midi_to_note(pitch)
        is_flat = False
        is_sharp = False
        natural = None
        quarter = None
        is_double = False
        acc = 0

        if note.startswith('_'):
            is_flat = True
            acc = -1
            # check quarter flat
            if at(note, 1) == '/':
                is_flat = False
                quarter = "v"
                acc = 0
            elif at(note, 1) == '_':
                # double flat
                is_double = True
                acc -= 1
        elif note.startswith('^'):
            is_sharp = True
            acc = +1
            # check quarter sharp
            if at(note, 1) == '/':
                is_sharp = False
                quarter = "^"
                acc = 0
            elif at(note, 1) == '^':
                # double sharp
                is_double = True
                acc += 1
        elif note.startswith('='):
            natural = True
            acc = 0
        is_altered = is_flat or is_sharp or (quarter is not None)
        if is_altered or natural:
            if quarter is not None or is_double:
                new_note = note[2:]
            else:
                new_note = note[1:]
        has_comma = new_note.count(',')
        has_quote = new_note.count("'")

        self.pitch = pitch
        self.pitchAltered = 0
        self.name = new_note
        self.acc = acc
        self.isSharp = is_sharp
        self.isKeySharp = False
        self.isDouble = is_double
        self.isAltered = is_altered
        self.isFlat = is_flat
        self.isKeyFlat = False
        self.natural = natural
        self.quarter = quarter
        self.isLower = self.name == self.name.lower()
        self.name = self.name[0].upper()
        self.hasComma = has_comma
        self.isQuoted = has_quote

    def _clone(self):
        n = TabNote(self.name)
        n.pitch = self.pitch
        n.hasComma = self.hasComma
        n.isLower = self.isLower
        n.isQuoted = self.isQuoted
        n.isSharp = self.isSharp
        n.isKeySharp = self.isKeySharp
        n.isFlat = self.isFlat
        n.isKeyFlat = self.isKeyFlat
        return n

    def same_note_as(self, note):
        return note.pitch == self.pitch

    def is_lower_than(self, note):
        return note.pitch > self.pitch

    def check_key_accidentals(self, accidentals, measure_accidentals):
        if self.isAltered or self.natural:
            return
        m = measure_accidentals.get(self.name.upper())
        if m:
            table = {"__": -2, "_": -1, "=": 0, "^": 1, "^^": 2}
            if m in table:
                self.acc = table[m]
                self.pitchAltered = table[m]
            return
        elif accidentals:
            cur_note = self.name
            for cur_acc in accidentals:
                if cur_note == cur_acc.note.upper():
                    if cur_acc.acc == 'flat':
                        self.acc = -1
                        self.isKeyFlat = True
                        self.pitchAltered = -1
                    if cur_acc.acc == 'sharp':
                        self.acc = +1
                        self.isKeySharp = True
                        self.pitchAltered = 1

    def get_accidental_equiv(self):
        cloned = self._clone()
        if cloned.isSharp or cloned.isKeySharp:
            cloned = cloned.next_note()
            cloned.isFlat = True
            cloned.isSharp = False
            cloned.isKeySharp = False
        elif cloned.isFlat or cloned.isKeyFlat:
            cloned = cloned.prev_note()
            cloned.isSharp = True
            cloned.isFlat = False
            cloned.isKeyFlat = False
        return cloned

    def next_note(self):
        return TabNote(midi_to_note(self.pitch + 1 + self.pitchAltered))

    def prev_note(self):
        return TabNote(midi_to_note(self.pitch - 1 + self.pitchAltered))

    def emit_no_accidentals(self):
        returned = self.name
        if self.isLower:
            returned = returned.lower()
        returned += "'" * self.isQuoted
        returned += "," * self.hasComma
        return returned

    def emit(self):
        returned = self.name
        if self.isSharp or self.isKeySharp:
            returned = '^' + returned
            if self.isDouble:
                returned = '^' + returned
        if self.isFlat or self.isKeyFlat:
            returned = '_' + returned
            if self.isDouble:
                returned = '_' + returned
        if self.quarter:
            if self.quarter == "^":
                returned = "^/" + returned
            else:
                returned = "_/" + returned
        if self.natural:
            returned = '=' + returned
        returned += ',' * self.hasComma
        if self.isLower:
            returned = returned.lower()
            returned += "'" * self.isQuoted
        return returned


# -- tab-notes.js -------------------------------------------------------------------------

_notes = ['A', 'B', 'C', 'D', 'E', 'F', 'G']


def tab_notes(from_note, to_note):
    from_n = TabNote(from_note)
    to_n = TabNote(to_note)
    # check that toN is not lower than fromN
    if to_n.is_lower_than(from_n):
        return Obj(error='Invalid string Instrument tuning : ' + to_n.emit() + ' string lower than ' + from_n.emit() + ' string')
    build_returned = []
    if from_n.name not in _notes or to_n.name not in _notes:
        return build_returned
    finished = False
    while not finished:
        build_returned.append(from_n.emit())
        from_n = from_n.next_note()
        if from_n.same_note_as(to_n):
            finished = True
    return build_returned


# -- string-patterns.js -------------------------------------------------------------------

def _build_capo(self):
    capo_tuning = None
    tuning = self.tuning
    if self.capo > 0:
        capo_tuning = []
        for t in tuning:
            cur_note = TabNote(t)
            for _ in range(self.capo):
                cur_note = cur_note.next_note()
            capo_tuning.append(cur_note.emit())
    return capo_tuning


def _build_patterns(self):
    tuning = self.tuning
    if self.capo > 0:
        tuning = self.capoTuning
    strings = [None] * len(tuning)
    pos = len(tuning) - 1
    for iii in range(len(tuning)):
        next_note = self.highestNote  # highest handled note
        if iii != len(tuning) - 1:
            next_note = tuning[iii + 1]
        string_notes = tab_notes(tuning[iii], next_note)
        if isinstance(string_notes, dict) and string_notes.error:
            return string_notes
        strings[pos] = string_notes
        pos -= 1
    return strings


def _build_second(first):
    seconds = [[]]
    strings = first.strings
    for iii in range(1, len(strings)):
        seconds.append(strings[iii - 1])
    return seconds


def _same_string(self, chord):
    for jjjj in range(len(chord) - 1):
        cur_pos = chord[jjjj]
        next_pos = chord[jjjj + 1]
        if cur_pos.str == next_pos.str:
            # same String => change lower pos
            if cur_pos.str == len(self.strings) - 1:
                # Invalid tab Chord position for instrument
                cur_pos.num = "?"
                next_pos.num = "?"
                return None
            # change lower pitch on lowest string
            if _lt(next_pos.num, cur_pos.num):
                next_pos.str += 1
                next_pos = _note_to_number(self, next_pos.note, next_pos.str, self.secondPos, len(self.strings[next_pos.str]))
            else:
                cur_pos.str += 1
                cur_pos = _note_to_number(self, cur_pos.note, cur_pos.str, self.secondPos, len(self.strings[cur_pos.str]))
            # update table
            chord[jjjj] = cur_pos
            chord[jjjj + 1] = next_pos
    return None


def _lt(a, b):
    from ..jsutil import lt, number
    return lt(number(a) if isinstance(a, str) else a, number(b) if isinstance(b, str) else b)


def _handle_chord_notes(self, notes):
    ret_notes = _ErrList()
    for n in notes:
        if n.endTie:
            continue
        note = TabNote(n.name, self.clefTranspose)
        note.check_key_accidentals(self.accidentals, self.measureAccidentals)
        cur_pos = _to_number(self, note)
        ret_notes.append(cur_pos)
    _same_string(self, ret_notes)
    return ret_notes


class _ErrList(list):
    error = None


def _note_to_number(self, note, string_number, second_position, first_size):
    strings = self.strings
    note.check_key_accidentals(self.accidentals, self.measureAccidentals)
    if second_position:
        strings = second_position
    note_name = note.emit_no_accidentals()
    num = strings[string_number].index(note_name) if note_name in strings[string_number] else -1
    acc = note.acc
    if num != -1:
        if second_position:
            num += first_size
        if (note.isFlat or note.acc == -1) and num == 0:
            # flat on 0 pos => previous string 7th position
            note_equiv = note.get_accidental_equiv()
            string_number += 1
            e = note_equiv.emit()
            num = strings[string_number].index(e) if e in strings[string_number] else -1
            acc = 0
        return Obj(num=num + acc, str=string_number, note=note)
    return None


def _to_number(self, note):
    if note.isAltered or note.natural:
        acc = None
        if note.isFlat:
            acc = "__" if note.isDouble else "_"
        elif note.isSharp:
            acc = "^^" if note.isDouble else "^"
        elif note.natural:
            acc = "="
        self.measureAccidentals[note.name.upper()] = acc
    for i in range(len(self.stringPitches) - 1, -1, -1):
        if note.pitch + note.pitchAltered >= self.stringPitches[i]:
            num = note.pitch + note.pitchAltered - self.stringPitches[i]
            if note.quarter == '^':
                num -= 0.5
            elif note.quarter == "v":
                num += 0.5
            return Obj(num=js_round(num), str=len(self.stringPitches) - 1 - i, note=note)  # reverse the strings because string 0 is on the bottom
    return Obj(num="?", str=len(self.stringPitches) - 1, note=note)


def _invalid_number(ret_notes, note):
    number = Obj(num="?", str=0, note=note)
    ret_notes.append(number)
    ret_notes.error = note.emit() + ': unexpected note for instrument'


class StringPatterns:
    """Common patterns for all string instruments."""

    def __init__(self, plugin):
        tuning = plugin.tuning
        capo = plugin.capo
        highest_note = plugin.params.get('highestNote')
        self.linePitch = plugin.linePitch
        self.highestNote = "a'"
        if highest_note:
            # override default
            self.highestNote = highest_note
        self.measureAccidentals = {}
        self.capo = 0
        if capo:
            self.capo = parse_int(capo, 10)
        self.transpose = plugin.transpose if plugin.transpose else 0
        self.tuning = tuning
        self.clefTranspose = None
        self.accidentals = None
        self.capoTuning = None
        self.stringPitches = []
        for t in self.tuning:
            pitch = note_to_midi(t) + self.capo
            self.stringPitches.append(pitch)
        if self.capo > 0:
            self.capoTuning = _build_capo(self)
        self.strings = _build_patterns(self)
        if isinstance(self.strings, dict) and self.strings.error:
            plugin.set_error(self.strings.error)
            plugin.inError = True
            return
        # second position pattern per string
        self.secondPos = _build_second(self)

    def string_to_pitch(self, string_number):
        starting_pitch = 5.3
        bottom = len(self.strings) - 1
        return starting_pitch + ((bottom - string_number) * self.linePitch)

    def notes_to_number(self, notes, graces):
        error = None
        ret_notes = None
        if notes:
            ret_notes = _ErrList()
            if len(notes) > 1:
                ret_notes = _handle_chord_notes(self, notes)
                if ret_notes.error:
                    error = ret_notes.error
            else:
                if not notes[0].endTie:
                    note = TabNote(notes[0].name, self.clefTranspose)
                    note.check_key_accidentals(self.accidentals, self.measureAccidentals)
                    number = _to_number(self, note)
                    if number:
                        ret_notes.append(number)
                    else:
                        _invalid_number(ret_notes, note)
                        error = ret_notes.error
        if error:
            return ret_notes
        ret_graces = None
        if graces:
            ret_graces = _ErrList()
            for g in graces:
                note = TabNote(g.name, self.clefTranspose)
                note.check_key_accidentals(self.accidentals, self.measureAccidentals)
                number = _to_number(self, note)
                if number:
                    ret_graces.append(number)
                else:
                    _invalid_number(ret_graces, note)
                    error = ret_notes.error

        return Obj(notes=ret_notes, graces=ret_graces, error=error)

    def to_string(self):
        arr = []
        for t in self.tuning:
            s = t.replace(',', '').replace("'", '').upper()
            if at(s, 0) == '_':
                s = s[1] + 'b '
            elif at(s, 0) == '^':
                s = s[1] + "# "
            arr.append(s)
        return ''.join(arr)

    def tab_infos(self, plugin):
        name = plugin.params.get('label')
        if name:
            tune_pos = name.find('%T')
            tuning = ""
            if tune_pos != -1:
                tuning = self.to_string()
                if plugin.capo and parse_int(plugin.capo) > 0:
                    tuning += ' capo:' + js_str(plugin.capo)
                name = name.replace('%T', tuning, 1)
            return name
        return ''

    def suppress(self, plugin):
        return bool(plugin.params.get('suppress'))


# -- string-tablature.js ---------------------------------------------------------------------

class StringTablature:
    """Layout tablature informations for draw."""

    def __init__(self, num_lines, line_space):
        self.numLines = num_lines
        self.lineSpace = line_space
        self.verticalSize = self.numLines * self.lineSpace
        pitch = 3
        self.bar = Obj(pitch=pitch, pitch2=line_space * num_lines, height=5)
        self.height = None

    def bypass(self, line):
        """Return true if the current line should not produce a tab."""
        voices = line.staffGroup.voices
        if len(voices) > 0:
            if voices[0].isPercussion:
                return True
        return False

    def set_relative(self, child, relative, first):
        if child.type == 'bar':
            relative.pitch = self.bar.pitch
            relative.pitch2 = self.bar.pitch2
            relative.height = self.height
        elif child.type == 'symbol':
            top = self.bar.pitch2 / 2
            if child.name == 'dots.dot':
                if first:
                    relative.pitch = top
                    return False
                relative.pitch = top + self.lineSpace
                return True
        return first


# -- tab-string.js ---------------------------------------------------------------------------

class StringTabPlugin:
    def init(self, abc_tune, tune_number, params, tab_settings):
        self.tune = abc_tune
        self.params = params
        self.tuneNumber = tune_number
        self.inError = False
        self.abcTune = abc_tune
        self.linePitch = 3
        self.nbLines = len(tab_settings.defaultTuning)
        self.isTabBig = tab_settings.isTabBig
        self.tabSymbolOffset = tab_settings.tabSymbolOffset
        self.capo = params.get('capo')
        self.transpose = params.get('visualTranspose')
        self.hideTabSymbol = params.get('hideTabSymbol')
        self.tablature = StringTablature(self.nbLines, self.linePitch)
        tuning = params.get('tuning')
        if not tuning:
            tuning = tab_settings.defaultTuning
        self.tuning = tuning
        self.error = None
        self.semantics = StringPatterns(self)

    def set_error(self, error):
        if error:
            self.error = error
            self.inError = True
            if self.tune.warnings:
                self.tune.warnings.append(error)
            else:
                self.tune.warnings = [error]

    def render(self, renderer, line, staff_index):
        if self.inError:
            return
        if self.tablature.bypass(line):
            return
        tab_renderer(self, renderer, line, staff_index)


# -- tab-renderer.js ------------------------------------------------------------------------

def _init_special_y():
    return Obj(tempoHeightAbove=0, partHeightAbove=0, volumeHeightAbove=0, dynamicHeightAbove=0, endingHeightAbove=0,
               chordHeightAbove=0, lyricHeightAbove=0, lyricHeightBelow=0, chordHeightBelow=0, volumeHeightBelow=0,
               dynamicHeightBelow=0)


def _get_lyric_height(voice):
    max_lyric_height = 0
    for cur_abs in voice.children:
        if cur_abs.specialY:
            if cur_abs.specialY.lyricHeightBelow > max_lyric_height:
                max_lyric_height = cur_abs.specialY.lyricHeightBelow
    return max_lyric_height  # add spacing


def _build_tab_name(plugin, renderer, dest):
    string_semantics = plugin.semantics
    text_size = renderer.controller.getTextSize
    tab_name = string_semantics.tab_infos(plugin)
    suppress = string_semantics.suppress(plugin)
    if not suppress:
        size = text_size.calc(tab_name, 'tablabelfont', 'text instrumentname')
        dest.tabNameInfos = Obj(textSize=Obj(height=size.height, width=size.width), name=tab_name)
        return size.height
    return 0


def _is_last_tab_in_staff(index, staff_group):
    if staff_group[index].isTabStaff:
        if index == len(staff_group) - 1:
            return True
        if staff_group[index + 1].isTabStaff:
            return False
        return True
    return False


def _get_staff_numbers(staffs):
    return sum(1 for s in staffs if not s.isTabStaff)


def _get_parent_staff_index(staffs, index):
    for ii in range(index, -1, -1):
        if not staffs[ii].isTabStaff:
            return ii
    return -1


def _link_staff_and_tabs(staffs):
    for ii in range(len(staffs)):
        if staffs[ii].isTabStaff:
            # link to parent staff
            parent_index = _get_parent_staff_index(staffs, ii)
            staffs[ii].hasStaff = staffs[parent_index]
            if not staffs[parent_index].hasTab:
                staffs[parent_index].hasTab = []
            staffs[parent_index].hasTab.append(staffs[ii])


def _is_multi_voice_single_staff(staffs, parent):
    if _get_staff_numbers(staffs) == 1:
        if len(parent.voices) > 1:
            return True
    return False


def _get_next_tab_pos(tab_index, staff_group):
    start_index = 0
    handled_voices = 0
    nb_voices = 0
    while True:
        if not at(staff_group, start_index):
            return -1
        if not staff_group[start_index].isTabStaff:
            nb_voices = len(staff_group[start_index].voices)  # get number of staff voices
        if staff_group[start_index].isTabStaff:
            handled_voices += 1
            if _is_last_tab_in_staff(start_index, staff_group):
                if handled_voices < nb_voices:
                    return start_index + 1
        else:
            handled_voices = 0
            if start_index >= tab_index:
                if start_index + 1 == len(staff_group):
                    return start_index + 1
                if not staff_group[start_index + 1].isTabStaff:
                    return start_index + 1
        start_index += 1
        # out of space case
        if start_index > len(staff_group):
            return -1


def _get_last_staff(staffs, last_tab):
    for ii in range(last_tab, -1, -1):
        if not staffs[ii].isTabStaff:
            return staffs[ii]
    return None


def _check_voice_key_sig(voices, ii):
    cur_voice = voices[ii]
    # on multivoice multistaff only the first voice has key signature
    # following consecutive do not have one => we should provide the first voice key sig back then
    elem0 = cur_voice.children[0].abcelem
    if elem0.el_type == 'clef':
        return None
    if ii == 0:
        # not found => clef=none case
        return 'none'
    return voices[ii - 1].children[0]


def tab_renderer(plugin, renderer, line, staff_index):
    absolutes = TabAbsoluteElements()
    tab_staff = Obj(clef=Obj(type='TAB'))
    tab_size = plugin.linePitch * plugin.nbLines
    staffs = line.staff
    if staffs:
        # give up on staffline=0 in key
        first_staff = staffs[0]
        if first_staff:
            if first_staff.clef:
                if first_staff.clef.stafflines == 0:
                    plugin.set_error("No tablatures when stafflines=0")
                    return
        staffs.append(tab_staff)
    staff_group = line.staffGroup

    voices = staff_group.voices
    first_voice = voices[0]
    # take lyrics into account if any
    lyrics_height = _get_lyric_height(first_voice)
    padd = 3
    prev_index = staff_index
    previous_staff = staff_group.staffs[prev_index]
    tab_top = tab_size + padd - previous_staff.bottom - lyrics_height
    if previous_staff.isTabStaff:
        tab_top = previous_staff.top
    staff_group_infos = Obj(bottom=-1, isTabStaff=True, specialY=_init_special_y(), lines=plugin.nbLines,
                            linePitch=plugin.linePitch, dy=0.15, top=tab_top)
    next_tab_pos = _get_next_tab_pos(staff_index, staff_group.staffs)
    if next_tab_pos == -1:
        return
    staff_group_infos.parentIndex = next_tab_pos - 1
    staff_group.staffs.insert(next_tab_pos, staff_group_infos)
    staff_group.height += tab_size + padd
    parent_staff = _get_last_staff(staff_group.staffs, next_tab_pos)
    nb_voices = 1
    if _is_multi_voice_single_staff(staff_group.staffs, parent_staff):
        nb_voices = len(parent_staff.voices)
    # build from staff
    tab_staff.voices = []
    for ii in range(nb_voices):
        tab_voice = VoiceElement(0, 0)
        if ii > 0:
            tab_voice.duplicate = True
        name_height = _build_tab_name(plugin, renderer, tab_voice) / spacing.STEP
        name_height = js_max(name_height, 1)  # If there is no label for the tab line, then there needs to be a little padding
        staff_group.staffs[staff_index].top += 1
        staff_group.height += name_height
        tab_voice.staff = staff_group_infos
        tab_voice_index = len(voices)
        voices.append(tab_voice)
        key_sig = _check_voice_key_sig(voices, ii + staff_index)
        tab_staff.voices.append([])
        absolutes.build(plugin, voices, tab_staff.voices[ii], ii, staff_index, key_sig, tab_voice_index)
    _link_staff_and_tabs(staff_group.staffs)  # crossreference tabs and staff


# -- tab-absolute-elements.js -----------------------------------------------------------------

def _clone_object(dest, src):
    items = src.items() if isinstance(src, dict) else list(src.__dict__.items())
    for prop, value in items:
        if not (isinstance(value, (list, dict))):
            if isinstance(dest, dict):
                dest[prop] = value
            else:
                setattr(dest, prop, value)


def _clone_absolute(abs_src):
    returned = AbsoluteElement('', 0, 0, '', 0)
    _clone_object(returned, abs_src)
    returned.top = 0
    returned.bottom = -1
    if abs_src.abcelem:
        returned.abcelem = Obj()
        _clone_object(returned.abcelem, abs_src.abcelem)
        if returned.abcelem.el_type == "note":
            returned.abcelem.el_type = 'tabNumber'
    # TODO-PER: This fixes the classes because the element isn't created at the right time.
    abs_src.cloned = returned
    return returned


def _clone_absolute_and_relatives(abs_src, plugin):
    returned = _clone_absolute(abs_src)
    if plugin:
        first = True
        for child in abs_src.children:
            relative = RelativeElement('', 0, 0, 0, '')
            _clone_object(relative, child)
            first = plugin.tablature.set_relative(child, relative, first)
            returned.children.append(relative)
    return returned


def _build_tab_absolute(plugin, abs_x, rel_x):
    tab_icon = 'tab.tiny'
    tab_y_pos = 7.5
    if plugin.isTabBig:
        tab_icon = 'tab.big'
        tab_y_pos = 10
    element = Obj(el_type="tab", icon=tab_icon, Ypos=tab_y_pos)

    # Offset the TAB symbol position if specified in the tab description
    tab_y_pos += plugin.tabSymbolOffset

    tab_absolute = None
    # For tablature like whistle tab where you want the TAB symbol hidden
    if not plugin.hideTabSymbol:
        tab_absolute = AbsoluteElement(element, 0, 0, "symbol", 0)
        tab_absolute.x = abs_x
        tab_relative = RelativeElement(tab_icon, 0, 0, 7.5, "tab")
        tab_relative.x = rel_x
        tab_absolute.children.append(tab_relative)
        if tab_absolute.abcelem.el_type == 'tab':
            tab_relative.pitch = tab_y_pos
    return tab_absolute


def _lyrics_dim(abs_):
    if abs_.extra:
        for extra in abs_.extra:
            if extra.type == 'lyric':
                return Obj(bottom=extra.bottom, height=extra.height)
    return None


def _get_initial_staff_size(staff_group):
    return sum(1 for s in staff_group if not s.tabNameInfos)


def _build_relative_tab_note(plugin, rel_x, d, cur_note, is_grace):
    str_note = cur_note.num
    if cur_note.note.quarter is not None:
        # add tab quarter => needs to string conversion then
        str_note = js_str(str_note)
        str_note += cur_note.note.quarter
    pitch = plugin.semantics.string_to_pitch(cur_note.str)
    d.notes.append(Obj(num=str_note, str=cur_note.str, pitch=cur_note.note.emit()))
    opt = Obj(type='tabNumber')
    tab_note_relative = RelativeElement(str_note, 0, 0, pitch + 0.3, opt)
    tab_note_relative.x = rel_x
    tab_note_relative.isGrace = is_grace
    tab_note_relative.isAltered = cur_note.note.isAltered
    return tab_note_relative


def _get_x_grace(abs_, index):
    found = 0
    if abs_.extra:
        for e in abs_.extra:
            if isinstance(e.c, str) and 'noteheads' in e.c:
                if found == index:
                    return e.x + e.w / 2
                found += 1
    return -1


def _grace_in_rest(abs_elem):
    if abs_elem.abcelem:
        elem = abs_elem.abcelem
        if elem.rest:
            return elem.gracenotes
    return None


def _convert_to_number(plugin, pitches, grace_notes):
    tab_pos = plugin.semantics.notes_to_number(pitches, grace_notes)
    if tab_pos.error:
        plugin.set_error(tab_pos.error)
        return tab_pos  # give up on error here
    if tab_pos.graces and tab_pos.notes:
        # add graces to last note in notes
        pos_note = len(tab_pos.notes) - 1
        tab_pos.notes[pos_note].graces = tab_pos.graces
    return tab_pos


def _build_grace_relatives_for_rest(plugin, abs_, abs_child, grace_notes, tab_voice):
    for mm in range(len(grace_notes)):
        def_grace = Obj(el_type="note", startChar=abs_child.abcelem.startChar, endChar=abs_child.abcelem.endChar, notes=[], grace=True)
        grace_x = _get_x_grace(abs_child, mm)
        cur_grace = grace_notes[mm]
        tab_grace_relative = _build_relative_tab_note(plugin, grace_x, def_grace, cur_grace, True)
        abs_.children.append(tab_grace_relative)
        tab_voice.append(def_grace)


class TabAbsoluteElements:
    def __init__(self):
        self.accidentals = None

    def build(self, plugin, staff_absolute, tab_voice, voice_index, staff_index, key_sig, tab_voice_index):
        """Build tab absolutes by scanning current staff line absolute array."""
        source = staff_absolute[staff_index + voice_index]
        dest = staff_absolute[tab_voice_index]
        abs_ = None  # (function scoped in abcjs: the rest case may use the last note's element)
        if source.children[0].abcelem.el_type != 'clef':
            # keysig missing => provide one for tabs
            if key_sig != 'none':
                source.children.insert(0, key_sig)
        ii = 0
        while ii < len(source.children):
            abs_child = source.children[ii]
            abs_x = abs_child.x
            rel_x = abs_x
            if abs_child.isClef:
                dest.children.append(_build_tab_absolute(plugin, abs_x, rel_x))
                if '-8' in abs_child.abcelem.type:
                    plugin.semantics.clefTranspose = -12
                if '+8' in abs_child.abcelem.type:
                    plugin.semantics.clefTranspose = 12
            t = abs_child.type
            if t == 'staff-extra key-signature':
                # refresh key accidentals
                self.accidentals = abs_child.abcelem.accidentals
                plugin.semantics.accidentals = self.accidentals
            elif t == 'bar':
                plugin.semantics.measureAccidentals = {}
                last_bar = ii == len(source.children) - 1  # used for final line bar drawing for multi tabs / multi staves
                cloned = _clone_absolute_and_relatives(abs_child, plugin)
                if cloned.abcelem.barNumber:
                    del cloned.abcelem.barNumber
                    for bn in range(len(cloned.children)):
                        if cloned.children[bn].type == "barNumber":
                            del cloned.children[bn]
                            break
                cloned.abcelem.lastBar = last_bar
                dest.children.append(cloned)
                tab_voice.append(Obj(el_type=abs_child.abcelem.el_type, type=abs_child.abcelem.type, endChar=abs_child.abcelem.endChar, startChar=abs_child.abcelem.startChar, abselem=cloned))
            elif t == 'rest':
                rest_graces = _grace_in_rest(abs_child)
                if rest_graces:
                    # to number conversion
                    tab_pos = _convert_to_number(plugin, None, rest_graces)
                    if tab_pos.error:
                        return
                    # build relative for grace
                    _build_grace_relatives_for_rest(plugin, abs_, abs_child, tab_pos.graces, tab_voice)
            elif t == 'note':
                abs_ = _clone_absolute(abs_child)
                abs_.x = abs_child.heads[0].x + abs_child.heads[0].w / 2  # center the number
                abs_.lyricDim = _lyrics_dim(abs_child)
                pitches = abs_child.abcelem.pitches
                grace_notes = abs_child.abcelem.gracenotes
                abs_.type = 'tabNumber'
                # to number conversion
                tab_pos = _convert_to_number(plugin, pitches, grace_notes)
                if tab_pos.error:
                    return
                if tab_pos.graces:
                    # add graces to last note in notes
                    pos_note = len(tab_pos.notes) - 1
                    tab_pos.notes[pos_note].graces = tab_pos.graces
                # build relative
                def_note = Obj(el_type="note", startChar=abs_child.abcelem.startChar, endChar=abs_child.abcelem.endChar, notes=[])
                for ll in range(len(tab_pos.notes)):
                    cur_note = tab_pos.notes[ll]
                    if cur_note.graces:
                        for mm in range(len(cur_note.graces)):
                            def_grace = Obj(el_type="note", startChar=abs_child.abcelem.startChar, endChar=abs_child.abcelem.endChar, notes=[], grace=True)
                            grace_x = _get_x_grace(abs_child, mm)
                            cur_grace = cur_note.graces[mm]
                            tab_grace_relative = _build_relative_tab_note(plugin, grace_x, def_grace, cur_grace, True)
                            abs_.children.append(tab_grace_relative)
                            tab_voice.append(def_grace)
                    tab_note_relative = _build_relative_tab_note(plugin, abs_.x + abs_child.heads[ll].dx, def_note, cur_note, False)
                    abs_.children.append(tab_note_relative)
                if len(def_note.notes) > 0:
                    def_note.abselem = abs_
                    tab_voice.append(def_note)
                    dest.children.append(abs_)
            ii += 1
