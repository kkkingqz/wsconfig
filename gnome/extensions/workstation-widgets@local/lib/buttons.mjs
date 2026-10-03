export function buttonPresentation(snapshot, id, label) {
    const state = snapshot?.widgets[id];
    const error = state && !state.available ? (snapshot.lastError?.id === id ? snapshot.lastError.reason : 'QML component unavailable') : null;
    return {reactive: Boolean(state && snapshot.adapter.ready), active: Boolean(state?.desiredOpen), error,
        accessibleName: error ? `${label}: ${error}` : label};
}
