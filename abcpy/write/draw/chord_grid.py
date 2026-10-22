"""Draws a chord grid (port of ``draw/chord-grid.js``)."""

from ...jsutil import Obj, js_str
from .draw import print_symbol, print_stem

ROW_HEIGHT = 50
ENDING_HEIGHT = 10
ANNOTATION_HEIGHT = 14
PART_MARGIN_TOP = 10
PART_MARGIN_BOTTOM = 20
TEXT_MARGIN = 16

MAX_ONE_CHORD = 34
MAX_TWO_CHORDS = 26
MAX_FOUR_CHORDS = 20
TOP_MARGIN = -3

_symbols = {
    'segno': "scripts.segno",
    'coda': "scripts.coda",
    "fermata": "scripts.ufermata",
}


def draw_chord_grid(renderer, parts, left_margin, page_width, fonts):
    chord_font = fonts.gchordfont
    annotation_font = fonts.annotationfont
    ending_font = fonts.repeatfont
    text_font = fonts.textfont
    subtitle_font = fonts.subtitlefont

    renderer.paper.open_group(Obj(klass='abcjs-chord-grid'))
    for part in parts:
        if part.type == "text":
            _text(renderer, part.text, left_margin, renderer.y, 16, text_font, None, None, False)
            renderer.move_y(TEXT_MARGIN)
        elif part.type == "subtitle":
            _text(renderer, part.subtitle, left_margin, renderer.y + PART_MARGIN_TOP, 20, subtitle_font, None, "abcjs-subtitle", False)
            renderer.move_y(PART_MARGIN_BOTTOM)
        elif part.type == "part":
            if len(part.lines) > 0:
                _text(renderer, part.name, left_margin, renderer.y + PART_MARGIN_TOP, 20, subtitle_font, part.name, "abcjs-part", False)

                renderer.move_y(PART_MARGIN_BOTTOM)
                num_cols = len(part.lines[0])
                col_width = page_width / num_cols
                for line_num, line in enumerate(part.lines):
                    has_ending = False
                    has_annotation = False
                    for measure in line:
                        if measure.ending:
                            has_ending = True
                        if measure.annotations and len(measure.annotations) > 0:
                            has_annotation = True
                    extra_top = ANNOTATION_HEIGHT if has_annotation else (ENDING_HEIGHT if has_ending else 0)
                    for bar_num, measure in enumerate(line):
                        rect_width = 1
                        if not measure.noBorder:
                            renderer.paper.rect(Obj(x=left_margin + bar_num * col_width, y=renderer.y, width=col_width, height=extra_top + ROW_HEIGHT))
                            renderer.paper.rect(Obj(x=left_margin + bar_num * col_width + rect_width, y=renderer.y + rect_width, width=col_width - rect_width * 2, height=extra_top + ROW_HEIGHT - rect_width * 2))
                            repeat_left = 0
                            repeat_right = 0
                            top = renderer.y
                            left = left_margin + col_width * bar_num
                            if measure.hasStartRepeat:
                                _draw_repeat(renderer, left, top, top + ROW_HEIGHT + extra_top, True, extra_top)
                                repeat_left = 12
                            if measure.hasEndRepeat:
                                _draw_repeat(renderer, left + col_width, top, top + ROW_HEIGHT + extra_top, False, extra_top)
                                repeat_right = 12

                            ending_width = 0
                            if measure.ending:
                                ending_el = _text(renderer, measure.ending, left_margin + bar_num * col_width + 4, top + 10, 12, ending_font, None, None, False)
                                ending_width = ending_el.get_bbox().width + 4
                            _draw_measure(renderer, top, left_margin + repeat_left, col_width, line_num, bar_num, measure.chord, chord_font, repeat_left + repeat_right, ROW_HEIGHT, extra_top)
                            if measure.annotations and len(measure.annotations) > 0:
                                _draw_annotations(renderer, top, left_margin + bar_num * col_width + ending_width, measure.annotations, annotation_font)
                            if extra_top:
                                renderer.paper.rect_beneath(Obj(x=left_margin + bar_num * col_width, y=renderer.y, width=col_width, height=extra_top, fill='#e8e8e8', stroke='none'))
                    renderer.move_y(extra_top + ROW_HEIGHT)
                renderer.move_y(PART_MARGIN_BOTTOM)
    renderer.paper.close_group()


def _draw_percent(renderer, x, y, offset):
    line_x1 = x - 10
    line_x2 = x + 10
    line_y1 = y + 10
    line_y2 = y - 10
    left_dot_x = x - 10
    left_dot_y = -renderer.y_to_pitch(offset) + 2
    right_dot_x = x + 6.5
    right_dot_y = -renderer.y_to_pitch(offset) - 2.3

    a = Obj(x1=line_x1, x2=line_x2, y1=line_y1, y2=line_y2)
    a['stroke-width'] = '3px'
    a['stroke-linecap'] = "round"
    renderer.paper.line_to_back(a)

    print_symbol(renderer, left_dot_x, left_dot_y, "dots.dot", Obj(scalex=1, scaley=1, klass="", name="dot"))
    print_symbol(renderer, right_dot_x, right_dot_y, "dots.dot", Obj(scalex=1, scaley=1, klass="", name="dot"))


def _draw_repeat(renderer, x, y1, y2, is_start, offset):
    line_x = x + 2 if is_start else x - 4
    circle_x = x + 9 if is_start else x - 11

    renderer.paper.open_group(Obj(klass='abcjs-repeat'))
    print_stem(renderer, line_x, 3 + renderer.lineThickness, y1, y2, None, "bar")

    print_symbol(renderer, circle_x, -renderer.y_to_pitch(offset) - 4, "dots.dot", Obj(scalex=1, scaley=1, klass="", name="dot"))
    print_symbol(renderer, circle_x, -renderer.y_to_pitch(offset) - 8, "dots.dot", Obj(scalex=1, scaley=1, klass="", name="dot"))
    renderer.paper.close_group()


def _draw_annotations(renderer, offset, left, annotations, annotation_font):
    left += 3
    for a in annotations:
        if a in ('segno', 'coda', "fermata"):
            left += 12
            el = print_symbol(renderer, left, -3, _symbols[a], Obj(scalex=1, scaley=1, name=_symbols[a]))
            box = el.get_bbox()
            left += box.width
        else:
            _text(renderer, a, left, offset + 12, 12, annotation_font, None, None, False)


def _draw_measure(renderer, offset, left_margin, col_width, line_num, bar_num, chords, chord_font, margin, height, extra_top):
    left = left_margin + col_width * bar_num

    def ch(i):
        return chords[i] if i < len(chords) else None

    if not ch(1) and not ch(2) and not ch(3):
        _draw_single_chord(renderer, left, offset + extra_top, col_width - margin, height, ch(0), chord_font, extra_top)
    elif not ch(1) and not ch(3):
        _draw_two_chords(renderer, left, offset, col_width - margin, height, ch(0), ch(2), chord_font, extra_top)
    else:
        _draw_four_chords(renderer, left, offset, col_width - margin, height, chords, chord_font, extra_top)


def _render_chord(renderer, x, y, size, chord, font, max_width):
    el = _text(renderer, chord, x, y, size, font, None, "abcjs-chord", True)
    bb = el.get_bbox()
    font_size = size
    while bb.width > max_width and font_size >= 14:
        font_size -= 2
        el.set_attribute('font-size', font_size)
        bb = el.get_bbox()


def _draw_single_chord(renderer, left, top, width, height, chord, font, extra_top):
    if chord == '%':
        _draw_percent(renderer, left + width / 2, top + height / 2, extra_top + height / 2)
    else:
        _render_chord(renderer, left + width / 2, top + height / 2 + TOP_MARGIN, MAX_ONE_CHORD, chord, font, width)


def _draw_two_chords(renderer, left, top, width, height, chord1, chord2, font, extra_top):
    renderer.paper.line_to_back(Obj(x1=left, x2=left + width, y1=top + height + extra_top, y2=top + 2))
    _render_chord(renderer, left + width / 4, top + height / 4 + 5 + extra_top + TOP_MARGIN, MAX_TWO_CHORDS, chord1, font, width / 2)
    _render_chord(renderer, left + 3 * width / 4, top + 3 * height / 4 + extra_top + TOP_MARGIN, MAX_TWO_CHORDS, chord2, font, width / 2)


def _draw_four_chords(renderer, left, top, width, height, chords, font, extra_top):
    margin = 3
    renderer.paper.line_to_back(Obj(x1=left + margin, x2=left + width - margin, y1=top + height / 2 + extra_top, y2=top + height / 2 + extra_top))
    renderer.paper.line_to_back(Obj(x1=left + width / 2, x2=left + width / 2, y1=top + margin + extra_top, y2=top + height - margin + extra_top))

    def ch(i):
        return chords[i] if i < len(chords) else None

    if ch(0):
        _render_chord(renderer, left + width / 4, top + height / 4 + 2 + extra_top + TOP_MARGIN, MAX_FOUR_CHORDS, _shorten_chord(ch(0)), font, width / 2)
    if ch(1):
        _render_chord(renderer, left + 3 * width / 4, top + height / 4 + 2 + extra_top + TOP_MARGIN, MAX_FOUR_CHORDS, _shorten_chord(ch(1)), font, width / 2)
    if ch(2):
        _render_chord(renderer, left + width / 4, top + 3 * height / 4 + extra_top + TOP_MARGIN, MAX_FOUR_CHORDS, _shorten_chord(ch(2)), font, width / 2)
    if ch(3):
        _render_chord(renderer, left + 3 * width / 4, top + 3 * height / 4 + extra_top + TOP_MARGIN, MAX_FOUR_CHORDS, _shorten_chord(ch(3)), font, width / 2)


def _shorten_chord(chord):
    if chord == "No Chord":
        return "N.C."
    return chord


def _text(renderer, s, x, y, size, font, data_name, klass, align_center):
    attr = Obj(x=x, y=y, stroke="none")
    attr['font-size'] = size
    attr['font-style'] = font.style
    attr['font-family'] = font.face
    attr['font-weight'] = font.weight
    attr['text-decoration'] = font.decoration
    if data_name:
        attr['data-name'] = data_name
    if klass:
        attr['class'] = klass
    attr["text-anchor"] = "middle" if align_center else "start"
    span = Obj()
    span["alignment-baseline"] = "middle"
    return renderer.paper.text(s if s is not None else js_str(s), attr, None, span)
