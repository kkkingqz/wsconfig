export function pointerInFamily(source, familyActors = []) {
    const family = new Set(familyActors.filter(Boolean));
    for (let actor = source; actor; actor = actor.get_parent()) {
        if (family.has(actor)) return true;
    }
    return false;
}

export function shouldDismiss(event, context) {
    if (event.ownButton) return false;
    const phases = event.type === 'pointer' ? ['preparing', 'opening', 'open'] : ['opening', 'open'];
    if (!phases.includes(context.phase)) return false;
    if (event.type === 'focus' && context.ownButtonSuppressed) return false;
    return event.type === 'pointer' ? !pointerInFamily(event.source, event.familyActors) : !event.inFamily;
}
