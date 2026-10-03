export function acceptSnapshot(previous, value) {
    if (!value || value.protocolVersion !== 1 || typeof value.instanceId !== 'string'
        || !Number.isInteger(value.pid) || value.pid <= 0 || !Number.isInteger(value.revision) || value.revision < 0
        || !value.widgets || typeof value.widgets !== 'object' || Array.isArray(value.widgets)
        || !value.adapter || typeof value.adapter.ready !== 'boolean') return null;
    for (const [id, w] of Object.entries(value.widgets)) {
        if (!/^[a-z][a-z0-9-]*$/.test(id) || !w || !['closed', 'preparing', 'opening', 'open', 'closing'].includes(w.phase)
            || !Number.isInteger(w.requestId) || w.requestId < 0 || typeof w.desiredOpen !== 'boolean'
            || typeof w.available !== 'boolean' || ![w.width, w.height, w.panelWidth, w.panelHeight].every(n => Number.isInteger(n) && n > 0)) return null;
    }
    if (value.selectedId !== null && !Object.hasOwn(value.widgets, value.selectedId)) return null;
    if (previous?.instanceId === value.instanceId && previous.revision >= value.revision) return null;
    return value;
}
