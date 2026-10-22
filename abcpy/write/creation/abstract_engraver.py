"""Creates a data structure suitable for printing a line of abc (port of ``abstract-engraver.js``)."""

import json
import math

from ...jsutil import Obj, assign, at, js_round, js_str, js_floor, js_max, js_min, truthy, lt, gt, js_keys
from ..helpers import spacing
from . import glyphs
from .elements import (AbsoluteElement, RelativeElement, BeamElem, BraceElem, EndingElem, StaffGroupElement,
                       TempoElement, TieElem, TripletElem, VoiceElement)
from .note_parts import create_clef, create_key_signature, create_note_head, create_time_signature
from .decoration import Decoration
from .text_rows import add_chord
from ...synth.midi_tables import pitches_to_perc


def _get_duration(elem):
    d = 0
    if truthy(elem.duration):
        d = elem.duration
    return d


# (Like abcjs, this is module state.)
_state = {'hint': False}

chartable = {
    'rest': {0: "rests.whole", 1: "rests.half", 2: "rests.quarter", 3: "rests.8th", 4: "rests.16th", 5: "rests.32nd", 6: "rests.64th", 7: "rests.128th", "multi": "rests.multimeasure"},
    'note': {-1: "noteheads.dbl", 0: "noteheads.whole", 1: "noteheads.half", 2: "noteheads.quarter", 3: "noteheads.quarter", 4: "noteheads.quarter", 5: "noteheads.quarter", 6: "noteheads.quarter", 7: "noteheads.quarter", 'nostem': "noteheads.quarter"},
    'rhythm': {-1: "noteheads.slash.whole", 0: "noteheads.slash.whole", 1: "noteheads.slash.whole", 2: "noteheads.slash.quarter", 3: "noteheads.slash.quarter", 4: "noteheads.slash.quarter", 5: "noteheads.slash.quarter", 6: "noteheads.slash.quarter", 7: "noteheads.slash.quarter", 'nostem': "noteheads.slash.nostem"},
    'x': {-1: "noteheads.indeterminate", 0: "noteheads.indeterminate", 1: "noteheads.indeterminate", 2: "noteheads.indeterminate", 3: "noteheads.indeterminate", 4: "noteheads.indeterminate", 5: "noteheads.indeterminate", 6: "noteheads.indeterminate", 7: "noteheads.indeterminate", 'nostem': "noteheads.indeterminate"},
    'harmonic': {-1: "noteheads.harmonic.quarter", 0: "noteheads.harmonic.quarter", 1: "noteheads.harmonic.quarter", 2: "noteheads.harmonic.quarter", 3: "noteheads.harmonic.quarter", 4: "noteheads.harmonic.quarter", 5: "noteheads.harmonic.quarter", 6: "noteheads.harmonic.quarter", 7: "noteheads.harmonic.quarter", 'nostem': "noteheads.harmonic.quarter"},
    'triangle': {-1: "noteheads.triangle.quarter", 0: "noteheads.triangle.quarter", 1: "noteheads.triangle.quarter", 2: "noteheads.triangle.quarter", 3: "noteheads.triangle.quarter", 4: "noteheads.triangle.quarter", 5: "noteheads.triangle.quarter", 6: "noteheads.triangle.quarter", 7: "noteheads.triangle.quarter", 'nostem': "noteheads.triangle.quarter"},
    'uflags': {3: "flags.u8th", 4: "flags.u16th", 5: "flags.u32nd", 6: "flags.u64th"},
    'dflags': {3: "flags.d8th", 4: "flags.d16th", 5: "flags.d32nd", 6: "flags.d64th"},
}


def _chart(table, key):
    t = chartable.get(table)
    if t is None:
        return None
    if isinstance(key, float):
        if key != key:
            return None
        if key == int(key):
            key = int(key)
    return t.get(key)


def _clone_hash_of_hash(source):
    return Obj((k, _shallow(v)) for k, v in source.items())


def _shallow(v):
    if isinstance(v, dict):
        return Obj(v)
    if hasattr(v, '__dict__'):
        o = object.__new__(type(v))
        o.__dict__.update(v.__dict__)
        return o
    return v


def _get_beam_group(abcline, pos):
    # If there are notes beamed together, they are handled as a group, so find all of them here.
    elem = abcline[pos]
    if elem.el_type != 'note' or not elem.startBeam or elem.endBeam:
        return Obj(count=1, elem=elem)

    group = []
    while pos < len(abcline) and abcline[pos].el_type == 'note':
        group.append(abcline[pos])
        if abcline[pos].endBeam:
            break
        pos += 1
    return Obj(count=len(group), elem=group)


def _sort_pitch(elem):
    while True:
        is_sorted = True
        for p in range(len(elem.pitches) - 1):
            if elem.pitches[p].pitch > elem.pitches[p + 1].pitch:
                is_sorted = False
                elem.pitches[p], elem.pitches[p + 1] = elem.pitches[p + 1], elem.pitches[p]
        if is_sorted:
            break


def _set_average_pitch(elem):
    if elem.pitches:
        _sort_pitch(elem)
        total = 0
        for p in elem.pitches:
            total += p.verticalPos
        elem.averagepitch = total / len(elem.pitches)
        elem.minpitch = elem.pitches[0].verticalPos
        elem.maxpitch = elem.pitches[-1].verticalPos


def _ledger_lines(abselem, min_pitch, max_pitch, is_rest, symbol_width, additional_ledgers, d, dx, scale):
    if max_pitch is not None:
        i = max_pitch
        while i > 11:
            if i % 2 == 0 and not is_rest:
                abselem.add_fixed(RelativeElement(None, dx, (symbol_width + 4) * scale, i, Obj(type="ledger")))
            i -= 1

    if min_pitch is not None:
        i = min_pitch
        while i < 1:
            if i % 2 == 0 and not is_rest:
                abselem.add_fixed(RelativeElement(None, dx, (symbol_width + 4) * scale, i, Obj(type="ledger")))
            i += 1

    for ledger in additional_ledgers:  # PER: draw additional ledgers
        ofs = symbol_width
        if d == 'down':
            ofs = -ofs
        abselem.add_fixed(RelativeElement(None, ofs + dx, (symbol_width + 4) * scale, ledger, Obj(type="ledger")))


def _add_rest_to_abs_element(abselem, elem, duration, dot, is_multi_voice, stemdir, is_single_line_staff, durlog, voice_scale):
    c = None
    restpitch = 7
    note_head = None
    room_taken = None
    room_taken_right = None

    if is_multi_voice:
        if stemdir == "down":
            restpitch = 3
        if stemdir == "up":
            restpitch = 11
    # There is special placement for the percussion staff. If there is one staff line, then move the rest position.
    if is_single_line_staff:
        # The half and whole rests are attached to different lines normally, so we need to tweak their position to get them to both be attached to the same one.
        if duration < 0.5:
            restpitch = 7
        elif duration < 1:
            restpitch = 7  # half rest
        else:
            restpitch = 5  # whole rest
    t = elem.rest.type
    if t == "whole":
        c = chartable['rest'][0]
        elem.averagepitch = restpitch
        elem.minpitch = restpitch
        elem.maxpitch = restpitch
        dot = 0
    elif t == "rest":
        if elem.style == "rhythm":  # special case for rhythm: rests are a handy way to express the rhythm.
            c = _chart('rhythm', -durlog)
        else:
            c = _chart('rest', -durlog)
        elem.averagepitch = restpitch
        elem.minpitch = restpitch
        elem.maxpitch = restpitch
    elif t in ("invisible", "invisible-multimeasure", "spacer"):
        c = ""
        elem.averagepitch = restpitch
        elem.minpitch = restpitch
        elem.maxpitch = restpitch
    elif t == "multimeasure":
        c = chartable['rest']['multi']
        elem.averagepitch = restpitch
        elem.minpitch = restpitch
        elem.maxpitch = restpitch
        dot = 0
        mm_width = glyphs.get_symbol_width(c)
        abselem.add_head(RelativeElement(c, mm_width, mm_width * 2, 7))
        num_measures = RelativeElement(js_str(elem.rest.text), mm_width, mm_width, 16, Obj(type="multimeasure-text"))
        abselem.add_extra(num_measures)
    if "multimeasure" not in elem.rest.type and elem.rest.type != "invisible":
        ret = create_note_head(abselem, c, Obj(verticalPos=restpitch), Obj(dot=dot, scale=voice_scale))
        note_head = ret.notehead
        if note_head:
            abselem.add_head(note_head)
            room_taken = ret.accidentalshiftx
            room_taken_right = ret.dotshiftx
    return Obj(noteHead=note_head, roomTaken=room_taken, roomTakenRight=room_taken_right)


def _stringify(o):
    return json.dumps(o, sort_keys=False, default=lambda x: None)


def _add_if_not_exist(arr, item):
    s = _stringify(item)
    for a in arr:
        if _stringify(a) == s:
            return
    arr.append(item)


class AbstractEngraver:
    def __init__(self, get_text_size, tune_number, options):
        self.decoration = Decoration()
        self.getTextSize = get_text_size
        self.tuneNumber = tune_number
        self.isBagpipes = options.get('bagpipes')
        self.flatBeams = options.get('flatbeams')
        self.graceSlurs = options.get('graceSlurs')
        self.percmap = options.get('percmap')
        self.initialClef = options.get('initialClef')
        self.jazzchords = bool(options.get('jazzchords'))
        self.accentAbove = bool(options.get('accentAbove'))
        self.germanAlphabet = bool(options.get('germanAlphabet'))
        self.stemHeight = None
        self.measureLength = None
        self.triplet = None
        self.style = None
        self.tempoSet = False
        self.reset()

    def reset(self):
        self.slurs = Obj()
        self.ties = []
        self.voiceScale = 1
        self.voiceColor = None
        self.slursbyvoice = Obj()
        self.tiesbyvoice = Obj()
        self.endingsbyvoice = Obj()
        self.scaleByVoice = Obj()
        self.colorByVoice = Obj()
        self.tripletmultiplier = 1

        self.abcline = None
        self.accidentalSlot = None
        self.accidentalshiftx = None
        self.dotshiftx = None
        self.hasVocals = False
        self.minY = None
        self.partstartelem = None
        self.startlimitelem = None
        self.stemdir = None

    def set_stem_height(self, height_in_pixels):
        self.stemHeight = js_round(height_in_pixels * 10 / spacing.STEP) / 10

    def get_current_voice_id(self, s, v):
        return "s" + js_str(s) + "v" + js_str(v)

    def push_cross_line_elems(self, s, v):
        vid = self.get_current_voice_id(s, v)
        self.slursbyvoice[vid] = self.slurs
        self.tiesbyvoice[vid] = self.ties
        self.endingsbyvoice[vid] = self.partstartelem
        self.scaleByVoice[vid] = self.voiceScale
        if self.voiceColor:
            self.colorByVoice[vid] = self.voiceColor

    def pop_cross_line_elems(self, s, v):
        vid = self.get_current_voice_id(s, v)
        self.slurs = self.slursbyvoice[vid] or Obj()
        self.ties = self.tiesbyvoice[vid] if self.tiesbyvoice[vid] is not None else []
        self.partstartelem = self.endingsbyvoice[vid]
        self.voiceScale = self.scaleByVoice[vid]
        if self.voiceScale is None:
            self.voiceScale = 1
        self.voiceColor = self.colorByVoice[vid]

    def contains_lyrics(self, staves):
        for st in staves:
            for voice in st.voices:
                for el in voice:
                    if el.lyric:
                        # We just want to see if there are vocals below the music to know where to put the dynamics.
                        if not el.positioning or el.positioning.vocalPosition == 'below':
                            self.hasVocals = True
                        return

    def create_abc_line(self, staffs, tempo, l):
        self.minY = 2  # PER: This will be the lowest that any note reaches. It will be used to set the dynamics row.
        # See if there are any lyrics on this line.
        self.contains_lyrics(staffs)
        staffgroup = StaffGroupElement(self.getTextSize)
        self.tempoSet = False
        for s in range(len(staffs)):
            if _state['hint']:
                self.restore_state()
            _state['hint'] = False
            self.create_abc_staff(staffgroup, staffs[s], tempo, s, l)
        return staffgroup

    def create_abc_staff(self, staffgroup, abcstaff, tempo, s, l):
        # If the tempo is passed in, then the first element should get the tempo attached to it.
        staffgroup.getTextSize.update_fonts(abcstaff)
        for v in range(len(abcstaff.voices)):
            voice = VoiceElement(v, len(abcstaff.voices))
            if v == 0:
                voice.barfrom = abcstaff.connectBarLines == "start" or abcstaff.connectBarLines == "continue"
                voice.barto = abcstaff.connectBarLines == "continue" or abcstaff.connectBarLines == "end"
            else:
                voice.duplicate = True  # bar lines and other duplicate info need not be created
            if abcstaff.title and at(abcstaff.title, v):
                voice.header = abcstaff.title[v].replace("\\n", "\n")
                voice.headerPosition = 6 + staffgroup.getTextSize.baseline_to_center(voice.header, "voicefont", 'staff-extra voice-name', v, len(abcstaff.voices)) / spacing.STEP
            if abcstaff.clef and abcstaff.clef.type == "perc":
                voice.isPercussion = True
            clef = (not self.initialClef or l == 0) and create_clef(abcstaff.clef, self.tuneNumber)
            if clef:
                if v == 0 and abcstaff.barNumber:
                    self.add_measure_number(abcstaff.barNumber, clef)
                voice.add_child(clef)
                self.startlimitelem = clef  # limit ties here
            key_sig = create_key_signature(abcstaff.key, self.tuneNumber)
            if key_sig:
                voice.add_child(key_sig)
                self.startlimitelem = key_sig  # limit ties here
            if abcstaff.meter:
                if abcstaff.meter.type == 'specified':
                    from ...jsutil import number
                    self.measureLength = number(abcstaff.meter.value[0].num) / number(abcstaff.meter.value[0].den) if number(abcstaff.meter.value[0].den) else float('nan')
                else:
                    self.measureLength = 1
                ts = create_time_signature(abcstaff.meter, self.tuneNumber)
                voice.add_child(ts)
                self.startlimitelem = ts  # limit ties here
            if voice.duplicate:
                voice.children = []  # we shouldn't reprint the above if we're reusing the same staff. We just created them to get the right spacing.
            sl = abcstaff.clef.stafflines
            staff_lines = sl if (truthy(sl) or sl == 0) else 5
            staffgroup.add_voice(voice, s, staff_lines)
            is_single_line_staff = staff_lines == 1
            self.create_abc_voice(abcstaff.voices[v], tempo, s, v, is_single_line_staff, voice)
            staffgroup.set_staff_limits(voice)
            if v == 0:
                # only do brace and bracket processing on the first voice, otherwise it would be done twice.
                if abcstaff.brace == "start" or (not staffgroup.brace and abcstaff.brace):
                    if not staffgroup.brace:
                        staffgroup.brace = []
                    staffgroup.brace.append(BraceElem(voice, "brace"))
                elif abcstaff.brace == "end" and staffgroup.brace:
                    staffgroup.brace[-1].set_bottom_staff(voice)
                elif abcstaff.brace == "continue" and staffgroup.brace:
                    staffgroup.brace[-1].continuing(voice)
                if abcstaff.bracket == "start" or (not staffgroup.bracket and abcstaff.bracket):
                    if not staffgroup.bracket:
                        staffgroup.bracket = []
                    staffgroup.bracket.append(BraceElem(voice, "bracket"))
                elif abcstaff.bracket == "end" and staffgroup.bracket:
                    staffgroup.bracket[-1].set_bottom_staff(voice)
                elif abcstaff.bracket == "continue" and staffgroup.bracket:
                    staffgroup.bracket[-1].continuing(voice)

    def create_abc_voice(self, abcline, tempo, s, v, is_single_line_staff, voice):
        self.pop_cross_line_elems(s, v)
        self.stemdir = "down" if self.isBagpipes else None
        self.abcline = abcline
        if self.partstartelem:
            self.partstartelem = EndingElem("", None, None)
            voice.add_other(self.partstartelem)
        voice_number = -1 if voice.voicetotal < 2 else voice.voicenumber
        for slur in js_keys(self.slurs):
            # this is already a slur element, but it was created for the last line, so recreate it.
            old = self.slurs[slur]
            self.slurs[slur] = TieElem(Obj(force=old.force, voiceNumber=voice_number, stemDir=old.stemDir, style=old.dotted))
            if _state['hint']:
                self.slurs[slur].set_hint()
            voice.add_other(self.slurs[slur])
        for i in range(len(self.ties)):
            # this is already a tie element, but it was created for the last line, so recreate it.
            old = self.ties[i]
            self.ties[i] = TieElem(Obj(force=old.force, stemDir=old.stemDir, voiceNumber=voice_number, style=old.dotted))
            if _state['hint']:
                self.ties[i].set_hint()
            voice.add_other(self.ties[i])

        for el in self.abcline:
            _set_average_pitch(el)
            self.minY = js_min(el.minpitch, self.minY)

        is_first_staff = s == 0
        pos = 0
        while pos < len(self.abcline):
            ret = _get_beam_group(self.abcline, pos)
            abselems = self.create_abc_element(is_first_staff, is_single_line_staff, voice, ret.elem)
            if abselems:
                for a in abselems:
                    if not self.tempoSet and tempo and not tempo.suppress:
                        self.tempoSet = True
                        tempo_element = AbsoluteElement(tempo, 0, 0, "tempo", self.tuneNumber, {})
                        tempo_element.add_fixed_x(TempoElement(tempo, self.tuneNumber, create_note_head))
                        voice.add_child(tempo_element)
                    voice.add_child(a)
            pos += ret.count
        self.decoration.end_line(voice)
        self.push_cross_line_elems(s, v)

    def save_state(self):
        self.tiesSave = [_shallow(t) for t in self.ties]
        self.slursSave = _clone_hash_of_hash(self.slurs)
        self.slursbyvoiceSave = _clone_hash_of_hash(self.slursbyvoice)
        self.tiesbyvoiceSave = Obj((k, [_shallow(t) for t in v]) for k, v in self.tiesbyvoice.items())

    def restore_state(self):
        self.ties = [_shallow(t) for t in self.tiesSave]
        self.slurs = _clone_hash_of_hash(self.slursSave)
        self.slursbyvoice = _clone_hash_of_hash(self.slursbyvoiceSave)
        self.tiesbyvoice = Obj((k, [_shallow(t) for t in v]) for k, v in self.tiesbyvoiceSave.items())

    # return an array of AbsoluteElement
    def create_abc_element(self, is_first_staff, is_single_line_staff, voice, elem):
        elemset = []
        t = elem.el_type if isinstance(elem, dict) else None
        if t is None:
            # it is undefined if we were passed an array in - an array means a set of notes that should be beamed together.
            elemset = self.create_beam(is_single_line_staff, voice, elem)
        elif t == "note":
            elemset.append(self.create_note(elem, False, is_single_line_staff, voice))
            if self.triplet and self.triplet.is_closed():
                voice.add_other(self.triplet)
                self.triplet = None
                self.tripletmultiplier = 1
        elif t == "bar":
            elemset.append(self.create_bar_line(voice, elem, is_first_staff))
            if voice.duplicate and len(elemset) > 0:
                elemset[0].invisible = True
        elif t == "meter":
            elemset.append(create_time_signature(elem, self.tuneNumber))
            self.startlimitelem = elemset[0]  # limit ties here
            if voice.duplicate and len(elemset) > 0:
                elemset[0].invisible = True
        elif t == "clef":
            c = create_clef(elem, self.tuneNumber)
            if not c:
                return None
            elemset.append(c)
            if voice.duplicate and len(elemset) > 0:
                elemset[0].invisible = True
        elif t == "key":
            abs_key = create_key_signature(elem, self.tuneNumber)
            if abs_key:
                elemset.append(abs_key)
                self.startlimitelem = elemset[0]  # limit ties here
            if voice.duplicate and len(elemset) > 0:
                elemset[0].invisible = True
        elif t == "stem":
            self.stemdir = None if elem.direction == "auto" else elem.direction
        elif t == "part":
            abselem = AbsoluteElement(elem, 0, 0, 'part', self.tuneNumber)
            dim = self.getTextSize.calc(elem.title, 'partsfont', "part")
            abselem.add_fixed_x(RelativeElement(elem.title, 0, 0, None, Obj(type="part", height=dim.height / spacing.STEP)))
            elemset.append(abselem)
        elif t == "tempo":
            # For %%printtempo after initial header
            abselem3 = AbsoluteElement(elem, 0, 0, 'tempo', self.tuneNumber)
            if not elem.suppress:
                abselem3.add_fixed_x(TempoElement(elem, self.tuneNumber, create_note_head))
            elemset.append(abselem3)
        elif t == "style":
            if elem.head == "normal":
                self.style = None
            else:
                self.style = elem.head
        elif t == "hint":
            _state['hint'] = True
            self.save_state()
        elif t == "midi":
            # This has no effect on the visible music, so just skip it.
            pass
        elif t == "scale":
            self.voiceScale = elem.size
        elif t == "color":
            self.voiceColor = elem.color
            voice.color = self.voiceColor
        else:
            abselem2 = AbsoluteElement(elem, 0, 0, 'unsupported', self.tuneNumber)
            abselem2.add_fixed(RelativeElement("element type " + js_str(elem.el_type), 0, 0, None, Obj(type="debug")))
            elemset.append(abselem2)

        return elemset

    def create_beam(self, is_single_line_staff, voice, elems):
        abselemset = []

        beamelem = BeamElem(self.stemHeight * self.voiceScale, self.stemdir, self.flatBeams, elems[0])
        if _state['hint']:
            beamelem.set_hint()
        for e in elems:
            # Do a first pass to figure out the stem direction before creating the notes, so that staccatos and other decorations can be placed correctly.
            beamelem.running_direction(e)
        beamelem.set_stem_direction()
        temp_stem_dir = self.stemdir
        self.stemdir = 'up' if beamelem.stemsUp else 'down'
        for elem in elems:
            abselem = self.create_note(elem, True, is_single_line_staff, voice)
            abselemset.append(abselem)
            beamelem.add(abselem)
            if self.triplet and self.triplet.is_closed():
                voice.add_other(self.triplet)
                self.triplet = None
                self.tripletmultiplier = 1
        beamelem.calc_dir()
        voice.add_beam(beamelem)
        self.stemdir = temp_stem_dir
        return abselemset

    def add_grace_notes(self, elem, voice, abselem, notehead, stem_height, is_bagpipes, roomtaken):
        gracescale = 3 / 5
        grace_scale_stem = 3.5 / 5  # TODO-PER: empirically found constant.
        stem_height = js_round(stem_height * grace_scale_stem)
        gracebeam = None

        if len(elem.gracenotes) > 1:
            gracebeam = BeamElem(stem_height, "grace", is_bagpipes)
            if _state['hint']:
                gracebeam.set_hint()
            gracebeam.mainNote = abselem  # this gives us a reference back to the note this is attached to so that the stems can be attached somewhere.

        graceoffsets = [0] * len(elem.gracenotes)
        for i in range(len(elem.gracenotes) - 1, -1, -1):  # figure out where to place each gracenote
            roomtaken += 10
            graceoffsets[i] = roomtaken
            if elem.gracenotes[i].accidental:
                roomtaken += 7

        for i in range(len(elem.gracenotes)):
            gn = elem.gracenotes[i]
            gracepitch = gn.verticalPos

            flag = None if gracebeam else chartable['uflags'][5 if is_bagpipes else 3]
            accidental_slot = []
            ret = create_note_head(abselem, "noteheads.quarter", gn,
                                   Obj(dir="up", headx=-graceoffsets[i], extrax=-graceoffsets[i], flag=flag, scale=gracescale * self.voiceScale, accidentalSlot=accidental_slot))
            ret.notehead.highestVert = ret.notehead.pitch + stem_height
            grace = ret.notehead
            self.add_slurs_and_ties(abselem, gn, grace, voice, "up", True)

            abselem.add_extra(grace)
            # PER: added acciaccatura slash
            if gn.acciaccatura:
                pos = gn.verticalPos + 7 * gracescale  # the same formula that determines the flag position.
                d_acciaccatura = 5 if gracebeam else 6  # just an offset to make it line up correctly.
                abselem.add_right(RelativeElement("flags.ugrace", -graceoffsets[i] + d_acciaccatura, 0, pos, Obj(scalex=gracescale, scaley=gracescale)))
            if gracebeam:  # give the beam the necessary info
                grace_duration = gn.duration / 2
                if is_bagpipes:
                    grace_duration /= 2
                pseudoabselem = Obj(heads=[grace], abcelem=Obj(averagepitch=gracepitch, minpitch=gracepitch, maxpitch=gracepitch, duration=grace_duration))
                gracebeam.add(pseudoabselem)
            else:  # draw the stem
                p1 = gracepitch + 1 / 3 * gracescale
                p2 = gracepitch + 7 * gracescale
                dx = grace.dx + grace.w
                width = -0.6
                abselem.add_extra(RelativeElement(None, dx, 0, p1, Obj(type="stem", pitch2=p2, linewidth=width)))
            _ledger_lines(abselem, gracepitch, gracepitch, False, glyphs.get_symbol_width("noteheads.quarter"), [], True, grace.dx - 1, 0.6)

            # if this is the first grace note, we might want to start a slur.
            # there is a slur if graceSlurs is specifically set.
            # there is no slur if it is bagpipes.
            # there is not a slur if the element is a spacer or invisible rest.
            is_invisible_rest = elem.rest and (elem.rest.type == "spacer" or elem.rest.type == "invisible")
            if i == 0 and not is_bagpipes and self.graceSlurs and not is_invisible_rest:
                # This is the overall slur that is under the grace notes.
                voice.add_other(TieElem(Obj(anchor1=grace, anchor2=notehead, isGrace=True)))

        if gracebeam:
            gracebeam.calc_dir()
            voice.add_beam(gracebeam)
        return roomtaken

    def add_note_to_abc_element(self, abselem, elem, dot, stemdir, style, zero_duration, durlog, nostem, voice):
        dotshiftx = 0  # room taken by chords with displaced noteheads which cause dots to shift
        note_head = None
        room_taken = 0
        room_taken_right = 0
        mn = None
        additional_ledgers = []
        # The accidentalSlot will hold a list of all the accidentals on this chord. Each element is a vertical place,
        # and contains a pitch, which is the last pitch that contains an accidental in that slot.
        accidental_slot = []
        symbol_width = 0

        d = "down" if ge_(elem.averagepitch, 6) else "up"
        if stemdir:
            d = stemdir

        style = elem.style if elem.style else style  # get the style of note head.
        if not style or style == "normal":
            style = "note"
        if zero_duration:
            note_symbol = _chart(style, 'nostem')
        else:
            note_symbol = _chart(style, -durlog)

        # determine elements of chords which should be shifted
        n = len(elem.pitches)
        rng = range(n - 2, -1, -1) if d == "down" else range(1, n)
        for p in rng:
            prev = elem.pitches[p + 1] if d == "down" else elem.pitches[p - 1]
            curr = elem.pitches[p]
            delta = prev.pitch - curr.pitch if d == "down" else curr.pitch - prev.pitch
            if delta <= 1 and not prev.printer_shift:
                curr.printer_shift = "different" if delta else "same"
                if curr.verticalPos > 11 or curr.verticalPos < 1:  # PER: add extra ledger line
                    additional_ledgers.append(curr.verticalPos - (_js_mod(curr.verticalPos, 2)))
                if d == "down":
                    room_taken = glyphs.get_symbol_width(note_symbol) + 2
                else:
                    dotshiftx = glyphs.get_symbol_width(note_symbol) + 2

        pp = len(elem.pitches)
        flag = None
        has_stem = False
        for p in range(len(elem.pitches)):
            if not nostem:
                if (d == "down" and p != 0) or (d == "up" and p != pp - 1):  # not the stemmed elem of the chord
                    flag = None
                else:
                    flag = _chart("dflags" if d == "down" else "uflags", -durlog)
            pitch = elem.pitches[p]
            if pitch.style:  # There is a style for the whole group of pitches, but there could also be an override for a particular pitch.
                c = _chart(pitch.style, -durlog)
            elif voice.isPercussion and self.percmap:
                c = note_symbol
                perc_head = self.percmap.get(pitches_to_perc(pitch))
                if perc_head and perc_head.noteHead:
                    if chartable.get(perc_head.noteHead):
                        c = _chart(perc_head.noteHead, -durlog)
            else:
                c = note_symbol
            # The highest position for the sake of placing slurs is itself if the slur is internal. It is the highest position possible if the slur is for the whole chord.
            # If the note is the only one in the chord, then any slur it has counts as if it were on the whole chord.
            pitch.highestVert = pitch.verticalPos
            is_top_when_stem_is_down = (stemdir == "up" or d == "up") and p == 0
            is_bottom_when_stem_is_up = (stemdir == "down" or d == "down") and p == pp - 1
            if is_top_when_stem_is_down or is_bottom_when_stem_is_up:  # place to put slurs if not already on pitches
                if elem.startSlur or pp == 1:
                    pitch.highestVert = elem.pitches[pp - 1].verticalPos
                    if _get_duration(elem) < 1 and (stemdir == "up" or d == "up"):
                        pitch.highestVert += 6  # If the stem is up, then compensate for the length of the stem
                if elem.startSlur:
                    if not pitch.startSlur:
                        pitch.startSlur = []
                    for ss in elem.startSlur:
                        _add_if_not_exist(pitch.startSlur, ss)

                if elem.endSlur:
                    pitch.highestVert = elem.pitches[pp - 1].verticalPos
                    if _get_duration(elem) < 1 and (stemdir == "up" or d == "up"):
                        pitch.highestVert += 6  # If the stem is up, then compensate for the length of the stem
                    if not pitch.endSlur:
                        pitch.endSlur = []
                    for es in elem.endSlur:
                        _add_if_not_exist(pitch.endSlur, es)

            has_stem = not nostem and durlog <= -1
            chord_pos = p + 1 if pp > 1 else None
            ret = create_note_head(abselem, c, pitch,
                                   Obj(dir=d, extrax=-room_taken, flag=flag, dot=dot, dotshiftx=dotshiftx, scale=self.voiceScale, accidentalSlot=accidental_slot, shouldExtendStem=not stemdir, printAccidentals=not voice.isPercussion, chordPos=chord_pos))
            symbol_width = max(glyphs.get_symbol_width(c), symbol_width)
            abselem.extraw -= ret.extraLeft
            note_head = ret.notehead
            if note_head:
                self.add_slurs_and_ties(abselem, pitch, note_head, voice, d if has_stem else None, False)

                if elem.gracenotes and len(elem.gracenotes) > 0:
                    note_head.bottom = note_head.bottom - 1  # If there is a tie to the grace notes, leave a little more room for the note to avoid collisions.
                abselem.add_head(note_head)
            room_taken += ret.accidentalshiftx
            room_taken_right = max(room_taken_right, ret.dotshiftx)

        # draw stem from the furthest note to a pitch above/below the stemmed note
        if has_stem:
            stem_height = js_round(70 * self.voiceScale) / 10
            p1 = elem.minpitch - stem_height if d == "down" else elem.minpitch + 1 / 3
            # PER added stemdir test to make the line meet the note.
            if p1 > 6 and not stemdir:
                p1 = 6
            p2 = elem.maxpitch - 1 / 3 if d == "down" else elem.maxpitch + stem_height
            # PER added stemdir test to make the line meet the note.
            if p2 < 6 and not stemdir:
                p2 = 6
            dx = 0 if (d == "down" or len(abselem.heads) == 0) else abselem.heads[0].w
            width = 1 if d == "down" else -1
            # TODO-PER-HACK: One type of note head has a different placement of the stem. This should be more generically calculated:
            if note_head and note_head.c == 'noteheads.slash.quarter':
                if d == 'down':
                    p2 -= 1
                else:
                    p1 += 1
            if note_head and note_head.c == 'noteheads.triangle.quarter':
                if d == 'down':
                    p2 -= 0.7
                else:
                    p1 -= 1.2
            abselem.add_right(RelativeElement(None, dx, 0, p1, Obj(type="stem", pitch2=p2, linewidth=width, bottom=p1 - 1)))
            mn = min(p1, p2)
        return Obj(noteHead=note_head, roomTaken=room_taken, roomTakenRight=room_taken_right, min=mn, additionalLedgers=additional_ledgers, dir=d, symbolWidth=symbol_width)

    def add_lyric(self, abselem, elem, voice_number):
        lyric_str = ""
        for ly in elem.lyric:
            div = "" if ly.divider == ' ' else ly.divider
            lyric_str += js_str(ly.syllable) + js_str(div) + "\n"
        lyric_dim = self.getTextSize.calc(lyric_str, 'vocalfont', "lyric")
        position = elem.positioning.vocalPosition if elem.positioning else 'below'
        abselem.add_centered(RelativeElement(lyric_str, 0, lyric_dim.width, None, Obj(type="lyric", position=position, height=lyric_dim.height / spacing.STEP, dim=self.getTextSize.attr('vocalfont', "lyric"), voiceNumber=voice_number)))

    def create_note(self, elem, nostem, is_single_line_staff, voice):  # stem presence: true for drawing stemless notehead
        notehead = None
        roomtaken = 0  # room needed to the left of the note
        roomtakenright = 0  # room needed to the right of the note
        symbol_width = 0
        additional_ledgers = []  # PER: handle the case of [bc'], where the b doesn't have a ledger line

        d = None

        duration = _get_duration(elem)
        zero_duration = False
        if duration == 0:
            zero_duration = True
            duration = 0.25
            nostem = True  # PER: zero duration will draw a quarter note head.
        durlog = js_floor(math.log(duration) / math.log(2)) if duration > 0 else float('nan')  # TODO use getDurlog
        dot = 0

        if durlog == durlog:
            tot = math.pow(2, durlog)
            inc = tot / 2
            while tot < duration:
                dot += 1
                tot += inc
                inc /= 2

        if elem.startTriplet:
            self.tripletmultiplier = elem.tripletMultiplier

        duration_for_spacing = duration * self.tripletmultiplier
        if elem.rest and elem.rest.type == 'multimeasure':
            duration_for_spacing = 1
        if elem.rest and elem.rest.type == 'invisible-multimeasure':
            duration_for_spacing = self.measureLength * elem.rest.text if self.measureLength is not None else float('nan')
        abs_type = "rest" if elem.rest else "note"
        dur_class = elem.duration * self.tripletmultiplier if elem.duration is not None else float('nan')
        abselem = AbsoluteElement(elem, duration_for_spacing, 1, abs_type, self.tuneNumber, {'durationClassOveride': dur_class if truthy(dur_class) else None})
        if _state['hint']:
            abselem.set_hint()

        if elem.rest:
            if self.measureLength == duration and elem.rest.type != 'invisible' and elem.rest.type != 'spacer' and 'multimeasure' not in elem.rest.type:
                elem.rest.type = 'whole'  # If the rest is exactly a measure, always use a whole rest
            ret1 = _add_rest_to_abs_element(abselem, elem, duration, dot, voice.voicetotal > 1, self.stemdir, is_single_line_staff, durlog, self.voiceScale)
            notehead = ret1.noteHead
            roomtaken = ret1.roomTaken
            roomtakenright = ret1.roomTakenRight
        else:
            ret2 = self.add_note_to_abc_element(abselem, elem, dot, self.stemdir, self.style, zero_duration, durlog, nostem, voice)
            if ret2.min is not None:
                self.minY = js_min(ret2.min, self.minY)
            notehead = ret2.noteHead
            roomtaken = ret2.roomTaken
            roomtakenright = ret2.roomTakenRight
            additional_ledgers = ret2.additionalLedgers
            d = ret2.dir
            symbol_width = ret2.symbolWidth

        if elem.lyric is not None:
            self.add_lyric(abselem, elem, voice.voicenumber)

        if elem.gracenotes is not None:
            roomtaken = _add_num(roomtaken, self.add_grace_notes(elem, voice, abselem, notehead, self.stemHeight * self.voiceScale, self.isBagpipes, roomtaken if roomtaken is not None else float('nan')))

        if elem.decoration:
            # TODO-PER: nostem is true if this is beamed. In that case we don't know where to place the decoration yet so just make a guess.
            bottom = js_min(-3, _add_num(abselem.bottom, -6)) if (nostem and d != 'up') else abselem.bottom
            self.decoration.create_decoration(voice, elem.decoration, abselem.top, notehead.w if notehead else 0, abselem, roomtaken, d, bottom, elem.positioning, self.hasVocals, self.accentAbove)

        if elem.barNumber:
            abselem.add_fixed(RelativeElement(elem.barNumber, -10, 0, 0, Obj(type="barNumber")))

        # ledger lines
        _ledger_lines(abselem, elem.minpitch, elem.maxpitch, elem.rest, symbol_width, additional_ledgers, d, -2, 1)

        if elem.chord is not None:
            ret3 = add_chord(self.getTextSize, abselem, elem, roomtaken, roomtakenright, symbol_width, self.jazzchords, self.germanAlphabet)
            roomtaken = ret3.roomTaken
            roomtakenright = ret3.roomTakenRight

        if elem.startTriplet:
            self.triplet = TripletElem(elem.startTriplet, notehead, Obj(flatBeams=self.flatBeams))  # above is opposite from case of slurs

        if elem.endTriplet and self.triplet:
            self.triplet.set_close_anchor(notehead)

        if self.triplet and not elem.startTriplet and not elem.endTriplet and not (elem.rest and elem.rest.type == "spacer"):
            self.triplet.middle_note(notehead)

        return abselem

    def add_slurs_and_ties(self, abselem, pitchelem, notehead, voice, d, is_grace):
        if pitchelem.endTie:
            if len(self.ties) > 0:
                # If there are multiple open ties, find the one that applies by matching the pitch, if possible.
                found = False
                for j in range(len(self.ties)):
                    if self.ties[j].anchor1 and self.ties[j].anchor1.pitch == notehead.pitch:
                        self.ties[j].set_end_anchor(notehead)
                        voice.set_range(self.ties[j])
                        del self.ties[j]
                        found = True
                        break
                if not found:
                    self.ties[0].set_end_anchor(notehead)
                    voice.set_range(self.ties[0])
                    del self.ties[0]

        voice_number = -1 if voice.voicetotal < 2 else voice.voicenumber
        if pitchelem.startTie:
            tie = TieElem(Obj(anchor1=notehead, force=(self.stemdir == "down" or self.stemdir == "up"), stemDir=self.stemdir, isGrace=is_grace, voiceNumber=voice_number, style=pitchelem.startTie.style))
            if _state['hint']:
                tie.set_hint()

            self.ties.append(tie)
            voice.add_other(tie)
            # HACK-PER: For the animation, we need to know if a note is tied to the next one, so here's a flag.
            abselem.startTie = True

        slur = None
        if pitchelem.endSlur:
            for slurid in pitchelem.endSlur:
                key = js_str(slurid)
                if self.slurs[key]:
                    slur = self.slurs[key]
                    slur.set_end_anchor(notehead)
                    voice.set_range(slur)
                    del self.slurs[key]
                else:
                    slur = TieElem(Obj(anchor2=notehead, stemDir=self.stemdir, voiceNumber=voice_number))
                    if _state['hint']:
                        slur.set_hint()
                    voice.add_other(slur)
                if self.startlimitelem:
                    slur.set_start_x(self.startlimitelem)
        elif not is_grace:
            for s in self.slurs:
                self.slurs[s].add_internal_note(notehead)

        if pitchelem.startSlur:
            for ss in pitchelem.startSlur:
                slurid = js_str(ss.label)
                slur = TieElem(Obj(anchor1=notehead, stemDir=self.stemdir, voiceNumber=voice_number, style=ss.style))
                if _state['hint']:
                    slur.set_hint()
                self.slurs[slurid] = slur
                voice.add_other(slur)

    def add_measure_number(self, number, abselem):
        measure_num_dim = self.getTextSize.calc(number, "measurefont", 'bar-number')
        dx = 0
        if abselem.isClef:  # If this is a clef rather than bar line, then the number shouldn't be centered because it could overlap the left side.
            dx += measure_num_dim.width / 2
        # Change 13 to 13.5 since previously bar numbers were very slightly overlapping the top of the clef
        vert = 13.5 if (measure_num_dim.width > 10 and abselem.abcelem.type == "treble") else 11
        abselem.add_fixed(RelativeElement(number, dx, measure_num_dim.width, vert + measure_num_dim.height / spacing.STEP, Obj(type="barNumber", dim=self.getTextSize.attr("measurefont", 'bar-number'))))

    def create_bar_line(self, voice, elem, is_first_staff):
        # bar_thin, bar_thin_thick, bar_thin_thin, bar_thick_thin, bar_right_repeat, bar_left_repeat, bar_double_repeat
        abselem = AbsoluteElement(elem, 0, 10, 'bar', self.tuneNumber)
        anchor = None  # place to attach part lines
        dx = 0

        if elem.barNumber:
            self.add_measure_number(elem.barNumber, abselem)

        t = elem.type
        firstdots = t == "bar_right_repeat" or t == "bar_dbl_repeat"
        firstthin = t != "bar_left_repeat" and t != "bar_thick_thin" and t != "bar_invisible"
        thick = t in ("bar_right_repeat", "bar_dbl_repeat", "bar_left_repeat", "bar_thin_thick", "bar_thick_thin")
        secondthin = t in ("bar_left_repeat", "bar_thick_thin", "bar_thin_thin", "bar_dbl_repeat")
        seconddots = t == "bar_left_repeat" or t == "bar_dbl_repeat"

        # limit positioning of slurs
        if firstdots or seconddots:
            for slur in self.slurs:
                self.slurs[slur].set_end_x(abselem)
            self.startlimitelem = abselem

        if firstdots:
            abselem.add_right(RelativeElement("dots.dot", dx, 1, 7))
            abselem.add_right(RelativeElement("dots.dot", dx, 1, 5))
            dx += 6  # 2 hardcoded, twice;

        if firstthin:
            anchor = RelativeElement(None, dx, 1, 2, Obj(type="bar", pitch2=10, linewidth=0.6))
            abselem.add_right(anchor)

        if t == "bar_invisible":
            anchor = RelativeElement(None, dx, 1, 2, Obj(type="none", pitch2=10, linewidth=0.6))
            abselem.add_right(anchor)

        if elem.decoration:
            self.decoration.create_decoration(voice, elem.decoration, 12, 3 if thick else 1, abselem, 0, "down", 2, elem.positioning, self.hasVocals, self.accentAbove)

        if thick:
            dx += 4  # 3 hardcoded;
            anchor = RelativeElement(None, dx, 4, 2, Obj(type="bar", pitch2=10, linewidth=4))
            abselem.add_right(anchor)
            dx += 5

        if self.partstartelem and elem.endEnding:
            self.partstartelem.anchor2 = anchor
            self.partstartelem = None

        if secondthin:
            dx += 3  # 3 hardcoded;
            anchor = RelativeElement(None, dx, 1, 2, Obj(type="bar", pitch2=10, linewidth=0.6))
            abselem.add_right(anchor)  # 3 is hardcoded

        if seconddots:
            dx += 3  # 3 hardcoded;
            abselem.add_right(RelativeElement("dots.dot", dx, 1, 7))
            abselem.add_right(RelativeElement("dots.dot", dx, 1, 5))

        if elem.startEnding and is_first_staff:
            # Fixes drawing issue
            if voice.voicenumber == 0:
                # only put the first & second ending marks on the first staff
                text_width = self.getTextSize.calc(elem.startEnding, "repeatfont", '').width
                abselem.minspacing += text_width + 10  # Give plenty of room for the ending number.
                self.partstartelem = EndingElem(elem.startEnding, anchor, None)
                voice.add_other(self.partstartelem)
        # Add a little space to the left of the bar line so that nothing can crowd it.
        abselem.extraw -= 5

        if elem.chord is not None:
            add_chord(self.getTextSize, abselem, elem, 0, 0, 0, False, self.germanAlphabet)

        return abselem


def ge_(a, b):
    from ...jsutil import ge
    return ge(a, b)


def _js_mod(a, b):
    from ...jsutil import js_mod
    return js_mod(a, b)


def _add_num(a, b):
    if a is None or b is None:
        return float('nan')
    return a + b
