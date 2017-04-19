# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from enum import IntEnum

# Map Cycle
from .cvars import config_manager


# =============================================================================
# >> CLASSES
# =============================================================================
class VoteStatus(IntEnum):
    NOT_STARTED = 0
    IN_PROGRESS = 1
    ENDED = 2


class Status:
    def __init__(self):
        # Current vote status
        self.vote_status = VoteStatus.NOT_STARTED

        # Current map (MapCycleMap)
        self.current_map = None

        # Next map (MapCycleMap) to change to, used by change_level()
        self.next_map = None

        # time() when current map started
        self.map_start_time = 0

        # time() when current map should end, used by !timeleft command
        self.map_end_time = 0

        # time() when last vote has started, used by keyhint_progress
        self.vote_start_time = 0

        # How many times "Extend this map..." option has won, used
        self.used_extends = 0

        # Set by change_level() if it's waiting for round end to
        # change the map
        self.round_end_needed = False

    def can_extend(self):
        return self.used_extends < config_manager['max_extends']

# The singleton object of the Status class
status = Status()
