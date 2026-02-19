# Standalone version of community core/modes/modes_not_dragon.talon
# Disabled: "sleep all" command (requires user.switcher_hide_running,
#   user.history_disable, user.homophones_hide, user.help_hide, user.mouse_sleep)
# Disabled: deprecation warning on "talon sleep" (requires user.deprecate_command)
mode: command
mode: dictation
mode: sleep
not speech.engine: dragon
-
^go to sleep [<phrase>]$: speech.disable()
^talon sleep [<phrase>]$: speech.disable()

# DISABLED — requires actions not available in standalone:
# ^sleep all [<phrase>]$:
#     user.switcher_hide_running()
#     user.history_disable()
#     user.homophones_hide()
#     user.help_hide()
#     user.mouse_sleep()
#     speech.disable()
