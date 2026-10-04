"""Offline recovery of this workstation from a forced-command Unraid receiver."""
import argparse
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

from recovery_catalog import TOKEN, UUID, parse_catalog, build_selections, validate_selection
from recovery_platform import RecoveryPlatform, safe_path
import recovery_transaction as transaction

VERSION = 'ws-restore 1'
LIMIT = 20000000


def ssh_argv(options, words):
    host = options.get('host', '')
    if not isinstance(host, str) or not host or host.startswith('-'):
        raise ValueError('invalid SSH host')
    try: ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host): raise ValueError('invalid SSH host')
    user = options.get('user','root'); port = options.get('port',22)
    if not isinstance(user,str) or not TOKEN.fullmatch(user): raise ValueError('invalid SSH user')
    if type(port) is not int or not 1 <= port <= 65535: raise ValueError('invalid SSH port')
    args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10']
    for field, flag in [('config','-F'),('key','-i')]:
        path = options.get(field)
        if not isinstance(path,str) or not Path(path).is_absolute() or '\x00' in path:
            raise ValueError('explicit absolute SSH ' + field + ' path required')
        args += [flag,path]
    if not words or any(not isinstance(w,str) or not TOKEN.fullmatch(w) for w in words):
        raise ValueError('unsafe receiver command')
    return args + ['-p',str(port),'-l',user,'--',host,' '.join(words)]


class LivePlatform(RecoveryPlatform):
    def remote(self, options, words):
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(ssh_argv(options, words), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors)
            try:
                output = process.stdout.read(LIMIT + 1)
                if len(output) > LIMIT: raise ValueError('receiver response too large')
                code = process.wait(timeout=60)
                if code:
                    errors.seek(0)
                    raise ValueError('receiver failed: ' + errors.read(2000).decode(errors='replace'))
                return output
            finally:
                if process.poll() is None: process.kill(); process.wait()
                process.stdout.close()

    def receive_stream(self, options, words, destination):
        sender = receiver = None
        with tempfile.TemporaryFile() as send_error, tempfile.TemporaryFile() as receive_error:
            try:
                sender = subprocess.Popen(ssh_argv(options,words), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=send_error)
                receiver = subprocess.Popen(['btrfs','receive',str(destination)], stdin=sender.stdout, stdout=receive_error, stderr=receive_error)
                sender.stdout.close()
                receive_code = receiver.wait(); send_code = sender.wait()
                if send_code or receive_code:
                    send_error.seek(0); receive_error.seek(0)
                    raise ValueError(f'stream failed (SSH {send_code}, receive {receive_code}): ' +
                                     (send_error.read(1500)+receive_error.read(1500)).decode(errors='replace'))
            finally:
                for process in (receiver,sender):
                    if process and process.poll() is None: process.terminate(); process.wait()


def decode_json(data):
    from recovery_catalog import _unique_fields
    if len(data) > LIMIT: raise ValueError('receiver response too large')
    return json.loads(data,object_pairs_hook=_unique_fields)


def probe(options, host_id, platform):
    if not isinstance(host_id,str) or not TOKEN.fullmatch(host_id): raise ValueError('invalid host ID')
    info=decode_json(platform.remote(options,['probe',host_id]))
    if (not isinstance(info,dict) or type(info.get('protocol_version')) is not int or info['protocol_version'] != 1 or
            'recovery-catalog-v1' not in info.get('capabilities',[]) or info.get('host_id') != host_id or
            not isinstance(info.get('filesystem_uuid'),str) or not UUID.fullmatch(info['filesystem_uuid'])):
        raise ValueError('receiver lacks valid recovery-catalog-v1; update receiver and backfill with ws backup')
    return info


def read_catalog(ssh_options, host_id, platform=None):
    platform=platform or LivePlatform()
    probe(ssh_options,host_id,platform)
    data=platform.remote(ssh_options,['catalog-list',host_id])
    if len(data)>LIMIT: raise ValueError('catalog too large')
    records=parse_catalog(data.decode())
    if any(r['host_id']!=host_id for r in records): raise ValueError('catalog host mismatch')
    build_selections(records)
    return records


def inspect_remote(options, record, platform):
    info=decode_json(platform.remote(options,['inspect',record['host_id'],record['scope'],record['id']]))
    if (not isinstance(info,dict) or not isinstance(info.get('uuid'),str) or not UUID.fullmatch(info['uuid']) or
            info.get('received_uuid') != record['source_uuid'] or info.get('ro') is not True):
        raise ValueError('NAS snapshot identity/readonly mismatch')
    return info


def receive_selection(top, tx, ssh_options, platform):
    top=safe_path(top); transaction.observe_transaction(top,tx,platform)
    selection=validate_selection(tx['selection']); probe(ssh_options,selection['host_id'],platform)
    if tx['phase'] not in ('selected','received') or tx.get('direction'):
        raise ValueError('transaction cannot receive in current phase')
    copies=tx.setdefault('received',{})
    for scope in ('system','home'):
        record=selection[scope]
        if record is None: continue
        platform.assert_offline(top)
        remote=inspect_remote(ssh_options,record,platform)
        if scope in copies:
            existing=platform.inspect_snapshot(top/copies[scope]['path'])
            if existing['uuid']!=copies[scope]['uuid'] or existing['received_uuid']!=record['source_uuid'] or not existing['readonly']:
                raise ValueError('received baseline changed')
            continue
        name='ws-recovery/receives/'+tx['id']+'/'+scope+'-'+uuid.uuid4().hex
        destination=safe_path(top/name)
        destination.mkdir(mode=0o700,parents=True)
        tx.setdefault('receive_attempts',[]).append({'scope':scope,'path':name,'status':'receiving','nas_uuid':remote['uuid']})
        transaction.save_transaction(top,tx,platform)
        platform.receive_stream(ssh_options,['send',record['host_id'],scope,record['id']],destination)
        entries=list(destination.iterdir())
        if len(entries)!=1 or entries[0].name!=record['id']: raise ValueError('unexpected received entries')
        path=safe_path(entries[0]); info=platform.inspect_snapshot(path)
        if not info['readonly'] or info['received_uuid']!=record['source_uuid']: raise ValueError('received UUID/readonly mismatch')
        platform.sync_filesystem(top)
        copies[scope]={'path':str(path.relative_to(top)),**info}
        tx['receive_attempts'][-1]['status']='received'
        transaction.save_transaction(top,tx,platform)
    checked=transaction.preflight(top,selection,{s:str(top/e['path']) for s,e in copies.items()},platform)
    if checked['old']!=tx['old'] or checked['original_default']!=tx['original_default']:
        raise ValueError('original system changed during receive')
    tx.update(boot=checked['boot'],phase='received')
    transaction.save_transaction(top,tx,platform)
    return tx


def show_plan(tx, output):
    output.write(json.dumps({'transaction':tx['id'],'target':tx.get('target'), 'selection':tx['selection'],
                            'old':tx['old'],'backups':tx['backups'], 'candidates':tx.get('candidates'),
                            'preserved':['@nix','@vms','@cache','@tmp','@log','@swap','EFI'],
                            'warning':'HOME replaces current files when selected. Switching is not atomic. No automatic reboot. Nix generations may need rebuilding.'},indent=2)+'\n')
    output.flush()


def ask(reader,output,message):
    output.write(message+' '); output.flush()
    answer=reader.readline()
    if not answer: raise ValueError('terminal input ended')
    return answer.strip()


def confirm(tx, reader, output):
    expected='RESTORE '+tx['id']
    return ask(reader,output,'To switch root/HOME, type '+expected+':')==expected


def finish_restore(top,tx,options,platform,reader,output):
    if tx['phase']=='selected': tx=receive_selection(top,tx,options,platform)
    tx=transaction.prepare_candidates(top,tx,platform)
    show_plan(tx,output)
    if not confirm(tx,reader,output):
        output.write('Switch cancelled. Original system remains. Prepared copies and journal retained.\n')
        return tx
    done=transaction.switch_transaction(top,tx,platform,confirmed=True)
    output.write('Recovery complete. Unmount finished on exit; reboot manually.\n')
    return done


def open_tty():
    try:
        tty=open('/dev/tty','r+',buffering=1)
        if not tty.isatty(): tty.close(); raise ValueError('controlling TTY required')
        return tty
    except OSError as error: raise ValueError('controlling TTY required') from error


def choose(values,reader,output,label):
    if not values: raise ValueError('no '+label+' available')
    for index,value in enumerate(values,1): output.write(f'{index}: '+json.dumps(value)+'\n')
    text=ask(reader,output,'Select '+label+' number:')
    if not text.isdigit() or not 1<=int(text)<=len(values): raise ValueError('invalid selection')
    return values[int(text)-1]


def connection(args,reader,output):
    options={}
    for key,label,default in [('host','SSH host',''),('user','SSH user','root'),('port','SSH port','22'),
                              ('config','Absolute SSH config path',''),('key','Absolute SSH private key path','')]:
        value=getattr(args,key) or ask(reader,output,label+(f' [{default}]' if default else '')+':') or default
        options[key]=int(value) if key=='port' else value
    ssh_argv(options,['probe','mbp16'])
    return options


def dependencies():
    missing=[name for name in ('ssh','btrfs','lsblk','blkid','findmnt','mount','umount') if not shutil.which(name)]
    if missing: raise ValueError('missing Live dependencies: '+', '.join(missing))


def local_action(action,top,tx,p,reader,output,options=None):
    observation=transaction.observe_transaction(top,tx,p)
    output.write(json.dumps(observation,indent=2)+'\n')
    if action=='status': return tx
    show_plan(tx,output)
    expected=('ROLLBACK ' if action=='rollback' else 'RESTORE ')+tx['id']
    if ask(reader,output,'Type '+expected+':')!=expected: return tx
    if action=='rollback': return transaction.rollback_transaction(top,tx,p,True)
    if tx['phase']=='selected':
        if options is None: raise ValueError('incomplete receive needs explicit SSH options')
        tx=receive_selection(top,tx,options,p)
    return transaction.resume_transaction(top,tx,p,True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',action='version',version=VERSION)
    parser.add_argument('action',nargs='?',choices=['restore','status','resume','rollback'],default='restore')
    parser.add_argument('--transaction'); parser.add_argument('--device'); parser.add_argument('--uuid')
    for field in ('host','user','port','config','key','host-id'): parser.add_argument('--'+field)
    args=parser.parse_args(argv)
    if os.geteuid()!=0: raise ValueError('run with sudo from Live USB')
    def interrupted(signum,frame): raise InterruptedError('interrupted; use status/resume/rollback')
    signal.signal(signal.SIGTERM,interrupted)
    with open_tty() as tty:
        dependencies(); p=LivePlatform()
        targets=p.discover_targets()
        if args.device:
            target=next((t for t in targets if t['device']==args.device),None)
            if target is None: raise ValueError('device unavailable')
        else: target=choose(targets,tty,tty,'target disk')
        if args.uuid and args.uuid!=target['uuid']: raise ValueError('target UUID mismatch')
        with p.open_target(target['device'],target['uuid']) as (top,target):
            directory=safe_path(top/'ws-recovery/transactions')
            transactions=[transaction.load_transaction(top,path.stem) for path in sorted(directory.glob('restore-*.json'))]
            if args.action!='restore':
                tx=next((t for t in transactions if t['id']==args.transaction),None) if args.transaction else choose(transactions,tty,tty,'transaction')
                if tx is None: raise ValueError('transaction unavailable')
                options=connection(args,tty,tty) if args.action=='resume' and tx['phase']=='selected' else None
                local_action(args.action,top,tx,p,tty,tty,options); return 0
            unfinished=[t for t in transactions if t['phase'] not in ('complete','rolled-back')]
            if unfinished:
                tx=choose(unfinished,tty,tty,'unfinished transaction')
                action=ask(tty,tty,'Choose status, resume or rollback:')
                if action not in ('status','resume','rollback'): raise ValueError('unfinished transaction must be handled first')
                options=connection(args,tty,tty) if action=='resume' and tx['phase']=='selected' else None
                local_action(action,top,tx,p,tty,tty,options); return 0
            options=connection(args,tty,tty)
            host_id=args.host_id or ask(tty,tty,'Backup host ID [mbp16]:') or 'mbp16'
            selections=[s for s in build_selections(read_catalog(options,host_id,p)) if s['source_fs_uuid']==target['uuid']]
            selection=choose(selections,tty,tty,'Timeshift date')
            include_home=ask(tty,tty,'Restore HOME from the same date? Type YES:')=='YES'
            plan=transaction.build_plan(selection,target,include_home)
            tx=transaction.create_transaction(top,plan,p)
            finish_restore(top,tx,options,p,tty,tty)
    return 0


def entrypoint():
    try: return main()
    except (ValueError,OSError,KeyError,TypeError) as error:
        print('ws-restore: '+str(error),file=sys.stderr); return 1
    except KeyboardInterrupt:
        print('ws-restore: interrupted; inspect status before retrying',file=sys.stderr); return 130


if __name__=='__main__': sys.exit(entrypoint())
