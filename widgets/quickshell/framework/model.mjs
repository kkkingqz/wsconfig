export function createState(entries, instanceId, pid) {
    const widgets = {};
    for (const entry of entries.filter(e => e.enabled)) {
        widgets[entry.id] = {phase: 'closed', desiredOpen: false, requestId: 0,
            available: true, width: entry.width, height: entry.height,
            panelWidth: entry.width, panelHeight: entry.height, deadline: 0};
    }
    return {protocolVersion: 2, instanceId, pid, revision: 0, selectedId: null,
        pendingId: null, widgets, lastError: null, adapter: {connected: false}};
}

export function reduce(previous, event, nowMs) {
    const state = JSON.parse(JSON.stringify(previous));
    const effects = [];
    let accepted = true;
    const widget = Object.prototype.hasOwnProperty.call(state.widgets, event.id) ? state.widgets[event.id] : null;
    function begin(id) {
        const w = state.widgets[id];
        state.selectedId = id;
        state.pendingId = null;
        w.requestId++;
        w.desiredOpen = true;
        w.phase = 'preparing';
        w.deadline = nowMs + 2000;
        state.lastError = null;
        effects.push({type: 'prepare', id, requestId: w.requestId});
    }
    function next() {
        const id = state.pendingId;
        state.pendingId = null;
        if (id && state.widgets[id].available && state.widgets[id].desiredOpen) begin(id);
    }
    function shut(id, force = false) {
        const w = state.widgets[id];
        w.desiredOpen = false;
        if (w.phase === 'closed') return;
        if (w.phase === 'closing' && !force) return;
        w.requestId++;
        if (force || w.phase === 'preparing') {
            w.phase = 'closed';
            if (state.selectedId === id) state.selectedId = null;
            effects.push({type: 'hide', id});
            next();
        } else {
            w.phase = 'closing';
            effects.push({type: 'animate', id, requestId: w.requestId, phase: 'closing'});
        }
    }
    function open(id) {
        const w = state.widgets[id];
        w.desiredOpen = true;
        if (state.selectedId && state.selectedId !== id) {
            if (state.pendingId && state.pendingId !== id) state.widgets[state.pendingId].desiredOpen = false;
            state.pendingId = id;
            shut(state.selectedId);
        } else if (w.phase === 'closed') begin(id);
        else if (w.phase === 'closing') {
            if (state.pendingId) state.widgets[state.pendingId].desiredOpen = false;
            state.pendingId = null;
            w.phase = 'opening';
            w.requestId++;
            effects.push({type: 'animate', id, requestId: w.requestId, phase: 'opening'});
        }
    }
    switch (event.type) {
    case 'COMMAND':
        if (event.action === 'hideAll') {
            state.pendingId = null;
            for (const id of Object.keys(state.widgets)) shut(id);
        } else if (!widget || !['show', 'hide', 'toggle'].includes(event.action)) accepted = false;
        else {
            const wants = event.action === 'show' || (event.action === 'toggle' && !widget.desiredOpen);
            if (wants && (!widget.available || !state.adapter.connected)) accepted = false;
            else if (wants) open(event.id);
            else {
                if (state.pendingId === event.id) state.pendingId = null;
                shut(event.id);
            }
        }
        break;
    case 'PLACED':
        if (!widget || widget.phase !== 'preparing' || widget.requestId !== event.requestId) accepted = false;
        else {
            widget.phase = 'opening';
            effects.push({type: 'animate', id: event.id, requestId: widget.requestId, phase: 'opening'});
        }
        break;
    case 'FINISHED':
        if (!widget || widget.phase !== event.phase || widget.requestId !== event.requestId
            || !['opening', 'closing'].includes(event.phase)) accepted = false;
        else if (event.phase === 'opening') widget.phase = 'open';
        else { widget.phase = 'closed'; state.selectedId = null; next(); }
        break;
    case 'FAILED':
        if (!widget || widget.requestId !== event.requestId) accepted = false;
        else { shut(event.id, true); state.lastError = {id: event.id, reason: event.reason}; }
        break;
    case 'AVAILABLE':
        if (!widget) accepted = false;
        else { widget.available = event.value; if (!event.value) { if (state.pendingId === event.id) state.pendingId = null; shut(event.id, true); state.lastError = {id: event.id, reason: event.reason || 'component unavailable'}; } }
        break;
    case 'GEOMETRY':
        if (!widget || widget.requestId !== event.requestId || ![event.width, event.height].every(x => Number.isInteger(x) && x > 0)
            || event.width > widget.width || event.height > widget.height) accepted = false;
        else { widget.panelWidth = event.width; widget.panelHeight = event.height; }
        break;
    case 'ADAPTER_CONNECTED':
        state.adapter.connected = true;
        if (state.lastError?.reason === 'desktop adapter disconnected') state.lastError = null;
        break;
    case 'ADAPTER_DISCONNECTED':
        state.adapter.connected = false;
        state.pendingId = null;
        for (const id of Object.keys(state.widgets)) shut(id, true);
        state.lastError = {id: null, reason: 'desktop adapter disconnected'};
        break;
    case 'TIMEOUT':
        for (const [id, w] of Object.entries(state.widgets)) {
            if (w.phase === 'preparing' && nowMs >= w.deadline) {
                shut(id, true);
                state.lastError = {id, reason: 'window placement timed out'};
            }
        }
        break;
    default: accepted = false;
    }
    if (!accepted) return {state: previous, accepted: false, effects: []};
    if (JSON.stringify(state) === JSON.stringify(previous)) return {state: previous, accepted, effects};
    state.revision++;
    return {state, accepted, effects};
}

export function nextDeadline(state) {
    const deadlines = Object.values(state.widgets).filter(w => w.phase === 'preparing').map(w => w.deadline);
    return deadlines.length ? Math.min(...deadlines) : null;
}
