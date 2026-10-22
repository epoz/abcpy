"""Remove the line breaks from a parsed tune (port of ``deline-tune.js``)."""

import json

from ..jsutil import Obj, at, js_set, truthy


def deline_tune(input_lines, options=None):
    if not options:
        options = {}
    line_breaks = bool(options.get('lineBreaks'))
    output_lines = []
    in_music_line = False
    current_meter = []
    current_key = []
    current_clef = []
    current_vocal_font = []
    current_gchord_font = []
    current_triplet_font = []
    current_annotation_font = []
    for i in range(len(input_lines)):
        input_line = _clone_line(input_lines[i])
        if input_line.staff is not None:
            if in_music_line and not input_line.vskip:
                output_line = output_lines[-1]
                for s in range(len(output_line.staff)):
                    input_staff = at(input_line.staff, s)
                    output_staff = output_line.staff[s]
                    if input_staff:
                        if not _obj_equal(input_staff.meter, at(current_meter, s)):
                            # The meter changed for this line, otherwise it wouldn't have been set
                            _add_to_voices(input_staff.meter, input_staff.voices, "meter")
                            js_set(current_meter, s, input_staff.meter)
                            del input_staff.meter
                        if not _obj_equal(input_staff.key, at(current_key, s)):
                            _add_to_voices(input_staff.key, input_staff.voices, "key")
                            js_set(current_key, s, input_staff.key)
                            del input_staff.key
                        if input_staff.title:
                            output_staff.abbrevTitle = input_staff.title
                        if not _obj_equal(input_staff.clef, at(current_clef, s)):
                            _add_to_voices(input_staff.clef, input_staff.voices, "clef")
                            js_set(current_clef, s, input_staff.clef)
                            del input_staff.clef
                        for name, arr in (('vocalfont', current_vocal_font), ('gchordfont', current_gchord_font),
                                          ('tripletfont', current_triplet_font), ('annotationfont', current_annotation_font)):
                            if not _obj_equal(input_staff[name], at(arr, s)):
                                _add_font_to_voices(input_staff[name], input_staff.voices, name)
                                js_set(arr, s, input_staff[name])
                                input_staff.pop(name, None)
                    if input_staff:
                        for v in range(len(output_staff.voices)):
                            output_voice = output_staff.voices[v]
                            input_voice = at(input_staff.voices, v)
                            if line_breaks:
                                output_voice.append(Obj(el_type="break"))
                            if input_voice is not None:
                                output_staff.voices[v] = output_voice + input_voice
            else:
                for ii in range(len(input_line.staff)):
                    js_set(current_key, ii, input_line.staff[ii].key)
                    js_set(current_meter, ii, input_line.staff[ii].meter)
                    js_set(current_clef, ii, input_line.staff[ii].clef)
                # copy this because we are going to change it and we don't want to change the original.
                output_lines.append(_clone_line(input_line))
            in_music_line = True
        else:
            in_music_line = False
            output_lines.append(input_line)
    return output_lines


def _replacer(o):
    return None


def _strip_abselem(value):
    if isinstance(value, dict):
        return {k: ('abselem' if k == 'abselem' else _strip_abselem(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_abselem(v) for v in value]
    return value


def _stringify(value):
    if value is None:
        return None
    return json.dumps(_strip_abselem(value), default=_replacer, ensure_ascii=False)


def _add_to_voices(item, voices, el_type):
    item.el_type = el_type
    item.startChar = -1
    item.endChar = -1
    for v in voices:
        v.insert(0, item)


def _add_font_to_voices(font, voices, typ):
    font.el_type = "font"
    font.type = typ
    font.startChar = -1
    font.endChar = -1
    for v in voices:
        v.insert(0, font)


def _obj_equal(inp, out):
    if not truthy(inp):
        return True  # the default is whatever the old output is.
    return _stringify(inp) == _stringify(out)


def _clone_line(line):
    output = Obj()
    for key in line.keys():
        if key != "staff":
            output[key] = line[key]
        else:
            output.staff = []
            for st in line.staff:
                staff = Obj()
                for k2 in st.keys():
                    if k2 != "voices":
                        staff[k2] = st[k2]
                    else:
                        staff.voices = [list(v) for v in st.voices]
                output.staff.append(staff)
    return output
