// usage: node svg_dump.js <abcjs-root> <input.json>   (input: [{abc, params}]) -> [[svg strings per tune] | {error}]
console.log = function () { process.stderr.write(Array.prototype.join.call(arguments, ' ') + '\n'); };
console.error = console.log;
const fakedom = require('./fakedom');
const path = require('path');
const root = process.argv[2];
const renderAbc = require(path.join(root, 'src/api/abc_tunebook_svg'));
const tunebook = require(path.join(root, 'src/api/abc_tunebook'));
const input = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
function collect(div) {
	return div.querySelectorAll('svg').map(function (s) { return s.toString2(true); });
}
const out = input.map(function (item) {
	try {
		const n = tunebook.numberOfTunes(item.abc);
		const divs = [];
		for (var i = 0; i < n; i++) divs.push(new fakedom.Element('div'));
		renderAbc(divs, item.abc, Object.assign({}, item.params || {}));
		return divs.map(collect);
	} catch (e) {
		return { error: String(e) + (e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : '') };
	}
});
process.stdout.write(JSON.stringify(out));
