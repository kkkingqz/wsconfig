"""lib/ws_inventory.py (ws help plan-v2, 9.5): the inventory of a machine
from fixtures of /sys, /proc and monitors.xml, and hosts/NAME written from
it or from a host of the same hardware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_inventory  # noqa: E402

MONITORS = """<monitors version="2">
  <configuration>
    <logicalmonitor><scale>1</scale></logicalmonitor>
    <logicalmonitor><scale>{scale}</scale><primary>yes</primary></logicalmonitor>
  </configuration>
  <configuration>
    <logicalmonitor><scale>2</scale><primary>yes</primary></logicalmonitor>
  </configuration>
</monitors>
"""
LAYERS = {"vm": True, "widgets": True, "nativeSteam": False, "gameMode": False}


class InventoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "root"
        self.home = self.tmp / "home"
        self.home.mkdir()

    def machine(self, vendor, product, guest=False, kvm=True, scale=None):
        dmi = self.root / "sys/class/dmi/id"
        dmi.mkdir(parents=True, exist_ok=True)
        (dmi / "sys_vendor").write_text(vendor + "\n")
        (dmi / "product_name").write_text(product + "\n")
        (self.root / "proc").mkdir(exist_ok=True)
        flags = "fpu vme" + (" hypervisor" if guest else "") + " lm"
        (self.root / "proc/cpuinfo").write_text(f"processor\t: 0\nflags\t\t: {flags}\n")
        (self.root / "etc").mkdir(exist_ok=True)
        (self.root / "etc/hostname").write_text("ubuntu\n")
        (self.root / "root-uuid").write_text("1111-uuid\n")
        if kvm:
            (self.root / "dev").mkdir(exist_ok=True)
            (self.root / "dev/kvm").touch()
        if scale is not None:
            (self.home / ".config").mkdir(exist_ok=True)
            (self.home / ".config/monitors.xml").write_text(MONITORS.format(scale=scale))
        return ws_inventory.inventory(self.root, self.home)

    def test_mbp16(self):
        inv = self.machine("Apple Inc.", "MacBookPro16,1", scale="1.5")
        self.assertEqual({k: inv[k] for k in ("hardware", "known", "boot", "guest", "kvm",
                                              "displayScale", "rootUuid", "hostname")},
                         {"hardware": "t2-mbp16", "known": True, "boot": "refind-grub-recovery",
                          "guest": False, "kvm": True, "displayScale": 1.5, "rootUuid": "1111-uuid",
                          "hostname": "ubuntu"})

    def test_legion_go(self):
        inv = self.machine("LENOVO", "83E1", scale="2")
        self.assertEqual((inv["hardware"], inv["boot"], inv["displayScale"]), ("legion-go", "grub", 2))

    def test_a_vm_guest_is_a_generic_pc(self):
        inv = self.machine("QEMU", "Standard PC (Q35 + ICH9, 2009)", guest=True, kvm=False)
        self.assertEqual((inv["hardware"], inv["known"], inv["guest"], inv["kvm"], inv["displayScale"]),
                         ("generic-pc", False, True, False, 1))
        self.assertEqual(inv["model"], "QEMU Standard PC (Q35 + ICH9, 2009)")

    def test_scale_out_of_range_or_broken_is_1(self):
        self.assertEqual(self.machine("X", "Y", scale="0.5")["displayScale"], 1)
        (self.home / ".config/monitors.xml").write_text("<monitors")
        self.assertEqual(ws_inventory.inventory(self.root, self.home)["displayScale"], 1)

    def test_cli_prints_json(self):
        self.machine("LENOVO", "83E1")
        p = subprocess.run([sys.executable, str(ROOT / "lib/ws_inventory.py"), "--root", str(self.root),
                            "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["hardware"], "legion-go")


class WriteHostTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.config = self.home / "wsconfig"
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.inv = {"hostname": "ubuntu", "user": "u", "model": "Apple Inc. MacBookPro16,1",
                    "hardware": "t2-mbp16", "known": True, "boot": "refind-grub-recovery",
                    "guest": False, "kvm": True, "displayScale": 1.5, "rootUuid": "1111-uuid"}

    def facts(self, name):
        return tomllib.loads((self.config / "hosts" / name / "host.toml").read_text())

    def test_from_the_inventory(self):
        ws_inventory.write_host(self.config, "mac2", self.inv, layers=LAYERS)
        f = self.facts("mac2")
        self.assertEqual(f["host"], {"hostname": "mac2", "user": "u", "wsconfig": "wsconfig"})
        self.assertEqual({k: f["platform"][k] for k in ("hardware", "boot", "rootUuid", "refindEspPartuuid",
                                                       "displayScale")},
                         {"hardware": "t2-mbp16", "boot": "refind-grub-recovery", "rootUuid": "1111-uuid",
                          "refindEspPartuuid": "", "displayScale": 1.5})
        self.assertEqual(f["layers"], LAYERS)
        self.assertTrue((self.config / "hosts/mac2/apt.txt").exists())
        # GRUB: no rEFInd keys.
        inv = self.inv | {"hardware": "generic-pc", "boot": "grub", "displayScale": 1}
        ws_inventory.write_host(self.config, "pc", inv, layers=LAYERS)
        self.assertNotIn("rootUuid", self.facts("pc")["platform"])

    def test_from_a_host_of_the_same_hardware(self):
        base = self.config / "hosts/mbp16"
        (base / "apt").mkdir(parents=True)
        (base / "apt/t2.sources").write_text("Types: deb\n")
        (base / "apt.txt").write_text("linux-t2\n")
        (base / "flatpak.toml").write_text("[choices]\n")
        (base / "host.toml").write_text(
            '[host]\nhostname = "mbp16"\nuser = "king"\nwsconfig = "wsconfig"\n\n'
            '[platform]\nhardware = "t2-mbp16"\nboot = "refind-grub-recovery"\n'
            '# the T2 kernel\nkernelParams = ["quiet", "intel_iommu=on"]\n'
            'rootUuid = "old"\nrefindEspPartuuid = "old-esp"\n\n'
            '[layers]\nvm = true\nwidgets = true\nnativeSteam = false\ngameMode = false\n')
        ws_inventory.write_host(self.config, "mac2", self.inv, base="mbp16",
                                layers=LAYERS | {"vm": False})
        f = self.facts("mac2")
        self.assertEqual(f["host"], {"hostname": "mac2", "user": "u", "wsconfig": "wsconfig"})
        self.assertEqual(f["platform"]["kernelParams"], ["quiet", "intel_iommu=on"])
        self.assertEqual((f["platform"]["rootUuid"], f["platform"]["refindEspPartuuid"]), ("1111-uuid", ""))
        self.assertFalse(f["layers"]["vm"])
        self.assertIn("# the T2 kernel", (self.config / "hosts/mac2/host.toml").read_text())
        self.assertEqual((self.config / "hosts/mac2/apt.txt").read_text(), "linux-t2\n")
        self.assertTrue((self.config / "hosts/mac2/apt/t2.sources").exists())
        self.assertFalse((self.config / "hosts/mac2/flatpak.toml").exists())

    def test_an_existing_host_is_not_touched(self):
        (self.config / "hosts/pc").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            ws_inventory.write_host(self.config, "pc", self.inv, layers=LAYERS)


if __name__ == "__main__":
    unittest.main()
