# Widget review fix pass

> **For agentic workers:** Use superpowers:executing-plans for this fix pass. The independent review was completed before the user authorized fixes; do not restart the eight implementation tasks or dispatch another whole-branch review.

**Goal:** Исправить четыре P2 из ревью framework без изменения реестра и пользовательских файлов.
**Architecture:** Controller проверяет собственные ключи реестра. GNOME подавляет свои эффекты только у окон PID/ID текущего runtime; Mutter picking определяет область внешнего клика по реальному input mask.
**Tech Stack:** QML/Quickshell, GJS, GNOME Shell 50, Nix/Home Manager.
**Spec:** ../specs/2026-10-03-widget-framework-design.md

## Global Constraints

Работать в существующем worktree, затем fast-forward ветки wsconfig и доставить через существующего владельца. Пользовательские staged/unstaged файлы сохранить; main не менять. Сессию GNOME не завершать. Все размеры логические, глобальную анимацию/scale не менять.

## Review Focus

- __proto__/constructor во всех внутренних событиях не изменяют прототип.
- Клик снаружи preparing отменяет запрос; focus в этой фазе не закрывает подготовку.
- Нераскрытая область, gutter и округлённый угол выбраны как внешний actor; дочерние поверхности принадлежат family.
- Чужие PID/ID и стандартные анимации других окон сохраняются; disable восстанавливает injected method.
- Surface не отображается до adapter lease: predicate получает проверенный PID до map.

## Task 1: Four reviewed regressions

**Files:** model.mjs/test-model.js; dismissal.mjs/test-dismissal.js; extension.js; new windowEffects.mjs/test-window-effects.js; GnomePopupWindow.qml/WidgetHost.qml; tests/widgets/qml/shell.qml and runtime-client.js; run-tests.js; runbook/live checklist.
**Interfaces:** matchesWidgetWindow(window,snapshot): bool; withoutWidgetEffects(original,getSnapshot): function; pointerInFamily(source,familyActors): bool. Inject the animation predicate with GNOME InjectionManager; clear it on disable. Pass adapterReady from WidgetController to GnomePopupWindow.

- [x] RED→GREEN: unknown inherited keys rejected, prototype unchanged; explicit constructor ID still works.
- [x] RED→GREEN: pointer outside preparing cancels; stale PLACED cannot reopen it; focus preparation suppression preserved.
- [x] RED→GREEN: mask-aware actor ancestry differentiates visible family/transient from background, gutter and hidden region. Wire stage reactive picking, keep event propagation.
- [x] RED→GREEN: scoped map-effect predicate delegates foreign windows, tracks runtime replacement, respects removal; real QML surface remains unmapped without lease and maps after lease.
- [x] Run GJS all suites, Python all tests, Nix manifest/qml/tests/runtime/home hosts/man and Wayland runtime smoke. Native adapter checks stay pending until UUID is loaded.
- [ ] Commit isolated changes, fast-forward wsconfig, apply Home Manager/extensions, verify managed service and original user changes.

Delivery update: during the fix pass another session committed the existing user changes and fast-forwarded main/wsconfig to 36e7773. Rebase the isolated fix commit onto that state, then update wsconfig; preserve the new main commit.

Self-review: all four reviewed defects assigned to Task 1; no new feature or schema version; no additional approval required by the user-authorized fix pass.
