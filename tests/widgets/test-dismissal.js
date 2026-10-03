import {shouldDismiss} from '../../gnome/extensions/workstation-widgets@local/lib/dismissal.mjs';
import {createState, reduce} from '../../widgets/quickshell/framework/model.mjs';
function assert(v) { if (!v) throw new Error('dismissal policy'); }
export const tests = {
    ownButton: () => assert(!shouldDismiss({type: 'pointer', ownButton: true}, {phase: 'open'})),
    unrelatedFocus: () => assert(shouldDismiss({type: 'focus', inFamily: false}, {phase: 'open'})),
    transient: () => assert(!shouldDismiss({type: 'focus', inFamily: true}, {phase: 'open'})),
    outside: () => assert(shouldDismiss({type: 'pointer', inFamily: false}, {phase: 'open'})),
    inside: () => assert(!shouldDismiss({type: 'pointer', inFamily: true}, {phase: 'open'})),
    ownButtonFocusRace: () => {
        for (const order of [['pointer', 'focus'], ['focus', 'pointer']]) {
            let state = createState([{id: 'example', enabled: true, width: 420, height: 580}], 'instance', 42);
            const dispatch = event => { state = reduce(state, event, 0).state; };
            dispatch({type: 'COMMAND', action: 'show', id: 'example'});
            dispatch({type: 'PLACED', id: 'example', requestId: 1});
            dispatch({type: 'FINISHED', id: 'example', requestId: 1, phase: 'opening'});
            let pendingFocus = false, suppressed = false, hides = 0;
            for (const type of order) { if (type === 'focus') pendingFocus = true; else suppressed = true; }
            // The deferred focus callback runs after the same panel gesture.
            if (pendingFocus && shouldDismiss({type: 'focus', inFamily: false}, {phase: state.widgets.example.phase, ownButtonSuppressed: suppressed})) {
                dispatch({type: 'COMMAND', action: 'hide', id: 'example'}); hides++;
            }
            dispatch({type: 'COMMAND', action: 'toggle', id: 'example'});
            assert(hides === 0 && state.widgets.example.phase === 'closing');
            dispatch({type: 'FINISHED', id: 'example', requestId: state.widgets.example.requestId, phase: 'closing'});
            assert(state.widgets.example.phase === 'closed' && !state.widgets.example.desiredOpen);
        }
    },
    preparing: () => assert(!shouldDismiss({type: 'focus', inFamily: false}, {phase: 'preparing'})),
};
