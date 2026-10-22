// Reference dumper: parses abc with abcjs and prints JSON like abcpy's Tune.to_json().
console.log = function () { process.stderr.write(Array.prototype.join.call(arguments, ' ') + '\n'); };
// usage: node parse_dump.js <abcjs-root> <input.json>   (input: [{abc, params}])
const path = require('path');
const root = process.argv[2];
const tunebook = require(path.join(root, 'src/api/abc_tunebook'));
const input = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
function strip(key, value) {
	if (key === 'abselem') return undefined;
	if (typeof value === 'function') return undefined;
	return value;
}
const out = input.map(function (item) {
	try {
		const tunes = tunebook.parseOnly(item.abc, item.params || {});
		return tunes.map(function (t) {
			const o = { formatting: t.formatting, lines: t.lines, media: t.media, metaText: t.metaText, metaTextInfo: t.metaTextInfo, version: t.version };
			if (t.lineBreaks) o.lineBreaks = t.lineBreaks;
			if (t.visualTranspose) o.visualTranspose = t.visualTranspose;
			if (t.chordGrid) o.chordGrid = t.chordGrid;
			if (t.warnings) o.warnings = t.warnings;
			return JSON.parse(JSON.stringify(o, strip));
		});
	} catch (e) {
		return { error: String(e) };
	}
});
process.stdout.write(JSON.stringify(out));
