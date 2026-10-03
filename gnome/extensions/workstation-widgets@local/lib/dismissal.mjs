export function shouldDismiss(event, context) {
    if (!['opening', 'open'].includes(context.phase) || event.ownButton) return false;
    if (event.type === 'focus' && context.ownButtonSuppressed) return false;
    return !event.inFamily;
}
