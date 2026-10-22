"""Horizontal and vertical layout of the engraved music.

Ports of the abcjs files in ``write/layout``: layout.js, staff-group.js,
voice.js, voice-elements.js, beam.js, triplet.js, get-bar-y-at.js,
get-left-edge-of-staff.js, set-upper-and-lower-elements.js,
to-time-and-staff-based.js and layout-in-grid.js.
"""

import math

from ...jsutil import Obj, at, js_round, js_floor, js_max, js_min, js_keys, js_set, gt, lt, truthy
from ..helpers import spacing
from ..creation.elements import RelativeElement, AbsoluteElement


def get_bar_y_at(startx, starty, endx, endy, x):
    if endx - startx == 0:
        if endy - starty == 0:
            return float('nan')
        return starty + (float('inf') if (endy - starty) > 0 else float('-inf')) * (x - startx) if x != startx else float('nan')
    return starty + (endy - starty) / (endx - startx) * (x - startx)


# -- layout.js ---------------------------------------------------------------------

def layout(renderer, abctune, width, space, expand_to_widest=None, time_based_layout=None):
    # This sets the "x" attribute on all the children in abctune.lines
    # It also sets the "w" and "startx" attributes on "voices"
    # It also sets the "w" and "startx" attributes on "voices.children"
    max_width = width
    i = 0
    while i < len(abctune.lines):
        abc_line = abctune.lines[i]
        if abc_line.staff:
            if time_based_layout is not None:
                this_width = layout_in_grid(renderer, abc_line.staffGroup, time_based_layout)
            else:
                this_width = _set_x_spacing(renderer, max_width, space, abc_line.staffGroup, abctune.formatting, i == len(abctune.lines) - 1, False)
            if js_round(this_width) > js_round(max_width):  # to take care of floating point weirdness
                max_width = this_width
                if expand_to_widest:
                    i = -1  # do the calculations over with the new width
        i += 1

    # Layout the beams and add the stems to the beamed notes.
    for abc_line in abctune.lines:
        if abc_line.staffGroup and abc_line.staffGroup.voices:
            for v in abc_line.staffGroup.voices:
                layout_voice(v)
            set_upper_and_lower_elements(renderer, abc_line.staffGroup)

    # See if there are collisions between voices that need to be tweaked
    time_based = to_time_and_staff_based(abctune.lines)
    for i in range(len(abctune.lines)):
        abc_line = abctune.lines[i]
        if abc_line.staffGroup:
            _fix_voice_collisions(time_based[i])

    # Set the staff spacing
    for abc_line in abctune.lines:
        if abc_line.staffGroup:
            abc_line.staffGroup.set_height()
    return max_width


def _set_x_spacing(renderer, width, space, staff_group, formatting, is_last_line, debug):
    # Do the x-axis positioning for a single line (a group of related staffs)
    left_edge = get_left_edge_of_staff(renderer, staff_group.getTextSize, staff_group.voices, staff_group.brace, staff_group.bracket)
    newspace = space
    for it in range(8):  # TODO-PER: shouldn't need multiple passes, but each pass gets it closer to the right spacing.
        ret = layout_staff_group(newspace, renderer.minPadding, debug, staff_group, left_edge)
        newspace = _calc_horizontal_spacing(is_last_line, formatting.stretchlast, width + renderer.padding.left, staff_group.w, newspace, ret.spacingUnits, ret.minSpace, renderer.padding.left + renderer.padding.right)
        if newspace is None:
            break
    _center_whole_rests(staff_group.voices)
    return staff_group.w - left_edge


def _calc_horizontal_spacing(is_last_line, stretch_last, target_width, line_width, spacing_, spacing_units, min_space, padding):
    if is_last_line:
        if stretch_last is None:
            if line_width / target_width < 0.66:
                return None  # keep this for backward compatibility. The break isn't quite the same for some reason.
        else:
            # "Stretch the last music line of a tune when it lacks less than the float fraction of the page width."
            lack = 1 - (line_width + padding) / target_width
            stretch = lack < stretch_last
            if not stretch:
                return None  # don't stretch last line too much
    if abs(target_width - line_width) < 2:
        return None  # if we are already near the target width, we're done.
    rel_space = spacing_units * spacing_
    const_space = line_width - rel_space
    if spacing_units > 0:
        spacing_ = (target_width - const_space) / spacing_units
        if spacing_ * min_space > 50:
            spacing_ = 50 / min_space
        return spacing_
    return None


def _center_whole_rests(voices):
    # whole rests are a special case: if they are by themselves in a measure, then they should be centered.
    for voice in voices:
        for j in range(1, len(voice.children) - 1):
            abs_elem = voice.children[j]
            if abs_elem.abcelem.rest and (abs_elem.abcelem.rest.type == 'whole' or abs_elem.abcelem.rest.type == 'multimeasure'):
                before = voice.children[j - 1]
                after = voice.children[j + 1]
                abs_elem.center(before, after)


def _fix_voice_collisions(time_based_line):
    for time_slot in time_based_line:
        # If there is more than one thing happening at the same time,
        # and one of those things is a rest, then:
        # If the rest is in the first element, check to see if the bottom bumps into the top of any of the rest of the elements
        # If the rest is in the last element, check to see if the top bumps into the bottom of any of the rest of the elements.
        for key in time_slot:
            slot = time_slot[key]  # slot is an array of all the things happening at a particular time
            last_index = len(slot) - 1
            if len(slot) > 1:
                is_real_rest = slot[0].abcelem.rest and slot[0].abcelem.rest.type == 'rest'  # weed out invisible rests
                is_real_rest2 = slot[last_index].abcelem.rest and slot[last_index].abcelem.rest.type == 'rest'
                if is_real_rest and not slot[last_index].abcelem.rest:
                    # the first voice has a rest and the second doesn't
                    rest_top = next((ch for ch in slot[0].children if 'rest' in ch.name), None)
                    other_top = _close_top(slot[last_index])
                    if rest_top:
                        distance1 = rest_top.bottom - other_top
                        distance1 -= 2  # give some room between the rest and the note
                        if distance1 < 0 and len(slot[0].children) > 0:
                            slot[0].bottom -= distance1
                            slot[0].top -= distance1
                            slot[0].children[0].bottom -= distance1
                            slot[0].children[0].top -= distance1
                            slot[0].children[0].pitch -= distance1
                elif is_real_rest2 and not slot[0].abcelem.rest:
                    # the last voice has a rest and the first doesn't
                    rest_bottom = next((ch for ch in slot[last_index].children if 'rest' in ch.name), None)
                    if rest_bottom:
                        distance2 = rest_bottom.top - _close_bottom(slot[0])
                        distance2 += 2  # give some room between the rest and the note
                        if distance2 > 0 and len(slot[last_index].children) > 0:
                            slot[last_index].bottom -= distance2
                            slot[last_index].top -= distance2
                            slot[last_index].children[0].bottom -= distance2
                            slot[last_index].children[0].top -= distance2
                            slot[last_index].children[0].pitch -= distance2


def _close_top(abs_elem):
    if abs_elem.children is not None:
        mx = -90  # This is clearly way lower than the max calculated below
        for child in abs_elem.children:
            if child.type != 'chord':
                mx = js_max(mx, child.top)
        if mx > -90:
            return mx
    return abs_elem.top


def _close_bottom(abs_elem):
    if abs_elem.children is not None:
        mn = 90  # This is clearly way higher than the min calculated below
        for child in abs_elem.children:
            if child.type != 'lyric':
                mn = js_min(mn, child.bottom)
        if mn < 90:
            return mn
    return abs_elem.bottom


# -- get-left-edge-of-staff.js -------------------------------------------------------

def get_left_edge_of_staff(renderer, get_text_size, voices, brace, bracket):
    x = renderer.padding.left

    # find out how much space will be taken up by voice headers
    voiceheaderw = 0
    for v in voices:
        if v.header:
            size = get_text_size.calc(v.header, 'voicefont', '')
            voiceheaderw = js_max(voiceheaderw, size.width)
    voiceheaderw = _add_brace_size(voiceheaderw, brace, get_text_size)
    voiceheaderw = _add_brace_size(voiceheaderw, bracket, get_text_size)

    if voiceheaderw:
        # Give enough spacing to the right - we use the width of an A for the amount of spacing.
        size_w = get_text_size.calc("A", 'voicefont', '')
        voiceheaderw += size_w.width
    x += voiceheaderw

    ofs = 0
    ofs = _set_brace_location(brace, x, ofs)
    ofs = _set_brace_location(bracket, x, ofs)
    return x + ofs


def _add_brace_size(voiceheaderw, brace, get_text_size):
    if brace:
        for b in brace:
            if b.header:
                size = get_text_size.calc(b.header, 'voicefont', '')
                voiceheaderw = js_max(voiceheaderw, size.width)
    return voiceheaderw


def _set_brace_location(brace, x, ofs):
    if brace:
        for b in brace:
            b.x = x
            ofs = js_max(ofs, b.get_width())
    return ofs


# -- staff-group.js --------------------------------------------------------------------

def _check_last_bar_x(voices):
    max_x = 0
    for cur_voice in voices:
        if len(cur_voice.children) > 0:
            max_child = cur_voice.children[-1]
            if max_child.abcelem.el_type == 'bar':
                bar_x = max_child.children[0].x
                if bar_x > max_x:
                    max_x = bar_x
                else:
                    max_child.children[0].x = max_x


def layout_staff_group(spacing_, min_padding, debug, staff_group, left_edge):
    epsilon = 0.0000001  # Fudging for inexactness of floating point math.
    spacingunits = 0  # number of times we will have ended up using the spacing distance (as opposed to fixed width distances)
    minspace = 1000  # a big number to start off with - used to find out what the smallest space between two notes is

    x = left_edge
    staff_group.startx = x

    for v in staff_group.voices:
        VoiceElements.begin_layout(x, v)

    spacingunit = 0  # number of spacingunits coming from the previously laid out element to this one
    while not _finished(staff_group.voices):
        # find first duration level to be laid out among candidates across voices
        currentduration = None  # candidate smallest duration level
        for v in staff_group.voices:
            if not VoiceElements.layout_ended(v) and (not truthy(currentduration) or _get_duration_index(v) < currentduration):
                currentduration = _get_duration_index(v)

        # isolate voices at current duration level
        currentvoices = []
        othervoices = []
        for v in staff_group.voices:
            duration_index = _get_duration_index(v)
            # PER: Because of the inexactness of JS floating point math, we just get close.
            cd = currentduration if currentduration is not None else 0
            if duration_index - cd > epsilon:
                othervoices.append(v)
            else:
                currentvoices.append(v)

        # among the current duration level find the one which needs starting furthest right
        spacingunit = 0
        spacingduration = 0
        for v in currentvoices:
            if VoiceElements.get_next_x(v) > x:
                x = VoiceElements.get_next_x(v)
                spacingunit = VoiceElements.get_spacing_units(v)
                spacingduration = v.spacingduration
        spacingunits += spacingunit
        minspace = js_min(minspace, spacingunit)

        last_top_voice = None
        for i in range(len(currentvoices)):
            v = currentvoices[i]
            if v.voicenumber == 0:
                last_top_voice = i
            top_voice = currentvoices[last_top_voice] if (last_top_voice is not None and currentvoices[last_top_voice].voicenumber != v.voicenumber) else None
            if not _is_same_staff(v, top_voice):
                top_voice = None
            voicechildx = VoiceElements.layout_one_item(x, spacing_, v, min_padding, top_voice)
            dx = voicechildx - x
            if dx > 0:
                x = voicechildx  # update x
                for j in range(i):  # shift over all previously laid out elements
                    VoiceElements.shift_right(dx, currentvoices[j])

        # remove the value of already counted spacing units in other voices
        for v in othervoices:
            v.spacingduration -= spacingduration
            VoiceElements.update_next_x(x, spacing_, v)  # adjust other voices expectations

        # update indexes of currently laid out elems
        for v in currentvoices:
            VoiceElements.update_indices(v)

    # find the greatest remaining x as a base for the width
    for v in staff_group.voices:
        if VoiceElements.get_next_x(v) > x:
            x = VoiceElements.get_next_x(v)
            spacingunit = VoiceElements.get_spacing_units(v)

    # adjust lastBar when needed (multi staves)
    _check_last_bar_x(staff_group.voices)
    spacingunits += spacingunit
    staff_group.set_width(x)

    return Obj(spacingUnits=spacingunits, minSpace=minspace)


def _finished(voices):
    for v in voices:
        if not VoiceElements.layout_ended(v):
            return False
    return True


def _get_duration_index(element):
    child = at(element.children, element.i)
    # if the ith element doesn't have a duration (is not a note), its duration index is fractionally before.
    # This enables CLEF KEYSIG TIMESIG PART, etc. to be laid out before we get to the first note of other voices
    return element.durationindex - (0 if (child and gt(child.duration, 0)) else 0.0000005)


def _is_same_staff(voice1, voice2):
    if not voice1 or not voice1.staff or not voice1.staff.voices or len(voice1.staff.voices) == 0:
        return False
    if not voice2 or not voice2.staff or not voice2.staff.voices or len(voice2.staff.voices) == 0:
        return False
    return voice1.staff.voices[0] == voice2.staff.voices[0]


# -- voice-elements.js ----------------------------------------------------------------

class VoiceElements:
    @staticmethod
    def begin_layout(startx, voice):
        voice.i = 0
        voice.durationindex = 0
        voice.startx = startx
        voice.minx = startx  # furthest left to where negatively positioned elements are allowed to go
        voice.nextx = startx  # x position where the next element of this voice should be placed assuming no other voices and no fixed width constraints
        voice.spacingduration = 0  # duration left to be laid out in current iteration

    @staticmethod
    def layout_ended(voice):
        return voice.i >= len(voice.children)

    @staticmethod
    def get_next_x(voice):
        return js_max(voice.minx, voice.nextx)

    @staticmethod
    def get_spacing_units(voice):
        # number of spacing units expected for next positioning
        return math.sqrt(voice.spacingduration * 8) if voice.spacingduration >= 0 else float('nan')

    @staticmethod
    def layout_one_item(x, spacing_, voice, min_padding, first_voice):
        # Try to layout the element at index this.i
        child = at(voice.children, voice.i)
        if not child:
            return 0
        er = x - voice.minx  # available extrawidth to the left
        pad = min_padding if (voice.durationindex + child.duration > 0) else 0  # only add padding to the items that aren't fixed to the left edge.
        # See if this item overlaps the item in the first voice. If firstVoice is undefined then there's nothing to compare.
        if child.abcelem.el_type == "note" and not child.abcelem.rest and voice.voicenumber != 0 and first_voice:
            first_child = at(first_voice.children, first_voice.i)
            ca = child.abcelem
            # It overlaps if the either the child's top or bottom is inside the firstChild's or at least within 1
            overlaps = bool(first_child and
                            ((_le(ca.maxpitch, _plus(first_child.abcelem.maxpitch, 1)) and _ge(ca.maxpitch, _plus(first_child.abcelem.minpitch, -1))) or
                             (_le(ca.minpitch, _plus(first_child.abcelem.maxpitch, 1)) and _ge(ca.minpitch, _plus(first_child.abcelem.minpitch, -1)))))
            # See if they can share a note head
            if (overlaps and ca.minpitch == first_child.abcelem.minpitch and ca.maxpitch == first_child.abcelem.maxpitch and
                    first_child.heads and len(first_child.heads) > 0 and child.heads and len(child.heads) > 0 and
                    first_child.heads[0].c == child.heads[0].c):
                overlaps = False
            # If this note overlaps the note in the first voice and we haven't moved the note yet (this can be called multiple times)
            if overlaps:
                first_child_note_width = first_child.heads[0].realWidth if (first_child.heads and len(first_child.heads) > 0) else first_child.fixed.w
                if not child.adjustedWidth:
                    child.adjustedWidth = first_child_note_width + child.w
                child.w = child.adjustedWidth
                for relative_child in child.children:
                    if "accidental" not in (relative_child.name if isinstance(relative_child.name, str) else ""):
                        if not relative_child.adjustedWidth:
                            relative_child.adjustedWidth = relative_child.dx + first_child_note_width
                        relative_child.dx = relative_child.adjustedWidth
        extra_width = _get_extra_width(child, pad)
        if er < extra_width:  # shift right by needed amount
            # There's an exception if a bar element is after a Part element, there is no shift.
            if voice.i == 0 or child.type != 'bar' or (voice.children[voice.i - 1].type != 'part' and voice.children[voice.i - 1].type != 'tempo'):
                x += extra_width - er
        child.set_x(x)

        voice.spacingduration = child.duration
        # update minx
        voice.minx = x + child.w  # add necessary layout space
        if voice.i != len(voice.children) - 1:
            voice.minx += child.minspacing  # add minimumspacing except on last elem

        VoiceElements.update_next_x(x, spacing_, voice)
        return x  # where we end up having placed the child

    @staticmethod
    def shift_right(dx, voice):
        child = at(voice.children, voice.i)
        if not child:
            return
        child.set_x(child.x + dx)
        voice.minx += dx
        voice.nextx += dx

    @staticmethod
    def update_next_x(x, spacing_, voice):
        # call when spacingduration has been updated
        voice.nextx = x + (spacing_ * VoiceElements.get_spacing_units(voice))

    @staticmethod
    def update_indices(voice):
        if not VoiceElements.layout_ended(voice):
            voice.durationindex += voice.children[voice.i].duration
            if voice.children[voice.i].type == 'bar':
                voice.durationindex = js_round(voice.durationindex * 64) / 64  # everytime we meet a barline, do rounding to nearest 64th
            voice.i += 1


def _plus(a, b):
    if a is None:
        return float('nan')
    return a + b


def _le(a, b):
    from ...jsutil import le
    return le(a, b)


def _ge(a, b):
    from ...jsutil import ge
    return ge(a, b)


def _get_extra_width(child, min_padding):  # space needed to the left of the note
    padding = 0
    if child.type == 'note' or child.type == 'bar':
        padding = min_padding
    return -child.extraw + padding


# -- voice.js --------------------------------------------------------------------------

def layout_voice(voice):
    for b in voice.beams:
        if not isinstance(b, str) and b.type == 'BeamElem':
            layout_beam(b)
            _move_decorations(b)
            # The above will change the top and bottom of the abselem children, so see if we need to expand our range.
            for e in b.elems:
                voice.adjust_range(e)
    voice.staff.specialY.chordLines = _set_lane_for_chord(voice.children)

    # Now we can layout the triplets
    for child in voice.otherchildren:
        if not isinstance(child, str) and child.type == 'TripletElem':
            layout_triplet(child)
            voice.adjust_range(child)
    voice.staff.top = js_max(voice.staff.top, voice.top)
    voice.staff.bottom = js_min(voice.staff.bottom, voice.bottom)


def _move_decorations(beam):
    padding = 1.5  # This is the vertical padding between elements, in pitches.
    for child in beam.elems:
        if truthy(child.top):
            # We now know where the ornaments should have been placed, so move them if they would overlap.
            top = _y_at_note(child, beam)
            for el in child.children:
                if el.klass == 'ornament' and el.position != 'below':
                    if el.bottom - padding < top:
                        distance = top - el.bottom + padding  # Find the distance that it needs to move and add a little margin so the element doesn't touch the beam.
                        el.bottom += distance
                        el.top += distance
                        el.pitch += distance
                        top = child.top = el.top


def _place_in_lane(right_most, rel_elem):
    # These items are centered so figure the coordinates accordingly.
    # The font reports some extra space so the margin is built in.
    x_coords = rel_elem.get_chord_dim()
    if x_coords:
        for i in range(len(right_most)):
            fits = right_most[i] < x_coords.left
            if fits:
                if i > 0:
                    rel_elem.put_chord_in_lane(i)
                right_most[i] = x_coords.right
                return
        # If we didn't return early, then we need a new row
        right_most.append(x_coords.right)
        rel_elem.put_chord_in_lane(len(right_most) - 1)


def _set_lane_for_chord(abs_elems):
    # Criteria:
    # 1) lane numbers start from the bottom so that as many items as possible are in lane 0, closest to the music.
    # 2) a chord can have more than one line (for instance "C\nD") each line is a lane.
    # 3) if two adjoining items would touch then push the second one to the next lane.
    # 4) use as many lanes as is necessary to get everything to not touch.
    right_most_above = [0]
    right_most_below = [0]
    for a in abs_elems:
        for rel_elem in a.children:
            if rel_elem.chordHeightAbove:
                _place_in_lane(right_most_above, rel_elem)
        for rel_elem in reversed(a.children):
            if rel_elem.chordHeightBelow:
                _place_in_lane(right_most_below, rel_elem)
    # If we used a second line, then we need to go back and set the first lines.
    # Also we need to flip the indexes of the names so that we can count from the top line.
    if len(right_most_above) > 1 or len(right_most_below) > 1:
        _set_lane(abs_elems, len(right_most_above), len(right_most_below))
    return Obj(above=len(right_most_above), below=len(right_most_below))


def _set_lane(abs_elems, num_lanes_above, num_lanes_below):
    for a in abs_elems:
        for rel_elem in a.children:
            if rel_elem.chordHeightAbove:
                rel_elem.invert_lane(num_lanes_above)


def _y_at_note(element, beam):
    beam = beam.beams[0]
    return get_bar_y_at(beam.startX, beam.startY, beam.endX, beam.endY, element.x)


# -- beam.js -----------------------------------------------------------------------------

def layout_beam(beam):
    if len(beam.elems) == 0 or beam.allrests:
        return

    dy = _calc_dy(beam.stemsUp, beam.isgrace)  # This is the width of the beam line.

    # create the main beam
    first_element = beam.elems[0]
    last_element = beam.elems[-1]
    min_stem_height = 0  # The following is to leave space for "!///!" marks.
    reference_pitch = first_element.abcelem.maxpitch if beam.stemsUp else first_element.abcelem.minpitch
    min_stem_height = _min_stem(first_element, beam.stemsUp, reference_pitch, min_stem_height)
    min_stem_height = _min_stem(last_element, beam.stemsUp, reference_pitch, min_stem_height)
    min_stem_height = js_max(beam.stemHeight, min_stem_height + 3)  # TODO-PER: The 3 is the width of a 16th beam.
    y_pos = _calc_y_pos(beam.average, len(beam.elems), min_stem_height, beam.stemsUp, first_element.abcelem.averagepitch, last_element.abcelem.averagepitch, beam.isflat, beam.min, beam.max, beam.isgrace)
    x_pos = _calc_x_pos(beam.stemsUp, first_element, last_element)
    beam.add_beam(Obj(startX=x_pos[0], endX=x_pos[1], startY=y_pos[0], endY=y_pos[1], dy=dy))

    # create the rest of the beams (in the case of 1/16th notes, etc.
    beams = _create_additional_beams(beam.elems, beam.stemsUp, beam.beams[0], beam.isgrace, dy)
    for b in beams:
        beam.add_beam(b)

    # Now that the main beam is defined, we know how tall the stems should be, so create them and attach them to the original notes.
    _create_stems(beam.elems, beam.stemsUp, beam.beams[0], dy, beam.mainNote)


def _get_durlog(duration):
    # TODO-PER: This is a hack to prevent a Chrome lockup. Duration should have been defined already,
    # but there's definitely a case where it isn't. [Probably something to do with triplets.]
    if duration is None:
        return 0
    if duration <= 0 or duration != duration:
        return float('-inf') if duration == 0 else float('nan')
    return js_floor(math.log(duration) / math.log(2))


def _min_stem(element, stems_up, reference_pitch, min_stem_height):
    if element.children is None:
        return min_stem_height
    for elem in element.children:
        if stems_up and elem.top is not None and elem.c == "flags.ugrace":
            min_stem_height = js_max(min_stem_height, elem.top - reference_pitch)
        elif not stems_up and elem.bottom is not None and elem.c == "flags.ugrace":
            min_stem_height = js_max(min_stem_height, reference_pitch - elem.bottom + 7)  # The extra 7 is because we are measuring the slash from the top.
    return min_stem_height


def _calc_slant(left_average_pitch, right_average_pitch, num_stems, is_flat):
    if is_flat:
        return 0
    slant = left_average_pitch - right_average_pitch
    max_slant = num_stems / 2

    if slant > max_slant:
        slant = max_slant
    if slant < -max_slant:
        slant = -max_slant
    return slant


def _calc_dy(asc, is_grace):
    dy = spacing.STEP if asc else -spacing.STEP
    if is_grace:
        dy = dy * 0.4
    return dy


def _calc_x_pos(asc, first_element, last_element):
    starthead = first_element.heads[0 if asc else len(first_element.heads) - 1]
    endhead = last_element.heads[0 if asc else len(last_element.heads) - 1]
    start_x = starthead.x
    if asc:
        start_x += starthead.w - 0.6
    end_x = endhead.x
    end_x += endhead.w if asc else 0.6
    return [start_x, end_x]


def _calc_y_pos(average, num_elements, stem_height, asc, first_average_pitch, last_average_pitch, is_flat, min_pitch, max_pitch, is_grace):
    barpos = stem_height - 2
    barminpos = stem_height - 2
    pos = js_round(js_max(average + barpos, max_pitch + barminpos) if asc else js_min(average - barpos, min_pitch - barminpos))

    slant = _calc_slant(first_average_pitch, last_average_pitch, num_elements, is_flat)
    start_y = pos + js_floor(slant / 2)
    end_y = pos + js_floor(-slant / 2)

    # If the notes are too high or too low, make the beam go down to the middle
    if not is_grace:
        if asc and pos < 6:
            start_y = 6
            end_y = 6
        elif not asc and pos > 6:
            start_y = 6
            end_y = 6

    return [start_y, end_y]


def _create_stems(elems, asc, beam, dy, main_note):
    for elem in elems:
        if elem.abcelem.rest:
            continue
        # TODO-PER: This is odd. If it is a regular beam then elems is an array of AbsoluteElements, if it is a grace beam then it is an array of objects
        is_grace = not isinstance(elem, AbsoluteElement)
        parent = main_note if is_grace else elem
        furthest_head = elem.heads[0 if asc else len(elem.heads) - 1]
        oval_delta = 1 / 5
        pitch = furthest_head.pitch + (oval_delta if asc else -oval_delta)
        dx = furthest_head.w if asc else 0  # down-pointing stems start on the left side of the note, up-pointing stems start on the right side, so we offset by the note width.
        if not is_grace:
            dx += furthest_head.dx
        x = furthest_head.x + dx  # this is now the actual x location in pixels.
        bary = get_bar_y_at(beam.startX, beam.startY, beam.endX, beam.endY, x)
        line_width = -0.6 if asc else 0.6
        if not asc:
            bary -= (dy / 2) / spacing.STEP  # TODO-PER: This is just a fudge factor so the down-pointing stems don't overlap.
        if is_grace:
            dx += elem.heads[0].dx
        # TODO-PER-HACK: One type of note head has a different placement of the stem. This should be more generically calculated:
        if furthest_head.c == 'noteheads.slash.quarter':
            if asc:
                pitch += 1
            else:
                pitch -= 1
        stem = RelativeElement(None, dx, 0, pitch, Obj(type="stem", pitch2=bary, linewidth=line_width))
        stem.set_x(parent.x)  # This is after the x coordinates were set, so we have to set it directly.
        parent.add_right(stem)


def _find_next_non_rest(elems, start_index):
    for k in range(start_index + 1, len(elems)):
        if not elems[k].abcelem.rest:
            return k
    return -1  # No non-rest element found


def _find_prev_non_rest(elems, start_index):
    for k in range(start_index - 1, -1, -1):
        if not elems[k].abcelem.rest:
            return k
    return -1  # No non-rest element found


def _create_additional_beams(elems, asc, beam, is_grace, dy):
    beams = []
    aux_beams = []  # auxbeam will be {x, y, durlog, single} auxbeam[0] should match with durlog=-4 (16th) (j=-4-durlog)
    for i in range(len(elems)):
        elem = elems[i]
        if elem.abcelem.rest:
            continue
        furthest_head = elem.heads[0 if asc else len(elem.heads) - 1]
        x = furthest_head.x + (furthest_head.w if asc else 0)
        bary = get_bar_y_at(beam.startX, beam.startY, beam.endX, beam.endY, x)

        sy = -1.5 if asc else 1.5
        if is_grace:
            sy = sy * 2 / 3  # This makes the second beam on grace notes closer to the first one.
        duration = elem.abcelem.duration  # get the duration via abcelem because of triplets
        if duration == 0:
            duration = 0.25  # if this is stemless, then we use quarter note as the duration.
        durlog = _get_durlog(duration)
        while durlog < -3:
            index = -4 - durlog
            if at(aux_beams, index):
                aux_beams[index].single = False
            else:
                js_set(aux_beams, index, Obj(x=x + (-0.6 if asc else 0), y=bary + sy * (index + 1), durlog=durlog, single=True))
            if i > 0 and elem.abcelem.beambr and elem.abcelem.beambr <= (index + 1):
                if not aux_beams[index].split:
                    aux_beams[index].split = [aux_beams[index].x]
                prev_elem_index = i - 1
                while prev_elem_index >= 0 and elems[prev_elem_index].type == 'rest':
                    prev_elem_index -= 1

                x_pos = _calc_x_pos(asc, elems[prev_elem_index], elem)
                if aux_beams[index].split[-1] >= x_pos[0]:
                    # the reduction in beams leaves a note unattached so create a small flag for it.
                    x_pos[0] += elem.w
                aux_beams[index].split.append(x_pos[0])
                aux_beams[index].split.append(x_pos[1])
            durlog += 1

        for j in range(len(aux_beams) - 1, -1, -1):
            # Find the next non-rest element to check if we should end the beam
            next_non_rest_index = _find_next_non_rest(elems, i)
            should_end_beam = (next_non_rest_index == -1) or (next_non_rest_index < len(elems) and _get_durlog(elems[next_non_rest_index].abcelem.duration) > (-j - 4))

            if should_end_beam:
                aux_beam_end_x = x
                aux_beam_end_y = bary + sy * (j + 1)

                ab = aux_beams[j]
                if ab is None:
                    aux_beams = aux_beams[0:j]
                    continue
                if ab.single:
                    prev_non_rest_index = _find_prev_non_rest(elems, i)
                    is_first_note = prev_non_rest_index == -1
                    is_last_note = next_non_rest_index == -1

                    if is_first_note:
                        # This is the first note in the group, always draw the beam to the right
                        aux_beam_end_x = x + 5
                    elif is_last_note:
                        # This is the last note in the group, always draw the beam to the left
                        aux_beam_end_x = x - 5
                    else:
                        # This is a middle note, check the note durations of the notes to the left and right (skipping rests)
                        prev_duration = elems[prev_non_rest_index].abcelem.duration
                        next_duration = elems[next_non_rest_index].abcelem.duration
                        if prev_duration == next_duration:
                            # The notes on either side are the same duration, alternate which side the beam goes to
                            aux_beam_end_x = x + 5 if i % 2 == 0 else x - 5
                        else:
                            # The notes on either side are different durations, draw the beam to the longer note
                            aux_beam_end_x = x + 5 if prev_duration < next_duration else x - 5
                    aux_beam_end_y = get_bar_y_at(beam.startX, beam.startY, beam.endX, beam.endY, aux_beam_end_x) + sy * (j + 1)
                b = Obj(startX=ab.x, endX=aux_beam_end_x, startY=ab.y, endY=aux_beam_end_y, dy=dy)
                if ab.split is not None:
                    split = ab.split
                    if b.endX <= split[-1]:
                        # the reduction in beams leaves the last note by itself, so create a little flag for it
                        split[-1] -= elem.w
                    split.append(b.endX)
                    b.split = ab.split
                beams.append(b)
                aux_beams = aux_beams[0:j]
    return beams


# -- triplet.js ----------------------------------------------------------------------------

def layout_triplet(element):
    # TODO end and beginning of line (PER: P.S. I'm not sure this can happen: I think the parser will always specify both the start and end points.)
    if element.anchor1 and element.anchor2:
        element.hasBeam = bool(element.anchor1.parent.beam) and element.anchor1.parent.beam is element.anchor2.parent.beam
        beam = element.anchor1.parent.beam
        # if hasBeam is true, then the first and last element in the triplet have the same beam.
        # We also need to check if the beam doesn't contain other notes so that `(3 dcdcc` will do a bracket.
        if element.hasBeam and (beam.elems[0] is not element.anchor1.parent or beam.elems[-1] is not element.anchor2.parent):
            element.hasBeam = False

        if element.hasBeam:
            # If there is a beam then we don't need to draw anything except the text. The beam could either be above or below.
            left = element.anchor1.x + element.anchor1.w if beam.stemsUp else element.anchor1.x
            element.yTextPos = _height_at_midpoint(left, element.anchor2.x, beam)
            element.yTextPos += 3 if beam.stemsUp else -2  # This creates some space between the beam and the number.
            element.xTextPos = left + (element.anchor2.x - left) / 2
            element.top = element.yTextPos + 1
            element.bottom = element.yTextPos - 2
            if beam.stemsUp:
                element.endingHeightAbove = 4
        else:
            # If there isn't a beam, then we need to draw the bracket and the text. The bracket is either above or below depending on the stem direction of the notes.
            up = _stem_direction_up(element)
            element.up = up
            p1 = element.anchor1.parent
            p2 = element.anchor2.parent
            element.startNote = js_max(p1.top, 9) + 4 if up else js_min(p1.bottom, 0) - 2
            element.endNote = js_max(p2.top, 9) + 4 if up else js_min(p2.bottom, 0) - 2

            # If it starts or ends on a rest, make the beam horizontal
            if p1.type == "rest" and p2.type != "rest":
                element.startNote = element.endNote
            elif p2.type == "rest" and p1.type != "rest":
                element.endNote = element.startNote
            if up:
                # See if the middle note is really high.
                mx = 0
                for m in element.middleElems:
                    mx = js_max(mx, m.top)
                mx += 4
                if mx > element.startNote or mx > element.endNote:
                    element.startNote = mx + 3
                    element.endNote = mx + 3
            else:
                # See if the middle note is really low.
                mn = 0
                for m in element.middleElems:
                    mn = js_min(mn, (m.bottom - m.height) if (m.bottom is not None and m.height is not None) else float('nan'))
                mn -= 3
                if mn < element.startNote and mn < element.endNote:
                    element.startNote = js_min(mn, element.startNote) - 2
                    element.endNote = js_min(mn, element.endNote) - 2
            if element.flatBeams:
                if up:
                    element.startNote = js_max(element.startNote, element.endNote)
                    element.endNote = js_max(element.startNote, element.endNote)
                else:
                    element.startNote = js_min(element.startNote, element.endNote)
                    element.endNote = js_min(element.startNote, element.endNote)

            element.yTextPos = element.startNote + (element.endNote - element.startNote) / 2
            element.xTextPos = element.anchor1.x + (element.anchor2.x + element.anchor2.w - element.anchor1.x) / 2
            element.top = element.yTextPos + 1
            element.bottom = element.yTextPos - 2
    element.__dict__.pop('middleElems', None)
    element.__dict__.pop('flatBeams', None)


def _stem_direction_up(element):
    up = 0
    down = 0
    if element.anchor1:
        if element.anchor1.stemDir == 'up':
            up += 1
        if element.anchor1.stemDir == 'down':
            down += 1
    if element.anchor2:
        if element.anchor2.stemDir == 'up':
            up += 1
        if element.anchor2.stemDir == 'down':
            down += 1
    if element.middleElems:
        for elem in element.middleElems:
            if elem.stemDir == 'up':
                up += 1
            if elem.stemDir == 'down':
                down += 1
    return up >= down


def _height_at_midpoint(start_x, end_x, beam):
    # We can't just use the entire beam for the calculation. The range has to be passed in, because the beam might extend into some unrelated notes.
    if len(beam.beams) == 0:
        return 0
    beam = beam.beams[0]
    mid_point = start_x + (end_x - start_x) / 2
    return get_bar_y_at(beam.startX, beam.startY, beam.endX, beam.endY, mid_point)


# -- set-upper-and-lower-elements.js -----------------------------------------------------

_MARGIN = 1


def _position_y():
    return Obj(
        tempoHeightAbove=0,
        partHeightAbove=0,
        volumeHeightAbove=0,
        dynamicHeightAbove=0,
        endingHeightAbove=0,
        chordHeightAbove=0,
        lyricHeightAbove=0,

        lyricHeightBelow=0,
        chordHeightBelow=0,
        volumeHeightBelow=0,
        dynamicHeightBelow=0,
    )


def set_upper_and_lower_elements(renderer, staff_group):
    # Each staff already has the top and bottom set, now we see if there are elements that are always on top and bottom, and resolve their pitch.
    # Also, get the overall height of all the staves in this group.
    last_staff_bottom = None
    for staff in staff_group.staffs:
        # the vertical order of elements that are above is: tempo, part, volume/dynamic, ending/chord, lyric
        # the vertical order of elements that are below is: lyric, chord, volume/dynamic
        position_y = _position_y()

        if renderer.showDebug and "box" in renderer.showDebug:
            staff.originalTop = staff.top  # This is just being stored for debugging purposes.
            staff.originalBottom = staff.bottom

        sy = staff.specialY
        _inc_top(staff, position_y, 'lyricHeightAbove')
        _inc_top(staff, position_y, 'chordHeightAbove', sy.chordLines.above)
        if sy.endingHeightAbove:
            if sy.chordHeightAbove:
                staff.top += 2
            else:
                staff.top += sy.endingHeightAbove + _MARGIN
            position_y.endingHeightAbove = staff.top
        if sy.dynamicHeightAbove and sy.volumeHeightAbove:
            staff.top += js_max(sy.dynamicHeightAbove, sy.volumeHeightAbove) + _MARGIN
            position_y.dynamicHeightAbove = staff.top
            position_y.volumeHeightAbove = staff.top
        else:
            _inc_top(staff, position_y, 'dynamicHeightAbove')
            _inc_top(staff, position_y, 'volumeHeightAbove')
        _inc_top(staff, position_y, 'partHeightAbove')
        _inc_top(staff, position_y, 'tempoHeightAbove')

        if sy.lyricHeightBelow:
            sy.lyricHeightBelow += renderer.spacing.vocal / spacing.STEP
            position_y.lyricHeightBelow = staff.bottom
            staff.bottom -= (sy.lyricHeightBelow + _MARGIN)
        if sy.chordHeightBelow:
            position_y.chordHeightBelow = staff.bottom
            hgt = sy.chordHeightBelow
            if sy.chordLines.below:
                hgt *= sy.chordLines.below
            staff.bottom -= (hgt + _MARGIN)
        if sy.volumeHeightBelow and sy.dynamicHeightBelow:
            position_y.volumeHeightBelow = staff.bottom
            position_y.dynamicHeightBelow = staff.bottom
            staff.bottom -= (js_max(sy.volumeHeightBelow, sy.dynamicHeightBelow) + _MARGIN)
        elif sy.volumeHeightBelow:
            position_y.volumeHeightBelow = staff.bottom
            staff.bottom -= (sy.volumeHeightBelow + _MARGIN)
        elif sy.dynamicHeightBelow:
            position_y.dynamicHeightBelow = staff.bottom
            staff.bottom -= (sy.dynamicHeightBelow + _MARGIN)

        if renderer.showDebug and "box" in renderer.showDebug:
            staff.positionY = position_y  # This is just being stored for debugging purposes.

        for vi in staff.voices:
            voice = staff_group.voices[vi]
            diff = _set_upper_and_lower_voice_elements(position_y, voice, renderer.spacing)
            staff.bottom -= diff
        # We might need a little space in between staves if the staves haven't been pushed far enough apart by notes or extra vertical stuff.
        # Only try to put in extra space if this isn't the top staff.
        if last_staff_bottom is not None:
            this_staff_top = staff.top - 10
            forced_spacing_between = last_staff_bottom + this_staff_top
            min_spacing_in_pitches = renderer.spacing.systemStaffSeparation / spacing.STEP
            added_space = min_spacing_in_pitches - forced_spacing_between
            if added_space > 0:
                staff.top += added_space
        staff.top += renderer.spacing.staffTopMargin / spacing.STEP

        last_staff_bottom = 2 - staff.bottom  # the staff starts at position 2 and the bottom variable is negative.


def _inc_top(staff, position_y, item, count=None):
    if staff.specialY[item]:
        height = staff.specialY[item]
        if count:
            height *= count
        staff.top += height + _MARGIN
        position_y[item] = staff.top


def _set_upper_and_lower_voice_elements(position_y, voice, spacing_):
    diff = 0
    for abselem in voice.children:
        bottom = _set_upper_and_lower_absolute_elements(position_y, abselem, spacing_)
        if lt(bottom, abselem.bottom):
            # We're moving things down so tell the staff that it needs to be taller
            diff = abselem.bottom - bottom
            abselem.bottom = bottom
            voice.bottom = bottom
    for abselem in voice.otherchildren:
        if isinstance(abselem, str):
            continue
        t = abselem.type
        if t == 'CrescendoElem':
            if abselem.dynamicHeightAbove:
                abselem.pitch = position_y.dynamicHeightAbove
            else:
                abselem.pitch = position_y.dynamicHeightBelow
        elif t == 'DynamicDecoration':
            if abselem.volumeHeightAbove:
                abselem.pitch = position_y.volumeHeightAbove
            else:
                abselem.pitch = position_y.volumeHeightBelow
        elif t == 'EndingElem':
            abselem.pitch = position_y.endingHeightAbove - 2
        elif t == 'TieElem':
            # If a tie element is the highest or lowest thing then space might need to make room for it.
            y_bounds = abselem.get_y_bounds()
            voice.staff.top = js_max(voice.staff.top, y_bounds[0])
            voice.staff.top = js_max(voice.staff.top, y_bounds[1])
            voice.staff.bottom = js_min(voice.staff.bottom, y_bounds[0])
            voice.staff.bottom = js_min(voice.staff.bottom, y_bounds[1])
    return diff


def _set_upper_and_lower_absolute_elements(special_y_resolved, element, spacing_):
    # For each of the relative elements that can't be placed in advance (because their vertical placement depends on everything
    # else on the line), this iterates through them and sets their pitch.
    bottom = element.bottom
    for child in element.children:
        for key in element.specialY:  # for each class of element that needs to be placed vertically
            v = getattr(child, key)
            if v:  # If this relative element has defined a height for this class of element
                child.pitch = special_y_resolved[key]
                if key == 'lyricHeightBelow' and child.type == 'lyric' and child.voiceNumber:
                    # TODO-PER: This can result in extra unused vertical space if there are lyrics only on the second but not the first voice.
                    child.pitch -= child.voiceNumber * v
                    bottom = js_min(element.bottom, child.pitch)
                if child.top is None:  # TODO-PER: HACK! Not sure this is the right place to do this.
                    if child.type == 'TempoElement':
                        _set_upper_and_lower_tempo_element(special_y_resolved, child)
                    else:
                        _set_upper_and_lower_relative_elements(special_y_resolved, child, spacing_)
                    element.push_top(child.top)
                    element.push_bottom(child.bottom)
    return bottom


def _set_upper_and_lower_tempo_element(position_y, element):
    element.pitch = position_y.tempoHeightAbove
    element.top = position_y.tempoHeightAbove
    element.bottom = position_y.tempoHeightAbove
    if element.note:
        tempo_pitch = element.pitch - element.totalHeightInPitches + 1  # The pitch we receive is the top of the allotted area: change that to practically the bottom.
        element.note.top = tempo_pitch
        element.note.bottom = tempo_pitch
        for child in element.note.children:
            child.top += tempo_pitch
            child.bottom += tempo_pitch
            child.pitch += tempo_pitch
            if child.pitch2 is not None:
                child.pitch2 += tempo_pitch


def _set_upper_and_lower_relative_elements(position_y, element, render_spacing):
    t = element.type
    if t == "part":
        element.top = position_y.partHeightAbove + element.height
        element.bottom = position_y.partHeightAbove
    elif t in ("text", "chord"):
        if element.chordHeightAbove:
            element.top = position_y.chordHeightAbove
            element.bottom = position_y.chordHeightAbove
        else:
            element.top = position_y.chordHeightBelow
            element.bottom = position_y.chordHeightBelow
    elif t == "lyric":
        if element.lyricHeightAbove:
            element.top = position_y.lyricHeightAbove
            element.bottom = position_y.lyricHeightAbove
        else:
            element.top = position_y.lyricHeightBelow + render_spacing.vocal / spacing.STEP
            element.bottom = position_y.lyricHeightBelow + render_spacing.vocal / spacing.STEP
            element.pitch -= render_spacing.vocal / spacing.STEP
    elif t == "debug":
        element.top = position_y.chordHeightAbove
        element.bottom = position_y.chordHeightAbove


# -- to-time-and-staff-based.js --------------------------------------------------------------

def to_time_and_staff_based(abc_lines):
    results = []
    for line in abc_lines:
        staff_group = line.staffGroup
        group = []
        if staff_group and staff_group.staffs:
            for staff in staff_group.staffs:
                time_slot = Obj()
                for vi in staff.voices:
                    voice = staff_group.voices[vi]
                    time = 0
                    for child in voice.children:
                        index = 'T' + str(js_round(time * 1000))  # There can be inexactness when calculating triplets, so we'll round
                        if time_slot.get(index) is None:
                            time_slot[index] = []
                        if child.abcelem.el_type == 'note':
                            time_slot[index].append(child)
                            time += child.duration
                # Now timeSlot is an object with all the voices on a particular staff that happen at the same time as an array.
                group.append(time_slot)
        results.append(group)
    return results


# -- layout-in-grid.js --------------------------------------------------------------------------

def layout_in_grid(renderer, staff_group, time_based_layout):
    left_edge = get_left_edge_of_staff(renderer, staff_group.getTextSize, staff_group.voices, staff_group.brace, staff_group.bracket)
    ret = _get_total_duration(staff_group, time_based_layout.get('minPadding'))
    total_duration = ret.totalDuration
    min_spacing = ret.minSpacing
    total_width = min_spacing * total_duration
    if time_based_layout.get('minWidth'):
        total_width = js_max(total_width, time_based_layout['minWidth'])
    left_align_padding = time_based_layout['minPadding'] / 2 if time_based_layout.get('minPadding') else 2  # If the padding isn't specified still give it some

    staff_group.startx = left_edge
    staff_group.w = total_width + left_edge
    for voice in staff_group.voices:
        voice.startx = left_edge
        voice.w = total_width + left_edge

        x = left_edge
        after_fixed_left = False
        duration_unit = 0
        for child in voice.children:
            if not after_fixed_left:
                if child.duration != 0:
                    # We got to the first music element on the line
                    after_fixed_left = True
                    duration_unit = (total_width + left_edge - x) / total_duration
                    staff_group.gridStart = x
                else:
                    # We are still doing the preliminary stuff - clef, time sig, etc.
                    child.x = x
                    x += child.w + child.minspacing
            if after_fixed_left:
                if time_based_layout.get('align') == 'center':
                    child.x = x + (child.duration * duration_unit) / 2 - child.w / 2
                else:
                    # left align with padding - but no padding for barlines, they should be right aligned.
                    if child.duration == 0:
                        child.x = x + 1 - child.w
                    else:
                        # child.extraw has the width of the accidentals - push the note to the right to take that into consideration.
                        child.x = x + left_align_padding - child.extraw
                x += child.duration * duration_unit
            for grandchild in child.children:
                # some elements don't have a dx - Tempo, for instance
                dx = grandchild.dx if grandchild.dx else 0
                grandchild.x = child.x + dx
        staff_group.gridEnd = x
    return total_width


def _get_total_duration(staff_group, time_based_layout):
    max_spacing = 0
    max_count = 0
    for voice in staff_group.voices:
        count = 0
        for element in voice.children:
            count += element.duration
            if truthy(element.duration):
                width = (element.w + (time_based_layout if time_based_layout is not None else float('nan'))) / element.duration
                max_spacing = js_max(max_spacing, width)
        max_count = js_max(max_count, count)
    return Obj(totalDuration=max_count, minSpacing=max_spacing)
