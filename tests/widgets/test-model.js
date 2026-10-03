import {createState, reduce} from '../../widgets/quickshell/framework/model.mjs';
const entries = [{id: 'example', enabled: true, width: 420, height: 580}, {id: 'compact', enabled: true, width: 320, height: 240}];
function assert(v, m = 'assertion failed') { if (!v) throw new Error(m); }
function initial() { return createState(entries, 'one', 42); }
function event(s, type, args = {}, time = 0) { return reduce(s, {type, ...args}, time); }
function show(s, id = 'example') { return event(s, 'COMMAND', {action: 'show', id}).state; }
function placed(s) { return event(s, 'PLACED', {id: 'example', requestId: s.widgets.example.requestId}).state; }
export const tests = {
    switchBackClearsPendingIntent: () => { let s = show(placed(show(initial())), 'compact'); s = show(s); assert(s.pendingId === null && !s.widgets.compact.desiredOpen); },
    prepareAndAck: () => { let s = show(initial()); assert(s.widgets.example.phase === 'preparing'); s = placed(s); assert(s.widgets.example.phase === 'opening'); },
    placementTimeout: () => { const s = show(initial()); assert(event(s, 'TICK', {}, 1999).state.widgets.example.phase === 'preparing'); const r = event(s, 'TICK', {}, 2000); assert(r.state.widgets.example.phase === 'closed'); assert(r.state.lastError !== null); },
    cancelPreparation: () => { const s = show(initial()); const r = event(s, 'COMMAND', {action: 'toggle', id: 'example'}); assert(r.state.widgets.example.phase === 'closed'); assert(r.state.selectedId === null); },
    staleAck: () => { let s = show(initial()); const old = s.widgets.example.requestId; s = event(s, 'COMMAND', {action: 'hide', id: 'example'}).state; s = show(s); assert(!event(s, 'PLACED', {id: 'example', requestId: old}).accepted); },
    switchWaits: () => { let s = placed(show(initial())); s = show(s, 'compact'); assert(s.widgets.example.phase === 'closing'); assert(s.widgets.compact.phase === 'closed'); s = event(s, 'FINISHED', {id: 'example', requestId: s.widgets.example.requestId, phase: 'closing'}).state; assert(s.widgets.compact.phase === 'preparing'); assert(s.selectedId === 'compact'); },
    reverseClosing: () => { let s = placed(show(initial())); s = event(s, 'COMMAND', {action: 'hide', id: 'example'}).state; const old = s.widgets.example.requestId; s = show(s); assert(s.widgets.example.phase === 'opening'); assert(!event(s, 'FINISHED', {id: 'example', requestId: old, phase: 'closing'}).accepted); },
    unknown: () => { const s = initial(); const r = event(s, 'COMMAND', {action: 'show', id: 'unknown'}); assert(!r.accepted && r.state === s); },
    unavailable: () => { let s = event(initial(), 'AVAILABLE', {id: 'example', value: false}).state; assert(!event(s, 'COMMAND', {action: 'show', id: 'example'}).accepted); assert(event(s, 'COMMAND', {action: 'show', id: 'compact'}).accepted); },
    leaseExpiry: () => { let s = event(initial(), 'LEASE', {instanceId: 'one'}).state; s = placed(show(s)); assert(event(s, 'TICK', {}, 5999).state.widgets.example.phase === 'opening'); s = event(s, 'TICK', {}, 6000).state; assert(s.widgets.example.phase === 'closed' && !s.adapter.ready); },
    staleLease: () => assert(!event(initial(), 'LEASE', {instanceId: 'old'}).accepted),
    hideAllCancelsPending: () => { let s = show(placed(show(initial())), 'compact'); s = event(s, 'COMMAND', {action: 'hideAll'}).state; assert(s.pendingId === null && !s.widgets.compact.desiredOpen); },
};
