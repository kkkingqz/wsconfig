"""A throwaway core and configuration for tests of bin/ws: bin/ws, lib/ and
libexec/ copied or stubbed, nix and sudo stubbed in PATH, every call
recorded in CALLS (ws help plan-v2, stage 6)."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

NIX = '''#!/bin/sh
printf 'nix %s\\n' "$*" >> "$CALLS"
case "$1" in
    flake) exit 0 ;;
    build) exit "${BUILD_STATUS:-0}" ;;
    run)
        case "$2" in
            *'#home-manager') exit "${SWITCH_STATUS:-0}" ;;
            *'#nvd') exit 0 ;;
            *) exit 99 ;;
        esac ;;
    *) exit 99 ;;
esac
'''

# Runs only the stubs (and true): nothing of the real system.
SUDO = '''#!/bin/sh
printf 'sudo %s\\n' "$*" >> "$CALLS"
case "$1" in -v|true) exit 0 ;; esac
case "$(command -v "$1")" in
    "$STUBS"/*) exec "$@" ;;
esac
exit 0
'''

# dpkg and apt over $STATE/installed, one package per line.
APT = {
    "dpkg-query": '''pkg="$(eval echo \\${$#})"
grep -qx "$pkg" "$STATE/installed" 2>/dev/null && printf 'install ok installed' && exit 0
exit 1
''',
    "apt-get": '''printf 'apt-get %s\\n' "$*" >> "$CALLS"
case " $* " in
    *" install "*) for a; do case "$a" in -*|install|DPkg*) ;; *) echo "$a" >> "$STATE/installed" ;; esac; done ;;
    *" -s "*) for a; do case "$a" in -*|purge|Debug*) ;; *) echo "Purg $a [1]" ;; esac; done; cat "$STATE/purge-extra" 2>/dev/null ;;
esac
exit 0
''',
    "apt-mark": '''printf 'apt-mark %s\\n' "$*" >> "$CALLS"
exit 0
''',
    "dpkg": '''exit 0
''',
}

# ws-system as ws apply sees it: pending lists $STATE/system-todo, apply
# empties it.
SYSTEM = '''#!/bin/sh
printf 'ws-system %s\\n' "$*" >> "$CALLS"
case "$1" in
    pending) cat "$STATE/system-todo" 2>/dev/null || true ;;
    apply) sudo true; : > "$STATE/system-todo"; exit "${SYSTEM_STATUS:-0}" ;;
esac
'''


class Workspace:
    def __init__(self, root, modules=None, real=("ws_run",)):
        self.root = Path(root)
        self.repo = self.root / "repo"
        self.state = self.root / "state"
        self.bin = self.root / "bin"
        self.calls = self.root / "calls"
        for d in (self.repo / "bin", self.repo / "libexec", self.repo / "flatpak", self.state, self.bin):
            d.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "bin/ws", self.repo / "bin/ws")
        shutil.copytree(ROOT / "lib", self.repo / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "libexec/ws-apt", self.repo / "libexec/ws-apt")
        shutil.copyfile(ROOT / ".gitignore", self.repo / ".gitignore")
        (self.repo / "flatpak/catalog.toml").write_text("[remotes]\n")
        (self.repo / "flake.lock").write_text('{"nodes": {"root": {}}}\n')
        (self.repo / "nix/hosts/test").mkdir(parents=True)
        (self.repo / "nix/hosts/test/host.toml").write_text(
            '[platform]\nboot = "grub"\n\n[layers]\nvm = false\nnativeSteam = false\ngameMode = false\n')
        (self.repo / "nix/hosts/apt.txt").write_text("")
        (self.repo / "nix/hosts/machine-apt.txt").write_text("")
        (self.repo / "nix/hosts/test/apt.txt").write_text("")
        self.write(self.bin / "nix", NIX)
        self.write(self.bin / "sudo", SUDO)
        for name, body in APT.items():
            self.stub(name, body, where="bin")
        self.write(self.repo / "libexec/ws-system", SYSTEM)
        for name, body in (modules or {}).items():
            self.stub(name, body)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "GIT_"))}
        self.env.update(HOME=str(self.root), WS_HOST="test", STATE=str(self.state), STUBS=str(self.bin),
                        XDG_STATE_HOME=str(self.root / ".state"), CALLS=str(self.calls),
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "init")

    @staticmethod
    def write(path, body):
        path.write_text(body)
        path.chmod(0o755)

    def stub(self, name, body, where="libexec"):
        self.write((self.repo / where if where == "libexec" else self.bin) / name, "#!/bin/sh\n" + body)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=getattr(self, "env", None),
                              check=True, text=True, capture_output=True).stdout.strip()

    def ws(self, *args, **env):
        p = subprocess.run([str(self.repo / "bin/ws"), *args], text=True, capture_output=True,
                           env=dict(self.env, **env), stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout, p.stderr

    def take_calls(self):
        """The calls since the last take."""
        lines = self.calls.read_text().splitlines() if self.calls.exists() else []
        self.calls.unlink(missing_ok=True)
        return lines
