import System from 'system';

export function assert(condition, message = 'assertion failed') {
    if (!condition) throw new Error(message);
}
export function rejects(fn) {
    let failed = false;
    try { fn(); } catch (_) { failed = true; }
    assert(failed, 'invalid input accepted');
}
let count = 0;
const suites = ARGV.length ? ARGV : ['manifest', 'model', 'geometry', 'protocol', 'ipc-client', 'dismissal'];
for (const suite of suites) {
    const module = await import(`./test-${suite}.js`);
    for (const [name, test] of Object.entries(module.tests)) {
        try { await test(); print(`PASS ${suite}: ${name}`); count++; }
        catch (error) { printerr(`FAIL ${suite}: ${name}: ${error.stack}`); System.exit(1); }
    }
}
print(`${count} tests passed`);
