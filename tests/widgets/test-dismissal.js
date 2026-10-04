import {shouldDismiss} from '../../gnome/extensions/workstation-widgets@local/lib/dismissal.mjs';
import * as dismissal from '../../gnome/extensions/workstation-widgets@local/lib/dismissal.mjs';
import {createState, reduce} from '../../widgets/quickshell/framework/model.mjs';
function assert(v, message = 'dismissal policy') { if (!v) throw new Error(message); }
const panelActor = {get_parent: () => null};
const panelSurface = {get_parent: () => panelActor};
const background = {get_parent: () => null};
export const tests = {
    panelPressWithNullEventSourceClosesOnSecondClick: () => {
        assert(typeof dismissal.pointerDecision === 'function');
        const button = {get_parent: () => null};
        // Mutter 50 BUTTON_PRESS and TOUCH_BEGIN have no event source actor.
        const event = {get_source: () => null, get_coords: () => [1800, 16]};
        const pick = (x, y) => { assert(x === 1800 && y === 16); return button; };
        const owns = actor => actor === button;
        let state = createState([{id: 'example', enabled: true, width: 420, height: 580}], 'instance', 42);
        const dispatch = event => { state = reduce(state, event, 0).state; };
        const click = () => {
            const decision = dismissal.pointerDecision(event, pick, owns, {phase: state.widgets.example.phase, familyActors: []});
            if (decision.dismiss) dispatch({type: 'COMMAND', action: 'hideAll'});
            dispatch({type: 'COMMAND', action: 'toggle', id: 'example'});
            return decision;
        };
        click();
        dispatch({type: 'PLACED', id: 'example', requestId: 1});
        dispatch({type: 'FINISHED', id: 'example', requestId: 1, phase: 'opening'});
        const second = click();
        assert(state.widgets.example.phase === 'closing' && !state.widgets.example.desiredOpen, 'second panel click reopened instead of closing');
        assert(second.ownButton && !second.dismiss);
        dispatch({type: 'FINISHED', id: 'example', requestId: state.widgets.example.requestId, phase: 'closing'});
        assert(state.widgets.example.phase === 'closed');
    },
    pickedSurfaceAndBackgroundKeepTheirDismissalPolicy: () => {
        const event = {get_source: () => null, get_coords: () => [100, 200]};
        for (const [source, dismiss] of [[panelSurface, false], [background, true]]) {
            const decision = dismissal.pointerDecision(event, () => source, () => false,
                {phase: 'open', familyActors: [panelActor]});
            assert(!decision.ownButton && decision.dismiss === dismiss);
        }
    },
    maskedAreaFallsThrough: () => assert(shouldDismiss({type: 'pointer', source: background, familyActors: [panelActor], inFamily: true}, {phase: 'opening'})),
    transientPointer: () => {
        const popupActor = {get_parent: () => null};
        const popupSurface = {get_parent: () => popupActor};
        assert(!shouldDismiss({type: 'pointer', source: popupSurface, familyActors: [panelActor, popupActor]}, {phase: 'open'}));
    },
    outsideWhilePreparingCancelsPlacement: () => {
        let state = createState([{id: 'example', enabled: true, width: 420, height: 580}], 'instance', 42);
        state = reduce(state, {type: 'COMMAND', action: 'show', id: 'example'}, 0).state;
        const requestId = state.widgets.example.requestId;
        if (shouldDismiss({type: 'pointer', ownButton: false, inFamily: false}, {phase: 'preparing', ownButtonSuppressed: true})) {
            state = reduce(state, {type: 'COMMAND', action: 'hideAll'}, 0).state;
        }
        assert(state.widgets.example.phase === 'closed' && state.selectedId === null);
        assert(!reduce(state, {type: 'PLACED', id: 'example', requestId}, 0).accepted);
    },
    ownButtonWhilePreparing: () => assert(!shouldDismiss({type: 'pointer', ownButton: true, inFamily: false}, {phase: 'preparing'})),
    ownButton: () => assert(!shouldDismiss({type: 'pointer', ownButton: true}, {phase: 'open'})),
    unrelatedFocus: () => assert(shouldDismiss({type: 'focus', inFamily: false}, {phase: 'open'})),
    transient: () => assert(!shouldDismiss({type: 'focus', inFamily: true}, {phase: 'open'})),
    outside: () => assert(shouldDismiss({type: 'pointer', inFamily: false}, {phase: 'open'})),
    inside: () => assert(!shouldDismiss({type: 'pointer', source: panelSurface, familyActors: [panelActor]}, {phase: 'open'})),
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
