"""Turn a parsed tune into a linear series of events, one list per voice (port of ``abc_midi_sequencer.js``).

The abc is provided line by line and might have repeats in it.  The elements
are rearranged to be a list of voices with all the repeats embedded, and no
lines.  The result is the input of :func:`abcpy.synth.flattener.flatten`.
"""

import json
import math

from ..jsutil import Obj, assign, at, js_set, js_round, js_str, js_keys, parse_int, is_nan, truthy, json_clone, obj_copy, js_floor
from .repeats import Repeats

PERCUSSION_PROGRAM = 128

# This should be set by the meter, but just in case that is missing, we'll take a guess.
# (Like abcjs, this is module state that persists between calls.)
_state = {'measureLength': 1}

_volumes = {  # stressBeat1, stressBeatDown, stressBeatUp
    'pppp': [15, 10, 5, 1],
    'ppp': [30, 20, 10, 1],
    'pp': [45, 35, 20, 1],
    'p': [60, 50, 35, 1],
    'mp': [75, 65, 50, 1],
    'mf': [90, 80, 65, 1],
    'f': [105, 95, 80, 1],
    'ff': [120, 110, 95, 1],
    'fff': [127, 125, 110, 1],
    'ffff': [127, 125, 110, 1],
}


def _int(v):
    r = parse_int(v, 10)
    return r


def sequence(abctune, options=None):
    """Create the per-voice event lists for ``abctune``.

    Options: ``program``, ``midiTranspose``, ``channel``, ``drum``, ``drumBars``,
    ``drumIntro``, ``drumOff``, ``qpm``, ``defaultQpm``.
    """
    options = obj_copy(options) if options else Obj()
    program = options.program or 0  # The program if there isn't a program specified.
    transpose = options.midiTranspose or 0
    # If the tune has a visual transpose then that needs to be subtracted out because we are getting the visual object.
    if abctune.visualTranspose:
        transpose -= abctune.visualTranspose
    channel = options.channel or 0
    channel_explicitly_set = False
    drum_pattern = options.drum or ""
    drum_bars = options.drumBars or 1
    drum_intro = options.drumIntro or 0
    drum_on = drum_pattern != ""
    drum_off_after_intro = bool(options.drumOff)
    style = {}  # The note head style for each voice.
    crescendo_size = 50  # how much to increase or decrease volume when crescendo/diminuendo is encountered.

    # All of the above overrides need to be integers
    program = _int(program)
    transpose = _int(transpose)
    channel = _int(channel)
    if channel == 10:
        program = PERCUSSION_PROGRAM
    drum_pattern = drum_pattern.split(" ") if isinstance(drum_pattern, str) else drum_pattern
    drum_bars = _int(drum_bars)
    drum_intro = _int(drum_intro)

    bagpipes = abctune.formatting.bagpipes  # If it is bagpipes, then the gracenotes are played on top of the main note.
    if bagpipes:
        program = 71

    starting_midi = []
    if abctune.formatting.midi:
        g = abctune.formatting.midi
        if g.program and len(g.program) > 0:
            program = g.program[0]
            if len(g.program) > 1:
                program = g.program[1]
                channel = g.program[0]
            channel_explicitly_set = True
        if g.transpose:
            transpose = g.transpose[0]
        if g.channel:
            channel = g.channel[0]
            channel_explicitly_set = True
        if g.drum:
            drum_pattern = g.drum
        if g.drumbars:
            drum_bars = g.drumbars[0]
        if g.drumon:
            drum_on = True
        if channel == 10:
            program = PERCUSSION_PROGRAM
        if g.beat:
            starting_midi.append(Obj(el_type='beat', beats=g.beat))
        if g.nobeataccents:
            starting_midi.append(Obj(el_type='beataccents', value=False))

    # If the tempo was passed in, use that.
    # If the tempo is specified, use that.
    # If there is a default, use that.
    # Otherwise, use the default.
    if options.qpm:
        qpm = _int(options.qpm)
    elif abctune.metaText.get('tempo'):
        qpm = _interpret_tempo(abctune.metaText['tempo'], abctune.get_beat_length())
    elif options.defaultQpm:
        qpm = options.defaultQpm
    else:
        qpm = 180  # The tempo if there isn't a tempo specified.

    start_voice = []
    if bagpipes:
        start_voice.append(Obj(el_type='bagpipes'))
    start_voice.append(Obj(el_type='instrument', program=program))
    if channel:
        start_voice.append(Obj(el_type='channel', channel=channel))
    if transpose:
        start_voice.append(Obj(el_type='transpose', transpose=transpose))
    start_voice.append(Obj(el_type='tempo', qpm=qpm))
    for sm in starting_midi:
        start_voice.append(sm)

    # visit each voice completely in turn
    voices = []
    clef_transpose_active = {}
    in_crescendo = {}
    in_diminuendo = {}
    duration_counter = [0]
    tempo_changes = Obj()
    tempo_changes["0"] = Obj(el_type='tempo', qpm=qpm, timing=0)
    st = Obj(currentVolume=None, drumOn=drum_on, drumPattern=drum_pattern, drumBars=drum_bars,
             startingDrumSet=False, channelExplicitlySet=channel_explicitly_set, qpm=qpm)
    repeats = []
    lines = abctune.lines
    for line in lines:
        # For each group of staff lines in the tune.
        if line.staff:
            staves = line.staff
            voice_number = 0
            for staff in staves:
                if staff.clef and staff.clef.type == "TAB":
                    continue

                # For each staff line
                for k in range(len(staff.voices)):
                    # For each voice in a staff line
                    voice = staff.voices[k]
                    if at(voices, voice_number) is None:
                        js_set(voices, voice_number, json_clone(start_voice))
                        voice_name = _get_track_title(line.staff, voice_number)
                        if voice_name:
                            voices[voice_number].insert(0, Obj(el_type="name", trackName=voice_name))
                        js_set(repeats, voice_number, Repeats(voices[voice_number]))
                    vv = voices[voice_number]
                    # Negate any transposition for the percussion staff.
                    if transpose and staff.clef.type == "perc":
                        vv.append(Obj(el_type='transpose', transpose=0))

                    if staff.clef and staff.clef.type == 'perc' and not st.channelExplicitlySet:
                        for item in vv:
                            if item.el_type == 'instrument':
                                item.program = PERCUSSION_PROGRAM
                    elif staff.key:
                        _add_key(vv, staff.key)
                    if staff.meter:
                        _add_meter(vv, staff.meter)
                    if not st.startingDrumSet and st.drumOn:  # drum information is only needed once, so use the first line and track 0.
                        vv.append(Obj(el_type='drum', params=Obj(pattern=st.drumPattern, bars=st.drumBars, on=st.drumOn, intro=drum_intro)))
                        st.startingDrumSet = True
                    if staff.clef and staff.clef.type != "perc" and staff.clef.transpose:
                        staff.clef.el_type = 'clef'
                        vv.append(Obj(el_type='transpose', transpose=staff.clef.transpose))
                        clef_transpose_active[voice_number] = False
                    if staff.clef and staff.clef.type:
                        if "-8" in staff.clef.type:
                            vv.append(Obj(el_type='transpose', transpose=-12))
                            clef_transpose_active[voice_number] = True
                        elif "+8" in staff.clef.type:
                            vv.append(Obj(el_type='transpose', transpose=12))
                            clef_transpose_active[voice_number] = True
                        else:
                            # if we had a previous treble+8 and now have a regular clef, then cancel the transposition
                            if clef_transpose_active.get(voice_number):
                                vv.append(Obj(el_type='transpose', transpose=0))
                                clef_transpose_active[voice_number] = False

                    if abctune.formatting.midi and abctune.formatting.midi.drumoff:
                        # If there is a drum off command right at the beginning it is put in the metaText instead of the stream,
                        # so we will just insert it here.
                        vv.append(Obj(el_type='bar'))
                        vv.append(Obj(el_type='drum', params=Obj(pattern="", on=False)))
                    note_events_in_bar = 0
                    triplet_multiplier = 0
                    triplet_duration_total = 0  # try to mitigate the js rounding problems.
                    triplet_duration_count = 0
                    st.currentVolume = [105, 95, 85, 1]

                    def set_dynamics(elem, v):
                        dynamic_type = None
                        if elem.decoration:
                            for name in ('pppp', 'ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff', 'ffff'):
                                if name in elem.decoration:
                                    dynamic_type = name
                                    break

                            if dynamic_type:
                                st.currentVolume = list(_volumes[dynamic_type])
                                volumes_per_note_pitch = [st.currentVolume]
                                if isinstance(elem.decoration, list):
                                    volumes_per_note_pitch = []
                                    for d in elem.decoration:
                                        if d in _volumes:
                                            volumes_per_note_pitch.append(list(_volumes[d]))
                                vv.append(Obj(el_type='beat', beats=list(st.currentVolume), volumesPerNotePitch=volumes_per_note_pitch))
                                in_crescendo[k] = False
                                in_diminuendo[k] = False

                            if "crescendo(" in elem.decoration:
                                n = _num_notes_to_decoration(voice, v, "crescendo)")
                                top = min(127, st.currentVolume[0] + crescendo_size)
                                end_dec = _ending_volume(voice, v + n + 1, list(_volumes.keys()))
                                if end_dec:
                                    top = _volumes[end_dec][0]
                                if n > 0:
                                    in_crescendo[k] = js_floor((top - st.currentVolume[0]) / n)
                                else:
                                    in_crescendo[k] = False
                                in_diminuendo[k] = False
                            elif "crescendo)" in elem.decoration:
                                in_crescendo[k] = False
                            elif "diminuendo(" in elem.decoration:
                                n2 = _num_notes_to_decoration(voice, v, "diminuendo)")
                                bottom = max(15, st.currentVolume[0] - crescendo_size)
                                end_dec2 = _ending_volume(voice, v + n2 + 1, list(_volumes.keys()))
                                if end_dec2:
                                    bottom = _volumes[end_dec2][0]
                                in_crescendo[k] = False
                                if n2 > 0:
                                    in_diminuendo[k] = js_floor((bottom - st.currentVolume[0]) / n2)
                                else:
                                    in_diminuendo[k] = False
                            elif "diminuendo)" in elem.decoration:
                                in_diminuendo[k] = False

                    for v in range(len(voice)):
                        # For each element in a voice
                        elem = voice[v]
                        t = elem.el_type
                        if t == "note":
                            if in_crescendo.get(k):
                                for x in range(3):
                                    st.currentVolume[x] += in_crescendo[k]
                                vv.append(Obj(el_type='beat', beats=list(st.currentVolume)))

                            if in_diminuendo.get(k):
                                for x in range(3):
                                    st.currentVolume[x] += in_diminuendo[k]
                                vv.append(Obj(el_type='beat', beats=list(st.currentVolume)))
                            set_dynamics(elem, v)

                            # regular items are just pushed.
                            if not elem.rest or elem.rest.type != 'spacer':
                                note_elem = Obj(elem=elem, el_type="note", timing=duration_counter[voice_number])  # Make a copy so that modifications aren't kept except for adding the midiPitches
                                if elem.style:
                                    note_elem.style = elem.style
                                elif style.get(voice_number):
                                    note_elem.style = style[voice_number]
                                note_elem.duration = 0.25 if elem.duration == 0 else elem.duration
                                if elem.startTriplet:
                                    triplet_multiplier = elem.tripletMultiplier
                                    triplet_duration_total = elem.startTriplet * triplet_multiplier * elem.duration
                                    if elem.startTriplet != elem.tripletR:  # most commonly (3:2:2
                                        if v + elem.tripletR <= len(voice):
                                            duration_total = 0
                                            for w in range(v, v + elem.tripletR):
                                                duration_total += voice[w].duration if voice[w].duration is not None else float('nan')
                                            triplet_duration_total = triplet_multiplier * duration_total
                                    note_elem.duration = note_elem.duration * triplet_multiplier
                                    note_elem.duration = js_round(note_elem.duration * 1000000) / 1000000
                                    triplet_duration_count = note_elem.duration
                                elif triplet_multiplier:
                                    if elem.endTriplet:
                                        triplet_multiplier = 0
                                        note_elem.duration = js_round((triplet_duration_total - triplet_duration_count) * 1000000) / 1000000
                                    else:
                                        note_elem.duration = note_elem.duration * triplet_multiplier
                                        note_elem.duration = js_round(note_elem.duration * 1000000) / 1000000
                                        triplet_duration_count += note_elem.duration
                                if elem.rest:
                                    note_elem.rest = elem.rest
                                if elem.decoration is not None:
                                    note_elem.decoration = list(elem.decoration)
                                if elem.pitches is not None:
                                    note_elem.pitches = [assign(p) for p in elem.pitches]
                                if elem.gracenotes is not None:
                                    note_elem.gracenotes = [assign(p) for p in elem.gracenotes]
                                if elem.chord is not None:
                                    note_elem.chord = [assign(p) for p in elem.chord]

                                vv.append(note_elem)
                                if elem.style == "rhythm":
                                    _chord_voice_off_this_bar(voices)
                                note_events_in_bar += 1
                                duration_counter[voice_number] += note_elem.duration
                        elif t in ("key", "keySignature"):
                            _add_key(vv, elem)
                        elif t == "meter":
                            _add_meter(vv, elem)
                        elif t == "clef":  # need to keep this to catch the "transpose" element.
                            if elem.transpose:
                                vv.append(Obj(el_type='transpose', transpose=elem.transpose))
                            if elem.type:
                                if "-8" in elem.type:
                                    vv.append(Obj(el_type='transpose', transpose=-12))
                                elif "+8" in elem.type:
                                    vv.append(Obj(el_type='transpose', transpose=12))
                        elif t == "tempo":
                            st.qpm = _interpret_tempo(elem, abctune.get_beat_length())
                            vv.append(Obj(el_type='tempo', qpm=st.qpm, timing=duration_counter[voice_number]))
                            tempo_changes[js_str(duration_counter[voice_number])] = Obj(el_type='tempo', qpm=st.qpm, timing=duration_counter[voice_number])
                        elif t == "bar":
                            if note_events_in_bar > 0:  # don't add two bars in a row.
                                vv.append(Obj(el_type='bar'))  # We need the bar marking to reset the accidentals.
                            set_dynamics(elem, v)
                            note_events_in_bar = 0
                            repeats[voice_number].add_bar(elem, voice_number)
                        elif t == 'style':
                            style[voice_number] = elem.head
                        elif t == 'timeSignature':
                            vv.append(_interpret_meter(elem))
                        elif t in ('part', 'stem', 'scale', 'break', 'font'):
                            # These elements don't affect sound
                            pass
                        elif t == 'midi':
                            drum_change = False
                            cmd = elem.cmd
                            if cmd == "drumon":
                                st.drumOn = True
                                drum_change = True
                            elif cmd == "drumoff":
                                st.drumOn = False
                                drum_change = True
                            elif cmd == "drum":
                                st.drumPattern = elem.params
                                drum_change = True
                            elif cmd == "drumbars":
                                st.drumBars = elem.params[0]
                                drum_change = True
                            elif cmd == "drummap":
                                # This is handled before getting here so it can be ignored.
                                pass
                            elif cmd == "channel":
                                # There's not much needed for the channel except to look out for the percussion channel
                                if at(elem.params, 0) == 10:
                                    vv.append(Obj(el_type='instrument', program=PERCUSSION_PROGRAM))
                            elif cmd == "program":
                                _add_if_different(vv, Obj(el_type='instrument', program=at(elem.params, 0)))
                                st.channelExplicitlySet = True
                            elif cmd == "transpose":
                                vv.append(Obj(el_type='transpose', transpose=at(elem.params, 0)))
                            elif cmd == "gchordoff":
                                vv.append(Obj(el_type='gchordOn', tacet=True))
                            elif cmd == "gchordon":
                                vv.append(Obj(el_type='gchordOn', tacet=False))
                            elif cmd == "beat":
                                vv.append(Obj(el_type='beat', beats=elem.params))
                            elif cmd == "nobeataccents":
                                vv.append(Obj(el_type='beataccents', value=False))
                            elif cmd == "beataccents":
                                vv.append(Obj(el_type='beataccents', value=True))
                            elif cmd in ("vol", "volinc"):
                                vv.append(Obj(el_type=cmd, volume=at(elem.params, 0)))
                            elif cmd in ("swing", "gchord", "bassvol", "chordvol"):
                                vv.append(Obj(el_type=cmd, param=at(elem.params, 0)))
                            elif cmd in ("bassprog", "chordprog"):
                                vv.append(Obj(el_type=cmd, value=at(elem.params, 0), octaveShift=at(elem.params, 1)))
                            elif cmd == "gchordbars":
                                vv.append(Obj(el_type=cmd, param=at(elem.params, 0)))
                            # other midi commands are not handled
                            if drum_change:
                                voices[0].append(Obj(el_type='drum', params=Obj(pattern=st.drumPattern, bars=st.drumBars, intro=drum_intro, on=st.drumOn)))
                                st.startingDrumSet = True
                        # other element types are ignored
                    voice_number += 1
                    if not at(duration_counter, voice_number):
                        js_set(duration_counter, voice_number, 0)
    for r in range(len(repeats)):
        if repeats[r] is not None:
            voices[r] = repeats[r].resolve_repeats()

    # If there are tempo changes, make sure they are in all the voices. This must be done post process because all the elements in all the voices need to be created first.
    _insert_tempo_changes(voices, tempo_changes)

    if drum_intro:
        pickups = abctune.get_pickup_length()
        # add some measures of rests to the start of each track.
        for vv in voices:
            insert_point = 0
            while insert_point < len(vv) and vv[insert_point].el_type != "note":
                insert_point += 1
            if len(vv) > insert_point:
                for w in range(drum_intro):
                    # If it is the last measure of intro, subtract the pickups.
                    if pickups == 0 or w < drum_intro - 1:
                        vv[insert_point:insert_point] = [
                            Obj(el_type="note", rest=Obj(type="rest"), duration=_state['measureLength']),
                            Obj(el_type="bar"),
                        ]
                        insert_point += 2
                    else:
                        vv.insert(insert_point, Obj(el_type="note", rest=Obj(type="rest"), duration=_state['measureLength'] - pickups))
                        insert_point += 1
                if drum_off_after_intro:
                    st.drumOn = False
                    vv.insert(insert_point, Obj(el_type='drum', params=Obj(pattern=st.drumPattern, bars=st.drumBars, intro=drum_intro, on=st.drumOn)))
                    insert_point += 1
                    drum_off_after_intro = False
    if len(voices) > 0 and len(voices[0]) > 0:
        voices[0][0].pickupLength = abctune.get_pickup_length()
    return [v if v is not None else [] for v in voices]


def _num_notes_to_decoration(voice, start, decoration):
    counter = 0
    for i in range(start + 1, len(voice)):
        if voice[i].el_type == "note":
            counter += 1
        if voice[i].decoration and decoration in voice[i].decoration:
            return counter
    return counter


def _ending_volume(voice, start, volume_decorations):
    end = min(len(voice), start + 3)  # If we have a volume within a couple notes of the end then assume that is the destination.
    for i in range(start, end):
        if voice[i].el_type == "note":
            if voice[i].decoration:
                for d in voice[i].decoration:
                    if d in volume_decorations:
                        return d
    return None


def _insert_tempo_changes(voices, tempo_changes):
    if not tempo_changes or len(tempo_changes) == 0:
        return
    change_positions = js_keys(tempo_changes)
    for i in range(len(voices)):
        voice = voices[i]
        if voice is None:
            continue
        last_tempo = tempo_changes['0'].qpm if tempo_changes['0'] else 0  # Don't insert redundant changes.
        j = 0
        while j < len(voice):
            el = voice[j]
            if el.el_type == "tempo":
                last_tempo = el.qpm
            key = js_str(el.timing)
            if key in change_positions and last_tempo != tempo_changes[key].qpm:
                last_tempo = tempo_changes[key].qpm
                if el.el_type == "tempo":
                    el.qpm = tempo_changes[key].qpm
                    j += 1  # when there is a tempo element the next element has the same timing and we don't want it to match the second time.
                else:
                    voices[i].insert(j, Obj(el_type="tempo", qpm=tempo_changes[key].qpm, timing=el.timing))
                    j += 2  # skip the element we just inserted.
            j += 1


def _chord_voice_off_this_bar(voices):
    for voice in voices:
        if voice is None:
            continue
        j = len(voice) - 1
        while j >= 0 and voice[j].el_type != 'bar':
            voice[j].noChordVoice = True
            j -= 1


def _get_track_title(staff, voice_number):
    if not staff or len(staff) <= voice_number or not staff[voice_number].title:
        return None
    return " ".join(js_str(t) if t is not None else "" for t in staff[voice_number].title)


def _interpret_tempo(element, beat_length):
    duration = 1 / 4
    if truthy(element.duration):
        duration = element.duration[0]
    bpm = 60
    if element.bpm:
        bpm = element.bpm
    # The tempo is defined with a beat length of "duration". If that isn't the natural beat length then there is a translation.
    return duration * bpm / beat_length


def _interpret_meter(element):
    t = element.type
    if t == "common_time":
        meter = Obj(el_type='meter', num=4, den=4)
        _state['measureLength'] = 4 / 4
    elif t == "cut_time":
        meter = Obj(el_type='meter', num=2, den=2)
        _state['measureLength'] = 2 / 2
    elif t == "specified":
        # TODO-PER: only taking the first meter, so the complex meters are not handled.
        num = 0
        if element.value and len(element.value) > 0 and element.value[0].num.find('+') > 0:
            for p in element.value[0].num.split('+'):
                num += parse_int(p, 10)
        else:
            num = parse_int(element.value[0].num, 10)
        meter = Obj(el_type='meter', num=num, den=element.value[0].den)
        den = parse_int(element.value[0].den, 10)
        _state['measureLength'] = num / den if den else float('nan')
    else:
        # This should never happen.
        meter = Obj(el_type='meter')
        _state['measureLength'] = 1
    return meter


def _remove_naturals(accidentals):
    return [a for a in accidentals if a.acc != "natural"]


def _add_key(arr, key):
    if key.root == 'HP':
        new_key = Obj(el_type='key', accidentals=[Obj(acc='natural', note='g'), Obj(acc='sharp', note='f'), Obj(acc='sharp', note='c')])
    else:
        new_key = Obj(el_type='key', accidentals=_remove_naturals(key.accidentals))
    _add_if_different(arr, new_key)


def _add_meter(arr, meter):
    new_meter = _interpret_meter(meter)
    _add_if_different(arr, new_meter)


def _stringify(o):
    return json.dumps(o, default=lambda x: None)


def _add_if_different(arr, item):
    for i in range(len(arr) - 1, -1, -1):
        if arr[i].el_type == item.el_type:
            if _stringify(arr[i]) != _stringify(item):
                arr.append(item)
            return
    arr.append(item)
