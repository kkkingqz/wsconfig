export function matchesWidgetWindow(window, snapshot) {
    if (!window || !snapshot || window.get_pid() !== snapshot.pid) return false;
    const title = window.get_title();
    const prefix = 'workstation-widgets:';
    return typeof title === 'string' && title.startsWith(prefix)
        && Object.prototype.hasOwnProperty.call(snapshot.widgets, title.slice(prefix.length));
}

// Installed before adapterReady can map a surface. A late window-type change
// cannot cancel the map animation that Shell has already started.
export function withoutWidgetEffects(original, getSnapshot) {
    return function (actor, ...args) {
        if (matchesWidgetWindow(actor?.meta_window, getSnapshot())) return false;
        return original.call(this, actor, ...args);
    };
}
