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
- After destroying the real GJS client, runtime unmaps the open window after
  lease expiry. All temporary runtime/client processes are terminated by tests.
- Headless clamp: compact panel 160×120, fixed surface 184×144, context 128×88,
  overflowing content remains scrollable. Broken QML is isolated.
  Contents load on first open, remain instantiated after close; disabled
  animations finish correctly. Pure button policy reports component errors.

Pending after loading the extension in a new GNOME session:

- Both buttons; anchoring gap, focus, no center flash, no decorations and no
  duplicate compositor animation; actual panel coverage at scale 1.5.
- Esc, own-button rapid toggle, external Shell/client clicks, focus/transients;
  invisible parts and gutter pass pointer input through.
- Overview, workspace, lock/unlock, disable/re-enable, runtime restart;
  no stale windows, Shell signals, timers or subscriptions.
- Ubuntu Dock, Alt-Tab and Tiling Assistant exclusion; monitor/workarea changes.
- Additional scales and a second monitor: unavailable in this run; not passed.

Reason: the new UUID is installed on disk, but `gnome-extensions info
workstation-widgets@local` says it does not exist in the running Shell.
The session was not restarted and the user was not logged out automatically.
