from ..resource.config_cvars import cvar_max_extends


class VoteStatus:
    NOT_STARTED = 0
    IN_PROGRESS = 1
    ENDED = 2

# Current vote status
vote_status = VoteStatus.NOT_STARTED

# Current map (MapCycleMap)
current_map = None

# Next map (MapCycleMap) to change to, used by change_level()
next_map = None

# time() when current map started
map_start_time = 0

# time() when current map should end, used by !timeleft command
map_end_time = 0

# How many times "Extend this map..." option has won, used
used_extends = 0

# Set by change_level() if it's waiting for round end to
# change the map
round_end_needed = False


def can_extend():
    return used_extends < cvar_max_extends.get_int()
