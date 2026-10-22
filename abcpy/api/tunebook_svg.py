"""Rendering abc to SVG (port of ``abc_tunebook_svg.js``).

abcjs draws into DOM elements in the browser.  abcpy draws into the small DOM of
:mod:`abcpy.write.dom`; use :func:`render_svg` to get the SVG markup as
strings, or :func:`write_svg` to save it to files.
"""

from ..jsutil import Obj, obj_copy
from .tunebook import render_engine
from ..parse.parse import Parse
from ..parse import wrap_lines
from ..write.engraver_controller import EngraverController
from ..write.dom import Element


def _render_one(div, tune, params, tune_number, line_offset):
    if params.viewportHorizontal:
        # Create an inner div that holds the music, so that the passed in div will be the viewport.
        div.innerHTML = '<div class="abcjs-inner"></div>'
        if params.scrollHorizontal:
            div.style.overflowX = "auto"
            div.style.overflowY = "hidden"
        else:
            div.style.overflow = "hidden"
        div = div.children[0]  # The music should be rendered in the inner div.
    elif params.viewportVertical:
        div.innerHTML = '<div class="abcjs-inner scroll-amount"></div>'
        div.style.overflowX = "hidden"
        div.style.overflowY = "auto"
        div = div.children[0]
    else:
        div.innerHTML = ""
    engraver_controller = EngraverController(div, params)
    engraver_controller.engrave_abc(tune, tune_number, line_offset)
    tune.engraver = engraver_controller
    if params.viewportVertical or params.viewportHorizontal:
        # If we added a wrapper around the div, then we need to size the wrapper, too.
        parent = div.parent
        parent.style.width = div.style.width


def _do_line_wrapping(div, tune, tune_number, abc_string, params):
    engraver_controller = EngraverController(div, params)
    widths = engraver_controller.get_measure_widths(tune)

    ret = wrap_lines.calc_line_wraps(tune, widths, params)
    if ret.reParse:
        abc_parser = Parse()
        abc_parser.parse(abc_string, ret.revisedParams)
        tune = abc_parser.get_tune()
        warnings = abc_parser.get_warnings()
        if warnings:
            tune.warnings = warnings
    if params.afterParsing:
        params.afterParsing(tune, tune_number, abc_string)
    _render_one(div, tune, Obj(ret.revisedParams), tune_number, 0)
    tune.explanation = ret.explanation
    return tune


def render_abc(output, abc, parser_params=None, engraver_params=None, render_params=None):
    """Parse and engrave ``abc``.

    ``output`` is a :class:`abcpy.write.dom.Element` (or a list of them, one per
    tune) that receives the ``<svg>``; pass ``"*"`` (or a list of ``"*"``) to
    render without keeping a container.  The parameters are the same as for
    abcjs's ``renderAbc``.  Returns the list of tunes; each tune has an
    ``engraver`` attribute whose ``svgs`` list holds the generated SVG elements.
    """
    params = Obj()
    parser_params = obj_copy(parser_params)
    engraver_params = obj_copy(engraver_params)
    render_params = obj_copy(render_params)
    if parser_params:
        for key in parser_params:
            params[key] = parser_params[key]
    if engraver_params:
        for key in engraver_params:
            # There is a conflict with the name of the parameter "listener". If it is in the second parameter, then it is for click.
            if key == "listener":
                if engraver_params[key].get('highlight'):
                    params.clickListener = engraver_params[key]['highlight']
            else:
                params[key] = engraver_params[key]
    if render_params:
        for key in render_params:
            params[key] = render_params[key]

    def callback(div, tune, tune_number, abc_string):
        remove_div = False
        if div == "*":
            remove_div = True
            div = Element("div")
            div.set_attribute("style", "visibility: hidden;")
        if not remove_div and params.wrap and params.staffwidth:
            tune = _do_line_wrapping(div, tune, tune_number, abc_string, params)
            return tune
        if params.afterParsing:
            params.afterParsing(tune, tune_number, abc_string)
        _render_one(div, tune, params, tune_number, 0)
        return None

    return render_engine(callback, output, abc, params)


def render_svg(abc, params=None, xmlns=True):
    """Render every tune in ``abc`` and return a list with one SVG document (a string) per tune.

    With ``oneSvgPerLine`` in ``params`` the list contains a list of SVG strings for each tune.
    """
    from .tunebook import number_of_tunes
    params = dict(params or {})
    n = number_of_tunes(abc)
    divs = [Element("div") for _ in range(n)]
    tunes = render_abc(divs, abc, params)
    result = []
    for tune in tunes:
        svgs = tune.engraver.svgs if tune.engraver else []
        strings = [_svg_document(s, xmlns) for s in svgs]
        if params.get('oneSvgPerLine'):
            result.append(strings)
        else:
            result.append(strings[0] if strings else None)
    return result


def _svg_document(svg, xmlns):
    return svg.to_string(xmlns=xmlns)


def write_svg(abc, path, params=None, tune_index=None):
    """Render ``abc`` and save the SVG to ``path``.

    If the abc contains several tunes and ``tune_index`` is not given, ``path``
    may contain ``{index}`` (or ``{n}``) which is replaced by the tune number;
    otherwise only the first tune is written.  With ``oneSvgPerLine`` the line
    number replaces ``{line}``.  Returns the list of files written.
    """
    svgs = render_svg(abc, params)
    written = []
    indexes = [tune_index] if tune_index is not None else range(len(svgs))
    if tune_index is None and "{index}" not in path and "{n}" not in path:
        indexes = [0]
    for i in indexes:
        doc = svgs[i]
        docs = doc if isinstance(doc, list) else [doc]
        for line_num, d in enumerate(docs):
            p = path.replace("{index}", str(i)).replace("{n}", str(i)).replace("{line}", str(line_num))
            if isinstance(doc, list) and "{line}" not in path and len(docs) > 1:
                base, dot, ext = p.rpartition(".")
                p = "%s-%d.%s" % (base, line_num, ext) if dot else "%s-%d" % (p, line_num)
            with open(p, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(d)
            written.append(p)
    return written


def tune_metrics(abc, params=None):
    """Return the measure widths of each tune: ``[{'sections': [{'left', 'measureWidths', 'total'}, ...]}]``."""
    from .tunebook import number_of_tunes
    params = obj_copy(params) if params else Obj()

    def callback(div, tune, tune_number, abc_string):
        div = Element("div")
        div.set_attribute("style", "visibility: hidden;")
        engraver_controller = EngraverController(div, params)
        widths = engraver_controller.get_measure_widths(tune)
        return Obj(sections=widths)

    return render_engine(callback, "*", abc, params)
