#!/bin/bash
# sync_from_active.sh — Copy core recall files from the active Talon installation
# to this standalone project. Run from the standalone recall directory.
#
# Usage: .scripts/sync_from_active.sh [--dry-run]   (run from the standalone recall directory)
#
# --dry-run  Show what would be synced without copying any files.
#
# Files synced (active -> standalone):
#   recall.py, recall_state.py, recall_terminal.py, recall_commands.py,
#   recall.talon, recall_overlay.py,
#   recall_combine_mode.talon, recall_overlay_keys.talon,
#   forbidden_recall_names.talon-list
#
# Community dependencies synced (exact copies preserving directory structure):
#   core/user_settings.py
#   core/create_spoken_forms.py
#   core/app_running.py
#   core/text/{text_and_dictation,phrase_history}.py + talon-lists
#   core/numbers/numbers.py
#   core/keys/{keys,symbols}.py + talon-lists (incl. win/ and mac/)
#   core/edit/{edit,insert_between}.py
#   core/modes/dictation_mode.talon
#   core/formatters/formatters.py + talon-lists
#   core/vocabulary/vocabulary.py (vocabulary.talon-list is NOT synced)
#   core/abbreviate/abbreviate.py
#   core/contacts/contacts.py
#   core/app_switcher/app_name_overrides.{linux,mac,windows}.csv
#   core/windows_and_tabs/windows_and_tabs.py
#   utils/overlay_kit.py, utils/overlay_dismiss.talon (from trillium/utils/)
#
# Files NOT synced (standalone-only):
#   recall_core.py, basic_keys.talon, dictation_bravely.talon,
#   dictation_ender.py, dictation_ender.talon-list,
#   mode_indicator.py, modes.talon,
#   core/modes/{modes_not_dragon,sleep_mode,sleep_mode_not_dragon,
#     sleep_mode_wakeup}.talon (custom versions with disabled lines)
#   core/app_switcher/app_switcher.py (sanitized — no OBS imports)
#   core/windows_and_tabs/window_management.talon (subset — focus/window only)
#   README.md, saved_windows.json
#   core/vocabulary/vocabulary.talon-list (sanitized default, not personal)
#
# Sanitized files (from .scripts/, always overwritten):
#   recall_commands.talon-list — personal commands stripped
#   core/app_switcher/app_switcher.py — OBS imports removed
#   core/windows_and_tabs/window_management.talon — focus/window commands only

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

ACTIVE_DIR="$HOME/.talon/user/trillium_talon/plugin/recall"
STANDALONE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMMUNITY_DIR="$HOME/.talon/user/trillium_talon"

SYNC_FILES=(
    recall.py
    recall_state.py
    recall_terminal.py
    recall_commands.py
    recall.talon
    recall_overlay.py
    recall_combine_mode.talon
    recall_overlay_keys.talon
    forbidden_recall_names.talon-list
)

if [ ! -d "$ACTIVE_DIR" ]; then
    echo "Error: Active recall directory not found at $ACTIVE_DIR"
    exit 1
fi

[ "$DRY_RUN" -eq 1 ] && echo "(dry run — no files will be written)"
echo ""

changed=0

# ── Post-copy import rewrites ─────────────────────────────────────────
# Some recall plugin files use deep relative imports that don't resolve
# in the standalone's flatter package structure. List rewrites as
# "filename:old_import:new_import" — applied after each cp in the recall
# plugin loop below.
#
# recall_overlay.py: ...trillium.utils.overlay_kit  →  .utils.overlay_kit
#   (active lives 3 levels deep; standalone is at root)

POST_COPY_REWRITES=(
    "recall_overlay.py:from ...trillium.utils.overlay_kit import:from .utils.overlay_kit import"
)

echo "── Recall plugin files ──────────────────────────────────────────"
for file in "${SYNC_FILES[@]}"; do
    src="$ACTIVE_DIR/$file"
    dst="$STANDALONE_DIR/$file"

    if [ ! -f "$src" ]; then
        echo "  SKIP  $file (not in active)"
        continue
    fi

    # Apply any post-copy rewrites to a temp file for diffing purposes
    tmp=$(mktemp)
    cp -f "$src" "$tmp"
    for rewrite in "${POST_COPY_REWRITES[@]}"; do
        rw_file="${rewrite%%:*}"
        rw_rest="${rewrite#*:}"
        rw_old="${rw_rest%%:*}"
        rw_new="${rw_rest##*:}"
        if [ "$file" = "$rw_file" ]; then
            sed -i'' -e "s|${rw_old}|${rw_new}|g" "$tmp"
        fi
    done

    if [ -f "$dst" ] && diff -q "$tmp" "$dst" > /dev/null 2>&1; then
        echo "  OK    $file (identical)"
        rm -f "$tmp"
    else
        if [ "$DRY_RUN" -eq 0 ]; then
            cp -f "$tmp" "$dst"
        fi
        rm -f "$tmp"
        echo "  SYNC  $file"
        changed=$((changed + 1))
    fi
done

# ── Community dependencies (exact copies, preserving directory structure) ──
# Format: "source_path_relative_to_community:dest_path_relative_to_standalone"

echo ""
echo "── Community dependencies ─────────────────────────────────────"

COMMUNITY_SYNC=(
    # Infrastructure
    "core/user_settings.py:core/user_settings.py"
    "core/create_spoken_forms.py:core/create_spoken_forms.py"
    "core/app_running.py:core/app_running.py"
    # App switcher (CSV overrides only — app_switcher.py is sanitized, see below)
    "core/app_switcher/app_name_overrides.linux.csv:core/app_switcher/app_name_overrides.linux.csv"
    "core/app_switcher/app_name_overrides.mac.csv:core/app_switcher/app_name_overrides.mac.csv"
    "core/app_switcher/app_name_overrides.windows.csv:core/app_switcher/app_name_overrides.windows.csv"
    # Windows and tabs (windows_and_tabs.py only — window_management.talon is sanitized)
    "core/windows_and_tabs/windows_and_tabs.py:core/windows_and_tabs/windows_and_tabs.py"
    # Text & dictation
    "core/text/text_and_dictation.py:core/text/text_and_dictation.py"
    "core/text/phrase_history.py:core/text/phrase_history.py"
    "core/text/phrase_ender.talon-list:core/text/phrase_ender.talon-list"
    "core/text/prose_snippets.talon-list:core/text/prose_snippets.talon-list"
    "core/text/prose_modifiers.talon-list:core/text/prose_modifiers.talon-list"
    "core/text/currency.talon-list:core/text/currency.talon-list"
    # Numbers
    "core/numbers/numbers.py:core/numbers/numbers.py"
    "core/numbers/ordinals.py:core/numbers/ordinals.py"
    # Keys
    "core/keys/keys.py:core/keys/keys.py"
    "core/keys/symbols.py:core/keys/symbols.py"
    "core/keys/letter.talon-list:core/keys/letter.talon-list"
    "core/keys/arrow_key.talon-list:core/keys/arrow_key.talon-list"
    "core/keys/number_key.talon-list:core/keys/number_key.talon-list"
    "core/keys/function_key.talon-list:core/keys/function_key.talon-list"
    "core/keys/keypad_key.talon-list:core/keys/keypad_key.talon-list"
    "core/keys/win/modifier_key.talon-list:core/keys/win/modifier_key.talon-list"
    "core/keys/win/special_key.talon-list:core/keys/win/special_key.talon-list"
    "core/keys/mac/modifier_key.talon-list:core/keys/mac/modifier_key.talon-list"
    "core/keys/mac/special_key.talon-list:core/keys/mac/special_key.talon-list"
    # Edit
    "core/edit/edit.py:core/edit/edit.py"
    "core/edit/insert_between.py:core/edit/insert_between.py"
    # Modes
    "core/modes/dictation_mode.talon:core/modes/dictation_mode.talon"
    "core/modes/to_wake_mode.talon:core/modes/to_wake_mode.talon"
    # NOTE: modes_not_dragon, sleep_mode, sleep_mode_not_dragon, sleep_mode_wakeup
    # are standalone custom versions (disabled lines noted in comments).
    # They are NOT synced from community.
    # Formatters
    "core/formatters/formatters.py:core/formatters/formatters.py"
    "core/formatters/code_formatter.talon-list:core/formatters/code_formatter.talon-list"
    "core/formatters/prose_formatter.talon-list:core/formatters/prose_formatter.talon-list"
    "core/formatters/reformatter.talon-list:core/formatters/reformatter.talon-list"
    "core/formatters/word_formatter.talon-list:core/formatters/word_formatter.talon-list"
    # Vocabulary
    "core/vocabulary/vocabulary.py:core/vocabulary/vocabulary.py"
    # NOTE: vocabulary.talon-list is NOT synced (standalone has sanitized default)
    # Abbreviate
    "core/abbreviate/abbreviate.py:core/abbreviate/abbreviate.py"
    # Contacts
    "core/contacts/contacts.py:core/contacts/contacts.py"
    # Trillium custom commands (flattened into standalone root)
    "trillium/clear_text_commands.py:clear_text_commands.py"
    "trillium/clear_text_commands.talon:clear_text_commands.talon"
    # Trillium shared overlay utilities
    "trillium/utils/overlay_kit.py:utils/overlay_kit.py"
    "trillium/utils/overlay_dismiss.talon:utils/overlay_dismiss.talon"
)

for entry in "${COMMUNITY_SYNC[@]}"; do
    src_rel="${entry%%:*}"
    dst_rel="${entry##*:}"
    src="$COMMUNITY_DIR/$src_rel"
    dst="$STANDALONE_DIR/$dst_rel"

    if [ ! -f "$src" ]; then
        echo "  SKIP  $dst_rel (source not found: $src_rel)"
        continue
    fi

    if [ -f "$dst" ] && diff -q "$src" "$dst" > /dev/null 2>&1; then
        echo "  OK    $dst_rel"
    else
        if [ "$DRY_RUN" -eq 0 ]; then
            mkdir -p "$(dirname "$dst")"
            cp -f "$src" "$dst"
        fi
        echo "  SYNC  $dst_rel"
        changed=$((changed + 1))
    fi
done

# ── Sanitized files ──────────────────────────────────────────────────
# These are standalone-only versions stored in .scripts/ that replace
# their community counterparts. Always overwritten during sync.
# Format: "source_in_.scripts:dest_relative_to_standalone"

echo ""
echo "── Sanitized files ────────────────────────────────────────────"

SANITIZED_FILES=(
    "recall_commands.sanitized.talon-list:recall_commands.talon-list"
    "app_switcher.sanitized.py:core/app_switcher/app_switcher.py"
    "window_management.sanitized.talon:core/windows_and_tabs/window_management.talon"
)

for entry in "${SANITIZED_FILES[@]}"; do
    src_name="${entry%%:*}"
    dst_rel="${entry##*:}"
    src="$STANDALONE_DIR/.scripts/$src_name"
    dst="$STANDALONE_DIR/$dst_rel"

    if [ ! -f "$src" ]; then
        echo "  SKIP  $dst_rel (no sanitized source: .scripts/$src_name)"
        continue
    fi

    if [ -f "$dst" ] && diff -q "$src" "$dst" > /dev/null 2>&1; then
        echo "  OK    $dst_rel (sanitized, identical)"
    else
        if [ "$DRY_RUN" -eq 0 ]; then
            mkdir -p "$(dirname "$dst")"
            cp -f "$src" "$dst"
        fi
        echo "  SYNC  $dst_rel (sanitized)"
        changed=$((changed + 1))
    fi
done

# ── Summary ──────────────────────────────────────────────────────────

echo ""
if [ "$changed" -eq 0 ]; then
    echo "Already in sync."
elif [ "$DRY_RUN" -eq 1 ]; then
    echo "Would sync $changed file(s). (dry run — nothing written)"
else
    echo "Synced $changed file(s)."
fi

# ── Dependency check ─────────────────────────────────────────────────
# Find actions.user.X() calls in recall .py files that aren't defined
# anywhere in the standalone package (recall files + core/ files).

echo ""
echo "Checking dependencies..."

# Collect all actions.user.X calls from recall python files
calls=$(grep -rohP 'actions\.user\.\w+' \
    "$STANDALONE_DIR/recall.py" \
    "$STANDALONE_DIR/recall_state.py" \
    "$STANDALONE_DIR/recall_terminal.py" \
    "$STANDALONE_DIR/recall_commands.py" \
    "$STANDALONE_DIR/recall_overlay.py" 2>/dev/null \
    | sed 's/actions\.user\.//' | sort -u)

# Collect all action definitions from all .py files in the standalone package
defs=$(grep -rohP 'def \w+\(' \
    "$STANDALONE_DIR"/*.py \
    "$STANDALONE_DIR"/core/*.py \
    "$STANDALONE_DIR"/core/text/*.py \
    "$STANDALONE_DIR"/core/numbers/*.py \
    "$STANDALONE_DIR"/core/keys/*.py \
    "$STANDALONE_DIR"/core/edit/*.py \
    "$STANDALONE_DIR"/core/formatters/*.py \
    "$STANDALONE_DIR"/core/vocabulary/*.py \
    "$STANDALONE_DIR"/core/abbreviate/*.py \
    "$STANDALONE_DIR"/core/contacts/*.py \
    "$STANDALONE_DIR"/core/app_switcher/*.py \
    "$STANDALONE_DIR"/core/windows_and_tabs/*.py 2>/dev/null \
    | sed 's/def //; s/(//' | sort -u)

missing=0
for call in $calls; do
    if ! echo "$defs" | grep -qx "$call"; then
        echo "  MISSING  actions.user.$call — not defined in standalone"
        missing=$((missing + 1))
    fi
done

if [ "$missing" -eq 0 ]; then
    echo "All dependencies satisfied."
else
    echo ""
    echo "WARNING: $missing action(s) used but not defined in standalone."
    echo "Add shims to recall_core.py for the missing actions above."
    exit 1
fi
