# Standalone version of community core/modes/sleep_mode_not_dragon.talon
# Disabled: deep_sleep tag check (requires user.deep_sleep tag)
# Disabled: deprecation warning on "talon wake" (requires user.deprecate_command)
mode: command
mode: dictation
mode: sleep
not speech.engine: dragon
-

^(wake up)+$: speech.enable()
^(talon wake)+$: speech.enable()

# DISABLED — requires actions not available in standalone:
# ^talon wake [<phrase>]$:
#     speech.enable()
#     user.deprecate_command("2025-06-25", "talon wake (without dragon)", "wake up")
