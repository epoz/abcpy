"""A computer usable internal structure representing one tune (port of ``abc_tune.js``).

The parsed music lives in :attr:`Tune.lines`.  Each line is a dict which is
either a music line (it has a ``staff`` list) or a non-music line (``subtitle``,
``text``, ``separator``, ``newpage``).  Each staff has a list of ``voices`` and
each voice is a list of elements (dicts with an ``el_type`` such as ``note``,
``bar``, ``key``, ``clef``, ``meter``...).  The structure is identical to the
abcjs "tune object", so the abcjs documentation applies.
"""

import json
import math

from ..jsutil import Obj, assign, at, parse_int, js_round, js_sort, js_keys, truthy, stringify
from .deline_tune import deline_tune


class Tune:
    def __init__(self):
        self.reset()

    def reset(self):
        self.version = "1.1.0"
        self.media = "screen"
        self.metaText = Obj()
        self.metaTextInfo = Obj()
        self.formatting = Obj()
        self.lines = []
        self.staffNum = 0
        self.voiceNum = 0
        self.lineNum = 0
        self.runningFonts = Obj()
        self.visualTranspose = None
        self.lineBreaks = None
        self.chordGrid = None
        self.potentialStartBeam = None
        self.potentialEndBeam = None
        self.vskipPending = None
        self.warnings = None
        self.tablatures = None
        self.engraver = None
        self.meter = None

    # -- serialization -------------------------------------------------------
    def to_dict(self):
        """Return the tune as plain data (the same as what abcjs's ``parseOnly`` produces)."""
        t = Obj(formatting=self.formatting, lines=self.lines, media=self.media,
                metaText=self.metaText, metaTextInfo=self.metaTextInfo, version=self.version)
        if self.lineBreaks:
            t.lineBreaks = self.lineBreaks
        if self.visualTranspose:
            t.visualTranspose = self.visualTranspose
        if self.chordGrid:
            t.chordGrid = self.chordGrid
        if self.warnings:
            t.warnings = self.warnings
        return t

    def to_json(self, **kwargs):
        """Serialize :meth:`to_dict` as JSON (keyword arguments go to :func:`json.dumps`)."""
        return stringify(_strip_engraver_refs(self.to_dict()), **kwargs)

    # -- copying info between tunes ----------------------------------------
    def copy_top_info(self, src):
        attrs = ['tempo', 'title', 'header', 'rhythm', 'origin', 'composer', 'author', 'partOrder']
        for a in attrs:
            self.metaText[a] = src.metaText.get(a)
            self.metaTextInfo[a] = src.metaTextInfo.get(a)

    def copy_bottom_info(self, src):
        attrs = ['unalignedWords', 'book', 'source', 'discography', 'notes', 'transcription', 'history',
                 'abc-copyright', 'abc-creator', 'abc-edited-by', 'footer']
        for a in attrs:
            self.metaText[a] = src.metaText.get(a)
            self.metaTextInfo[a] = src.metaTextInfo.get(a)

    # -- meter and timing helpers --------------------------------------------
    def get_beat_length(self):
        """The beat as a fraction of a whole note: for instance 1/4 for a quarter."""
        meter = self.get_meter_fraction()
        multiplier = 1
        if meter.num == 6 or meter.num == 9 or meter.num == 12:
            multiplier = 3
        elif meter.num == 3 and meter.den == 8:
            multiplier = 3
        elif meter.den == 8 and (meter.num == 5 or meter.num == 7):
            multiplier = 2
        return multiplier / meter.den

    def get_pickup_length(self):
        bar_length = self.get_bar_length()
        pickup_length = _compute_pickup_length(self.lines, bar_length)
        # If computed pickup length is very close to 0 or the bar length, we assume
        # that we actually have a full bar and hence no pickup.
        return 0 if (pickup_length < 1e-8 or bar_length - pickup_length < 1e-8) else pickup_length

    def get_bar_length(self):
        meter = self.get_meter_fraction()
        return meter.num / meter.den

    def get_total_time(self):
        return getattr(self, 'totalTime', None)

    def get_total_beats(self):
        return getattr(self, 'totalBeats', None)

    def milliseconds_per_measure(self, bpm_override=None):
        if bpm_override:
            bpm = bpm_override
        else:
            tempo = self.metaText.get('tempo') if self.metaText else None
            bpm = self.get_bpm(tempo)
        if bpm <= 0:
            bpm = 1  # we don't want a possibility of dividing by zero.
        beats_per_measure = self.get_beats_per_measure()
        minutes_per_measure = beats_per_measure / bpm
        return minutes_per_measure * 60000

    def get_beats_per_measure(self):
        beat_len = self.get_beat_length()
        bar_len = self.get_bar_length()
        return bar_len / beat_len

    def get_meter(self):
        for line in self.lines:
            if line.staff:
                for st in line.staff:
                    if st is None:
                        continue
                    meter = st.meter
                    if meter:
                        return meter
        return Obj(type="common_time")

    def get_meter_fraction(self):
        meter = self.get_meter()
        num = 4
        den = 4
        if meter:
            if meter.type == 'specified':
                if meter.value and len(meter.value) > 0 and meter.value[0].num.find('+') > 0:
                    parts = meter.value[0].num.split('+')
                    num = 0
                    for p in parts:
                        num += parse_int(p, 10)
                else:
                    num = parse_int(meter.value[0].num, 10)
                den = parse_int(meter.value[0].den, 10)
            elif meter.type == 'cut_time':
                num = 2
                den = 2
            elif meter.type == 'common_time':
                num = 4
                den = 4
        self.meter = Obj(num=num, den=den)
        return self.meter

    def get_key_signature(self):
        for line in self.lines:
            if line.staff:
                for st in line.staff:
                    if st is not None and st.key:
                        return st.key
        return Obj()

    def get_element_from_char(self, char):
        """Return the element whose source text covers the character position ``char``."""
        for line in self.lines:
            if line.staff:
                for staff in line.staff:
                    for voice in staff.voices:
                        for elem in voice:
                            if elem.startChar and elem.endChar and elem.startChar <= char < elem.endChar:
                                return elem
        return None

    def get_bpm(self, tempo=None):
        bpm = None
        if not tempo:
            tempo = self.metaText.get('tempo') if self.metaText else None
        if tempo:
            bpm = tempo.bpm
            beat_length = self.get_beat_length()
            stated_beat_length = tempo.duration[0] if tempo.duration and len(tempo.duration) > 0 else beat_length
            bpm = bpm * stated_beat_length / beat_length if bpm is not None else float('nan')
        if not truthy(bpm):
            bpm = 180
            # Compensate for compound meter, where the beat isn't a beat.
            meter = self.get_meter_fraction()
            if meter and meter.num != 3 and (meter.num % 3 == 0):
                bpm = 120
        return bpm

    # -- other representations ---------------------------------------------
    def deline(self, options=None):
        """Return the music lines joined together (no line breaks).

        With ``{'lineBreaks': True}`` an element ``{'el_type': 'break'}`` is
        inserted where the original line breaks were.
        """
        return deline_tune(self.lines, options)

    def set_up_audio(self, options=None):
        """Create the flattened audio representation of the tune (see :mod:`abcpy.synth`)."""
        from ..synth.sequencer import sequence
        from ..synth.flattener import flatten
        if not options:
            options = Obj()
        seq = sequence(self, options)
        return flatten(seq, options, self.formatting.get('percmap'), self.formatting.get('midi'))

    # -- timing (requires the tune to have been rendered) ---------------
    def make_voices_array(self):
        from ..write.helpers import spacing
        voices_arr = []
        measure_number = []
        tempos = {}
        for group in self.engraver.staffgroups:
            if group and group.staffs and len(group.staffs) > 0:
                first_staff = group.staffs[0]
                middle_c = first_staff.absoluteY
                top = middle_c - first_staff.top * spacing.STEP
                last_staff = group.staffs[-1]
                middle_c = last_staff.absoluteY
                bottom = middle_c - last_staff.bottom * spacing.STEP
                height = bottom - top

                voices = group.voices
                for v in range(len(voices)):
                    if voices[v].staff and voices[v].staff.isTabStaff:
                        continue
                    note_found = False
                    if at(voices_arr, v) is None:
                        while len(voices_arr) <= v:
                            voices_arr.append(None)
                        voices_arr[v] = []
                    while len(measure_number) <= v:
                        measure_number.append(None)
                    if measure_number[v] is None:
                        measure_number[v] = 0
                    elements = voices[v].children
                    for elem in elements:
                        if elem.type == "tempo":
                            tempos[measure_number[v]] = self.get_bpm(elem.abcelem)
                        voices_arr[v].append(Obj(top=top, height=height, line=group.line, measureNumber=measure_number[v], elem=elem))
                        if elem.type == 'bar' and note_found:
                            measure_number[v] += 1
                        if elem.type == 'note' or elem.type == 'rest':
                            note_found = True
        self.tempoLocations = tempos
        return [v if v is not None else [] for v in voices_arr]

    def add_element_to_events(self, event_hash, element, voice_time_milliseconds, top, height, line, measure_number, time_divider, is_tied_state, next_is_bar):
        if element.hint:
            return Obj(isTiedState=None, duration=0)
        real_duration = element.durationClass if truthy(element.durationClass) else element.duration
        if element.abcelem.rest and element.abcelem.rest.type == "spacer":
            real_duration = 0
        if real_duration > 0:
            es = [e for e in element.elemset if e is not None]
            is_tied_to_next = element.startTie
            key = "event" + _num_key(voice_time_milliseconds)
            if is_tied_state is not None:
                event_hash["event" + _num_key(is_tied_state)].elements.append(es)  # Add the tied note to the first note that it is tied to
                if next_is_bar:
                    if key not in event_hash:
                        event_hash[key] = Obj(type="event", milliseconds=voice_time_milliseconds, line=line,
                                              measureNumber=measure_number, top=top, height=height, left=None,
                                              width=0, elements=[], startChar=None, endChar=None,
                                              startCharArray=[], endCharArray=[])
                    event_hash[key].measureStart = True
                    next_is_bar = False
                if not is_tied_to_next:
                    is_tied_state = None
            else:
                # the last note wasn't tied.
                if key not in event_hash:
                    ev = Obj(type="event", milliseconds=voice_time_milliseconds, line=line,
                             measureNumber=measure_number, top=top, height=height, left=element.x,
                             width=element.w, elements=[es], startChar=element.abcelem.startChar,
                             endChar=element.abcelem.endChar, startCharArray=[element.abcelem.startChar],
                             endCharArray=[element.abcelem.endChar],
                             midiPitches=[assign(p) for p in element.abcelem.midiPitches] if element.abcelem.midiPitches else [])
                    if element.abcelem.midiGraceNotePitches:
                        ev.midiGraceNotePitches = [assign(p) for p in element.abcelem.midiGraceNotePitches]
                    event_hash[key] = ev
                else:
                    # If there is more than one voice then two notes can fall at the same time. The left most element wins.
                    ev = event_hash[key]
                    if ev.left:
                        ev.left = min(ev.left, element.x)
                    else:
                        ev.left = element.x
                    ev.elements.append(es)
                    ev.startCharArray.append(element.abcelem.startChar)
                    ev.endCharArray.append(element.abcelem.endChar)
                    if ev.startChar is None:
                        ev.startChar = element.abcelem.startChar
                    if ev.endChar is None:
                        ev.endChar = element.abcelem.endChar
                    if element.abcelem.midiPitches and len(element.abcelem.midiPitches):
                        if not ev.midiPitches:
                            ev.midiPitches = []
                        ev.midiPitches.extend(element.abcelem.midiPitches)
                    if element.abcelem.midiGraceNotePitches and len(element.abcelem.midiGraceNotePitches):
                        if not ev.midiGraceNotePitches:
                            ev.midiGraceNotePitches = []
                        ev.midiGraceNotePitches.extend(element.abcelem.midiGraceNotePitches)
                if next_is_bar:
                    event_hash[key].measureStart = True
                    next_is_bar = False
        return Obj(isTiedState=is_tied_state, duration=real_duration / time_divider, nextIsBar=next_is_bar or element.type == 'bar')

    def setup_events(self, starting_delay, time_divider, starting_bpm, warp=None):
        if not warp:
            warp = 1
        event_hash = Obj()
        # The time is the number of seconds from the beginning of the piece.
        time = starting_delay
        is_tied_state = None
        next_is_bar = True
        voices = self.make_voices_array()
        max_voice_time_milliseconds = 0
        bpm = starting_bpm
        for v in range(len(voices)):
            voice_time = time
            voice_time_milliseconds = js_round(voice_time * 1000)
            starting_repeat_elem = 0
            ending_repeat_elem = -1
            elements = voices[v]
            bpm = starting_bpm
            time_divider = self.get_beat_length() * bpm / 60
            tempo_done = -1
            last_hash = None
            for elem in range(len(elements)):
                this_measure = elements[elem].measureNumber
                if tempo_done != this_measure and self.tempoLocations.get(this_measure):
                    bpm = self.tempoLocations[this_measure]
                    time_divider = warp * self.get_beat_length() * bpm / 60
                    tempo_done = this_measure
                element = elements[elem].elem
                ret = self.add_element_to_events(event_hash, element, voice_time_milliseconds, elements[elem].top, elements[elem].height, elements[elem].line, elements[elem].measureNumber, time_divider, is_tied_state, next_is_bar)
                is_tied_state = ret.isTiedState
                next_is_bar = ret.nextIsBar
                voice_time += ret.duration
                if element.duration > 0 and ("event" + _num_key(voice_time_milliseconds)) in event_hash:  # This won't exist if this is the end of a tie.
                    last_hash = "event" + _num_key(voice_time_milliseconds)
                voice_time_milliseconds = js_round(voice_time * 1000)
                if element.type == 'bar':
                    bar_type = element.abcelem.type
                    end_repeat = bar_type == "bar_right_repeat" or bar_type == "bar_dbl_repeat"
                    start_ending = element.abcelem.startEnding == '1'
                    start_repeat = bar_type in ("bar_left_repeat", "bar_dbl_repeat", "bar_right_repeat")
                    if end_repeat:
                        # Force the end of the previous note to the position of the measure - the cursor won't go past the end repeat
                        if elem > 0 and last_hash in event_hash:
                            event_hash[last_hash].endX = element.x

                        if ending_repeat_elem == -1:
                            ending_repeat_elem = elem
                        last_voice_time_milliseconds = 0
                        tempo_done = -1
                        for el2 in range(starting_repeat_elem, ending_repeat_elem):
                            this_measure = elements[el2].measureNumber
                            if tempo_done != this_measure and self.tempoLocations.get(this_measure):
                                bpm = self.tempoLocations[this_measure]
                                time_divider = warp * self.get_beat_length() * bpm / 60
                                tempo_done = this_measure
                            element2 = elements[el2].elem
                            ret = self.add_element_to_events(event_hash, element2, voice_time_milliseconds, elements[el2].top, elements[el2].height, elements[el2].line, elements[el2].measureNumber, time_divider, is_tied_state, next_is_bar)
                            is_tied_state = ret.isTiedState
                            next_is_bar = ret.nextIsBar
                            voice_time += ret.duration
                            last_voice_time_milliseconds = voice_time_milliseconds
                            voice_time_milliseconds = js_round(voice_time * 1000)
                        lk = "event" + _num_key(last_voice_time_milliseconds)
                        if lk in event_hash:
                            event_hash[lk].endX = elements[ending_repeat_elem].elem.x
                        next_is_bar = True
                        ending_repeat_elem = -1
                    if start_ending:
                        ending_repeat_elem = elem
                    if start_repeat:
                        starting_repeat_elem = elem
            max_voice_time_milliseconds = max(max_voice_time_milliseconds, voice_time_milliseconds)
        # now we have all the events, but if there are multiple voices then there may be events out of order or duplicated, so normalize it.
        timing_events = _make_sorted_array(event_hash)
        _add_vertical_info(timing_events)
        _add_end_points(self.lines, timing_events)
        timing_events.append(Obj(type="end", milliseconds=max_voice_time_milliseconds))
        self.add_useful_callback_info(timing_events, bpm * warp)
        return timing_events

    def add_useful_callback_info(self, timing_events, bpm):
        milliseconds_per_measure = self.milliseconds_per_measure(bpm)
        for ev in timing_events:
            ev.millisecondsPerMeasure = milliseconds_per_measure

    def set_timing(self, bpm=None, measures_of_delay=None):
        """Compute the timing events of a rendered tune (``tune.noteTimings``)."""
        measures_of_delay = measures_of_delay or 0
        if not self.engraver or self.engraver.staffgroups is None:
            self.noteTimings = []
            return self.noteTimings

        tempo = self.metaText.get('tempo') if self.metaText else None
        natural_bpm = self.get_bpm(tempo)
        warp = 1
        if bpm:
            if tempo:
                warp = bpm / natural_bpm
        else:
            bpm = natural_bpm

        beat_length = self.get_beat_length()
        beats_per_second = bpm / 60
        measure_length = self.get_bar_length()

        starting_delay = measure_length / beat_length * measures_of_delay / beats_per_second
        if starting_delay:
            starting_delay -= self.get_pickup_length() / beat_length / beats_per_second
        time_divider = beat_length * beats_per_second

        self.noteTimings = self.setup_events(starting_delay, time_divider, bpm, warp)
        if len(self.noteTimings) > 0:
            self.totalTime = self.noteTimings[-1].milliseconds / 1000
            self.totalBeats = self.totalTime * beats_per_second
        else:
            self.totalTime = None
            self.totalBeats = None
        return self.noteTimings

    def find_selectable_element(self, target):
        if self.engraver and self.engraver.selectables:
            return self.engraver.find_selectable_element(target)
        return None

    def get_selectable_array(self):
        if self.engraver and self.engraver.selectables:
            return self.engraver.selectables
        return []

    # camelCase aliases matching the abcjs API
    getBeatLength = get_beat_length
    getPickupLength = get_pickup_length
    getBarLength = get_bar_length
    getTotalTime = get_total_time
    getTotalBeats = get_total_beats
    millisecondsPerMeasure = milliseconds_per_measure
    getBeatsPerMeasure = get_beats_per_measure
    getMeter = get_meter
    getMeterFraction = get_meter_fraction
    getKeySignature = get_key_signature
    getElementFromChar = get_element_from_char
    getBpm = get_bpm
    setUpAudio = set_up_audio
    setTiming = set_timing


def _num_key(n):
    from ..jsutil import js_str
    return js_str(n)


def _strip_engraver_refs(value):
    """Remove references to drawing objects (``abselem``) so the tune can be serialized."""
    if isinstance(value, dict):
        return {k: _strip_engraver_refs(v) for k, v in value.items() if k not in ('abselem',)}
    if isinstance(value, list):
        return [_strip_engraver_refs(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _compute_pickup_length(lines, bar_length):
    pickup_length = 0
    for line in lines:
        if line.staff:
            for st in line.staff:
                for voice in st.voices:
                    triplet_multiplier = 1
                    for el in voice:
                        is_spacer = el.rest and el.rest.type == "spacer"
                        if el.startTriplet:
                            triplet_multiplier = el.tripletMultiplier
                        if truthy(el.duration) and not is_spacer and el.el_type != "tempo":
                            pickup_length += el.duration * triplet_multiplier
                        if el.endTriplet:
                            triplet_multiplier = 1
                        if pickup_length >= bar_length:
                            pickup_length -= bar_length
                        if el.el_type == 'bar':
                            return pickup_length
    return pickup_length


def _add_vertical_info(timing_events):
    # Add vertical info to the bar events: put the next event's top, and the event after the next measure's top.
    last_bar_top = None
    last_bar_bottom = None
    last_event_top = None
    last_event_bottom = None
    for ev in reversed(timing_events):
        if ev.type == 'bar':
            ev.top = last_event_top
            ev.nextTop = last_bar_top
            last_bar_top = last_event_top

            ev.bottom = last_event_bottom
            ev.nextBottom = last_bar_bottom
            last_bar_bottom = last_event_bottom
        elif ev.type == 'event':
            last_event_top = ev.top
            last_event_bottom = ev.top + ev.height


def _make_sorted_array(h):
    arr = [h[k] for k in js_keys(h)]

    def cmp(a, b):
        diff = a.milliseconds - b.milliseconds
        # if the events have the same time, make sure a bar comes before a note
        if diff != 0:
            return diff
        return -1 if a.type == "bar" else 1

    return js_sort(arr, cmp)


def _skip_ties(elements, index):
    while index < len(elements) and elements[index].left is None:
        index += 1
    return at(elements, index)


def _add_end_points(lines, elements):
    if len(elements) < 1:
        return
    for i in range(len(elements) - 1):
        el = elements[i]
        nxt = _skip_ties(elements, i + 1)
        if el.left is not None:
            # If there is no left element that is because this is a tie so it should be skipped.
            end_x = nxt.left if (nxt and el.top == nxt.top) else lines[el.line].staffGroup.w
            if el.endX is not None:
                if end_x > el.left:
                    el.endX = min(el.endX, end_x)
            else:
                el.endX = end_x
    last_el = elements[-1]
    last_el.endX = lines[last_el.line].staffGroup.w
