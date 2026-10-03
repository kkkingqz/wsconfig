import {acceptSnapshot} from '../../gnome/extensions/workstation-widgets@local/lib/protocol.mjs';
import {createState} from '../../widgets/quickshell/framework/model.mjs';
function assert(v) { if (!v) throw new Error('protocol validation'); }
export const tests = {
    order: () => { const a = createState([], 'one', 42); a.revision = 9; assert(acceptSnapshot(a, {...a, revision: 8}) === null); assert(acceptSnapshot(a, {...a, instanceId: 'two', revision: 0}) !== null); },
    malformed: () => { for (const s of [null, {}, {protocolVersion: 2}, {...createState([], 'one', 42), revision: -1}, {...createState([], 'one', 42), widgets: {bad: {phase: 'oops'}}}]) assert(acceptSnapshot(null, s) === null); },
};
