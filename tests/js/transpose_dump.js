// usage: node transpose_dump.js <abcjs-root> <input.json>  (input: [{abc, steps}])
console.log = function () { process.stderr.write(Array.prototype.join.call(arguments, ' ') + '\n'); };
const path = require('path');
const root = process.argv[2];
const tunebook = require(path.join(root, 'src/api/abc_tunebook'));
const strTranspose = require(path.join(root, 'src/str/output'));
const input = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const out = input.map(function (item) {
	try {
		const tunes = tunebook.parseOnly(item.abc);
		return strTranspose(item.abc, tunes, item.steps);
	} catch (e) {
		return { error: String(e) };
	}
});
process.stdout.write(JSON.stringify(out));
