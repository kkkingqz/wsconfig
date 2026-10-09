import GLib from 'gi://GLib';
import {validateCommand} from '../../widgets/quickshell/framework/wire.mjs';
const theme = await import('../../gnome/extensions/workstation-widgets@local/lib/menuTheme.js').catch(() => ({}));
const assert = (value, message) => {if (!value) throw Error(message);};
const delay = () => new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {resolve();return GLib.SOURCE_REMOVE;}));
function emitter() {
    const callbacks = new Map(); let seq = 0;
    return {connect(name, cb) {callbacks.set(++seq, {name, cb});return seq;}, disconnect(id) {callbacks.delete(id);}, emit(name) {for(const {name:n,cb} of callbacks.values())if(n===name)cb();}};
}
async function fixture(run) {
    assert(typeof theme.MenuTheme === 'function', 'native menu theme synchronization is missing');
    let background = {red:32,green:48,blue:64,alpha:128};
    const foreground = {red:240,green:241,blue:242,alpha:255};
    const node = {get_background_color: () => background,get_foreground_color: () => foreground};
    const actor = {...emitter(),get_theme_node: () => node};
    const context = emitter(); const calls = [];
    const client = {snapshot:null,generation:1,call:async (method,args) => {calls.push({method,args});return true;}};
    const sync = new theme.MenuTheme(client,actor,context);
    try {await run({sync,actor,context,client,calls,setBackground:value=>{background=value;}});}
    finally {sync.destroy();}
}
export const tests = {
    themeCommandValidatesRoleAndColors: () => {
        const command = args => ({protocolVersion:2,type:'command',seq:1,method:'setTheme',args});
        const colors = {background:'#80203040',foreground:'#fff0f1f2'};
        assert(validateCommand(command(colors),'adapter'),'adapter theme command rejected');
        assert(!validateCommand(command(colors),'cli'),'CLI can replace desktop theme');
        for(const args of [{},{...colors,background:'red'},{...colors,foreground:'#fff'},{...colors,background:'#gg203040'},{...colors,foreground:null}])assert(!validateCommand(command(args),'adapter'),'malformed color accepted');
    },
    nativeColorsKeepAlphaAndQtChannelOrder: () => fixture(async ({sync,client,calls}) => {
        sync.sync();assert(calls.length===0,'sends before adapter connects');
        client.snapshot={instanceId:'one'};sync.sync();await delay();
        assert(calls.length===1 && calls[0].method==='setTheme','theme not sent');
        assert(calls[0].args.background==='#80203040' && calls[0].args.foreground==='#fff0f1f2','RGBA becomes wrong Qt color');
        sync.sync();await delay();assert(calls.length===1,'unchanged theme generates traffic');
    }),
    themeChangeCoalescesAndReconnectResends: () => fixture(async ({sync,actor,context,client,calls,setBackground}) => {
        client.snapshot={instanceId:'one'};sync.sync();await delay();
        setBackground({red:246,green:245,blue:244,alpha:255});context.emit('changed');actor.emit('style-changed');
        await delay();assert(calls.length===2 && calls[1].args.background==='#fff6f5f4','theme change not coalesced/applied');
        client.generation++;sync.sync();await delay();assert(calls.length===3,'reconnect to same runtime loses current theme');
        await delay();assert(calls.length===3,'idle generates theme traffic');
    }),
    destroyCancelsQueuedThemeWork: () => fixture(async ({sync,actor,context,client,calls}) => {
        client.snapshot={instanceId:'one'};actor.emit('style-changed');sync.destroy();context.emit('changed');
        await delay();assert(calls.length===0,'destroyed adapter sends theme');
    }),
};
