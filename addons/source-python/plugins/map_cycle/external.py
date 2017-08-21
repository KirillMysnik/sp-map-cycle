# =============================================================================
# >> IMPORTS
# =============================================================================
from .core.server_maps import server_map_manager
from .core.status import status, VoteStatus
from .map_cycle import (
    change_level as _change_level, finish_vote, launch_likemap_survey,
    launch_vote as _launch_vote, set_next_map as _set_next_map)


# =============================================================================
# >> ALL DECLARATION
# =============================================================================
__all__ = (
    'can_launch_vote',
    'launch_vote',
    'can_finish_vote',
    'finish_vote',
    'get_map_list',
    'get_next_map',
    'set_next_map',
    'change_level',
    'launch_likemap_survey'
)


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def can_launch_vote():
    return status.vote_status == VoteStatus.NOT_STARTED


def launch_vote():
    _launch_vote(scheduled=False)


def can_finish_vote():
    return status.vote_status == VoteStatus.IN_PROGRESS


def get_map_list():
    return sorted(server_map_manager.keys())


def get_next_map():
    return status.next_map.filename


def set_next_map(map_name):
    map_name = map_name.lower()
    if map_name not in server_map_manager:
        raise ValueError("Map {} was not found in Map Cycle".format(map_name))

    server_map = server_map_manager[map_name]
    _set_next_map(server_map)


def change_level(map_name=None):
    if map_name is not None:
        set_next_map(map_name)

    _change_level(round_end=True)
