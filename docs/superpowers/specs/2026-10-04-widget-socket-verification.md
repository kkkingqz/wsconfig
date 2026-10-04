# Widget socket rewrite verification

Worktree: `/home/king/wsconfig/.worktrees/widget-framework`, original base053d0dc.

- Real Quickshell0.3.0 probe: independent clients/parsers, EOF from orderly close and killed Gio client, responsive asynchronous reader, stale socket replaced after SIGKILL.
- Runtime/model tests: no adapter rejects opening, EOF immediately closes all widgets, replacement adapter owns state, CLI cannot place windows, stale acknowledgements ignored, only preparing has a deadline. Partial UTF-8 reason survives split socket reads.
- Gio client tests use a real temporary Unix server: correlated simultaneous requests, snapshot handshake, EOF reconnect, malformed snapshot disconnect, pending requests cancelled on shutdown.
- Python CLI tests use a real temporary Unix server and a Quickshell executable that always fails if invoked: commands do not launch Quickshell, status/check read only, unknown IDs, EOF, reply mismatch and insecure socket mode rejected.
- QML:300ms gentle reveal and continuous reversal preserved; lazy default retains contents; unloadOnClose unloads and reloads; clamped panel/context/scroll and component error isolation preserved.
- Wayland test with real Gio adapter: example444×604, compact344×264, DPR1.5; both transitions, runtime kill/restart/reconnect, immediate EOF closure. Placement acknowledgement is manual in this isolated test; this does not replace native button observation.
- Idle test uses production QML without test observer and a GLib main loop adapter.60.01s: runtime0.00CPU seconds,0.05 context switches/sec; adapter0.00CPU seconds,0.117 context switches/sec. Context switches are a wakeup proxy, not a kernel wakeup trace. No recurring IPC request/process. The temporary pair has one Quickshell runtime, one standalone GJS test adapter.
- Full Python suite:142 cases; completion tests may be skipped if fish is unavailable in the execution environment. GJS51 cases. Nix widget manifest/QML/tests/runtime, both Home Manager hosts and man are checked before delivery.

Decisions recorded during execution:

1. Use existing inline execution and one final independent review, following the user's authorized continuation.
2. UMask0177 would create Quickshell's own directories with0600, preventing use. Service uses0077 and runtime runs chmod0600 once before accepting hello. Directory0700 protects that short startup interval; no extra Quickshell client is created.
3. Full Nix runtime validation follows the integration-driver migration, rather than running the obsolete driver midway through the rewrite.
4. Standalone GJS top-level await spins during idle in this environment. The performance driver uses GLib.MainLoop, matching Shell's event loop; production client required no change.
5. Use SplitParser's newline byte buffering to preserve partial UTF-8. Complete frames are limited64KiB; incomplete buffering belongs to upstream parser. Same-UID clients are trusted regarding unfinished-frame memory use.

Installed-code GUI matrix remains separate: panel toggle/Esc/outside click/switch, runtime restart with window open, disable/enable, and ws check without new warnings after a normal GNOME login loads the rewritten module. Native session is never forcibly terminated.
