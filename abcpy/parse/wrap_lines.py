"""Line wrapping of an already parsed tune (port of ``wrap_lines.js``)."""

import math

from ..jsutil import Obj, at, js_set, js_round, parse_float, parse_int, js_floor, js_ceil


def wrap_lines(tune, line_breaks, bar_numbers):
    if not line_breaks or len(tune.lines) == 0:
        return

    # tune.lines contains nested arrays: there is an array of lines (that's the part this function rewrites),
    # there is an array of staffs per line (for instance, piano will have 2, orchestra will have many)
    # there is an array of voices per staff (for instance, 4-part harmony might have bass and tenor on a single staff)
    lines = tune.deline(Obj(lineBreaks=False))
    lines_break_elements = _find_line_breaks(lines, line_breaks)
    tune.lines = _add_line_breaks(lines, lines_break_elements, bar_numbers)
    tune.lineBreaks = lines_break_elements


def _add_line_breaks(lines, lines_break_elements, bar_numbers):
    # linesBreakElements is an array of all of the elements that break for a new line
    # The objects in the array look like:
    # {"ogLine":0,"line":0,"staff":0,"voice":0,"start":0, "end":21}
    output_lines = []
    last_key_sig = {}  # This is per staff - if the key changed then this will be populated.
    last_stem = {}
    current_bar_number = 1
    for action in lines_break_elements:
        if lines[action.ogLine].staff:
            input_staff = lines[action.ogLine].staff[action.staff]
            if not at(output_lines, action.line):
                js_set(output_lines, action.line, Obj(staff=[]))
            out_line = output_lines[action.line]
            if not at(out_line.staff, action.staff):
                st = Obj(voices=[])
                js_set(out_line.staff, action.staff, st)
                if bar_numbers is not None and action.staff == 0 and action.line > 0:
                    st.barNumber = current_bar_number
                for k in input_staff.keys():
                    skip = k == "voices"
                    if k == "meter" and action.line != 0:
                        skip = True
                    if not skip:
                        st[k] = input_staff[k]
                if last_key_sig.get(action.staff):
                    st.key = last_key_sig[action.staff]
            out_staff = out_line.staff[action.staff]
            if at(out_staff.voices, action.voice) is None:
                js_set(out_staff.voices, action.voice, [])
            out_staff.voices[action.voice] = lines[action.ogLine].staff[action.staff].voices[action.voice][action.start:action.end + 1]
            stem_key = action.staff * 10 + action.voice
            if last_stem.get(stem_key):
                out_staff.voices[action.voice].insert(0, Obj(el_type="stem", direction=last_stem[stem_key].direction))
            curr_voice = out_staff.voices[action.voice]
            for kk in range(len(curr_voice) - 1, -1, -1):
                if curr_voice[kk].el_type == "key":
                    last_key_sig[action.staff] = Obj(
                        root=curr_voice[kk].root,
                        acc=curr_voice[kk].acc,
                        mode=curr_voice[kk].mode,
                        accidentals=[a for a in curr_voice[kk].accidentals if a.acc != 'natural'])
                    break
            for kk in range(len(curr_voice) - 1, -1, -1):
                if curr_voice[kk].el_type == "stem":
                    last_stem[stem_key] = Obj(direction=curr_voice[kk].direction)
                    break
            if bar_numbers is not None and action.staff == 0 and action.voice == 0:
                for kk in range(len(curr_voice)):
                    if curr_voice[kk].el_type == 'bar':
                        current_bar_number += 1
                        if kk == len(curr_voice) - 1:
                            curr_voice[kk].pop('barNumber', None)
                        else:
                            curr_voice[kk].barNumber = current_bar_number
        else:
            js_set(output_lines, action.line, lines[action.ogLine])
    # There could be some missing info - if the tune passed in was incomplete or had different lengths for different voices or was missing a voice altogether - just fill in the gaps.
    for ol in output_lines:
        if ol is not None and ol.staff:
            ol.staff = [el for el in ol.staff if el is not None]
    return output_lines


def _find_line_breaks(lines, line_break_array):
    # lineBreakArray is an array of all of the sections of the tune - often there will just be one
    # section unless there is a subtitle or other non-music lines.
    # Each element of lineBreakArray is an array of the zero-based last measure of the line.
    line_break_indexes = []
    lbai = 0
    line_counter = 0
    output_line = 0
    for i in range(len(lines)):
        line = lines[i]
        if line.staff:
            line_start = line_counter
            line_breaks = at(line_break_array, lbai)
            lbai += 1
            for j in range(len(line.staff)):
                staff = line.staff[j]
                for k in range(len(staff.voices)):
                    output_line = line_start
                    measure_number = 0
                    lbi = 0
                    voice = staff.voices[k]
                    start = 0
                    for e in range(len(voice)):
                        el = voice[e]
                        if el.el_type == 'bar':
                            if at(line_breaks, lbi) == measure_number:
                                line_break_indexes.append(Obj(ogLine=i, line=output_line, staff=j, voice=k, start=start, end=e))
                                start = e + 1
                                output_line += 1
                                line_counter = max(line_counter, output_line)
                                lbi += 1
                            measure_number += 1
                    line_break_indexes.append(Obj(ogLine=i, line=output_line, staff=j, voice=k, start=start, end=len(voice)))
                    output_line += 1
                    line_counter = max(line_counter, output_line)
        else:
            line_break_indexes.append(Obj(ogLine=i, line=output_line))
            output_line += 1
            line_counter = max(line_counter, output_line)
    return line_break_indexes


def _free_form_line_breaks(widths, line_break_point):
    line_breaks = []
    totals = []
    total_this_line = 0
    # run through each measure and see if the accumulation is less than the ideal.
    # if it passes the ideal, then see whether the last or this one is closer to the ideal.
    for i in range(len(widths)):
        width = widths[i]
        attempted_width = total_this_line + width
        if attempted_width < line_break_point:
            total_this_line = attempted_width
        else:
            # This just passed the ideal, so see whether the previous or the current number of measures is closer.
            old_distance = line_break_point - total_this_line
            new_distance = attempted_width - line_break_point
            if old_distance < new_distance and total_this_line > 0:
                line_breaks.append(i - 1)
                totals.append(js_round(total_this_line - width))
                total_this_line = width
            else:
                if i < len(widths) - 1:
                    line_breaks.append(i)
                    totals.append(js_round(total_this_line))
                    total_this_line = 0
    totals.append(js_round(total_this_line))
    return Obj(lineBreaks=line_breaks, totals=totals)


def _one_try(measure_widths, ideal_widths, accumulator, line_accumulator, line_widths, last_variance, highest_variance, curr_line, line_breaks, start_index, other_tries):
    def ideal(n):
        v = at(ideal_widths, n)
        return v if v is not None else float('nan')

    for i in range(start_index, len(measure_widths)):
        measure_width = measure_widths[i]
        accumulator += measure_width
        line_accumulator += measure_width
        this_variance = abs(accumulator - ideal(curr_line))
        variance_is_close = abs(this_variance - last_variance) < ideal_widths[0] / 10  # see if the difference is less than 10%, if so, run the test both ways.
        if variance_is_close:
            if this_variance < last_variance:
                # Also attempt one less measure on the current line - sometimes that works out better.
                new_widths = list(line_widths)
                new_breaks = list(line_breaks)
                new_breaks.append(i - 1)
                new_widths.append(line_accumulator - measure_width)
                other_tries.append(Obj(
                    accumulator=accumulator,
                    lineAccumulator=measure_width,
                    lineWidths=new_widths,
                    lastVariance=abs(accumulator - ideal(curr_line + 1)),
                    highestVariance=max(highest_variance, last_variance),
                    currLine=curr_line + 1,
                    lineBreaks=new_breaks,
                    startIndex=i + 1))
            elif this_variance > last_variance and i < len(measure_widths) - 1:
                # Also attempt one extra measure on this line.
                new_widths = list(line_widths)
                new_breaks = list(line_breaks)
                other_tries.append(Obj(
                    accumulator=accumulator,
                    lineAccumulator=line_accumulator,
                    lineWidths=new_widths,
                    lastVariance=this_variance,
                    highestVariance=max(highest_variance, this_variance),
                    currLine=curr_line,
                    lineBreaks=new_breaks,
                    startIndex=i + 1))
        if this_variance > last_variance:
            line_breaks.append(i - 1)
            curr_line += 1
            highest_variance = max(highest_variance, last_variance)
            last_variance = abs(accumulator - ideal(curr_line))
            line_widths.append(line_accumulator - measure_width)
            line_accumulator = measure_width
        else:
            last_variance = this_variance
    line_widths.append(line_accumulator)


def _optimize_line_widths(widths, line_break_point, line_breaks, explanation):
    # figure out how many lines
    num_lines = js_ceil(widths.total / line_break_point)

    # get the ideal width for a line (cumulative width / num lines) - approx the same as lineBreakPoint except for rounding
    ideal_width = js_floor(widths.total / num_lines)

    # get each ideal line width (1*ideal, 2*ideal, 3*ideal, etc)
    ideal_widths = [ideal_width * (i + 1) for i in range(num_lines)]

    # from first measure, step through accum. Widths until the abs of the ideal is greater than the last one.
    # This can sometimes look funny in edge cases, so when the length is within 10%, try one more or one less to see which is better.
    other_tries = [Obj(
        accumulator=0,
        lineAccumulator=0,
        lineWidths=[],
        lastVariance=999999,
        highestVariance=0,
        currLine=0,
        lineBreaks=[],  # These are the zero-based last measure on each line
        startIndex=0)]
    index = 0
    while index < len(other_tries):
        t = other_tries[index]
        _one_try(widths.measureWidths, ideal_widths, t.accumulator, t.lineAccumulator, t.lineWidths,
                 t.lastVariance, t.highestVariance, t.currLine, t.lineBreaks, t.startIndex, other_tries)
        index += 1
    for other_try in other_tries:
        other_try.variances = []
        other_try.aveVariance = 0
        for line_width in other_try.lineWidths:
            other_try.variances.append(line_width - ideal_widths[0])
            other_try.aveVariance += abs(line_width - ideal_widths[0])
        other_try.aveVariance = other_try.aveVariance / len(other_try.lineWidths)
        explanation.attempts.append(Obj(type="optimizeLineWidths", lineBreaks=other_try.lineBreaks, variances=other_try.variances, aveVariance=other_try.aveVariance, widths=widths.measureWidths))
    smallest = 9999999
    smallest_index = -1
    for i in range(len(other_tries)):
        if other_tries[i].aveVariance < smallest:
            smallest = other_tries[i].aveVariance
            smallest_index = i
    return Obj(failed=False, lineBreaks=other_tries[smallest_index].lineBreaks, variance=other_tries[smallest_index].highestVariance)


def _fixed_measure_line_breaks(widths, line_break_point, preferred_measures_per_line):
    line_breaks = []
    totals = []
    this_width = 0
    failed = False
    for i in range(len(widths)):
        this_width += widths[i]
        if this_width > line_break_point:
            failed = True
        if i % preferred_measures_per_line == (preferred_measures_per_line - 1):
            if i != len(widths) - 1:  # Don't bother putting a line break for the last line - it's already a break.
                line_breaks.append(i)
            totals.append(js_round(this_width))
            this_width = 0
    return Obj(failed=failed, totals=totals, lineBreaks=line_breaks)


def _get_revised_tune_params(line_breaks, staff_width, params):
    revised_params = Obj(lineBreaks=line_breaks, staffwidth=staff_width)
    for key in params:
        if key != 'wrap' and key != 'staffwidth':
            revised_params[key] = params[key]
    return Obj(revisedParams=revised_params)


def calc_line_wraps(tune, widths, params):
    """Figure out where the line breaks should go to fit the requested width."""
    # If the desired width is less than the margin, just punt and return the original tune
    if len(widths) == 0 or params.staffwidth < widths[0].left:
        return Obj(reParse=False, explanation="Staff width is narrower than the margin", revisedParams=params)
    wrap = params.wrap
    scale = max(params.scale, 0.1) if params.scale else 1
    min_spacing = max(parse_float(wrap.minSpacing), 1) if wrap.minSpacing else 1
    min_spacing_limit = max(parse_float(wrap.minSpacingLimit), 1) if wrap.minSpacingLimit else min_spacing - 0.1
    max_spacing = max(parse_float(wrap.maxSpacing), 1) if wrap.maxSpacing else None
    if wrap.lastLineLimit and not max_spacing:
        max_spacing = max(parse_float(wrap.lastLineLimit), 1)
    preferred_measures_per_line = max(parse_int(wrap.preferredMeasuresPerLine, 10), 0) if wrap.preferredMeasuresPerLine else None

    accumulated_line_breaks = []
    explanations = []
    for section in widths:
        usable_width = params.staffwidth - section.left
        line_break_point = usable_width / min_spacing / scale
        min_line_size = usable_width / max_spacing / scale if max_spacing else float('nan')
        allowable_variance = usable_width / min_spacing_limit / scale
        explanation = Obj(
            widths=section,
            lineBreakPoint=line_break_point,
            minLineSize=min_line_size,
            attempts=[],
            staffWidth=params.staffwidth,
            minWidth=js_round(allowable_variance))

        # If there is a preferred number of measures per line, test that first. If none of the lines is too long, then we're finished.
        line_breaks = None
        if preferred_measures_per_line:
            f = _fixed_measure_line_breaks(section.measureWidths, line_break_point, preferred_measures_per_line)
            explanation.attempts.append(Obj(
                type="Fixed Measures Per Line",
                preferredMeasuresPerLine=preferred_measures_per_line,
                lineBreaks=f.lineBreaks,
                failed=f.failed,
                totals=f.totals))
            if not f.failed:
                line_breaks = f.lineBreaks

        # If we don't have lineBreaks yet, use the free form method of line breaks.
        if line_breaks is None:
            ff = _free_form_line_breaks(section.measureWidths, line_break_point)
            explanation.attempts.append(Obj(type="Free Form", lineBreaks=ff.lineBreaks, totals=ff.totals))
            line_breaks = ff.lineBreaks

            # We now have an acceptable number of lines, but the measures may not be optimally distributed. See if there is a better distribution.
            if len(line_breaks) > 0 and len(section.measureWidths) < 25:
                # Only do this if everything doesn't fit on one line.
                ff = _optimize_line_widths(section, line_break_point, line_breaks, explanation)
                explanation.attempts.append(Obj(
                    type="Optimize",
                    failed=ff.failed,
                    reason=ff.reason,
                    lineBreaks=ff.lineBreaks,
                    totals=ff.totals))
                if not ff.failed:
                    line_breaks = ff.lineBreaks
        accumulated_line_breaks.append(line_breaks)
        explanations.append(explanation)
    staff_width = params.staffwidth
    ret = _get_revised_tune_params(accumulated_line_breaks, staff_width, params)
    ret.explanation = explanations
    ret.reParse = True
    return ret
