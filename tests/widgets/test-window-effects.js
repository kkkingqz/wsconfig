// The external boundary is Shell's animation predicate; the wrapper itself is real.
const policy = await import('../../gnome/extensions/workstation-widgets@local/lib/windowEffects.mjs').catch(() => ({}));
function assert(value, message = 'window effects policy') { if (!value) throw new Error(message); }
function actor(pid, title) { return {meta_window: {get_pid: () => pid, get_title: () => title}}; }
function wrapper(original, getSnapshot) {
    assert(typeof policy.withoutWidgetEffects === 'function', 'scoped window effect guard is missing');
    return policy.withoutWidgetEffects(original, getSnapshot);
}
const snapshot = () => ({pid: 42, widgets: {example: {}}});
export const tests = {
    ownWindowDoesNotAnimate: () => {
        const animate = wrapper(() => true, snapshot);
        assert(animate(actor(42, 'workstation-widgets:example'), ['NORMAL']) === false, 'widget map still animates');
    },
    foreignWindowsDelegate: () => {
        const manager = {enabled: true};
        const types = ['NORMAL'];
        const original = function (windowActor, allowed) {
            assert(this === manager && allowed === types && windowActor.meta_window, 'native call context lost');
            return this.enabled;
        };
        const animate = wrapper(original, snapshot);
        for (const foreign of [actor(99, 'workstation-widgets:example'), actor(42, 'another-app'), actor(42, 'workstation-widgets:unknown'), actor(42, 'workstation-widgets:constructor')]) {
            assert(animate.call(manager, foreign, types) === true);
            manager.enabled = false;
            assert(animate.call(manager, foreign, types) === false);
            manager.enabled = true;
        }
    },
    replacementAndDisconnect: () => {
        let current = snapshot();
        const animate = wrapper(() => true, () => current);
        current = {pid: 84, widgets: {example: {}}};
        assert(animate(actor(42, 'workstation-widgets:example')) === true);
        assert(animate(actor(84, 'workstation-widgets:example')) === false);
        current = null;
        assert(animate(actor(84, 'workstation-widgets:example')) === true);
    },
};
