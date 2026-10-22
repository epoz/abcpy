"""Unrolls the repeats of a voice for playback (port of ``repeats.js``)."""

import json

from ..jsutil import Obj, assign, at, js_set, parse_int, is_nan, truthy


class Repeats:
    def __init__(self, voice):
        self.voice = voice
        self.sections = [Obj(type='startRepeat', index=-1)]

    def add_bar(self, elem, voice_number=None):
        # Record the "interesting" parts for analysis at the end.
        this_index = len(self.voice) - 1
        is_start_repeat = elem.type == "bar_left_repeat" or elem.type == "bar_dbl_repeat"
        is_end_repeat = elem.type == "bar_right_repeat" or elem.type == "bar_dbl_repeat"
        start_ending = _start_ending_numbers(elem.startEnding) if elem.startEnding else None
        if is_end_repeat:
            # If there are two endRepeats in a row, that is a notation error, but we'll recover by pretending there was a startRepeat right before it.
            if len(self.sections) > 0 and self.sections[-1].type == 'endRepeat':
                self.sections.append(Obj(type="startRepeat", index=self.sections[-1].index))
            self.sections.append(Obj(type="endRepeat", index=this_index))
        if start_ending is not None:
            self.sections.append(Obj(type="startEnding", index=this_index, endings=start_ending))
        if is_start_repeat:
            self.sections.append(Obj(type="startRepeat", index=this_index))

    def resolve_repeats(self):
        voice = self.voice
        # There may be one last set of events after the last interesting bar, so capture that now.
        last_section = self.sections[-1]
        last_element = len(voice) - 1
        if last_section.type == 'startRepeat':
            last_section.end = last_element
        elif last_section.index + 1 < last_element:
            self.sections.append(Obj(type="startRepeat", index=last_section.index + 1))

        if len(self.sections) < 2:
            return voice  # If there are no repeats then don't bother copying anything

        # Go through all the markers and turn that into an array of sets of sections in order.
        repeat_instructions = []  # { common: { start: number, end: number }, endings: Array<{start:number, end:number> }
        current_repeat = None
        for i in range(len(self.sections)):
            section = self.sections[i]
            if section.type == "startRepeat":
                if current_repeat:
                    if not current_repeat.common.end:
                        current_repeat.common.end = section.index
                    if current_repeat.endings is not None:
                        for e in current_repeat.endings:
                            if e and not e.end and e.start != section.index:
                                e.end = section.index
                    # If the last event was an end repeat, then there is one more repeat of just the common area. (Only when there are ending markers - otherwise it is already taken care of.)
                    if self.sections[i - 1].type == 'endRepeat' and current_repeat.endings is not None and len(current_repeat.endings):
                        current_repeat.endings.append(Obj(start=-1, end=-1))
                    repeat_instructions.append(current_repeat)

                # if there is a gap between the last event and this start, then
                # insert those items.
                if current_repeat:
                    last_used = current_repeat.common.end
                    if current_repeat.endings is not None:
                        for e in current_repeat.endings:
                            if e:
                                last_used = _js_max(last_used, e.end)
                    if last_used is not None and last_used < section.index - 1:
                        repeat_instructions.append(Obj(common=Obj(start=last_used + 1, end=section.index)))
                current_repeat = Obj(common=Obj(start=section.index))
            elif section.type == "startEnding":
                if current_repeat:
                    if not current_repeat.common.end:
                        current_repeat.common.end = section.index
                    if current_repeat.endings is None:
                        current_repeat.endings = []
                    for n in section.endings:
                        js_set(current_repeat.endings, n, Obj(start=section.index + 1))
            elif section.type == "endRepeat":
                if current_repeat:
                    if current_repeat.endings is None:
                        current_repeat.endings = []
                    if len(current_repeat.endings) > 0:
                        for e in current_repeat.endings:
                            if e and not e.end:
                                e.end = section.index
                    if not current_repeat.common.end:
                        # This is a repeat that doesn't have first and second endings
                        current_repeat.common.end = section.index
        if current_repeat:
            if not current_repeat.common.end:
                current_repeat.common.end = last_element
            if current_repeat.endings is not None:
                for e in current_repeat.endings:
                    if e and not e.end:
                        e.end = last_element
            repeat_instructions.append(current_repeat)

        output = []
        last_end = -1
        for instructions in repeat_instructions:
            if instructions.endings is None:
                _duplicate_span(voice, output, instructions.common.start, instructions.common.end)
            elif len(instructions.endings) == 0:
                # this is when there is no endings specified - it is just a repeat
                _duplicate_span(voice, output, instructions.common.start, instructions.common.end)
                _duplicate_span(voice, output, instructions.common.start, instructions.common.end)
            else:
                for ending in instructions.endings:
                    if ending:  # this is a sparse array so skip the empty ones
                        _duplicate_span(voice, output, instructions.common.start, instructions.common.end)
                        if ending.start > 0:
                            _duplicate_span(voice, output, ending.start, ending.end)
                        last_end = _js_max(last_end, ending.end)
        return output

    addBar = add_bar
    resolveRepeats = resolve_repeats


def _js_max(a, b):
    if a is None or b is None:
        return float('nan')
    return max(a, b)


def _duplicate_span(inp, output, start, end):
    if start is None or end is None or (isinstance(end, float) and is_nan(end)):
        return
    if start < 0:
        start = 0
    # If there is a bar at the end of a line and a bar to start the next line, it would be duplicated.
    if len(output) > 0 and at(inp, start) is not None and inp[start].el_type == 'bar' and output[-1].el_type == 'bar':
        start += 1

    i = start
    while i <= end:
        item = at(inp, i)
        if item is None:
            break
        skip = False
        if item.el_type in ('key', 'meter', 'tempo', 'instrument'):
            index = len(output) - 1
            while index >= 0 and output[index].el_type != item.el_type:
                index -= 1
            if index >= 0:
                if item.el_type == 'key' and _are_keys_equal(item, output[index]):
                    skip = True
                elif item.el_type == 'meter' and item.num == output[index].num and item.den == output[index].den:
                    skip = True
                elif item.el_type == 'instrument' and item.program == output[index].program:
                    skip = True
                elif item.el_type == 'tempo' and item.qpm == output[index].qpm:
                    skip = True
        if not skip:
            output.append(_duplicate_item(item))
        i += 1


def _duplicate_item(src):
    item = assign(src)
    if item.pitches:
        item.pitches = [assign(p) if p is not None else None for p in item.pitches]
    return item


def _are_keys_equal(el1, el2):
    if el1.accidentals is None or el2.accidentals is None:
        return False  # this shouldn't happen, but if so, we don't want to skip the element
    return json.dumps(el1.accidentals) == json.dumps(el2.accidentals)


def _start_ending_numbers(start_ending):
    # The ending can be in four different types: "random-string", "number", "number-number", "number,number"
    # If we don't get a number out of it then we will just skip the ending - we don't know what to do with it.
    nums = []
    if start_ending.find(',') > 0:
        for e in start_ending.split(','):
            ending = parse_int(e, 10)
            if not is_nan(ending) and ending > 0:
                nums.append(ending)
    elif start_ending.find('-') > 0:
        endings = start_ending.split('-')
        se = parse_int(endings[0], 10)
        ee = parse_int(endings[1], 10)
        if not is_nan(se) and not is_nan(ee):
            for i in range(se, ee + 1):
                nums.append(i)
    else:
        ending = parse_int(start_ending, 10)
        if not is_nan(ending) and ending > 0:
            nums.append(ending)
    return nums
