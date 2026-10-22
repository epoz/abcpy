// Collects the abc strings that the abcjs test-suite feeds to abcjs, by running the test files
// against a recording stub of the abcjs API.  usage: node collect_abc.js <abcjs-root> > corpus.json
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = process.argv[2];
const found = [];
const seen = new Set();
function record(args) {
	for (let i = 0; i < args.length; i++) {
		const a = args[i];
		if (typeof a === 'string' && (a.indexOf('\n') >= 0 || a.indexOf('K:') >= 0) && a.length > 3) {
			let params = args[i + 1];
			try { params = params && typeof params === 'object' ? JSON.parse(JSON.stringify(params)) : undefined; } catch (e) { params = undefined; }
			const key = a + JSON.stringify(params || {});
			if (!seen.has(key)) { seen.add(key); found.push({ abc: a, params: params || {} }); }
		}
	}
}
function makeStub() {
	const fn = function () { record(arguments); return makeStub(); };
	return new Proxy(fn, {
		get: function (target, prop) {
			if (prop === Symbol.toPrimitive) return function () { return 0; };
			if (prop === 'length') return 0;
			if (prop === Symbol.iterator) return function* () {};
			if (prop === 'then') return undefined;
			return makeStub();
		},
		construct: function (target, args) { record(args); return makeStub(); },
		apply: function (target, thisArg, args) { record(args); return makeStub(); },
	});
}
const files = [];
function walk(d) { fs.readdirSync(d).forEach(f => { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p); else if (f.endsWith('.test.js') || f === 'helpers.js') files.push(p); }); }
walk(path.join(root, 'tests'));
const helpers = files.filter(f => f.endsWith('helpers.js'));
const tests = files.filter(f => !f.endsWith('helpers.js'));
tests.forEach(function (file) {
	const ctx = {
		abcjs: makeStub(), chai: makeStub(), document: makeStub(), window: makeStub(), console: { log: function () {}, error: function () {}, warn: function () {} },
		describe: function (n, f) { try { f.call(ctx); } catch (e) {} },
		it: function (n, f) { try { const r = f.call(ctx, function () {}); if (r && r.catch) r.catch(function () {}); } catch (e) {} },
		before: function () {}, after: function () {}, beforeEach: function () {}, afterEach: function () {},
		setTimeout: function () {}, Promise: Promise, JSON: JSON, Math: Math, Object: Object, Array: Array, String: String, Number: Number, parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN,
		XMLSerializer: makeStub(), Audio: makeStub(), AudioContext: makeStub(),
	};
	ctx.self = ctx;
	vm.createContext(ctx);
	helpers.forEach(h => { try { vm.runInContext(fs.readFileSync(h, 'utf8'), ctx, { filename: h }); } catch (e) {} });
	try { vm.runInContext(fs.readFileSync(file, 'utf8'), ctx, { filename: file }); } catch (e) { }
});
process.stdout.write(JSON.stringify(found, null, 1));
