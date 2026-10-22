"""Creates a chord grid ("chord chart") from a parsed tune (port of ``chord-grid.js``).

1) It will always be 8 measures on a line, unless it is a 12 bar blues, then it will be 4 measures.
2) If it is not in 4/4 (or 2/2) it raises an error.
3) If there are no chords it raises an error.
4) It is divided into parts with the part title and an array of measures.
...see the abcjs source for the complete list of rules.
"""

import math

from ..jsutil import Obj, at, js_set, is_nan, js_floor


class ChordGridError(Exception):
    pass


break_synonyms = ['break', '(break)', 'no chord', 'n.c.', 'tacet']


def chord_grid(visual_obj):
    meter = visual_obj.get_meter_fraction()
    is_common_time = meter.num == 4 and meter.den == 4
    is_cut_time = meter.num == 2 and meter.den == 2
    if not is_cut_time and not is_common_time:
        raise ChordGridError("notCommonTime")
    deline = visual_obj.deline()

    chart_lines = []

    non_subtitle = False
    for section in deline:
        if section.subtitle:
            if non_subtitle:
                # Don't do the subtitle if the first thing is the subtitle, but that is already printed on the top
                chart_lines.append(Obj(type="subtitle", subtitle=section.subtitle.text))
        elif section.text:
            non_subtitle = True
            chart_lines.append(Obj(type="text", text=section.text.text if isinstance(section.text, dict) else None))
        elif section.staff:
            non_subtitle = True
            # The first staff and the first voice in it drive everything.
            parts = _flatten_voices(section.staff)
            chart_lines = chart_lines + parts
    _collapse_identical_endings(chart_lines)
    _add_line_breaks(chart_lines)
    _add_percents(chart_lines)
    return chart_lines


def _flatten_voices(staves):
    parts = []
    st = Obj(partName="", measures=[], currentBar=Obj(chord=['', '', '', '']), lastChord="", nextBarEnding="")
    for staff_num, staff in enumerate(staves):
        if staff.voices:
            for voice_num, voice in enumerate(staff.voices):
                beat_num = 0
                measure_num = 0
                for element in voice:
                    current_bar = st.currentBar
                    if element.el_type == 'part':
                        if len(st.measures) > 0:
                            if staff_num == 0 and voice_num == 0:
                                parts.append(Obj(type="part", name=st.partName, lines=[st.measures]))
                                st.measures = []
                        st.partName = element.title
                    elif element.el_type == 'note':
                        _add_decoration(element, current_bar)
                        int_beat = js_floor(beat_num)
                        if element.chord and len(element.chord) > 0:
                            chord = element.chord[0]  # Use just the first chord specified - if there are multiple ones, then ignore them
                            chord_name = chord.name if (chord.position == 'default' or chord.name.lower() in break_synonyms) else ''
                            if chord_name:
                                if int_beat > 0 and not current_bar.chord[0]:  # Be sure there is a chord for the first beat in a measure
                                    current_bar.chord[0] = st.lastChord
                                st.lastChord = chord_name
                                if is_nan(int_beat):
                                    pass  # (abcjs sets a "NaN" property on the array here, which has no effect)
                                elif at(current_bar.chord, int_beat):
                                    # If there is already a chord on this beat put the next chord on the next beat, but don't overwrite anything.
                                    if int_beat < 4 and not at(current_bar.chord, int_beat + 1):
                                        js_set(current_bar.chord, int_beat + 1, chord_name)
                                else:
                                    js_set(current_bar.chord, int_beat, chord_name)
                            for ch in element.chord:
                                if ch.position != 'default' and chord.name.lower() not in break_synonyms:
                                    if not current_bar.annotations:
                                        current_bar.annotations = []
                                    current_bar.annotations.append(ch.name)
                        if not element.rest or element.rest.type != 'spacer':
                            # if the duration is zero and it is a note, then it is stemless and should count as a quarter note
                            dur = 0.25 if (element.duration == 0 and not element.rest) else element.duration
                            this_duration = js_floor(dur * 4)
                            if this_duration > 4:
                                measure_num += js_floor(this_duration / 4)
                                beat_num = 0
                            else:
                                this_beat = dur * 4
                                if element.tripletMultiplier:
                                    this_beat *= element.tripletMultiplier
                                beat_num += this_beat
                    elif element.el_type == 'bar':
                        if st.nextBarEnding:
                            current_bar.ending = st.nextBarEnding
                            st.nextBarEnding = ""
                        _add_decoration(element, current_bar)
                        if element.chord:
                            for ch in element.chord:
                                if ch.position != 'default':
                                    if not current_bar.annotations:
                                        current_bar.annotations = []
                                    current_bar.annotations.append(ch.name)
                        if element.type == 'bar_dbl_repeat' or element.type == 'bar_left_repeat':
                            current_bar.hasStartRepeat = True
                        if element.type == 'bar_dbl_repeat' or element.type == 'bar_right_repeat':
                            current_bar.hasEndRepeat = True
                        if element.startEnding:
                            st.nextBarEnding = element.startEnding
                        if beat_num >= 4:
                            if current_bar.chord[0] == '':
                                # If there isn't a chord change at the beginning, repeat the last chord found
                                if current_bar.chord[1] or current_bar.chord[2] or current_bar.chord[3]:
                                    current_bar.chord[0] = _find_last_chord(st.measures)
                            if staff_num == 0 and voice_num == 0:
                                st.measures.append(current_bar)
                            else:
                                # Add the found items of interest to the original array
                                index = measure_num
                                part_index = 0
                                while part_index < len(parts) and index >= len(parts[part_index].lines[0]):
                                    index -= len(parts[part_index].lines[0])
                                    part_index += 1
                                if part_index < len(parts) and index < len(parts[part_index].lines[0]):
                                    bar = parts[part_index].lines[0][index]
                                    for c in range(4):
                                        if not bar.chord[c] and current_bar.chord[c]:
                                            bar.chord[c] = current_bar.chord[c]
                                    if current_bar.annotations:
                                        if not bar.annotations:
                                            bar.annotations = current_bar.annotations
                                        else:
                                            bar.annotations = bar.annotations + current_bar.annotations
                                measure_num += 1
                            st.currentBar = Obj(chord=['', '', '', ''])
                        else:
                            current_bar.chord = ['', '', '', '']
                        beat_num = 0
                if staff_num == 0 and voice_num == 0:
                    parts.append(Obj(type="part", name=st.partName, lines=[st.measures]))
    if not st.lastChord:
        raise ChordGridError("noChords")
    return parts


def _find_last_chord(measures):
    for m in range(len(measures) - 1, -1, -1):
        for c in range(len(measures[m].chord) - 1, -1, -1):
            if measures[m].chord[c]:
                return measures[m].chord[c]
    return None


def _collapse_identical_endings(chart_lines):
    for line in chart_lines:
        if line.type == "part":
            part_line = line.lines[0]
            ending1 = next((i for i, bar in enumerate(part_line) if bar.ending), -1)
            ending2 = next((i for i, bar in enumerate(part_line) if i > ending1 and bar.ending), -1)
            if ending1 >= 0 and ending2 >= 0:
                # If the endings are not the same length, don't collapse
                if ending2 - ending1 == len(part_line) - ending2:
                    matches = True
                    i = 0
                    while i < ending2 - ending1 and matches:
                        lhs = part_line[ending1 + i]
                        rhs = part_line[ending2 + i]
                        for c in range(4):
                            if at(lhs.chord, c) != at(rhs.chord, c):
                                matches = False
                        if lhs.annotations and not rhs.annotations:
                            matches = False
                        if not lhs.annotations and rhs.annotations:
                            matches = False
                        if lhs.annotations and rhs.annotations:
                            if len(lhs.annotations) != len(rhs.annotations):
                                matches = False
                            else:
                                for j in range(len(lhs.annotations)):
                                    if lhs.annotations[j] != rhs.annotations[j]:
                                        matches = False
                        i += 1
                    if matches:
                        del part_line[ending1].ending
                        del part_line[ending2:]


def _add_line_breaks(chart_lines):
    for line in chart_lines:
        if line.type == "part":
            new_lines = []
            old_lines = line.lines[0]
            is12bar = False
            first_end_repeat = next((i for i, l in enumerate(old_lines) if l.hasEndRepeat), -1)
            length = min(first_end_repeat + 1, len(old_lines)) if first_end_repeat >= 0 else len(old_lines)
            if length == 12:
                is12bar = True
            bars_per_line = 4 if is12bar else 8  # Only do 4 bars per line for 12-bar blues
            for i in range(0, len(old_lines), bars_per_line):
                new_line = old_lines[i:i + bars_per_line]
                end_repeat = next((j for j, l in enumerate(new_line) if l.hasEndRepeat), -1)
                if 0 <= end_repeat < len(new_line) - 1:
                    new_lines.append(new_line[0:end_repeat + 1])
                    new_lines.append(new_line[end_repeat + 1:])
                else:
                    new_lines.append(new_line)
            # TODO-PER: The following probably doesn't handle all cases. Rethink it.
            for i in range(len(new_lines)):
                if new_lines[i][0].ending:
                    prev_line = max(0, i - 1)
                    to_add = len(new_lines[prev_line]) - len(new_lines[i])
                    this_line = [Obj(noBorder=True, chord=['', '', '', '']) for _ in range(to_add)]
                    new_lines[i] = this_line + new_lines[i]
            line.lines = new_lines


def _add_percents(chart_lines):
    for part in chart_lines:
        if part.lines:
            last_measure_single = False
            last_chord = ""
            for line in part.lines:
                for measure in line:
                    if not measure.noBorder:
                        chords = measure.chord
                        if not at(chords, 0) and not at(chords, 1) and not at(chords, 2) and not at(chords, 3):
                            # if there are no chords specified for this measure
                            if last_measure_single:
                                if last_chord:
                                    chords[0] = '%'
                            else:
                                chords[0] = last_chord
                            last_measure_single = True
                        elif not at(chords, 1) and not at(chords, 2) and not at(chords, 3):
                            # if there is a single chord for this measure
                            last_measure_single = True
                            last_chord = chords[0]
                        else:
                            # if the measure is complicated - in that case the next measure won't get %
                            last_measure_single = False
                            last_chord = at(chords, 3) or at(chords, 2) or at(chords, 1)


def _add_decoration(element, current_bar):
    if element.decoration:
        # Some decorations are interesting to rhythm players
        for d in element.decoration:
            if d in ('fermata', 'segno', 'coda', "D.C.", "D.S.", "D.C.alcoda", "D.C.alfine", "D.S.alcoda", "D.S.alfine", "fine"):
                if not current_bar.annotations:
                    current_bar.annotations = []
                current_bar.annotations.append(d)
