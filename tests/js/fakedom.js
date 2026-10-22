// A minimal DOM for running the abcjs engraver in node. It mirrors abcpy/write/dom.py exactly
// (same serialization and the same font-metric based getBBox) so the outputs can be compared.
const metrics = require('./font_metrics.json');

function jsCssName(name) {
	if (name.startsWith('-')) return name;
	return name.replace(/[A-Z]/g, function (m) { return '-' + m.toLowerCase(); });
}

function makeStyle(el) {
	function props() {
		var text = el.attrs.style || '';
		var out = [];
		text.split(';').forEach(function (part) {
			var i = part.indexOf(':');
			if (i >= 0) out.push([part.substring(0, i).trim(), part.substring(i + 1).trim()]);
		});
		return out;
	}
	return new Proxy({}, {
		get: function (t, name) {
			if (typeof name !== 'string') return undefined;
			name = jsCssName(name);
			var p = props();
			for (var i = 0; i < p.length; i++) if (p[i][0] === name) return p[i][1];
			return '';
		},
		set: function (t, name, value) {
			name = jsCssName(name);
			value = '' + value;
			var p = props();
			var found = false;
			for (var i = 0; i < p.length; i++) {
				if (p[i][0] === name) {
					found = true;
					if (value === '') p.splice(i, 1); else p[i][1] = value;
					break;
				}
			}
			if (!found && value !== '') p.push([name, value]);
			if (p.length) el.attrs.style = p.map(function (kv) { return kv[0] + ': ' + kv[1] + ';'; }).join(' ');
			else delete el.attrs.style;
			return true;
		}
	});
}

function TextNode(text) { this.text = text; this.parentNode = null; this.nodeType = 3; }
TextNode.prototype.toString2 = function () { return escText(this.text); };

function Element(tag) {
	this.tag = tag;
	this.tagName = tag;
	this.attrs = {};
	this.childNodes = [];
	this.parentNode = null;
	this.nodeType = 1;
	this.style = makeStyle(this);
}
Object.defineProperty(Element.prototype, 'parentElement', { get: function () { return this.parentNode; } });
Object.defineProperty(Element.prototype, 'children', { get: function () { return this.childNodes.filter(function (c) { return c instanceof Element; }); } });
Object.defineProperty(Element.prototype, 'firstChild', { get: function () { return this.childNodes.length ? this.childNodes[0] : null; } });
Object.defineProperty(Element.prototype, 'classList', { get: function () { return (this.attrs['class'] || '').split(/\s+/).filter(function (x) { return x; }); } });
Object.defineProperty(Element.prototype, 'className', { get: function () { return { baseVal: this.attrs['class'] || '' }; } });
Object.defineProperty(Element.prototype, 'attributes', { get: function () {
	var self = this; var arr = Object.keys(this.attrs).map(function (k) { return { name: k, value: self.attrs[k], nodeValue: self.attrs[k] }; });
	Object.keys(this.attrs).forEach(function (k, i) { arr[k] = arr[i]; });
	return arr;
} });
Element.prototype.setAttribute = function (name, value) { this.attrs[name] = '' + value; };
Element.prototype.setAttributeNS = function (ns, name, value) { this.setAttribute(name, value); };
Element.prototype.getAttribute = function (name) { return this.attrs.hasOwnProperty(name) ? this.attrs[name] : null; };
Element.prototype.removeAttribute = function (name) { delete this.attrs[name]; };
Element.prototype.addEventListener = function () {};
Element.prototype.removeEventListener = function () {};
Element.prototype.appendChild = function (child) {
	if (child.parentNode) child.parentNode.removeChild(child);
	child.parentNode = this; this.childNodes.push(child); return child;
};
Element.prototype.insertBefore = function (child, ref) {
	if (child.parentNode) child.parentNode.removeChild(child);
	child.parentNode = this;
	var i = ref ? this.childNodes.indexOf(ref) : -1;
	if (i < 0) this.childNodes.push(child); else this.childNodes.splice(i, 0, child);
	return child;
};
Element.prototype.removeChild = function (child) {
	var i = this.childNodes.indexOf(child);
	if (i >= 0) { this.childNodes.splice(i, 1); child.parentNode = null; }
	return child;
};
Object.defineProperty(Element.prototype, 'textContent', {
	get: function () { return this.childNodes.map(function (c) { return c instanceof TextNode ? c.text : c.textContent; }).join(''); },
	set: function (v) {
		this.childNodes.forEach(function (c) { c.parentNode = null; });
		this.childNodes = [];
		v = '' + v;
		if (v !== '') { var t = new TextNode(v); t.parentNode = this; this.childNodes.push(t); }
	}
});
Object.defineProperty(Element.prototype, 'innerText', { set: function (v) { this.textContent = v; } });
Object.defineProperty(Element.prototype, 'innerHTML', {
	get: function () { return this.childNodes.map(function (c) { return c.toString2(); }).join(''); },
	set: function (v) {
		if (v === '&nbsp;') { this.textContent = '\xa0'; return; }
		this.textContent = '';
		var m = /^<(\w+)(?: class="([^"]*)")?><\/\1>$/.exec(v || '');
		if (m) { var el = new Element(m[1]); if (m[2] !== undefined) el.setAttribute('class', m[2]); this.appendChild(el); }
		else if (v) this.textContent = v;
	}
});
Element.prototype.cloneNode = function (deep) {
	var el = new Element(this.tag);
	el.attrs = Object.assign({}, this.attrs);
	if (deep) this.childNodes.forEach(function (c) { el.appendChild(c instanceof TextNode ? new TextNode(c.text) : c.cloneNode(true)); });
	return el;
};
Element.prototype.querySelectorAll = function (selector) {
	var parts = selector.split('>').map(function (p) { return p.trim(); });
	var results = [];
	function walk(el) {
		el.children.forEach(function (c) {
			if (c.tag === parts[parts.length - 1]) {
				var ok = true; var p = c.parentNode;
				for (var i = parts.length - 2; i >= 0; i--) { if (!p || p.tag !== parts[i]) { ok = false; break; } p = p.parentNode; }
				if (ok) results.push(c);
			}
			walk(c);
		});
	}
	walk(this);
	return results;
};
Element.prototype.querySelector = function (selector) { var r = this.querySelectorAll(selector); return r.length ? r[0] : null; };
Element.prototype.toString2 = function (xmlns) {
	var attrs = '';
	if (xmlns && this.tag === 'svg' && !this.attrs.hasOwnProperty('xmlns')) attrs += ' xmlns="http://www.w3.org/2000/svg"';
	for (var k in this.attrs) attrs += ' ' + k + '="' + escAttr(this.attrs[k]) + '"';
	return '<' + this.tag + attrs + '>' + this.childNodes.map(function (c) { return c.toString2(); }).join('') + '</' + this.tag + '>';
};
Element.prototype.getBBox = function () {
	var b = bbox(this);
	if (!b) return { x: 0, y: 0, width: 0, height: 0 };
	return { x: b[0], y: b[1], width: b[2] - b[0], height: b[3] - b[1] };
};
Element.prototype.closest = function (tag) { var e = this; while (e && e.tag !== tag) e = e.parentNode; return e; };

function escText(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ---- text metrics (same as abcpy/write/text_metrics.py) ----
function fontKey(family, weight, style) {
	var fam = (family || '').toLowerCase();
	var base;
	if (fam.indexOf('mono') >= 0 || fam.indexOf('courier') >= 0) base = 'mono';
	else if (fam.indexOf('sans') >= 0) base = 'sans';
	else if (fam.indexOf('times') >= 0 || fam.indexOf('serif') >= 0 || fam.indexOf('georgia') >= 0 || fam.indexOf('palatino') >= 0 || fam.indexOf('bookman') >= 0 || fam.indexOf('century') >= 0 || fam.indexOf('garamond') >= 0 || fam.indexOf('chancery') >= 0 || fam.indexOf('cursive') >= 0) base = 'serif';
	else base = 'sans';
	var w = ('' + (weight || '')).toLowerCase();
	var bold = w === 'bold' || w === 'bolder' || (/^\d+$/.test(w) && parseInt(w, 10) >= 600);
	var s = ('' + (style || '')).toLowerCase();
	var italic = s === 'italic' || s === 'oblique';
	if (bold && italic) return base + '-bolditalic';
	if (bold) return base + '-bold';
	if (italic) return base + '-italic';
	return base + '-normal';
}
function charWidth(widths, ch) {
	var cp = ch.codePointAt(0);
	var w = widths[cp];
	if (w !== undefined) return w;
	if (cp < 0x20 || (cp >= 0x200B && cp <= 0x200F) || (cp >= 0x0300 && cp <= 0x036F) || cp === 0xFEFF) return 0;
	if ((cp >= 0x1100 && cp <= 0x115F) || (cp >= 0x2E80 && cp <= 0xA4CF) || (cp >= 0xAC00 && cp <= 0xD7A3) || (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0xFE30 && cp <= 0xFE4F) || (cp >= 0xFF00 && cp <= 0xFF60) || (cp >= 0xFFE0 && cp <= 0xFFE6) || (cp >= 0x1F300 && cp <= 0x1FAFF) || (cp >= 0x20000 && cp <= 0x3FFFD)) return 1000;
	var n = widths[110];
	return n !== undefined ? n : 556;
}
function textWidth(text, size, family, weight, style) {
	var m = metrics[fontKey(family, weight, style)];
	var total = 0;
	for (var ch of text) total += charWidth(m.widths, ch);
	return total * size / 1000;
}
function lineHeight(size, family, weight, style) { var m = metrics[fontKey(family, weight, style)]; return (m.ascent + m.descent) * size / 1000; }
function ascent(size, family, weight, style) { var m = metrics[fontKey(family, weight, style)]; return m.ascent * size / 1000; }
function parseNum(v, def) {
	if (v === undefined || v === null) return def;
	var x = parseFloat(v); return isNaN(x) ? def : x;
}
function inherited(el, name) { while (el) { if (el.attrs && el.attrs.hasOwnProperty(name)) return el.attrs[name]; el = el.parentNode; } return undefined; }
function textRuns(tspan, size) {
	var runs = [];
	tspan.childNodes.forEach(function (c) {
		if (c instanceof TextNode) runs.push([c.text, size]);
		else {
			var st = c.attrs.style || '';
			var m = /font-size:\s*([\d.]+)em/.exec(st);
			var sub = m ? size * parseFloat(m[1]) : size;
			textRuns(c, sub).forEach(function (r) { runs.push(r); });
		}
	});
	return runs;
}
function textBBox(el) {
	var size = parseNum(inherited(el, 'font-size'), 16);
	var family = inherited(el, 'font-family'), weight = inherited(el, 'font-weight'), style = inherited(el, 'font-style');
	var anchor = inherited(el, 'text-anchor') || 'start';
	var baseline = el.attrs['dominant-baseline'];
	var x0 = parseNum(el.attrs.x, 0), y0 = parseNum(el.attrs.y, 0);
	var lines = el.childNodes.filter(function (c) { return c instanceof Element && c.tag === 'tspan'; });
	var linesText, xs;
	if (!lines.length) {
		var text = el.textContent;
		if (text === '') return null;
		linesText = [[[text, size]]]; xs = [x0];
	} else {
		linesText = lines.map(function (t) { return textRuns(t, size); });
		xs = lines.map(function (t) { return parseNum(t.attrs.x, x0); });
	}
	var widths = linesText.map(function (runs) { var w = 0; runs.forEach(function (r) { w += textWidth(r[0], r[1], family, weight, style); }); return w; });
	var allZero = widths.every(function (w) { return w === 0; });
	var allBlank = linesText.every(function (runs) { return runs.map(function (r) { return r[0]; }).join('').trim() === ''; });
	if (allZero && allBlank) return null;
	var height = lineHeight(size, family, weight, style) + (linesText.length - 1) * 1.2 * size;
	var left = null, right = null;
	for (var i = 0; i < xs.length; i++) {
		var x = xs[i], w = widths[i], lx;
		if (anchor === 'middle') lx = x - w / 2; else if (anchor === 'end') lx = x - w; else lx = x;
		left = left === null ? lx : Math.min(left, lx);
		right = right === null ? lx + w : Math.max(right, lx + w);
	}
	var top = baseline === 'middle' ? y0 - lineHeight(size, family, weight, style) / 2 : y0 - ascent(size, family, weight, style);
	return [left, top, right, top + height];
}
var argCounts = { M: 2, L: 2, H: 1, V: 1, C: 6, S: 4, Q: 4, T: 2, A: 7, Z: 0 };
function pathBBox(d) {
	var tokens = (d || '').match(/[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?/g) || [];
	var xs = [], ys = [], cx = 0, cy = 0, sx = 0, sy = 0, i = 0, cmd = null;
	while (i < tokens.length) {
		var t = tokens[i];
		if (/^[A-Za-z]$/.test(t)) { cmd = t; i++; if (cmd === 'Z' || cmd === 'z') { cx = sx; cy = sy; continue; } }
		if (cmd === null) { i++; continue; }
		var n = argCounts[cmd.toUpperCase()];
		var args = [];
		while (args.length < n && i < tokens.length && !/^[A-Za-z]$/.test(tokens[i])) { args.push(parseFloat(tokens[i])); i++; }
		if (args.length < n) break;
		var rel = cmd === cmd.toLowerCase();
		var c = cmd.toUpperCase();
		var pts;
		if (c === 'H') { cx = rel ? cx + args[0] : args[0]; pts = [[cx, cy]]; }
		else if (c === 'V') { cy = rel ? cy + args[0] : args[0]; pts = [[cx, cy]]; }
		else if (c === 'A') {
			var ex = rel ? cx + args[5] : args[5], ey = rel ? cy + args[6] : args[6];
			pts = [[cx, cy], [ex, ey]];
			var r = Math.max(Math.abs(args[0]), Math.abs(args[1]));
			var mx = (cx + ex) / 2, my = (cy + ey) / 2;
			pts.push([mx - r, my - r]); pts.push([mx + r, my + r]);
			cx = ex; cy = ey;
		} else {
			pts = [];
			for (var k = 0; k < n; k += 2) pts.push([rel ? cx + args[k] : args[k], rel ? cy + args[k + 1] : args[k + 1]]);
			cx = pts[pts.length - 1][0]; cy = pts[pts.length - 1][1];
		}
		if (c === 'M') { sx = cx; sy = cy; cmd = rel ? 'l' : 'L'; }
		pts.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); });
	}
	if (!xs.length) return null;
	return [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs), Math.max.apply(null, ys)];
}
function bbox(el) {
	if (!(el instanceof Element)) return null;
	var tag = el.tag;
	if (tag === 'text') return textBBox(el);
	if (tag === 'path') return pathBBox(el.attrs.d);
	if (tag === 'line') { var x1 = parseNum(el.attrs.x1, 0), x2 = parseNum(el.attrs.x2, 0), y1 = parseNum(el.attrs.y1, 0), y2 = parseNum(el.attrs.y2, 0); return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]; }
	if (tag === 'rect') { var x = parseNum(el.attrs.x, 0), y = parseNum(el.attrs.y, 0); return [x, y, x + parseNum(el.attrs.width, 0), y + parseNum(el.attrs.height, 0)]; }
	if (tag === 'title' || tag === 'style' || tag === 'desc' || tag === 'defs') return null;
	var box = null;
	el.children.forEach(function (c) {
		var b = bbox(c);
		if (!b) return;
		if (!box) box = b.slice(); else box = [Math.min(box[0], b[0]), Math.min(box[1], b[1]), Math.max(box[2], b[2]), Math.max(box[3], b[3])];
	});
	return box;
}

var body = new Element('body');
global.document = {
	createElementNS: function (ns, tag) { return new Element(tag); },
	createElement: function (tag) { return new Element(tag); },
	createTextNode: function (t) { return new TextNode(t); },
	querySelector: function (s) { return s === 'body' ? body : body.querySelector(s); },
	getElementById: function () { return null; },
	body: body,
};
global.window = { addEventListener: function () {}, console: console, innerWidth: 1024 };
try { global.navigator = { userAgent: 'node' }; } catch (e) { Object.defineProperty(global, 'navigator', { value: { userAgent: 'node' }, configurable: true }); }
module.exports = { Element: Element };
