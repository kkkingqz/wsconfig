export function validateManifest(value) {
    if (!value || value.schemaVersion !== 1 || !Array.isArray(value.widgets))
        throw new Error('unsupported widget manifest');
    const ids = new Set();
    return value.widgets.map(raw => {
        const entry = {enabled: true, panelPosition: 'right', panelOrder: 0, ...raw};
        if (typeof entry.id !== 'string' || !/^[a-z][a-z0-9-]*$/.test(entry.id) || ids.has(entry.id))
            throw new Error('invalid or duplicate widget ID');
        ids.add(entry.id);
        if (![entry.width, entry.height].every(x => Number.isInteger(x) && x > 0)
            || typeof entry.enabled !== 'boolean' || !Number.isInteger(entry.panelOrder)
            || !['left', 'center', 'right'].includes(entry.panelPosition))
            throw new Error(`invalid widget dimensions/placement: ${entry.id}`);
        if (![entry.label, entry.iconName].every(x => typeof x === 'string' && x.length > 0))
            throw new Error(`missing label/icon: ${entry.id}`);
        if (typeof entry.component !== 'string' || !/^[a-zA-Z0-9_./-]+\.qml$/.test(entry.component)
            || entry.component.startsWith('/') || entry.component.split('/').some(x => !x || x === '.' || x === '..'))
            throw new Error(`unsafe widget component: ${entry.id}`);
        return entry;
    });
}
