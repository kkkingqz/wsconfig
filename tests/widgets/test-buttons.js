import {buttonPresentation} from '../../gnome/extensions/workstation-widgets@local/lib/buttons.mjs';
function assert(v) { if (!v) throw new Error('broken widget feedback'); }
export const tests = {
    failureFeedback: () => { const p = buttonPresentation({adapter: {ready: true}, widgets: {broken: {available: false, desiredOpen: false}}, lastError: {id: 'broken', reason: 'QML component failed'}}, 'broken', 'Example'); assert(p.reactive && p.error === 'QML component failed' && p.accessibleName.includes(p.error)); },
    disconnected: () => assert(!buttonPresentation(null, 'example', 'Example').reactive),
};
