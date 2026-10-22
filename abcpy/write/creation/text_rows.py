"""The non-music text of a tune: title, composer, notes, free text, etc.

Ports of ``add-chord.js``, ``add-text-if.js``, ``elements/rich-text.js``, ``elements/top-text.js``,
``elements/bottom-text.js``, ``elements/free-text.js``, ``elements/separator.js`` and
``elements/subtitle.js``.  Each of these creates a list of "rows" that are drawn later.
"""

import re

from ...jsutil import Obj, js_round, js_str, truthy
from ..helpers import spacing
from .elements import RelativeElement
from .note_parts import translate_chord


# -- chords and annotations -------------------------------------------------------

def add_chord(get_text_size, abselem, elem, room_taken, room_taken_right, notehead_width, jazzchords, german_alphabet):
    for ch in elem.chord:
        pos = ch.position
        rel_position = ch.rel_position
        is_annotation = pos in ("left", "right", "below", "above") or bool(rel_position)
        if is_annotation:
            font = 'annotationfont'
            klass = "abcjs-annotation"
        else:
            font = 'gchordfont'
            klass = "abcjs-chord"
        attr = get_text_size.attr(font, klass)

        name = ch.name
        if isinstance(name, str):
            ret = _chord_string(name, pos, rel_position, is_annotation, font, klass, attr, get_text_size, abselem, elem, room_taken, room_taken_right, notehead_width, jazzchords, german_alphabet)
            room_taken = ret.roomTaken
            room_taken_right = ret.roomTakenRight
        else:
            for part in name:
                ret = _chord_string(part.text, pos, rel_position, is_annotation, font, klass, attr, get_text_size, abselem, elem, room_taken, room_taken_right, notehead_width, jazzchords, german_alphabet)
                room_taken = ret.roomTaken
                room_taken_right = ret.roomTakenRight
    return Obj(roomTaken=room_taken, roomTakenRight=room_taken_right)


def _chord_string(chord_string, pos, rel_position, is_annotation, font, klass, attr, get_text_size, abselem, elem, room_taken, room_taken_right, notehead_width, jazzchords, german_alphabet):
    chords = chord_string.split("\n")
    for j in range(len(chords) - 1, -1, -1):  # parse these in opposite order because we place them from bottom to top.
        chord = chords[j]
        x = 0
        if not is_annotation:
            chord = translate_chord(chord, jazzchords, german_alphabet)
        dim = get_text_size.calc(chord, font, klass)
        chord_width = dim.width
        chord_height = dim.height / spacing.STEP
        if pos == "left":
            room_taken += chord_width + 7
            x = -room_taken  # TODO-PER: This is just a guess from trial and error
            y = elem.averagepitch
            abselem.add_extra(RelativeElement(chord, x, chord_width + 4, y, Obj(type="text", height=chord_height, dim=attr, position="left")))
        elif pos == "right":
            room_taken_right += 4
            x = room_taken_right  # TODO-PER: This is just a guess from trial and error
            y = elem.averagepitch
            abselem.add_right(RelativeElement(chord, x, chord_width + 4, y, Obj(type="text", height=chord_height, dim=attr, position="right")))
        elif pos == "below":
            # setting the y-coordinate to undefined for now: it will be overwritten later on, after we figure out what the highest element on the line is.
            abselem.add_right(RelativeElement(chord, 0, 0, None, Obj(type="text", position="below", height=chord_height, dim=attr, realWidth=chord_width)))
        elif pos == "above":
            abselem.add_right(RelativeElement(chord, 0, 0, None, Obj(type="text", position="above", height=chord_height, dim=attr, realWidth=chord_width)))
        else:
            if rel_position:
                rel_position_y = rel_position.y + 3 * spacing.STEP  # TODO-PER: this is a fudge factor to make it line up with abcm2ps
                abselem.add_right(RelativeElement(chord, x + rel_position.x, 0, elem.minpitch + rel_position_y / spacing.STEP, Obj(position="relative", type="text", height=chord_height, dim=attr)))
            else:
                # setting the y-coordinate to undefined for now: it will be overwritten later on, after we figure out what the highest element on the line is.
                pos2 = 'above'
                if elem.positioning and elem.positioning.chordPosition:
                    pos2 = elem.positioning.chordPosition

                if pos2 != 'hidden':
                    abselem.add_centered(RelativeElement(chord, notehead_width / 2, chord_width, None, Obj(type="chord", position=pos2, height=chord_height, dim=attr, realWidth=chord_width)))
    return Obj(roomTaken=room_taken, roomTakenRight=room_taken_right)


# -- rows of text ---------------------------------------------------------------

def add_text_if(rows, params, get_text_size):
    if not params.get('text'):
        return
    if not params.get('marginLeft'):
        params['marginLeft'] = 0
    if not params.get('klass'):
        params['klass'] = ''
    if not params.get('anchor'):
        params['anchor'] = 'start'
    if not params.get('info'):
        params['info'] = Obj(startChar=-2, endChar=-2)

    if params.get('marginTop'):
        rows.append(Obj(move=params['marginTop']))
    attr = Obj(left=params['marginLeft'], text=params['text'], font=params.get('font'), anchor=params['anchor'],
               startChar=params['info'].get('startChar'), endChar=params['info'].get('endChar'))
    attr['dominant-baseline'] = params.get('dominant-baseline')
    if params.get('absElemType'):
        attr.absElemType = params['absElemType']
    if not params.get('inGroup') and params.get('klass'):
        attr.klass = params['klass']
    if params.get('name'):
        attr.name = params['name']

    rows.append(attr)
    # If there are blank lines they won't be counted by getTextSize, so just get the height of one line and multiply
    size = get_text_size.calc("A", params.get('font'), params['klass'])
    text = params['text']
    num_lines = len(text.split("\n"))
    if text[-1] == '\n':
        num_lines -= 1  # If there is a new line at the end of the string, then an extra line will be counted.
    if not params.get('noMove'):
        h = (size.height * 1.1) * num_lines
        rows.append(Obj(move=js_round(h)))
        if params.get('marginBottom'):
            rows.append(Obj(move=params['marginBottom']))


def rich_text(rows, s, def_font, klass, name, padding_left, attr, get_text_size):
    space = get_text_size.calc("i", def_font, klass)
    if s == '':
        rows.append(Obj(move=space.height))
    else:
        if isinstance(s, str):
            add_text_if(rows, dict(marginLeft=padding_left, text=s, font=def_font, klass=klass, marginTop=attr.get('marginTop'),
                                   anchor=attr.get('anchor'), absElemType=attr.get('absElemType'), info=attr.get('info'), name=name), get_text_size)
            return
        if attr.get('marginTop'):
            rows.append(Obj(move=attr['marginTop']))

        largest_y = 0
        row = Obj(left=padding_left, anchor=attr.get('anchor'), phrases=[])
        if klass:
            row.klass = klass
        rows.append(row)
        for this_word in s:
            font = this_word.font if this_word.font else get_text_size.attr(def_font, klass).font
            phrase = Obj(content=this_word.text)
            if font:
                phrase.attrs = Obj([
                    ("font-family", get_text_size.get_family(font.face)),
                    ("font-size", font.size),
                    ("font-weight", font.weight),
                    ("font-style", font.style),
                    ("font-decoration", font.decoration),
                ])
            row.phrases.append(phrase)
            size = get_text_size.calc(this_word.text, font, klass)
            largest_y = max(largest_y, size.height)
        rows.append(Obj(move=largest_y))


def top_text(meta_text, meta_text_info, formatting, lines, width, is_print, padding_left, spacing_, should_add_classes, get_text_size):
    rows = []
    if meta_text.header and is_print:
        # Note: whether there is a header or not doesn't change any other positioning, so this doesn't change the Y-coordinate.
        # This text goes above the margin, so we'll temporarily move up.
        header_text_height = get_text_size.calc("X", "headerfont", 'abcjs-header abcjs-meta-top').height
        add_text_if(rows, dict(marginLeft=padding_left, text=meta_text.header.left, font='headerfont', klass='header meta-top', marginTop=-header_text_height, info=meta_text_info.header, name="header"), get_text_size)
        add_text_if(rows, dict(marginLeft=padding_left + width / 2, text=meta_text.header.center, font='headerfont', klass='header meta-top', marginTop=-header_text_height, anchor='middle', info=meta_text_info.header, name="header"), get_text_size)
        add_text_if(rows, dict(marginLeft=padding_left + width, text=meta_text.header.right, font='headerfont', klass='header meta-top', marginTop=-header_text_height, anchor='end', info=meta_text_info.header, name="header"), get_text_size)
    if is_print:
        rows.append(Obj(move=spacing_.top))
    t_anchor = 'start' if formatting.titleleft else 'middle'
    t_left = padding_left if formatting.titleleft else padding_left + width / 2
    if meta_text.title:
        klass = 'abcjs-title' if should_add_classes else ''
        rich_text(rows, meta_text.title, "titlefont", klass, 'title', t_left, dict(marginTop=spacing_.title, anchor=t_anchor, absElemType="title", info=meta_text_info.title), get_text_size)
    if len(lines):
        index = 0
        while index < len(lines) and lines[index].subtitle:
            klass = 'abcjs-text abcjs-subtitle' if should_add_classes else ''
            rich_text(rows, lines[index].subtitle.text, "subtitlefont", klass, 'subtitle', t_left, dict(marginTop=spacing_.subtitle, anchor=t_anchor, absElemType="subtitle", info=lines[index].subtitle), get_text_size)
            index += 1

    if meta_text.rhythm or meta_text.origin or meta_text.composer:
        rows.append(Obj(move=spacing_.composer))
        if meta_text.rhythm and len(meta_text.rhythm) > 0:
            no_move = bool(meta_text.composer or meta_text.origin)
            klass = 'abcjs-rhythm' if should_add_classes else ''
            add_text_if(rows, dict(marginLeft=padding_left, text=meta_text.rhythm, font='infofont', klass=klass, absElemType="rhythm", noMove=no_move, info=meta_text_info.rhythm, name="rhythm"), get_text_size)

        composer_line = meta_text.composer if meta_text.composer else ''
        if meta_text.origin:
            if isinstance(composer_line, str) and isinstance(meta_text.origin, str):
                composer_line += ' (' + meta_text.origin + ')'
            elif isinstance(composer_line, str) and not isinstance(meta_text.origin, str):
                composer_line = [Obj(text=composer_line)]
                composer_line.append(Obj(text=" ("))
                composer_line = composer_line + list(meta_text.origin)
                composer_line.append(Obj(text=")"))
            else:
                composer_line = list(composer_line)
                composer_line.append(Obj(text=" ("))
                composer_line = composer_line + (list(meta_text.origin) if isinstance(meta_text.origin, list) else [meta_text.origin])
                composer_line.append(Obj(text=")"))
        if composer_line:
            klass = 'abcjs-composer' if should_add_classes else ''
            rich_text(rows, composer_line, 'composerfont', klass, "composer", padding_left + width, dict(anchor="end", absElemType="composer", info=meta_text_info.composer, ingroup=True), get_text_size)

    if meta_text.author and len(meta_text.author) > 0:
        klass = 'abcjs-author' if should_add_classes else ''
        rich_text(rows, meta_text.author, 'composerfont', klass, "author", padding_left + width, dict(anchor="end", absElemType="author", info=meta_text_info.author), get_text_size)

    if meta_text.partOrder and len(meta_text.partOrder) > 0:
        klass = 'abcjs-part-order' if should_add_classes else ''
        rich_text(rows, meta_text.partOrder, 'partsfont', klass, "part-order", padding_left, dict(absElemType="partOrder", info=meta_text_info.partOrder, anchor='start'), get_text_size)
    return Obj(rows=rows)


def bottom_text(meta_text, width, is_print, padding_left, spacing_, should_add_classes, get_text_size):
    rows = []
    if meta_text.unalignedWords and len(meta_text.unalignedWords) > 0:
        klass = 'abcjs-unaligned-words' if should_add_classes else ''
        def_font = 'wordsfont'
        space = get_text_size.calc("i", def_font, klass)
        rows.append(Obj(move=spacing_.words))
        _add_multi_line(rows, '', meta_text.unalignedWords, padding_left, def_font, "unalignedWords", "unalignedWords", klass, "unalignedWords", spacing_, should_add_classes, get_text_size)
        rows.append(Obj(move=space.height))
    _extra_text(rows, meta_text, padding_left, spacing_, should_add_classes, get_text_size)
    if meta_text.footer and is_print:
        _footer(rows, meta_text.footer, width, padding_left, get_text_size)
    return Obj(rows=rows)


def _add_single_line(rows, preface, text, margin_left, klass, should_add_classes, get_text_size):
    if text:
        if preface:
            if isinstance(text, str):
                text = preface + text
            else:
                text = [Obj(text=preface)] + list(text)
        klass = 'abcjs-extra-text ' + klass if should_add_classes else ''
        rich_text(rows, text, 'historyfont', klass, "description", margin_left, dict(absElemType="extraText", anchor='start'), get_text_size)


def _add_multi_line(rows, preface, content, margin_left, def_font, abs_elem_type, group_name, klass, name, spacing_, should_add_classes, get_text_size):
    if content:
        klass = 'abcjs-extra-text ' + klass if should_add_classes else ''
        size = get_text_size.calc("A", def_font, klass)
        if isinstance(content, str):
            if preface:
                content = preface + "\n" + content
            add_text_if(rows, {'marginLeft': margin_left, 'text': content, 'font': def_font, 'absElemType': "extraText", 'name': name, 'dominant-baseline': 'middle', 'klass': klass}, get_text_size)
        else:
            rows.append(Obj(startGroup=group_name, klass=klass, name=name))
            rows.append(Obj(move=spacing_.info))
            if preface:
                add_text_if(rows, {'marginLeft': margin_left, 'text': preface, 'font': def_font, 'absElemType': "extraText", 'name': name, 'dominant-baseline': 'middle'}, get_text_size)
                rows.append(Obj(move=size.height * 3 / 4))

            for j in range(len(content)):
                rich_text(rows, content[j], def_font, '', name, margin_left, dict(anchor='start'), get_text_size)
                # TODO-PER: Hack! the string and rich lines should have used up the same amount of space without this.
                if j < len(content) - 1 and isinstance(content[j], str) and not isinstance(content[j + 1], str):
                    rows.append(Obj(move=size.height * 3 / 4))
            rows.append(Obj(endGroup=group_name, absElemType=abs_elem_type, startChar=-1, endChar=-1, name=name))
            rows.append(Obj(move=size.height))


def _extra_text(rows, meta_text, margin_left, spacing_, should_add_classes, get_text_size):
    _add_single_line(rows, "Book: ", meta_text.book, margin_left, 'abcjs-book', should_add_classes, get_text_size)
    _add_single_line(rows, "Source: ", meta_text.source, margin_left, 'abcjs-source', should_add_classes, get_text_size)
    _add_single_line(rows, "Discography: ", meta_text.discography, margin_left, 'abcjs-discography', should_add_classes, get_text_size)

    _add_multi_line(rows, 'Notes:', meta_text.notes, margin_left, 'historyfont', "extraText", "notes", 'abcjs-notes', "description", spacing_, should_add_classes, get_text_size)

    _add_single_line(rows, "Transcription: ", meta_text.transcription, margin_left, 'abcjs-transcription', should_add_classes, get_text_size)

    _add_multi_line(rows, "History:", meta_text.history, margin_left, 'historyfont', "extraText", "history", 'abcjs-history', "description", spacing_, should_add_classes, get_text_size)

    _add_single_line(rows, "Copyright: ", meta_text['abc-copyright'], margin_left, 'abcjs-copyright', should_add_classes, get_text_size)
    _add_single_line(rows, "Creator: ", meta_text['abc-creator'], margin_left, 'abcjs-creator', should_add_classes, get_text_size)
    _add_single_line(rows, "Edited By: ", meta_text['abc-edited-by'], margin_left, 'abcjs-edited-by', should_add_classes, get_text_size)


def _footer(rows, footer, width, padding_left, get_text_size):
    klass = 'header meta-bottom'
    font = "footerfont"
    rows.append(Obj(startGroup="footer", klass=klass))
    # Note: whether there is a footer or not doesn't change any other positioning, so this doesn't change the Y-coordinate.
    add_text_if(rows, dict(marginLeft=padding_left, text=footer.left, font=font, klass=klass, name="footer"), get_text_size)
    add_text_if(rows, dict(marginLeft=padding_left + width / 2, text=footer.center, font=font, klass=klass, anchor='middle', name="footer"), get_text_size)
    add_text_if(rows, dict(marginLeft=padding_left + width, text=footer.right, font=font, klass=klass, anchor='end', name="footer"), get_text_size)


def free_text(info, vskip, get_font_and_attr, padding_left, width, get_text_size):
    text = info.text if isinstance(info, dict) and not isinstance(info, list) else None
    rows = []
    if truthy(vskip):
        rows.append(Obj(move=vskip))
    h = get_font_and_attr.calc('textfont', 'defined-text')
    if text == "":  # we do want to print out blank lines if they have been specified.
        rows.append(Obj(move=h.attr['font-size'] * 2))  # move the distance of the line, plus the distance of the margin, which is also one line.
    elif isinstance(text, str):
        rows.append(Obj(move=h.attr['font-size'] / 2))  # TODO-PER: move down some - the y location should be the top of the text, but we output text specifying the center line.
        rows.append(Obj(left=padding_left, text=text, font='textfont', klass='defined-text', anchor="start", startChar=info.startChar, endChar=info.endChar, absElemType="freeText", name="free-text"))
        # Force blank text lines in a text block to have height
        text_for_size = re.sub(r"^[ \t]*\n", 'X\n', text, flags=re.M)
        size = get_text_size.calc(text_for_size, 'textfont', 'defined-text')  # was text
        rows.append(Obj(move=size.height))
    elif text:
        max_height = 0
        left_side = padding_left
        for t in text:
            if t.font:
                current_font = t.font
            else:
                current_font = 'textfont'
            rows.append(Obj(left=left_side, text=t.text, font=current_font, klass='defined-text', anchor='start', startChar=info.startChar, endChar=info.endChar, absElemType="freeText", name="free-text"))
            size = get_text_size.calc(t.text, get_font_and_attr.calc(current_font, 'defined-text').font, 'defined-text')
            left_side += size.width + size.height / 2  # add a little padding to the right side. The height of the font is probably a close enough approximation.
            max_height = max(max_height, size.height)
        rows.append(Obj(move=max_height))
    else:
        # The structure is wrong here: it requires an array to do centering, but it shouldn't have.
        if isinstance(info, list) and len(info) == 1:
            x = width / 2
            rows.append(Obj(left=x, text=info[0].text, font='textfont', klass='defined-text', anchor='middle', startChar=None, endChar=None, absElemType="freeText", name="free-text"))
            size = get_text_size.calc(info[0].text, 'textfont', 'defined-text')
            rows.append(Obj(move=size.height))
    return Obj(rows=rows)


def separator(space_above, line_length, space_below):
    rows = []
    if space_above:
        rows.append(Obj(move=space_above))
    rows.append(Obj(separator=line_length, absElemType="separator"))
    if space_below:
        rows.append(Obj(move=space_below))
    return Obj(rows=rows)


def subtitle(space_above, formatting, info, center, padding_left, get_text_size):
    rows = []
    if space_above:
        rows.append(Obj(move=space_above))
    t_anchor = 'start' if formatting.titleleft else 'middle'
    t_left = padding_left if formatting.titleleft else center
    rows.append(Obj(left=t_left, text=info.text, font='subtitlefont', klass='text subtitle', anchor=t_anchor, startChar=info.startChar, endChar=info.endChar, absElemType="subtitle", name="subtitle"))
    size = get_text_size.calc(info.text, 'subtitlefont', 'text subtitle')
    rows.append(Obj(move=size.height))
    return Obj(rows=rows)
