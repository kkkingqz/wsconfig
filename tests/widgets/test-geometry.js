import {placePopup} from '../../gnome/extensions/workstation-widgets@local/lib/geometry.mjs';
function assert(v) { if (!v) throw new Error('geometry outside workarea'); }
export const tests = {
    edges: () => { for (const x of [-500, -2, 700]) { const a = {x: -500, y: 24, width: 1000, height: 700}; const r = placePopup({x, y: 0, width: 30, height: 24}, a, {width: 444, height: 604}); assert(r.x >= a.x && r.x + r.width <= a.x + a.width && r.y >= a.y && r.y + r.height <= a.y + a.height); } },
    small: () => { const r = placePopup({x: 20, y: 0, width: 30, height: 24}, {x: 0, y: 24, width: 200, height: 150}, {width: 444, height: 604}); assert(r.width === 200 && r.height === 150); },
};
