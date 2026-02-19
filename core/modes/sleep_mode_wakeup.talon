# Standalone version of community core/modes/sleep_mode_wakeup.talon
# Disabled: parrot(cluck) and "welcome back" commands
#   (require user.mouse_wake, user.history_enable, user.talon_mode)
# Disabled: deep_sleep tag check (requires user.deep_sleep tag)
mode: sleep
-

# DISABLED — requires actions not available in standalone:
# parrot(cluck):
#     user.mouse_wake()
#     user.talon_mode()
#
# ^(welcome back)+$:
#     user.mouse_wake()
#     user.history_enable()
#     user.talon_mode()
