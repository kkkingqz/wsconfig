# Live evidence — 2026-10-03

Environment: Ubuntu GNOME Shell 50.1, Wayland; eDP-1 native 3072×1920,
logical 2048×1280, scale 1.5. Scoped Quickshell 0.3.0 / Qt 6.11.2 / Mesa 26.1.8.

Verified:

- Runtime probe: Qt DPR 1.5, transparent Wayland window, 420×580 logical.
- Production manifest loads both components; real GJS client receives
  stateChanged and snapshot, obtains/renews lease and addresses both IDs.
- Forced listener loss during opening reconnects to the same runtime instance
  and request; status remains authoritative. No stale request is restored.
- Manual placement acknowledgement starts animation, hide waits for animation.
- Real compositor frames including gutters: example 444×604, compact 344×264.
  Observed positions (802,319) and (852,489) are compositor default placements
  in the temporary test; anchoring under a panel button has **not** been verified.
- After the lazy-loading changes, both actual Qt surfaces again report mapped,
  visible, expected dimensions and DPR 1.5 through a test-only inspector.
  Repeating compositor frame inspection was unavailable: the existing
  WindowControl D-Bus object no longer exists. This is reported explicitly.
- After destroying the real GJS client, runtime unmaps the open window after
  lease expiry. All temporary runtime/client processes are terminated by tests.
- Headless clamp: compact panel 160×120, fixed surface 184×144, context 128×88,
  overflowing content remains scrollable. Broken QML is isolated.
  Contents load on first open, remain instantiated after close; disabled
  animations finish correctly. Pure button policy reports component errors.
- Deployment: current `main` history merged into `wsconfig`; primary checkout
  switched to `wsconfig`, with existing staged/unstaged files and untracked
  user document preserved byte for byte. No merge into `main` was performed.
- After synchronization: all 122 Python tests and 37 GJS tests pass; Nix
  widgets-manifest/qml/tests/runtime, both Home Manager hosts and man build.
- `ws switch` and `ws apply extensions` completed. Production QML link resolves
  to `/home/king/wsconfig/widgets/quickshell`; runtime/manifest and CLI delivered.
  Managed service is enabled and active; restart creates a new runtime PID,
  IPC PID agrees with systemd, both widget IDs start closed, NRestarts is zero.
- Production owner check: three passes, two warnings, zero failures. Warnings
  are the unloaded GNOME adapter and absent lease; native window checks remain
  pending. Shell EnableExtension returns false for the new UUID;
  ReloadExtension returns UnknownMethod in the running GNOME 50.1.
- Managed runtime without adapter: valid `show` enters preparing, never enters
  opening/open, then closes with placement timeout after two seconds. Unknown
  ID is rejected; neither command creates another runtime process.

Review fix pass, verified separately on the same date:

- 46 GJS cases pass, including inherited ID rejection, cancellation during
  preparing, masked-area pointer policy and scoped Shell effect suppression.
  The QML/typed IPC checks also reject prototype keys in the actual Qt engine.
- The Wayland smoke confirms that surfaces remain unmapped before adapter
  readiness, then map with the expected dimensions and DPR 1.5. Compositor
  inspection is available again: example frame (802,319,444,604), compact
  (852,489,344,264). These are temporary test placements, not button anchoring.
- All 122 Python tests pass (701.694s). Nix widgets-manifest/qml/tests/runtime,
  both Home Manager hosts and man pass.
- Native effect injection and reactive picking were checked against Shell and
  Mutter 50.1 sources. Their integrated GUI behavior remains pending below.

Subsequent native-session evidence during delivery:

- After the user returned, the new GNOME session already had the extension
  ACTIVE. The managed runtime PID is 3890; adapter lease is ready, NRestarts=0.
- Both production IDs complete the real GNOME placement handshake and remain
  open; the adapter acknowledges only after verifying the compositor frame.
  Panel sizes are 420×580 and 320×240. Explicit hide completes, and restoring
  focus to the previous application closes compact through the native adapter.
- WindowControl lists NORMAL windows only; widgets disappear from that list
  after the adapter changes their native type. It cannot inspect their final
  frame/focus properties. This is not evidence for every Dock/Alt-Tab behavior.
- Live Qt IPC rejects __proto__ and constructor. Production check now reports
  five passes, zero warnings and zero failures; both widgets are left closed.
- Screenshot D-Bus denies access. No screenshot or visual animation/button
  verdict was obtained, and no unsafe Shell evaluation was enabled.
- Fixes are committed on wsconfig (c0498c7), rebased onto the existing 36e7773
  user commit. main remains at 36e7773; original user file hashes are preserved.
  ws switch and extension-owner delivery succeed; installed sources match.

Remaining native GUI matrix:

- Both buttons; anchoring gap, focus, no center flash, no decorations and no
  duplicate compositor animation; actual panel coverage at scale 1.5.
- Esc, own-button rapid toggle, external Shell/client clicks, focus/transients;
  invisible parts and gutter pass pointer input through.
- Overview, workspace, lock/unlock, disable/re-enable, runtime restart;
  no stale windows, Shell signals, timers or subscriptions.
- Ubuntu Dock, Alt-Tab and Tiling Assistant exclusion; monitor/workarea changes.
- Additional scales and a second monitor: unavailable in this run; not passed.

Earlier installation evidence predates the new session; the extension is now
ACTIVE. The remaining matrix needs direct GUI observation and input. This agent
did not restart the session or log the user out.
