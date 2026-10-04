#!/usr/bin/env python3
import os,subprocess,socket,sys,tempfile,time,pathlib,stat
runtime=str(pathlib.Path(sys.argv[1]).resolve()); config=pathlib.Path(__file__).parent
with tempfile.TemporaryDirectory(prefix='widgets-socket-') as tmp:
    path=pathlib.Path(tmp)/'control.sock';env=dict(os.environ,WIDGETS_SOCKET=str(path),QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software');env.pop('WAYLAND_DISPLAY',None)
    log=pathlib.Path(tmp)/'runtime.log'
    def start():
        stream=log.open('a');process=subprocess.Popen([runtime,'-p',str(config)],env=env,stdout=stream,stderr=stream,umask=0o177);stream.close()
        return process
    def connect(process):
        deadline=time.monotonic()+3
        while True:
            peer=socket.socket(socket.AF_UNIX);peer.settimeout(2)
            try:peer.connect(str(path));return peer
            except OSError:
                peer.close()
                if time.monotonic()>deadline or process.poll() is not None:raise AssertionError(log.read_text())
                time.sleep(.02)
    process=start();clients=[];gjs=None
    try:
        a,b=connect(process),connect(process);clients=[a,b]
        readers=[client.makefile('rb') for client in clients]
        assert all(reader.readline()==b'connected\n' for reader in readers)
        a.sendall(b'first');b.sendall(b'second\n');assert readers[1].readline()==b'second\n';a.sendall(b'\n');assert readers[0].readline()==b'first\n'
        assert stat.S_IMODE(path.stat().st_mode)==0o600, oct(stat.S_IMODE(path.stat().st_mode))
        print('Concurrent independent parsers/writes pass; umask0177 creates socket mode0600',flush=True)
        readers[0].close();a.close();time.sleep(.1);assert 'EOF' in log.read_text()
        gjs=subprocess.Popen(['gjs','-m',str(config/'client.js'),str(path)],stdout=subprocess.PIPE,text=True)
        lines=[gjs.stdout.readline().strip(),gjs.stdout.readline().strip()];assert set(lines)=={'ASYNC_CONNECTED','MAIN_LOOP_RESPONSIVE'},lines
        before=log.read_text().count('EOF');gjs.kill();gjs.wait();time.sleep(.1);assert log.read_text().count('EOF')>before
        print('EOF for orderly close and killed GJS client; Gio async reader leaves main loop responsive',flush=True)
        readers[1].close();b.close();process.kill();process.wait();assert path.exists()
        process=start();peer=connect(process);clients.append(peer);assert peer.makefile('rb').readline()==b'connected\n'
        print('SocketServer replaces a stale socket after SIGKILL',flush=True)
    finally:
        for peer in clients:peer.close()
        if gjs and gjs.poll() is None:gjs.kill();gjs.wait()
        if process.poll() is None:process.terminate();process.wait()
