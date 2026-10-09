export function validateHello(frame) {
    return frame && frame.protocolVersion === 2 && frame.type === 'hello'
        && ['adapter', 'cli'].includes(frame.role) ? frame.role : null;
}
export function validateCommand(frame, role) {
    if (!frame || frame.protocolVersion !== 2 || frame.type !== 'command'
        || !Number.isSafeInteger(frame.seq) || frame.seq <= 0
        || !frame.args || typeof frame.args !== 'object' || Array.isArray(frame.args)) return false;
    const allowed = role === 'adapter' ? ['toggle', 'hideAll', 'placed', 'placementFailed', 'setGeometry', 'setAnimations', 'setTheme']
        : role === 'cli' ? ['status', 'show', 'hide', 'toggle', 'hideAll'] : [];
    if (!allowed.includes(frame.method)) return false;
    const a = frame.args;
    if (['show', 'hide', 'toggle', 'placed', 'placementFailed', 'setGeometry'].includes(frame.method)
        && (typeof a.id !== 'string' || !/^[a-z][a-z0-9-]*$/.test(a.id))) return false;
    if (['placed', 'placementFailed', 'setGeometry'].includes(frame.method)
        && (!Number.isSafeInteger(a.requestId) || a.requestId < 0)) return false;
    if (frame.method === 'placementFailed' && (typeof a.reason !== 'string' || a.reason.length > 1024)) return false;
    if (frame.method === 'setGeometry' && ![a.width, a.height].every(n => Number.isSafeInteger(n) && n > 0)) return false;
    if (frame.method === 'setTheme' && ![a.background, a.foreground].every(color => typeof color === 'string' && /^#[0-9a-f]{8}$/i.test(color))) return false;
    return frame.method !== 'setAnimations' || typeof a.enabled === 'boolean';
}
