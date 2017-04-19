# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from time import time

# Source.Python
from messages import SayText2
from players.dictionary import PlayerDictionary
from players.entity import Player

# Map Cycle
from .cvars import config_manager
from .session_players import session_players
from .status import status, VoteStatus
from .strings import COLOR_SCHEME, common_strings


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def tell(players, message):
    """Send a SayText2 message to a list of Player instances."""
    if isinstance(players, Player):
        players = (players, )

    player_indexes = [player.index for player in players]

    message = message.tokenized(**message.tokens, **COLOR_SCHEME)
    message = common_strings['chat_base'].tokenized(
        message=message, **COLOR_SCHEME)

    SayText2(message=message).send(*player_indexes)


def broadcast(message):
    """Send a SayText2 message to all registered users."""
    tell([mcplayer.player for mcplayer in mcplayers.values()], message)


# =============================================================================
# >> CLASSES
# =============================================================================
class MCPlayerDictionary(PlayerDictionary):
    def get_nominated_maps(self):
        for mcplayer in self.values():
            if mcplayer.nominated_map is None:
                continue

            yield mcplayer.nominated_map

    def reset_nominated_maps(self):
        for mcplayer in self.values():
            mcplayer.reset(reset_nominated_map=True)

    def get_voted_maps(self):
        for mcplayer in self.values():
            if mcplayer.voted_map is None:
                continue

            yield mcplayer.voted_map

    def reset_voted_maps(self):
        for mcplayer in self.values():
            mcplayer.reset(reset_voted_map=True)

    def count_rtv_ratio(self):
        total_players, total_rtv = 0, 0
        for mcplayer in self.values():
            if mcplayer.is_bot():
                continue

            if mcplayer.used_rtv:
                total_rtv += 1

            total_players += 1

        # Be ready for ZeroDivisionError
        return total_rtv / total_players

    def reset_rtv(self):
        for mcplayer in self.values():
            mcplayer.reset(reset_used_rtv=True)

    def reset_all(self):
        for mcplayer in self.values():
            mcplayer.reset(reset_voted_map=True, reset_nominated_map=True,
                           reset_used_rtv=True)

    def on_automatically_removed(self, index):
        mcplayer = self[index]
        if mcplayer.is_bot():
            return

        if status.vote_status == VoteStatus.NOT_STARTED:
            from ..map_cycle import check_if_enough_rtv

            check_if_enough_rtv()

        elif status.vote_status == VoteStatus.IN_PROGRESS:
            from ..map_cycle import check_if_enough_votes

            check_if_enough_votes()


class MCPlayer:
    def __init__(self, index):
        self.player = Player(index)

        self._voted_map = None
        self._nominated_map = None
        self._used_rtv = False

        steamid = self.player.steamid
        self.session_player = session_players[steamid]

    @property
    def voted_map(self):
        return self._voted_map

    @property
    def nominated_map(self):
        return self._nominated_map

    @property
    def used_rtv(self):
        return self._used_rtv

    def is_bot(self):
        return 'BOT' in self.player.steamid

    def reset(self, reset_voted_map=False, reset_nominated_map=False,
              reset_used_rtv=False):

        if reset_voted_map:
            self._voted_map = None

        if reset_nominated_map:
            self._nominated_map = None

        if reset_used_rtv:
            self._used_rtv = False

    def send_popup(self, popup):
        popup.send(self.player.index)

    def get_vote_denial_reason(self):
        if not config_manager['votemap_enable']:
            return common_strings['error disabled']

        if status.vote_status != VoteStatus.IN_PROGRESS:
            return common_strings['error not_in_progress']

        if (self._voted_map is not None and
                not config_manager['votemap_allow_revote']):

            return common_strings['error already_voted'].tokenized(
                map=self._voted_map.name)

        return None

    def get_nominate_denial_reason(self):
        if (not config_manager['votemap_enable'] or
                not config_manager['nominate_enable']):

            return common_strings['error disabled']

        if status.vote_status != VoteStatus.NOT_STARTED:
            return common_strings['error in_progress']

        if (self._nominated_map is not None and
                not config_manager['nominate_allow_revote']):

            return common_strings['error already_nominated'].tokenized(
                map=self._nominated_map.name)

        return None

    def get_rtv_denial_reason(self):
        if (not config_manager['votemap_enable'] or
                not config_manager['rtv_enable']):

            return common_strings['error disabled']

        if status.vote_status != VoteStatus.NOT_STARTED:
            return common_strings['error in_progress']

        if self._used_rtv:
            return common_strings['error rtv_already_used']

        seconds = time() - status.map_start_time - config_manager['rtv_delay']
        if seconds < 0:
            return common_strings['error rtv_too_soon'].tokenized(
                seconds=-int(seconds))

        return None

    def get_likemap_denial_reason(self):
        if not config_manager['likemap_enable']:
            return common_strings['error disabled']

        if self.session_player.rating != 0:
            return common_strings['error likemap_already_used']

        return None

    def get_nextmap_denial_reason(self):
        if not config_manager['nextmap_enable']:
            return common_strings['error disabled']

        return None

    def get_timeleft_denial_reason(self):
        if not config_manager['timeleft_enable']:
            return common_strings['error disabled']

        return None

    def vote_callback(self, map_):
        from ..map_cycle import check_if_enough_votes

        reason = self.get_vote_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self._voted_map = map_

        if config_manager['votemap_chat_reaction'] == 3:

            # Show both name and choice
            broadcast(common_strings['chat_reaction3'].tokenized(
                      player=self.player.name, map=map_.name))

        elif config_manager['votemap_chat_reaction'] == 1:

            # Show the name only
            broadcast(common_strings['chat_reaction1'].tokenized(
                player=self.player.name))

        elif config_manager['votemap_chat_reaction'] == 2:

            # Show the choice only
            broadcast(common_strings['chat_reaction2'].tokenized(
                map=map_.name))

        check_if_enough_votes()

    def nominate_callback(self, map_):
        reason = self.get_nominate_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self._nominated_map = map_

        broadcast(common_strings['nominated'].tokenized(
            player=self.player.name, map=map_.name))

    def rtv_callback(self):
        from ..map_cycle import check_if_enough_rtv

        reason = self.get_rtv_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self._used_rtv = True

        broadcast(common_strings['used_rtv'].tokenized(
            player=self.player.name))

        check_if_enough_rtv()

    def likemap_callback(self, rating):
        reason = self.get_likemap_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self.session_player.rating = rating

    def nextmap_callback(self):
        reason = self.get_nextmap_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        if status.next_map is None:
            tell(self.player, common_strings['nextmap_unknown'])
        else:
            tell(self.player, common_strings['nextmap_is'].tokenized(
                map=status.next_map.name))

    def timeleft_callback(self):
        reason = self.get_timeleft_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        if config_manager['timelimit'] == 0:
            tell(self.player, common_strings['timeleft_never'])
            return

        if status.round_end_needed:
            tell(self.player, common_strings['timeleft_last_round'])
            return

        seconds = int(status.map_end_time - time())
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        tell(self.player, common_strings['timeleft_timeleft'].tokenized(
            timeleft="{:02}:{:02}:{:02}".format(hours, minutes, seconds)))


# =============================================================================
# >> PLAYER DICTIONARIES
# =============================================================================
mcplayers = MCPlayerDictionary(factory=MCPlayer)
