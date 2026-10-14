# =============================================================================
# Fish common config — Linux + macOS
# =============================================================================

if status is-interactive
    set -g fish_greeting

    # Standard Emacs-like editing
    fish_default_key_bindings

    # -------------------------------------------------------------------------
    # fzf
    # -------------------------------------------------------------------------
    if type -q fzf
        # Ctrl+T belongs to Ghostty (new tab).
        # Keep Ctrl+R = history and Alt+C = directory search.
        set -lx FZF_CTRL_T_COMMAND ""
        fzf --fish | source
        # fzf >= 0.70 also takes Shift+Tab (fzf_complete); keep fish's own
        # complete-and-search there, as with older fzf.
        bind -e shift-tab
        bind -M insert -e shift-tab
    end

    # -------------------------------------------------------------------------
    # zoxide
    # -------------------------------------------------------------------------
    if type -q zoxide
        # Fish >= 4.8 embeds cd.fish instead of installing it on disk.
        # Older/current zoxide init code still expects the physical file.
        if not functions --query __zoxide_cd_internal
            functions cd | string replace --regex -- "^function cd\s" "function __zoxide_cd_internal " | source
        end

        zoxide init fish | source
    end
end

# Custom Alt+C directory browser
if status is-interactive
    bind \ec fzf_cd_browser
    bind -M insert \ec fzf_cd_browser
end
