#!/usr/bin/env python3
"""Text that ws btrfs make (bin/ws-btrfs) writes for the Btrfs layout of a
fresh install: / on @, /home, /var/cache, /tmp and /var/log on their own
subvolumes (helpws rebuild, section 3).

    btrfs_layout.py fstab UUID < FSTAB      fstab of @: the root line of the
                                            installer becomes the five layout
                                            lines, swap files are dropped
    btrfs_layout.py swapfiles < FSTAB       swap files of the fstab, one per line
    btrfs_layout.py prefix UUID < GRUB.CFG  prefix of a GRUB stub on the ESP
                                            that loads this root
    btrfs_layout.py stub UUID < GRUB.CFG    the stub with its prefix in @

The signed GRUB of Ubuntu reads EFI/<dir>/grub.cfg next to it: that stub
finds the root by UUID and loads $prefix/grub.cfg. Input they do not know
is an error (exit 1, message on stderr): nothing is guessed.
"""
import re
import sys

LAYOUT = [('/', '@'), ('/home', '@home'), ('/var/cache', '@cache'),
          ('/tmp', '@tmp'), ('/var/log', '@log')]
OPTIONS = 'noatime,compress=zstd:1'
HEADER = ('# Btrfs layout of ws btrfs make (helpws rebuild, section 3);',
          '# the fstab of the installer: /etc/fstab.pre-btrfs-layout')
PREFIX = re.compile(r"^set prefix=\(\$root\)'([^']*)'\s*$")
OLD, NEW = '/boot/grub', '/@/boot/grub'


def same_fs(source, uuid):
    return source in ('UUID=' + uuid, '/dev/disk/by-uuid/' + uuid)


def is_swapfile(fields):
    return fields[2] == 'swap' and fields[0].startswith('/') and not fields[0].startswith('/dev/')


def entries(text):
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith('#'):
            yield line, None
            continue
        if len(fields) < 4:
            raise ValueError('unsupported fstab line: ' + line)
        yield line, fields


def fstab(text, uuid):
    targets = dict(LAYOUT)
    out = list(HEADER)
    root = False
    for line, fields in entries(text):
        if fields is None:
            out.append(line)
        elif fields[1] == '/':
            if fields[2] != 'btrfs' or not same_fs(fields[0], uuid):
                raise ValueError('the root line is not Btrfs ' + uuid + ': ' + line)
            if root:
                raise ValueError('two root lines')
            root = True
            out += ['UUID=%s  %-10s  btrfs  subvol=%s,%s  0 0' % (uuid, target, name, OPTIONS)
                    for target, name in LAYOUT]
        elif fields[1] == '/tmp' and fields[2] == 'tmpfs':
            pass  # @tmp instead
        elif fields[1] in targets:
            raise ValueError(fields[1] + ' has its own mount: ' + line)
        elif is_swapfile(fields):
            pass  # swap belongs to @swap (ws-suspend swap-setup)
        else:
            out.append(line)
    if not root:
        raise ValueError('no root line')
    return '\n'.join(out) + '\n'


def swapfiles(text):
    return [fields[0] for _, fields in entries(text) if fields and is_swapfile(fields)]


def prefix(text, uuid):
    lines = text.splitlines()
    if not any(line.split()[:2] == ['search.fs_uuid', uuid] for line in lines if line.strip()):
        raise ValueError('not a GRUB stub of ' + uuid)
    found = [m.group(1) for m in map(PREFIX.match, lines) if m]
    if len(found) != 1:
        raise ValueError('a GRUB stub needs exactly one set prefix line')
    return found[0]


def stub(text, uuid):
    current = prefix(text, uuid)
    if current == NEW:
        return text
    if current != OLD:
        raise ValueError('unknown prefix ' + current)
    return '\n'.join(PREFIX.sub(lambda m: "set prefix=($root)'%s'" % NEW, line)
                     for line in text.splitlines()) + '\n'


def main(argv):
    text = sys.stdin.read()
    if argv[1:2] == ['fstab'] and len(argv) == 3:
        sys.stdout.write(fstab(text, argv[2]))
    elif argv[1:] == ['swapfiles']:
        for path in swapfiles(text):
            print(path)
    elif argv[1:2] == ['prefix'] and len(argv) == 3:
        print(prefix(text, argv[2]))
    elif argv[1:2] == ['stub'] and len(argv) == 3:
        sys.stdout.write(stub(text, argv[2]))
    else:
        sys.stderr.write('usage: btrfs_layout.py fstab UUID | swapfiles | prefix UUID | stub UUID\n')
        return 64
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except ValueError as e:
        sys.stderr.write('btrfs_layout: %s\n' % e)
        sys.exit(1)
