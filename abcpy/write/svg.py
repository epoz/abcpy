"""Creates the SVG elements (port of abcjs ``svg.js``)."""

import json
import re

from ..jsutil import Obj, js_str, is_nan
from .dom import Element, create_element, XLINK_NS


def _create_svg():
    svg = Element("svg")
    svg.set_attribute("xmlns:xlink", XLINK_NS)
    svg.set_attribute('role', 'img')  # for accessibility
    svg.set_attribute('fill', 'currentColor')  # for automatically picking up dark mode and high contrast
    svg.set_attribute('stroke', 'currentColor')  # for automatically picking up dark mode and high contrast
    return svg


def _construct_h_line(x1, y1, x2):
    length = x2 - x1
    return ("M " + js_str(x1) + " " + js_str(y1) +
            " l " + js_str(length) + ' ' + "0" +
            " l " + "0" + " " + "1" + " " +
            " l " + js_str(-length) + " " + "0" + " " + " z ")


def _construct_v_line(x1, y1, y2):
    length = y2 - y1
    return ("M " + js_str(x1) + " " + js_str(y1) +
            " l " + "0" + ' ' + js_str(length) +
            " l " + "1" + " " + "0" + " " +
            " l " + "0" + " " + js_str(-length) + " " + " z ")


_size_cache = {}


class Svg:
    def __init__(self, wrapper):
        self.svg = _create_svg()
        self.currentGroup = []
        self.dummySvg = None
        if wrapper is not None:
            wrapper.append_child(self.svg)

    def clear(self):
        if self.svg:
            wrapper = self.svg.parent
            self.svg = _create_svg()
            self.currentGroup = []
            if wrapper:
                wrapper.innerHTML = ""
                wrapper.append_child(self.svg)

    def set_title(self, title):
        title_el = create_element("title")
        title_el.textContent = title
        self.svg.insert_before(title_el, self.svg.firstChild)

    def set_responsive_width(self, w, h):
        self.svg.set_attribute("viewBox", "0 0 " + js_str(w) + " " + js_str(h))
        self.svg.set_attribute("preserveAspectRatio", "xMinYMin meet")
        self.svg.remove_attribute("height")
        self.svg.remove_attribute("width")
        self.svg.style['display'] = "inline-block"
        self.svg.style['position'] = "absolute"
        self.svg.style['top'] = "0"
        self.svg.style['left'] = "0"

        parent = self.svg.parent
        if parent:
            cls = parent.get_attribute("class")
            if not cls:
                parent.set_attribute("class", "abcjs-container")
            elif "abcjs-container" not in cls:
                parent.set_attribute("class", cls + " abcjs-container")
            parent.style['display'] = "inline-block"
            parent.style['position'] = "relative"
            parent.style['width'] = "100%"
            padding = h / w * 100
            parent.style['padding-bottom'] = js_str(padding) + "%"
            parent.style['vertical-align'] = "middle"
            parent.style['overflow'] = "hidden"

    def set_size(self, w, h):
        self.svg.set_attribute('width', w)
        self.svg.set_attribute('height', h)

    def set_attribute(self, attr, value):
        self.svg.set_attribute(attr, value)

    def set_scale(self, scale):
        st = self.svg.style
        if scale != 1:
            s = "scale(" + js_str(scale) + "," + js_str(scale) + ")"
            st['transform'] = s
            st['-ms-transform'] = s
            st['-webkit-transform'] = s
            st['transform-origin'] = "0 0"
            st['-ms-transform-origin-x'] = "0"
            st['-ms-transform-origin-y'] = "0"
            st['-webkit-transform-origin-x'] = "0"
            st['-webkit-transform-origin-y'] = "0"
        else:
            st['transform'] = ""
            st['-ms-transform'] = ""
            st['-webkit-transform'] = ""

    def insert_styles(self, styles):
        el = Element("style")
        el.textContent = styles
        self.svg.insert_before(el, self.svg.firstChild)

    def set_parent_styles(self, attr):
        # This is needed to get the size right when there is scaling involved.
        for key in attr:
            if self.svg.parent:
                self.svg.parent.style[key] = attr[key]
        if self.dummySvg:
            self.dummySvg = None

    def rect(self, attr):
        # This uses path instead of rect so that it can be hollow and the color changes with "fill" instead of "stroke".
        x1 = attr['x']
        y1 = attr['y']
        x2 = attr['x'] + attr['width']
        y2 = attr['y'] + attr['height']
        lines = [_construct_h_line(x1, y1, x2), _construct_h_line(x1, y2, x2),
                 _construct_v_line(x2, y1, y2), _construct_v_line(x1, y2, y1)]
        return self.path(Obj([('path', " ".join(lines)), ('stroke', "none"), ("data-name", attr.get("data-name"))]))

    def dotted_line(self, attr):
        el = Element('line')
        el.set_attribute("x1", attr['x1'])
        el.set_attribute("x2", attr['x2'])
        el.set_attribute("y1", attr['y1'])
        el.set_attribute("y2", attr['y2'])
        el.set_attribute("stroke", attr.get('stroke'))
        el.set_attribute("stroke-dasharray", "5,5")
        self.svg.insert_before(el, self.svg.firstChild)

    def rect_beneath(self, attr):
        el = Element('rect')
        el.set_attribute("x", attr['x'])
        el.set_attribute("width", attr['width'])
        el.set_attribute("y", attr['y'])
        el.set_attribute("height", attr['height'])
        for k in ('stroke', 'stroke-opacity', 'fill', 'fill-opacity'):
            if attr.get(k):
                el.set_attribute(k, attr[k])
        self.svg.insert_before(el, self.svg.firstChild)

    def text(self, text, attr, target=None, span_attr=None):
        el = Element('text')
        el.set_attribute("stroke", "none")
        for key in attr:
            el.set_attribute(key, attr[key])
        is_free_text = attr.get("data-name") == "free-text"
        lines = (text if isinstance(text, str) else js_str(text)).split("\n")
        for i in range(len(lines)):
            if is_free_text and lines[i] == "":
                # Don't draw empty lines
                continue

            line = Element('tspan')
            if span_attr:
                for skey in span_attr:
                    line.set_attribute(skey, span_attr[skey])
            line.set_attribute("x", attr.get('x') if attr.get('x') else 0)
            if i != 0:
                line.set_attribute("dy", "1.2em")
            if "\x03" in lines[i]:
                parts = lines[i].split('\x03')
                line.textContent = parts[0]
                if len(parts) > 1 and parts[1]:
                    ts2 = Element('tspan')
                    ts2.set_attribute("dy", "-0.3em")
                    ts2.set_attribute("style", "font-size:0.7em")
                    ts2.textContent = parts[1]
                    line.append_child(ts2)
                if len(parts) > 2 and parts[2]:
                    dist = "0.4em" if (len(parts) > 1 and parts[1]) else "0.1em"
                    ts3 = Element('tspan')
                    ts3.set_attribute("dy", dist)
                    ts3.set_attribute("style", "font-size:0.7em")
                    ts3.textContent = parts[2]
                    line.append_child(ts3)
            else:
                # For improved block text
                if is_free_text:
                    # Fixes issue where blank lines in text blocks didn't take up any vertical
                    if lines[i].strip() == "":
                        line.innerHTML = "&nbsp;"
                    else:
                        line.textContent = lines[i]
                else:
                    line.textContent = lines[i]
            el.append_child(line)
        if target:
            target.append_child(el)
        else:
            self.append(el)
        return el

    def rich_text_line(self, phrases, x, y, klass, anchor, target=None):
        el = Element('text')
        el.set_attribute("stroke", "none")
        el.set_attribute("class", klass)
        el.set_attribute("x", x)
        el.set_attribute("y", y)
        el.set_attribute("text-anchor", anchor)
        el.set_attribute("dominant-baseline", "middle")

        for phrase in phrases:
            tspan = Element('tspan')
            attrs = phrase.get('attrs') or {}
            for k in attrs:
                value = attrs[k]
                if value != '':
                    tspan.set_attribute(k, value)
            tspan.textContent = phrase.get('content') if isinstance(phrase.get('content'), str) else js_str(phrase.get('content'))
            el.append_child(tspan)

        if target:
            target.append_child(el)
        else:
            self.append(el)
        return el

    def guess_width(self, text, attr):
        svg = self.create_dummy_svg()
        el = self.text(text, attr, svg)
        size = el.get_bbox()
        if is_nan(size.height) or not size.height:
            fs = attr.get('font-size')
            size = Obj(width=fs / 2, height=fs + 2)  # Just a wild guess.
        else:
            size = Obj(width=size.width, height=size.height)
        svg.remove_child(el)
        return size

    def create_dummy_svg(self):
        if not self.dummySvg:
            self.dummySvg = _create_svg()
        return self.dummySvg

    def get_text_size(self, text, attr, el=None):
        if isinstance(text, (int, float)) and not isinstance(text, bool):
            text = js_str(text)
        if not text or re.match(r"^\s+$", text):
            return Obj(width=0, height=0)
        key = None
        if len(text) < 20:
            # The short text tends to be repetitive, so lets cache.
            key = text + json.dumps(attr, ensure_ascii=False, default=lambda o: None)
            if key in _size_cache:
                return _size_cache[key]
        remove_later = el is None
        if el is None:
            el = self.text(text, attr)
        size = el.get_bbox()
        if is_nan(size.height) or not size.height:
            size = self.guess_width(text, attr)
        else:
            size = Obj(width=size.width, height=size.height)
        if remove_later:
            if len(self.currentGroup) > 0:
                self.currentGroup[0].remove_child(el)
            else:
                self.svg.remove_child(el)
        if key:
            _size_cache[key] = size
        return size

    def open_group(self, options=None):
        options = options or {}
        el = Element("g")
        if options.get('klass'):
            el.set_attribute("class", options['klass'])
        if options.get('fill'):
            el.set_attribute("fill", options['fill'])
        if options.get('stroke'):
            el.set_attribute("stroke", options['stroke'])
        if options.get('data-name'):
            el.set_attribute("data-name", options['data-name'])

        if options.get('prepend'):
            self.prepend(el)
        else:
            self.append(el)
        self.currentGroup.insert(0, el)
        return el

    def close_group(self):
        g = self.currentGroup.pop(0) if self.currentGroup else None
        if g and len(g.children) == 0:
            # If nothing was added to the group it is because all the elements were invisible. We don't need the group, then.
            g.parent.remove_child(g)
            return None
        return g

    def path(self, attr):
        el = Element("path")
        for key in attr:
            if key == 'path':
                el.set_attribute('d', attr['path'])
            elif key == 'klass':
                el.set_attribute("class", attr[key])
            elif attr[key] is not None:
                el.set_attribute(key, attr[key])
        self.append(el)
        return el

    def path_to_back(self, attr):
        el = Element("path")
        for key in attr:
            if key == 'path':
                el.set_attribute('d', attr['path'])
            elif key == 'klass':
                el.set_attribute("class", attr[key])
            else:
                el.set_attribute(key, attr[key])
        self.prepend(el)
        return el

    def line_to_back(self, attr):
        el = Element('line')
        for k in attr:
            el.set_attribute(k, attr[k])
        self.prepend(el)
        return el

    def append(self, el):
        if len(self.currentGroup) > 0:
            self.currentGroup[0].append_child(el)
        else:
            self.svg.append_child(el)

    def prepend(self, el):
        # The entire group is prepended, so don't prepend the individual elements.
        if len(self.currentGroup) > 0:
            self.currentGroup[0].append_child(el)
        else:
            self.svg.insert_before(el, self.svg.firstChild)

    def set_attribute_on_element(self, el, attr):
        for key in attr:
            el.set_attribute(key, attr[key])

    def move_element_to_child(self, parent, child):
        parent.append_child(child)
