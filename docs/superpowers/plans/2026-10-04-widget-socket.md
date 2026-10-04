# Widget socket implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace process-based widget IPC and lease polling with one private Unix socket and zero healthy-idle timers.

**Architecture:** One QML server owns connection roles and broadcasts model snapshots. Gio adapter uses persistent asynchronous transport; Python CLI connects for one command.

**Tech Stack:** Quickshell 0.3.0, Qt/QML, GJS/Gio, Python socket, Home Manager/Nix.

**Spec:** docs/superpowers/specs/2026-10-04-widget-socket-design.md

## Global Constraints

- Preserve animations, dismissal, logical geometry and one shared runtime.
- Wire protocolVersion=2; runtime schemaVersion=2; manifest schemaVersion=1.
- Directory0700/socket0600, same UID; no qs ipc or lease remains.
- Healthy idle has zero recurring timers. Placement timeout2000ms; reconnect250→2000ms.
- Work in existing isolated worktree; preserve primary main and unrelated changes.

## Review Focus

- Adapter takeover and delayed old EOF cannot close the new owner's windows (Task1).
- Fragmented/coalesced/malformed frames cannot dispatch unauthorized commands (Task1/2).
- Disable during connect/read/write cannot resurrect a client or leak retries (Task2).
- CLI connection failure/permissions and response mismatch fail promptly (Task3).
- Unload/reopen and deadline cancellation preserve animation and size (Task4).

### Task 1: Runtime socket and deadline model

**Files:** framework/model.mjs, WidgetController.qml, WidgetIpc.qml, new wire.mjs; tests/widgets/test-model.js, new socket integration helper, check-qml.py and qml/shell.qml.

**Interfaces:** Produces model nextDeadline(state):number|null, events ADAPTER_CONNECTED/DISCONNECTED/TIMEOUT, state.adapter.connected. WidgetIpc consumes controller.dispatch(event):bool and command(action,id):bool; provides protocol frames exactly as spec. Pure wire validateHello(frame):role|null and validateCommand(frame,role):bool validate before dispatch.

- [ ] Write failing tests: opening with no adapter rejected; EOF closes pending/open widgets; deadline only while preparing; malformed/role commands rejected; socket snapshot, concurrency, takeover and stale acknowledgement.
- [ ] Run `gjs -m tests/widgets/run-tests.js model` (Expected: FAIL new behavior) and real QML socket test (Expected: FAIL no socket).
- [ ] Replace lease and polling with connection events, one-shot deadline and SocketServer; connection handlers own parser and replies. Stop old-owner commands after takeover.
- [ ] Run model and `python3 tests/widgets/check-qml.py ./result/bin/qs-widgets` on host (Expected: PASS).
- [ ] Commit runtime changes.

### Task 2: Gio adapter transport

**Files:** extension lib/ipcClient.js, protocol.mjs, extension.js, windowPlacement.js, buttons.mjs, windowEffects.mjs and GJS tests.

**Interfaces:** Consumes wire v2 and state.adapter.connected. Produces IpcClient.call(method:string,args:object={}):Promise<any>, start(), destroy(), shutdown(); onSnapshot(state|null). Verifies server UID; serializes asynchronous writes; pending seq map handles interleaved snapshots/replies.

- [ ] Replace subprocess mocks with fake Unix server; tests require connected snapshot, commands, EOF reconnect, malformed input, cancellation and no healthy-idle sources.
- [ ] Run GJS tests (Expected: FAIL old subprocess client).
- [ ] Implement cancellable async socket transport, correlated replies, bounded command/handshake timeouts and backoff; migrate callers to typed results and data directory configuration.
- [ ] Run `gjs -m tests/widgets/run-tests.js` (Expected: PASS all suites).
- [ ] Commit adapter changes.

### Task 3: Python CLI and service delivery

**Files:** lib/widgets_cli.py, widgets_check.py, widgets/widgets.nix, tests/test_ws_widgets.py.

**Interfaces:** Consumes wire v2. ipc(config,method,*args) retains CompletedProcess-like returncode/stdout/stderr boundary for existing CLI/check callers. Config schema2 contains socketPath expanded from XDG_RUNTIME_DIR prefix; data location XDG_DATA_HOME/workstation/widgets.

- [ ] Add real fake-server tests for safe IDs, typed responses, disconnection, mode/UID validation and no subprocess QS invocation.
- [ ] Run Python widget tests (Expected: FAIL old config/IPC).
- [ ] Implement one-shot Python socket client and diagnostics; deliver data files; service RuntimeDirectoryMode0700 and UMask0077 plus startup socket chmod0600; socket environment.
- [ ] Run Python widget tests and Nix widget checks (Expected: PASS).
- [ ] Commit delivery changes.

### Task 4: Loading policy, integration and documentation

**Files:** manifest.nix, registry.nix, both manifest.mjs, WidgetHost.qml; runtime-client.js, check-runtime.py, runbook/spec/checklist.

**Interfaces:** Consumes complete socket framework; produces unloadOnClose defaultfalse manifest contract and full integration evidence.

- [ ] Add failing default/type/unload-reopen tests. Run manifest/QML suites (Expected: FAIL missing unload behavior).
- [ ] Implement optional unload; rewrite real runtime driver using socket-only adapter and test-only surface observation; update old lease documentation.
- [ ] Run all GJS, Python, QML, Nix checks, Wayland integration and idle60s measurement (Expected: PASS, zero runtime CPU near-idle and no periodic connection processes).
- [ ] Commit final changes; fresh whole-branch review and one fix pass for actionable findings. Deliver to wsconfig branch without changing main.
