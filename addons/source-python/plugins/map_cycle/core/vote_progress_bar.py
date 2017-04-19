# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from colors import Color
from time import time

# Source.Python
from listeners.tick import Delay
from messages import HintText, HudMsg

# Map Cycle
from .cvars import config_manager
from .mcplayers import mcplayers
from .server_maps import server_map_manager, whatever_entry
from .status import status
from .strings import popups_strings


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def format_map(server_map):
    return "-//-" if server_map is None else server_map.name


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
EXCLUDE_ENTRIES = (whatever_entry, )
REFRESH_INTERVAL = 2
HUDMSG_MSG_COLOR = Color(255, 255, 255)
HUDMSG_MSG_X = -1
HUDMSG_MSG_Y = 0.7
HUDMSG_MSG_EFFECT = 0
HUDMSG_MSG_FADEIN = 0.0
HUDMSG_MSG_FADEOUT = 0
HUDMSG_MSG_HOLDTIME = 2
HUDMSG_MSG_FXTIME = 0
HUDMSG_MSG_CHANNEL = 3


class VoteProgressBar:
    def __init__(self):
        self._refresh_delay = None
        self._message = None
        self._players_total = 0
        self._players_voted = 0

    def count_vote(self, map_):
        self._players_voted += 1

        for exception in EXCLUDE_ENTRIES:
            if map_ is exception:
                return

        maps = list(filter(lambda map_: map_.votes, sorted(
            server_map_manager.values(),
            key=lambda map_: map_.votes,
            reverse=True
        )))

        map_tokens = {
            'map1': popups_strings['vote_progress_map_without_votes'],
            'map2': popups_strings['vote_progress_map_without_votes'],
            'map3': popups_strings['vote_progress_map_without_votes'],
        }
        if len(maps) > 0:
            map_tokens['map1'] = popups_strings[
                'vote_progress_map_with_votes'].tokenized(
                map=maps[0].name,
                votes=maps[0].votes,
            )
            if len(maps) > 1:
                map_tokens['map2'] = popups_strings[
                    'vote_progress_map_with_votes'].tokenized(
                    map=maps[1].name,
                    votes=maps[1].votes,
                )
                if len(maps) > 2:
                    map_tokens['map3'] = popups_strings[
                        'vote_progress_map_with_votes'].tokenized(
                        map=maps[2].name,
                        votes=maps[2].votes,
                    )

        self._message = popups_strings['vote_progress'].tokenized(
            players_voted=self._players_voted,
            players_total=self._players_total,
            **map_tokens,
        )

        self.refresh()

    def refresh(self):
        if self._refresh_delay is not None and self._refresh_delay.running:
            self._refresh_delay.cancel()

        if not config_manager['votemap_show_progress']:
            return

        if self._message:
            time_left = int(status.vote_start_time +
                           config_manager['vote_duration'] - time())

            message_tokenized = self._message.tokenized(
                **self._message.tokens,
                time_left="{:02d}:{:02d}".format(*divmod(time_left, 60)))

            if config_manager['votemap_progress_use_hudmsg']:
                HudMsg(
                    message_tokenized,
                    color1=HUDMSG_MSG_COLOR,
                    x=HUDMSG_MSG_X,
                    y=HUDMSG_MSG_Y,
                    effect=HUDMSG_MSG_EFFECT,
                    fade_in=HUDMSG_MSG_FADEIN,
                    fade_out=HUDMSG_MSG_FADEOUT,
                    hold_time=HUDMSG_MSG_HOLDTIME,
                    fx_time=HUDMSG_MSG_FXTIME,
                    channel=HUDMSG_MSG_CHANNEL,
                ).send()
            else:
                HintText(message_tokenized).send()

        self._refresh_delay = Delay(REFRESH_INTERVAL, self.refresh)

    def start(self):
        self._players_total = len(mcplayers)
        self._players_voted = 0

        self._message = popups_strings['vote_progress'].tokenized(
            players_voted=self._players_voted,
            players_total=self._players_total,
            map1=popups_strings['vote_progress_map_without_votes'],
            map2=popups_strings['vote_progress_map_without_votes'],
            map3=popups_strings['vote_progress_map_without_votes'],
        )
        self.refresh()

    def stop(self):
        if self._refresh_delay is not None and self._refresh_delay.running:
            self._refresh_delay.cancel()

# The singleton object of the VoteProgressBar class
vote_progress_bar = VoteProgressBar()
