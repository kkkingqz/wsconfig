import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {IpcClient} from '../../gnome/extensions/workstation-widgets@local/lib/ipcClient.js';
import {createState} from '../../widgets/quickshell/framework/model.mjs';
const assert = (v,m='socket client assertion') => {if(!v) throw Error(m);};
const delay = ms => new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT,ms,()=>{resolve();return GLib.SOURCE_REMOVE;}));
async function wait(check) {for(let n=0;n<150;n++){if(check())return;await delay(10);}throw Error('wait timed out');}
async function fixture(run) {
    const dir=GLib.dir_make_tmp('widget-client-XXXXXX'), path=`${dir}/control.sock`;
    const server=new Gio.SocketService();
    server.add_address(new Gio.UnixSocketAddress({path}),Gio.SocketType.STREAM,Gio.SocketProtocol.DEFAULT,null);
    Gio.File.new_for_path(path).set_attribute_uint32('unix::mode',0o600,Gio.FileQueryInfoFlags.NONE,null);
    const peers=[]; const requests=[];
    const state=createState([], 'test-runtime', new Gio.Credentials().get_unix_pid());state.adapter.connected=true;
    let behavior='normal';
    server.connect('incoming',(_s,connection)=>{
        const peer={connection,reader:new Gio.DataInputStream({base_stream:connection.get_input_stream()}),cancel:new Gio.Cancellable()}; peers.push(peer);
        const send=frame=>connection.get_output_stream().write_all(new TextEncoder().encode(JSON.stringify({protocolVersion:2,...frame})+'\n'),null);
        const read=()=>peer.reader.read_line_async(0,peer.cancel,(stream,result)=>{
            try {
                const [line]=stream.read_line_finish_utf8(result);if(line===null)return;
                const f=JSON.parse(line);
                if(f.type==='hello') {
                    if(behavior==='malformed')send({type:'snapshot',state:{}});
                    else send({type:'snapshot',state});
                } else {
                    requests.push(f);
                    if(behavior!=='silent')send({type:'reply',seq:f.seq,ok:true,result:f.args.id || true});
                }
                read();
            } catch (_) {}
        });read();return true;
    });server.start();
    const snapshots=[];let unavailable=0;
    const client=new IpcClient({socketPath:path}, s=>snapshots.push(s),()=>unavailable++);
    try {await run({client,peers,requests,snapshots,getUnavailable:()=>unavailable,setBehavior:b=>behavior=b});}
    finally {client.destroy();for(const p of peers){p.cancel.cancel();p.connection.close(null);}server.stop();server.close();Gio.File.new_for_path(path).delete(null);Gio.File.new_for_path(dir).delete(null);}
}
export const tests={
    socketHandshakeAndInterleavedCalls:()=>fixture(async({client,requests,snapshots})=>{
        client.start();await wait(()=>snapshots.length===1);
        const replies=await Promise.all([client.call('toggle',{id:'example'}),client.call('toggle',{id:'compact'})]);
        assert(replies.join(',')==='example,compact');assert(requests.length===2);
        await delay(100);assert(snapshots.length===1,'idle generates traffic');
    }),
    eofReconnectsAndDestroyStops:()=>fixture(async({client,peers,snapshots,getUnavailable})=>{
        client.start();await wait(()=>snapshots.length===1);peers[0].connection.close(null);
        await wait(()=>snapshots.length===2);assert(getUnavailable()===1);
        client.destroy();const n=peers.length;await delay(350);assert(peers.length===n);
        let rejected=false;try{await client.call('toggle',{id:'example'});}catch(_){rejected=true;}assert(rejected);
    }),
    malformedSnapshotDisconnected:()=>fixture(async({client,setBehavior,getUnavailable,snapshots})=>{
        setBehavior('malformed');client.start();await wait(()=>getUnavailable()>0);assert(!snapshots.length);client.destroy();
    }),
    shutdownCancelsPendingReply:()=>fixture(async({client,snapshots,requests,setBehavior})=>{
        client.start();await wait(()=>snapshots.length);setBehavior('silent');
        const result=client.call('toggle',{id:'example'}).then(()=>false,()=>true);
        await wait(()=>requests.length);client.shutdown();assert(await result,'pending reply survived shutdown');
    }),
};
