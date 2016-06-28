# Main vote popup is created in launch_vote() and destroyed in finish_vote()
popup_main = None

# Nomination popup is recreated by reload_map_list() every time it's called
popup_nominate = None

# LikeMap popup is created in map_cycle_user.py once and never destroyed
popup_likemap = None
