#!/usr/bin/env python3
# Free space of the mounted filesystems.
import shutil
import sys

for path in sys.argv[1:] or ["/"]:
    usage = shutil.disk_usage(path)
    print(f"{path}: {usage.free // 2**30} GiB free")
