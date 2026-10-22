"""Builds the tune structure while parsing (port of ``tune-builder.js``)."""

from ..jsutil import Obj, at, assign, js_set, json_clone, truthy
from . import key_voice


class TuneBuilder:
    def __init__(self, tune):
        self.tune = tune
        self.voice_defs = {}
        self.current_voice_name = ''
        tune.reset()

    def set_visual_transpose(self, visual_transpose):
        if visual_transpose is not None:
            self.tune.visualTranspose = visual_transpose

    def clean_up(self, barsperstaff, staffnonote, curr_slur):
        tune = self.tune
        _close_line(tune)  # Close the last line.
        tune.runningFonts = None

        _simplify_meta_text(tune)

        # If the tempo was created with a string like "Allegro", then the duration of a beat needs to be set at the last moment, when it is most likely known.
        tempo = tune.metaText.get('tempo')
        if tempo and tempo.bpm and tempo.duration is None:
            tempo.duration = [tune.get_beat_length()]

        _no_warn_before_title(tune)

        # Remove any blank lines
        any_deleted = False
        for i in range(len(tune.lines)):
            if tune.lines[i].staff is not None:
                has_any = False
                staff = tune.lines[i].staff
                for s in range(len(staff)):
                    if staff[s] is None:
                        any_deleted = True
                        staff[s] = None
                    else:
                        voices = staff[s].voices
                        for v in range(len(voices)):
                            if voices[v] is None:
                                voices[v] = []
                            elif _contains_notes(voices[v]):
                                has_any = True
                if not has_any:
                    tune.lines[i] = None
                    any_deleted = True
        if any_deleted:
            tune.lines = [line for line in tune.lines if line is not None]
            for line in tune.lines:
                if line.staff is not None:
                    line.staff = [st for st in line.staff if st is not None]

        # if we exceeded the number of bars allowed on a line, then force a new line
        if barsperstaff:
            while _wrap_music_lines(tune.lines, barsperstaff):
                pass

        # If we were passed staffnonote, then we want to get rid of all staffs that contain only rests.
        if staffnonote:
            any_deleted = False
            for i in range(len(tune.lines)):
                if tune.lines[i].staff is not None:
                    staff = tune.lines[i].staff
                    for s in range(len(staff)):
                        keep_this = False
                        for v in range(len(staff[s].voices)):
                            if _contains_notes_strict(staff[s].voices[v]):
                                keep_this = True
                        if not keep_this:
                            any_deleted = True
                            staff[s] = None
            if any_deleted:
                for line in tune.lines:
                    if line.staff is not None:
                        line.staff = [st for st in line.staff if st is not None]

        _fix_titles(tune.lines)

        # Remove the temporary working variables
        for line in tune.lines:
            if line.staff:
                for st in line.staff:
                    st.pop('workingClef', None)

        # If there are overlays, create new voices for them.
        had_overlays = False
        while _resolve_overlays(tune):
            had_overlays = True
        if had_overlays:
            # remove any blank lines that got inserted - not sure how that happened.
            voice_num = 0
            is_useful = _voice_useful(tune.lines, voice_num)
            while is_useful != 'not-found':
                is_useful = _voice_useful(tune.lines, voice_num)
                if not is_useful:
                    _delete_voice(tune.lines, voice_num)
                else:
                    voice_num += 1

        for i in range(len(tune.lines)):
            staff = tune.lines[i].staff
            if staff:
                tune.staffNum = 0
                while tune.staffNum < len(staff):
                    if staff[tune.staffNum].clef:
                        key_voice.fix_clef(staff[tune.staffNum].clef)
                    tune.voiceNum = 0
                    while tune.voiceNum < len(staff[tune.staffNum].voices):
                        voice = staff[tune.staffNum].voices[tune.voiceNum]
                        _clean_up_slurs_in_line(voice, tune.staffNum, tune.voiceNum, curr_slur)
                        for el in voice:
                            if el.el_type == 'clef':
                                key_voice.fix_clef(el)
                        if len(voice) > 0 and voice[-1].barNumber:
                            # Don't hang a bar number on the last bar line: it should go on the next line.
                            next_line = _get_next_music_line(tune.lines, i)
                            if next_line:
                                next_line.staff[0].barNumber = voice[-1].barNumber
                            del voice[-1].barNumber
                        tune.voiceNum += 1
                    tune.staffNum += 1

        # Remove temporary variables that the outside doesn't need to know about
        tune.staffNum = None
        tune.voiceNum = None
        tune.lineNum = None
        tune.potentialStartBeam = None
        tune.potentialEndBeam = None
        tune.vskipPending = None

        return curr_slur

    def add_tie_to_last_note(self, dotted_tie):
        el = _get_last_note(self.tune)
        if el and el.pitches and len(el.pitches) > 0:
            el.pitches[0].startTie = Obj()
            if dotted_tie:
                el.pitches[0].startTie.style = 'dotted'
            return True
        return False

    def append_element(self, typ, start_char, end_char, hash_params):
        tune = self.tune
        hash_params.el_type = typ
        if start_char is not None:
            hash_params.startChar = start_char
        if end_char is not None:
            hash_params.endChar = end_char
        if typ == 'note':
            # Now, add the startBeam and endBeam where it is needed.
            dur = _get_duration(hash_params)
            if dur >= 0.25:  # The beam ends on the note before this.
                _end_beam_last(tune)
            elif hash_params.force_end_beam_last and tune.potentialStartBeam is not None:
                _end_beam_last(tune)
            elif hash_params.end_beam and tune.potentialStartBeam is not None:  # the beam is forced to end on this note, probably because of a space in the ABC
                if hash_params.rest is None:
                    _end_beam_here(hash_params, tune)
                else:
                    _end_beam_last(tune)
            elif hash_params.rest is None:  # this a short note and we aren't about to end the beam
                if tune.potentialStartBeam is None:  # We aren't collecting notes for a beam, so start here.
                    if not hash_params.end_beam:
                        tune.potentialStartBeam = hash_params
                        tune.potentialEndBeam = None
                else:
                    tune.potentialEndBeam = hash_params  # Continue the beaming, look for the end next note.
        else:  # It's not a note, so there definitely isn't beaming after it.
            _end_beam_last(tune)
        hash_params.pop('end_beam', None)  # We don't want this temporary variable hanging around.
        hash_params.pop('force_end_beam_last', None)
        if hash_params.rest and hash_params.rest.type == 'invisible':
            hash_params.pop('decoration', None)  # the decorations on invisible rests should be invisible, too.
        if len(tune.lines) <= tune.lineNum or len(tune.lines[tune.lineNum].staff) <= tune.staffNum:
            # This prevents a crash, but it drops the element.
            return False
        if tune.lines[tune.lineNum].staff[tune.staffNum] is None:
            # (abcjs crashes here when a staff is missing; drop the element instead)
            return False

        _push_note(self, tune, hash_params, self.voice_defs, self.current_voice_name)
        return True

    def append_starting_element(self, typ, start_char, end_char, hash_params2):
        tune = self.tune
        # If we're in the middle of beaming, then end the beam.
        _close_line(tune)

        # We only ever want implied naturals the first time.
        implied_naturals = None
        if typ == 'key':
            implied_naturals = hash_params2.impliedNaturals
            hash_params2.pop('impliedNaturals', None)
            hash_params2.pop('explicitAccidentals', None)

        # Clone the object because it will be sticking around for the next line and we don't want the extra fields in it.
        hash_params = assign(hash_params2)

        # be sure that we are on a music type line before doing the following.
        line = at(tune.lines, tune.lineNum)
        if line is None:
            return
        staff = line.staff
        if staff is None:
            return

        # If tune is the first item in tune staff, then we might have to initialize the staff, first.
        if len(staff) <= tune.staffNum:
            st = Obj()
            js_set(staff, tune.staffNum, st)
            st.clef = assign(staff[0].clef)
            st.key = assign(staff[0].key)
            if staff[0].meter:
                st.meter = assign(staff[0].meter)
            st.workingClef = assign(staff[0].workingClef)
            st.voices = [[]]
        # If tune is a clef type, then we replace the working clef on the line.
        if typ == 'clef':
            staff[tune.staffNum].workingClef = hash_params

        # These elements should not be added twice, so if the element exists on tune line without a note or bar before it, just replace the staff version.
        voice = staff[tune.staffNum].voices[tune.voiceNum]
        for i in range(len(voice)):
            if voice[i].el_type == 'note' or voice[i].el_type == 'bar':
                hash_params.el_type = typ
                hash_params.startChar = start_char
                hash_params.endChar = end_char
                if implied_naturals:
                    hash_params.accidentals = implied_naturals + hash_params.accidentals
                voice.append(hash_params)
                return
            if voice[i].el_type == typ:
                hash_params.el_type = typ
                hash_params.startChar = start_char
                hash_params.endChar = end_char
                if implied_naturals:
                    hash_params.accidentals = implied_naturals + hash_params.accidentals
                voice[i] = hash_params
                return
        # We didn't see either that type or a note, so replace the element to the staff.
        staff[tune.staffNum][typ] = hash_params2

    def add_subtitle(self, s, info):
        _push_line(self.tune, Obj(subtitle=Obj(text=s, startChar=info.startChar, endChar=info.endChar)))

    def add_spacing(self, num):
        self.tune.vskipPending = num

    def add_new_page(self, num):
        _push_line(self.tune, Obj(newpage=num))

    def add_separator(self, space_above, space_below, line_length, info):
        from ..jsutil import js_round
        _push_line(self.tune, Obj(separator=Obj(spaceAbove=js_round(space_above), spaceBelow=js_round(space_below), lineLength=js_round(line_length), startChar=info.startChar, endChar=info.endChar)))

    def add_text(self, s, info):
        _push_line(self.tune, Obj(text=Obj(text=s, startChar=info.startChar, endChar=info.endChar)))

    def add_centered(self, s):
        _push_line(self.tune, Obj(text=[Obj(text=s, center=True)]))

    def change_voice_scale(self, scale):
        self.append_element('scale', None, None, Obj(size=scale))

    def change_voice_color(self, color):
        self.append_element('color', None, None, Obj(color=color))

    def start_new_line(self, params):
        # If the pointed to line doesn't exist, just create that. If the line does exist, but doesn't have any music on it, just use it.
        # If it does exist and has music, then increment the line number. If the new element doesn't exist, create it.
        tune = self.tune
        _close_line(tune)  # Close the previous line.
        if params.currentVoiceName:
            self.current_voice_name = params.currentVoiceName
            self.voice_defs[params.currentVoiceName] = params

        while True:
            line = at(tune.lines, tune.lineNum)
            if line is None:
                _create_line(self, tune, params)
            elif line.staff is None:
                tune.lineNum += 1
                continue
            elif at(line.staff, tune.staffNum) is None:
                _create_staff(self, tune, params)
            elif at(line.staff[tune.staffNum].voices, tune.voiceNum) is None:
                _create_voice(self, tune, params)
            elif not _contains_notes(line.staff[tune.staffNum].voices[tune.voiceNum]):
                # We don't need a new line but we might need to update parts of it.
                if params.part:
                    self.append_element('part', params.part.startChar, params.part.endChar, Obj(title=params.part.title))
            else:
                tune.lineNum += 1
                continue
            break

    def set_running_font(self, typ, font):
        # This is called at tune start to set the current default fonts so we know whether to record a change.
        self.tune.runningFonts[typ] = font

    def set_bar_number_immediate(self, bar_number):
        # If tune is called right at the beginning of a line, then correct the measure number that is already written.
        # If tune is called at the beginning of a measure, then correct the measure number that was just created.
        # If tune is called in the middle of a measure, then subtract one from it, because it will be incremented before applied.
        current_voice = self.get_current_voice()
        if current_voice and len(current_voice) > 0:
            last_element = current_voice[-1]
            if last_element.el_type == 'bar':
                if last_element.barNumber is not None:  # the measure number might not be written for tune bar, don't override that.
                    last_element.barNumber = bar_number
            else:
                return bar_number - 1
        return bar_number

    def has_begin_music(self):
        # return true if there exists at least one line that contains "staff"
        for line in self.tune.lines:
            if line.staff is not None:
                return True
        return False

    def is_first_line(self, index):
        for i in range(index - 1, -1, -1):
            if self.tune.lines[i].staff is not None:
                return False
        return True

    def get_current_voice(self):
        tune = self.tune
        curr_line = _get_prev_music_line(tune.lines, tune.lineNum)
        if not curr_line:
            return None
        curr_staff = at(curr_line.staff, tune.staffNum)
        if not curr_staff:
            return None
        v = at(curr_staff.voices, tune.voiceNum)
        return v

    def set_current_voice(self, staff_num, voice_num, name):
        tune = self.tune
        tune.staffNum = staff_num
        tune.voiceNum = voice_num
        self.current_voice_name = name
        for i in range(len(tune.lines)):
            if tune.lines[i].staff:
                st = at(tune.lines[i].staff, staff_num)
                if st is None or at(st.voices, voice_num) is None or not _contains_notes(st.voices[voice_num]):
                    tune.lineNum = i
                    if not st or at(st.voices, voice_num) is not None:
                        return True
                    return False
        tune.lineNum = len(tune.lines)
        return False

    def add_meta_text(self, key, value, info):
        tune = self.tune
        if tune.metaText.get(key) is None:
            tune.metaText[key] = value
            tune.metaTextInfo[key] = info
        else:
            if isinstance(tune.metaText[key], str) and isinstance(value, str):
                tune.metaText[key] += "\n" + value
            else:
                if isinstance(tune.metaText[key], str):
                    # (abcjs compares against the literal 'string' here, so the string is never wrapped)
                    pass
                if isinstance(value, str):
                    value = [Obj(text=value)]
                cur = tune.metaText[key]
                if isinstance(cur, str):
                    # String.concat(array) in JS produces a string
                    from ..jsutil import js_str
                    tune.metaText[key] = cur + js_str(value)
                else:
                    tune.metaText[key] = cur + (value if isinstance(value, list) else [value])
            tune.metaTextInfo[key].endChar = info.endChar

    def add_meta_text_array(self, key, value, info):
        tune = self.tune
        if tune.metaText.get(key) is None:
            tune.metaText[key] = [value]
            tune.metaTextInfo[key] = info
        else:
            tune.metaText[key].append(value)
            tune.metaTextInfo[key].endChar = info.endChar

    def add_meta_text_obj(self, key, value, info):
        self.tune.metaText[key] = value
        self.tune.metaTextInfo[key] = info


def _is_array_of_strings(arr):
    if not arr:
        return False
    if isinstance(arr, str):
        return False
    for a in arr:
        if not isinstance(a, str):
            return False
    return True


def _simplify_meta_text(tune):
    if _is_array_of_strings(tune.metaText.get('notes')):
        tune.metaText['notes'] = "\n".join(tune.metaText['notes'])
    if _is_array_of_strings(tune.metaText.get('history')):
        tune.metaText['history'] = "\n".join(tune.metaText['history'])


def _resolve_overlays(tune):
    made_changes = False
    for i in range(len(tune.lines)):
        line = tune.lines[i]
        if line.staff:
            for j in range(len(line.staff)):
                staff = line.staff[j]
                overlay_voice = []
                for k in range(len(staff.voices)):
                    voice = staff.voices[k]
                    overlay_voice.append(Obj(hasOverlay=False, voice=[], snip=[]))
                    duration_this_bar = 0
                    in_overlay = False
                    snip_start = -1
                    for kk in range(len(voice)):
                        event = voice[kk]
                        if event.el_type == "overlay" and not in_overlay:
                            made_changes = True
                            in_overlay = True
                            snip_start = kk
                            overlay_voice[k].hasOverlay = True

                            for ii in range(i):
                                if tune.lines[ii].staff:
                                    for s in tune.lines[ii].staff:
                                        if len(staff.voices) >= len(s.voices):
                                            for v in list(s.voices):
                                                nv = []
                                                for ev in v:
                                                    if ev.el_type == "bar":
                                                        nv.append(ev)
                                                    elif ev.el_type == "note":
                                                        nv.append(Obj(el_type="note", duration=ev.duration, rest=Obj(type="invisible"), startChar=ev.startChar, endChar=ev.endChar))
                                                s.voices.append(nv)
                        elif event.el_type == "bar":
                            if in_overlay:
                                # delete the overlay events from this array without messing up this loop.
                                in_overlay = False
                                overlay_voice[k].snip.append(Obj(start=snip_start, len=kk - snip_start))
                                overlay_voice[k].voice.append(event)  # Also end the overlay with the barline.
                            else:
                                # This keeps the voices lined up: if the overlay isn't in the first measure then we need a bunch of invisible rests.
                                if duration_this_bar > 0:
                                    overlay_voice[k].voice.append(Obj(el_type="note", duration=duration_this_bar, rest=Obj(type="invisible"), startChar=event.startChar, endChar=event.endChar))
                                overlay_voice[k].voice.append(event)
                            duration_this_bar = 0
                        elif event.el_type == "note":
                            if in_overlay:
                                overlay_voice[k].voice.append(event)
                            elif not event.rest or event.rest.type != 'spacer':
                                duration_this_bar += event.duration
                        elif event.el_type in ("scale", "stem", "overlay", "style", "transpose", "color"):
                            # These types of events are duplicated on the overlay layer.
                            overlay_voice[k].voice.append(event)
                    if overlay_voice[k].hasOverlay and len(overlay_voice[k].snip) == 0:
                        # there was no closing bar, so we didn't set the snip amount.
                        overlay_voice[k].snip.append(Obj(start=snip_start, len=len(voice) - snip_start))
                for k in range(len(overlay_voice)):
                    ov = overlay_voice[k]
                    if ov.hasOverlay:
                        ov.voice.insert(0, Obj(el_type="stem", direction="down"))
                        staff.voices.append(ov.voice)
                        for kkk in range(len(ov.snip) - 1, -1, -1):
                            snip = ov.snip[kkk]
                            del staff.voices[k][snip.start:snip.start + snip['len']]
                            staff.voices[k].insert(snip.start + 1, Obj(el_type="stem", direction="auto"))
                            index_of_last_bar = _find_last_bar(staff.voices[k], snip.start)
                            staff.voices[k].insert(index_of_last_bar, Obj(el_type="stem", direction="up"))
                        # remove ending marks from the overlay voice so they are not repeated
                        last_voice = staff.voices[-1]
                        for kkk in range(len(last_voice)):
                            last_voice[kkk] = assign(last_voice[kkk])
                            el = last_voice[kkk]
                            if el.el_type == 'bar' and el.startEnding:
                                del el.startEnding
                            if el.el_type == 'bar' and el.endEnding:
                                del el.endEnding
    return made_changes


def _find_last_bar(voice, start):
    i = start - 1
    while i > 0 and voice[i].el_type != "bar":
        i -= 1
    return i


def _fix_titles(lines):
    # We might have name and subname defined. We now know what line everything is on, so we can determine which to use.
    first_music_line = True
    for line in lines:
        if line.staff:
            for staff in line.staff:
                if staff.title is not None:
                    has_a_title = False
                    for k in range(len(staff.title)):
                        if staff.title[k]:
                            staff.title[k] = staff.title[k].name if first_music_line else staff.title[k].subname
                            if staff.title[k]:
                                has_a_title = True
                            else:
                                staff.title[k] = ''
                        else:
                            staff.title[k] = ''
                    if not has_a_title:
                        del staff.title
            first_music_line = False


def _clean_up_slurs_in_line(line, staff_num, voice_num, curr_slur):
    if at(curr_slur, staff_num) is None:
        js_set(curr_slur, staff_num, [])
    if at(curr_slur[staff_num], voice_num) is None:
        js_set(curr_slur[staff_num], voice_num, [])
    cs = curr_slur[staff_num][voice_num]

    def add_end_slur(obj, num, chord_pos):
        if at(cs, chord_pos) is None:
            # There isn't an exact match for note position, but we'll take any other open slur.
            for x in range(len(cs)):
                if cs[x] is not None:
                    chord_pos = x
                    break
            if at(cs, chord_pos) is None:
                off_num = chord_pos * 100 + 1
                for x in obj.endSlur:
                    if off_num == x:
                        off_num -= 1
                js_set(cs, chord_pos, [off_num])
        slur_num = None
        for i in range(num):
            slur_num = cs[chord_pos].pop() if cs[chord_pos] else None
            obj.endSlur.append(slur_num)
        if len(cs[chord_pos]) == 0:
            cs[chord_pos] = None
        return slur_num

    def add_start_slur(obj, num, chord_pos, used_nums=None):
        obj.startSlur = []
        if at(cs, chord_pos) is None:
            js_set(cs, chord_pos, [])
        next_num = chord_pos * 100 + 1
        for i in range(num):
            if used_nums:
                for _ in range(3):
                    for x in used_nums:
                        if next_num == x:
                            next_num += 1
            for _ in range(2):
                for x in cs[chord_pos]:
                    if next_num == x:
                        next_num += 1

            cs[chord_pos].append(next_num)
            obj.startSlur.append(Obj(label=next_num))
            if obj.dottedSlur:
                obj.startSlur[-1].style = 'dotted'
                del obj.dottedSlur
            next_num += 1

    for el in line:
        if el.el_type == 'note':
            if el.gracenotes:
                for g in el.gracenotes:
                    if g.endSlur:
                        gg = g.endSlur
                        g.endSlur = []
                        for _ in range(gg):
                            add_end_slur(g, 1, 20)
                    if g.startSlur:
                        x = g.startSlur
                        add_start_slur(g, x, 20)
            if el.endSlur:
                x = el.endSlur
                el.endSlur = []
                add_end_slur(el, x, 0)
            if el.startSlur:
                x = el.startSlur
                add_start_slur(el, x, 0)
            if el.pitches:
                used_nums = []
                for p in range(len(el.pitches)):
                    if el.pitches[p].endSlur:
                        k = el.pitches[p].endSlur
                        el.pitches[p].endSlur = []
                        for _ in range(k):
                            slur_num = add_end_slur(el.pitches[p], 1, p + 1)
                            used_nums.append(slur_num)
                for p in range(len(el.pitches)):
                    if el.pitches[p].startSlur:
                        x = el.pitches[p].startSlur
                        add_start_slur(el.pitches[p], x, p + 1, used_nums)
                # Correct for the weird gracenote case where ({g}a) should match.
                # The end slur was already assigned to the note, and needs to be moved to the first note of the graces.
                p0 = el.pitches[0]
                if el.gracenotes and p0.endSlur and at(p0.endSlur, 0) == 100 and p0.startSlur:
                    if el.gracenotes[0].endSlur:
                        el.gracenotes[0].endSlur.append(p0.startSlur[0].label)
                    else:
                        el.gracenotes[0].endSlur = [p0.startSlur[0].label]
                    if len(p0.endSlur) == 1:
                        del p0.endSlur
                    elif p0.endSlur[0] == 100:
                        p0.endSlur.pop(0)
                    elif p0.endSlur[-1] == 100:
                        p0.endSlur.pop()
                    if len(cs[1]) == 1:
                        cs[1] = None
                    else:
                        cs[1].pop()


def _wrap_music_lines(lines, barsperstaff):
    for i in range(len(lines)):
        if lines[i].staff is not None:
            for s in range(len(lines[i].staff)):
                permanent_items = []
                for v in range(len(lines[i].staff[s].voices)):
                    voice = lines[i].staff[s].voices[v]
                    bar_num_this_line = 0
                    for n in range(len(voice)):
                        if voice[n].el_type == 'bar':
                            bar_num_this_line += 1
                            if bar_num_this_line >= barsperstaff:
                                # push everything else to the next line, if there is anything else,
                                # and there is a next line. If there isn't a next line, create one.
                                if n < len(voice) - 1:
                                    next_line = _get_next_music_line(lines, i)
                                    if not next_line:
                                        cp = json_clone(lines[i])
                                        lines.append(assign(cp))
                                        next_line = lines[-1]
                                        for ss in range(len(next_line.staff)):
                                            for vv in range(len(next_line.staff[ss].voices)):
                                                next_line.staff[ss].voices[vv] = []
                                    start_element = n + 1
                                    section = lines[i].staff[s].voices[v][start_element:]
                                    lines[i].staff[s].voices[v] = lines[i].staff[s].voices[v][0:start_element]
                                    next_line.staff[s].voices[v] = permanent_items + section + next_line.staff[s].voices[v]
                                    return True
                        elif not truthy(voice[n].duration):
                            permanent_items.append(voice[n])
    return False


def _get_prev_music_line(lines, current_line):
    if len(lines) <= current_line:
        return None
    # If the current line doesn't have music, search backwards until one is found.
    while current_line >= 0:
        if lines[current_line].staff is not None:
            return lines[current_line]
        current_line -= 1
    return None


def _get_next_music_line(lines, current_line):
    current_line += 1
    while len(lines) > current_line:
        if lines[current_line].staff is not None:
            return lines[current_line]
        current_line += 1
    return None


def _get_last_note(tune):
    line = at(tune.lines, tune.lineNum)
    if not line:
        return None
    if line.staff is None:
        return None
    st = at(line.staff, tune.staffNum)
    if not st:
        return None
    voice = at(st.voices, tune.voiceNum)
    if not voice:
        return None
    for el in reversed(voice):
        if el.el_type == 'note':
            return el
    return None


def _get_duration(el):
    if truthy(el.duration):
        return el.duration
    return 0


def _close_line(tune):
    if tune.potentialStartBeam and tune.potentialEndBeam:
        tune.potentialStartBeam.startBeam = True
        tune.potentialEndBeam.endBeam = True
    tune.potentialStartBeam = None
    tune.potentialEndBeam = None


def _contains_notes(voice):
    for el in voice:
        if el.el_type == 'note' or el.el_type == 'bar':
            return True
    return False


def _contains_notes_strict(voice):
    for el in voice:
        if el.el_type == 'note' and (el.rest is None or el.chord is not None):
            return True
    return False


def _push_line(tune, h):
    if truthy(tune.vskipPending):
        h.vskip = tune.vskipPending
        tune.vskipPending = None
    tune.lines.append(h)


def _push_note(builder, tune, hp, voice_defs, current_voice_name):
    curr_staff = tune.lines[tune.lineNum].staff[tune.staffNum]

    if hp.pitches is not None:
        mid = curr_staff.workingClef.verticalPos
        for p in hp.pitches:
            p.verticalPos = p.pitch - mid
    if hp.gracenotes is not None:
        mid2 = curr_staff.workingClef.verticalPos
        for p in hp.gracenotes:
            p.verticalPos = p.pitch - mid2
    if len(curr_staff.voices) <= tune.voiceNum:
        if not voice_defs.get(current_voice_name):
            voice_defs[current_voice_name] = Obj()
        _create_voice(builder, tune, voice_defs[current_voice_name])
    curr_staff.voices[tune.voiceNum].append(hp)


def _end_beam_here(hash_params, tune):
    tune.potentialStartBeam.startBeam = True
    hash_params.endBeam = True
    tune.potentialStartBeam = None
    tune.potentialEndBeam = None


def _end_beam_last(tune):
    if tune.potentialStartBeam is not None and tune.potentialEndBeam is not None:  # Do we have a set of notes to beam?
        tune.potentialStartBeam.startBeam = True
        tune.potentialEndBeam.endBeam = True
    tune.potentialStartBeam = None
    tune.potentialEndBeam = None


def _set_line_font(tune, typ, font):
    # If we haven't encountered the font type yet then we are using the default font so it doesn't
    # need to be noted. If we have encountered it, then only record it if it is different from the last time.
    if tune.runningFonts.get(typ):
        is_different = False
        for k in font.keys():
            if tune.runningFonts[typ].get(k) != font.get(k):
                is_different = True
        if is_different:
            tune.lines[tune.lineNum].staff[tune.staffNum][typ] = font
    tune.runningFonts[typ] = font


def _create_voice(builder, tune, params):
    this_staff = tune.lines[tune.lineNum].staff[tune.staffNum]
    js_set(this_staff.voices, tune.voiceNum, [])
    if this_staff.title is None:
        this_staff.title = []
    title = Obj(name=params.name, subname=params.subname)
    js_set(this_staff.title, tune.voiceNum, title)
    if params.style:
        builder.append_element('style', None, None, Obj(head=params.style))
    if params.stem:
        builder.append_element('stem', None, None, Obj(direction=params.stem))
    elif tune.voiceNum > 0:
        if at(this_staff.voices, 0) is not None:
            found = False
            for _ in this_staff.voices[0]:
                # (abcjs tests the voice array itself here, so this is never true)
                pass
            if not found:
                stem = Obj(el_type='stem', direction='up')
                this_staff.voices[0].insert(0, stem)
        builder.append_element('stem', None, None, Obj(direction='down'))
    if params.scale:
        builder.append_element('scale', None, None, Obj(size=params.scale))
    if params.color:
        builder.append_element('color', None, None, Obj(color=params.color))


def _create_staff(builder, tune, params):
    if params.key and params.key.impliedNaturals is not None:
        params.key.accidentals = params.key.accidentals + params.key.impliedNaturals
        del params.key.impliedNaturals

    staff = Obj(voices=[], clef=params.clef, key=params.key, workingClef=params.clef)
    js_set(tune.lines[tune.lineNum].staff, tune.staffNum, staff)
    if params.stafflines is not None:
        staff.clef.stafflines = params.stafflines
        staff.workingClef.stafflines = params.stafflines
    if params.staffscale:
        staff.staffscale = params.staffscale
    if params.annotationfont:
        _set_line_font(tune, "annotationfont", params.annotationfont)
    if params.gchordfont:
        _set_line_font(tune, "gchordfont", params.gchordfont)
    if params.tripletfont:
        _set_line_font(tune, "tripletfont", params.tripletfont)
    if params.vocalfont:
        _set_line_font(tune, "vocalfont", params.vocalfont)
    if params.bracket:
        staff.bracket = params.bracket
    if params.brace:
        staff.brace = params.brace
    if params.connectBarLines:
        staff.connectBarLines = params.connectBarLines
    if params.barNumber:
        staff.barNumber = params.barNumber
    _create_voice(builder, tune, params)
    # Some stuff just happens for the first voice
    if params.part:
        builder.append_element('part', params.part.startChar, params.part.endChar, Obj(title=params.part.title))
    if 'meter' in params:
        staff.meter = params.meter
    if truthy(tune.vskipPending):
        tune.lines[tune.lineNum].vskip = tune.vskipPending
        tune.vskipPending = None


def _create_line(builder, tune, params):
    js_set(tune.lines, tune.lineNum, Obj(staff=[]))
    _create_staff(builder, tune, params)


def _voice_useful(lines, voice_num):
    is_useful = False
    voice_exists = False
    for line in lines:
        staves = line.staff
        if staves:
            for staff in staves:
                if voice_num < len(staff.voices):
                    voice_exists = True
                    voice = staff.voices[voice_num]
                    for el in voice:
                        if el.el_type == 'note' and (not el.rest or el.chord):
                            is_useful = True
    if not voice_exists:
        return 'not-found'
    return is_useful


def _delete_voice(lines, voice_num):
    for line in lines:
        staves = line.staff
        if staves:
            for staff in staves:
                if voice_num < len(staff.voices):
                    staff.voices.pop(voice_num)


def _no_warn_before_title(tune):
    i = 1
    while i < len(tune.lines):
        line = tune.lines[i]
        if line.subtitle:
            previous_line = tune.lines[i - 1]
            if previous_line.staff:
                for j in range(len(previous_line.staff)):
                    for v in range(len(previous_line.staff[j].voices)):
                        voice = previous_line.staff[j].voices[v]
                        if voice and voice[-1].el_type == "key":
                            # There was a key change after a subtitle.
                            # Remove the courtesy key change.
                            voice.pop()
                            # Also, the new key signature might have some naturals, remove that.
                            next_line = at(tune.lines, i)
                            while i < len(tune.lines) and not next_line.staff:
                                i += 1
                                next_line = at(tune.lines, i)
                            if next_line:
                                for jj in range(len(next_line.staff)):
                                    accidentals = next_line.staff[jj].key.accidentals
                                    new_accidentals = [a for a in accidentals if a.acc != 'natural']
                                    next_line.staff[jj].key.accidentals = new_accidentals
        i += 1
