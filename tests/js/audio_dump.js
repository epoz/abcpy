// usage: node audio_dump.js <abcjs-root> <input.json>  (input: [{abc, params}])
console.log = function () { process.stderr.write(Array.prototype.join.call(arguments, ' ') + '\n'); };
const path = require('path');
const root = process.argv[2];
const tunebook = require(path.join(root, 'src/api/abc_tunebook'));
const getMidiFile = require(path.join(root, 'src/synth/get-midi-file'));
const input = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const out = input.map(function (item) {
	const r = {};
	try {
		const tunes = tunebook.parseOnly(item.abc, item.params || {});
		const audio = tunes[0].setUpAudio(item.params || {});
		r.audio = JSON.parse(JSON.stringify(audio, function (k, v) { return k === 'elem' ? undefined : v; }));
	} catch (e) { r.audio = { error: String(e) }; }
	try {
		r.midi = getMidiFile(item.abc, Object.assign({}, item.params || {}, { midiOutputType: 'encoded' }))[0];
	} catch (e) { r.midi = { error: String(e) }; }
	return r;
});
process.stdout.write(JSON.stringify(out));
