// usage: node timing_dump.js <abcjs-root> <input.json> -> per item: [timings of first tune] (render then setTiming)
console.log = function () { process.stderr.write(Array.prototype.join.call(arguments, ' ') + '\n'); };
console.error = console.log;
const fakedom = require('./fakedom');
const path = require('path');
const root = process.argv[2];
const renderAbc = require(path.join(root, 'src/api/abc_tunebook_svg'));
const input = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const out = input.map(function (item) {
	try {
		const div = new fakedom.Element('div');
		const tunes = renderAbc(div, item.abc, Object.assign({}, item.params || {}));
		const t = tunes[0];
		const timings = t.setTiming();
		return JSON.parse(JSON.stringify(timings, function (k, v) { return k === 'elements' ? (v ? v.length : v) : v; }));
	} catch (e) {
		return { error: String(e) };
	}
});
process.stdout.write(JSON.stringify(out));
