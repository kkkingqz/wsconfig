#!/usr/bin/env python3
"""What ws setup learns about this machine for a new host (ws help
plan-v2, 9.5), read as the desktop user, without root:

    hardware      DMI (/sys/class/dmi/id): MacBookPro16,1 is t2-mbp16, the
                  Legion Go (83E1) legion-go, anything else generic-pc;
                  known: whether it is one of the list
    boot          by the hardware: rEFInd with GRUB as recovery on
                  t2-mbp16 (ws help rebuild, section 5), GRUB elsewhere (the
                  ESP of Ubuntu is root only)
    guest         a virtual machine (the hypervisor flag of the CPU)
    kvm           /dev/kvm: the VM layer can run here
    displayScale  of the primary monitor in ~/.config/monitors.xml (GNOME),
                  1 without it
    rootUuid      of / (findmnt), for the rEFInd hosts
    user, hostname

    ws_inventory.py [--root DIR] [--home DIR]      the inventory as JSON
    ws_inventory.py write-host --config DIR --name NAME --inventory FILE
                    [--base HOST] [--vm] [--no-widgets] [--steam] [--game]
                                                   hosts/NAME of the configuration:
                                                   host.toml (and apt.txt)

write-host makes host.toml from the inventory, or with --base from
hosts/HOST (the same hardware: its kernel parameters, packages and apt
sources), with this machine's hostname, user, configuration path and
rootUuid. It refuses a NAME that exists. The host choices of HOST (its
other *.toml) are not taken: ws setup asks them.
"""
import argparse
import json
import math
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

# (sys_vendor, product_name) → hardware of system/hardware/.
KNOWN = {
    ("Apple Inc.", "MacBookPro16,1"): "t2-mbp16",
    ("LENOVO", "83E1"): "legion-go",
}
GENERIC = "generic-pc"
BOOT = {"t2-mbp16": "refind-grub-recovery"}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def display_scale(home):
    """The scale of the primary logical monitor of the first configuration
    of monitors.xml (GNOME writes it when the scale is set); 1 without
    it. A value out of 1..4 (lib/host.nix) is 1."""
    try:
        tree = ET.parse(Path(home) / ".config/monitors.xml")
    except (OSError, ET.ParseError):
        return 1
    for config in tree.getroot().iter("configuration"):
        for lm in config.iter("logicalmonitor"):
            if (lm.findtext("primary") or "").strip() == "yes":
                try:
                    scale = float(lm.findtext("scale") or 1)
                except ValueError:
                    return 1
                if not 1 <= scale <= 4 or math.isnan(scale):
                    return 1
                return int(scale) if scale.is_integer() else round(scale, 2)
        break
    return 1


def root_uuid(root):
    """The UUID of /; under a fixture root (tests) its file root-uuid."""
    if root != Path("/"):
        return read(root / "root-uuid")
    try:
        return subprocess.run(["findmnt", "-no", "UUID", "/"], capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return ""


def inventory(root=Path("/"), home=None):
    root = Path(root)
    dmi = root / "sys/class/dmi/id"
    vendor, product = read(dmi / "sys_vendor"), read(dmi / "product_name")
    hardware = KNOWN.get((vendor, product))
    cpu = read(root / "proc/cpuinfo")
    guest = any(line.startswith("flags") and " hypervisor" in line for line in cpu.splitlines())
    return {
        "hostname": read(root / "etc/hostname") if root != Path("/") else socket.gethostname(),
        "user": pwd.getpwuid(os.getuid()).pw_name,
        "model": " ".join(x for x in (vendor, product) if x) or "?",
        "hardware": hardware or GENERIC,
        "known": hardware is not None,
        "boot": BOOT.get(hardware, "grub"),
        "guest": guest,
        "kvm": (root / "dev/kvm").exists(),
        "displayScale": display_scale(home or Path.home()),
        "rootUuid": root_uuid(root),
    }


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v)


def new_host_toml(name, inv, rel, layers):
    lines = [
        f"# {name}: made by ws setup on this machine ({inv['model']}), from its",
        "# inventory (lib/ws_inventory.py; lib/host.nix checks the file).",
        "",
        "[host]",
        "# `ws host` finds the host by it.",
        f"hostname = {toml_value(name)}",
        f"user = {toml_value(inv['user'])}",
        f"wsconfig = {toml_value(rel)}",
        "",
        "[platform]",
        f"hardware = {toml_value(inv['hardware'])}",
        f"boot = {toml_value(inv['boot'])}",
        'kernelParams = ["quiet", "splash"]',
    ]
    if inv["boot"].startswith("refind"):
        lines += [
            "# rEFInd (ws help rebuild, section 5): the entry Ubuntu adds these;",
            "# the ESP of rEFInd by its PARTUUID (lsblk -no PARTUUID), / by its UUID.",
            "refindDefaultParams = []",
            f"rootUuid = {toml_value(inv['rootUuid'])}",
            'refindEspPartuuid = ""',
        ]
    lines += [
        "# Display scale of GNOME; Claude, ChatGPT and Wine DPI follow it.",
        f"displayScale = {toml_value(inv['displayScale'])}",
        "",
        "[layers]",
        "# Virtual machines (ws help virt).",
        f"vm = {toml_value(layers['vm'])}",
        "# Quickshell widgets on the GNOME panel (ws help widgets).",
        f"widgets = {toml_value(layers['widgets'])}",
        "# Native Steam (steam/apt.txt, @steam) and the Game Mode session",
        "# (gaming/apt.txt; ws help plan-legion-go).",
        f"nativeSteam = {toml_value(layers['nativeSteam'])}",
        f"gameMode = {toml_value(layers['gameMode'])}",
    ]
    return "\n".join(lines) + "\n"


def based_host_toml(base_file, name, inv, rel, layers):
    """hosts/BASE/host.toml with this machine in it; comments kept."""
    import tomlkit
    doc = tomlkit.parse(base_file.read_text())
    doc["host"]["hostname"] = name
    doc["host"]["user"] = inv["user"]
    doc["host"]["wsconfig"] = rel
    platform = doc["platform"]
    if "rootUuid" in platform and inv["rootUuid"]:
        platform["rootUuid"] = inv["rootUuid"]
    # The ESP of this machine is another partition: 9.9 asks for it.
    if "refindEspPartuuid" in platform:
        platform["refindEspPartuuid"] = ""
    for key, value in layers.items():
        doc["layers"][key] = value
    head = f"# {name}: made by ws setup from hosts/{base_file.parent.name} (the same hardware).\n"
    return head + tomlkit.dumps(doc)


def write_host(config, name, inv, base=None, layers=None):
    config = Path(config)
    target = config / "hosts" / name
    if target.exists():
        raise SystemExit(f"ws_inventory: {target} exists")
    home = Path.home()
    try:
        rel = str(config.resolve().relative_to(home.resolve()))
    except ValueError:
        raise SystemExit(f"ws_inventory: the configuration must be under {home}: {config}")
    target.mkdir(parents=True)
    if base:
        src = config / "hosts" / base
        (target / "host.toml").write_text(based_host_toml(src / "host.toml", name, inv, rel, layers))
        for extra in ("apt.txt", "apt"):
            if (src / extra).is_dir():
                shutil.copytree(src / extra, target / extra)
            elif (src / extra).is_file():
                shutil.copy2(src / extra, target / extra)
    else:
        (target / "host.toml").write_text(new_host_toml(name, inv, rel, layers))
    if not (target / "apt.txt").exists():
        (target / "apt.txt").write_text(f"# apt packages of {name} on top of system/apt.txt and apt.txt.\n")
    return target


def main(argv):
    if argv[:1] == ["write-host"]:
        ap = argparse.ArgumentParser(prog="ws_inventory.py write-host")
        ap.add_argument("--config", required=True)
        ap.add_argument("--name", required=True)
        ap.add_argument("--inventory", required=True)
        ap.add_argument("--base")
        ap.add_argument("--vm", action="store_true")
        ap.add_argument("--no-widgets", action="store_true")
        ap.add_argument("--steam", action="store_true")
        ap.add_argument("--game", action="store_true")
        a = ap.parse_args(argv[1:])
        if a.game and not a.steam:
            raise SystemExit("ws_inventory: --game needs --steam")
        inv = json.loads(Path(a.inventory).read_text())
        layers = {"vm": a.vm, "widgets": not a.no_widgets, "nativeSteam": a.steam, "gameMode": a.game}
        print(write_host(a.config, a.name, inv, a.base, layers))
        return 0
    ap = argparse.ArgumentParser(prog="ws_inventory.py")
    ap.add_argument("--root", default="/")
    ap.add_argument("--home")
    a = ap.parse_args(argv)
    json.dump(inventory(Path(a.root), a.home), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
