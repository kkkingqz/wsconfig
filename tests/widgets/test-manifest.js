import {validateManifest} from '../../widgets/quickshell/framework/manifest.mjs';

function assert(value) { if (!value) throw new Error('assertion failed'); }
function rejects(fn) { let failed = false; try { fn(); } catch (_) { failed = true; } assert(failed); }
const entry = {id: 'example', enabled: true, label: 'Example', iconName: 'view-grid-symbolic',
    component: 'widgets/example/Widget.qml', width: 420, height: 580, panelPosition: 'right', panelOrder: 0};
function manifest(changes = {}) { return {schemaVersion: 1, widgets: [{...entry, ...changes}]}; }
export const tests = {
    unloadPolicy: () => {
        assert(validateManifest(manifest())[0].unloadOnClose === false);
        assert(validateManifest(manifest({unloadOnClose:true}))[0].unloadOnClose === true);
        rejects(() => validateManifest(manifest({unloadOnClose:'yes'})));
    },
    disabled: () => assert(validateManifest(manifest({enabled: false}))[0].enabled === false),
    duplicate: () => rejects(() => validateManifest({schemaVersion: 1, widgets: [entry, entry]})),
    dimensions: () => { for (const width of [0, -1, 1.5, '420', Infinity]) rejects(() => validateManifest(manifest({width}))); },
    position: () => rejects(() => validateManifest(manifest({panelPosition: 'outside'}))),
    schema: () => rejects(() => validateManifest({...manifest(), schemaVersion: 2})),
    paths: () => { for (const component of ['../evil.qml', '/tmp/x.qml', 'https://x/Widget.qml', 'widgets/../Widget.qml']) rejects(() => validateManifest(manifest({component}))); },
    id: () => { for (const id of ['Example', '', 'x y', '../x']) rejects(() => validateManifest(manifest({id}))); },
    valid: () => assert(validateManifest(manifest())[0].width === 420),
};
