import {shouldDismiss} from '../../gnome/extensions/workstation-widgets@local/lib/dismissal.mjs';
function assert(v) { if (!v) throw new Error('dismissal policy'); }
export const tests = {
    ownButton: () => assert(!shouldDismiss({type: 'pointer', ownButton: true}, {phase: 'open'})),
    unrelatedFocus: () => assert(shouldDismiss({type: 'focus', inFamily: false}, {phase: 'open'})),
    transient: () => assert(!shouldDismiss({type: 'focus', inFamily: true}, {phase: 'open'})),
    outside: () => assert(shouldDismiss({type: 'pointer', inFamily: false}, {phase: 'open'})),
    inside: () => assert(!shouldDismiss({type: 'pointer', inFamily: true}, {phase: 'open'})),
    ownButtonFocusRace: () => { for (const order of [['pointer', 'focus'], ['focus', 'pointer']]) { let pendingFocus = false, suppressed = false, hides = 0; for (const type of order) { if (type === 'focus') pendingFocus = true; else suppressed = true; } if (pendingFocus && shouldDismiss({type: 'focus', inFamily: false}, {phase: 'open', ownButtonSuppressed: suppressed})) hides++; assert(hides === 0); } },
    preparing: () => assert(!shouldDismiss({type: 'focus', inFamily: false}, {phase: 'preparing'})),
};
