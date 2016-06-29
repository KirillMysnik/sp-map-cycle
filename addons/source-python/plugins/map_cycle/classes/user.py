from datetime import datetime
from time import time

from menus import Text
from menus.radio import SimpleRadioMenu, SimpleRadioOption
from messages import SayText2
from players.entity import Player

from .session_user import session_user_manager

from ..namespaces import popups, status

from ..resource.config_cvars import config_manager

from ..resource.strings import COLOR_SCHEME, strings_common, strings_popups


class UserManager(dict):
    def create(self, player):
        self[player.index] = MapCycleUser(self, player)
        return self[player.index]

    def delete(self, index):
        self[index].session_user.reset_disconnect()
        del self[index]

    def get_nominated_maps(self):
        for user in self.values():
            if user.nominated_map is None:
                continue

            yield user.nominated_map

    def reset_nominated_maps(self):
        for user in self.values():
            user.nominated_map = None

    def get_voted_maps(self):
        for user in self.values():
            if user.voted_map is None:
                continue

            yield user.voted_map

    def reset_voted_maps(self):
        for user in self.values():
            user.voted_map = None

    def count_rtv(self):
        total_users = 0
        total_rtv = 0
        for user in self.values():
            if user.used_rtv:
                total_rtv += 1
            total_users += 1

        # Be ready to catch ZeroDivisionError
        return total_rtv / total_users

    def reset_rtv(self):
        for user in self.values():
            user.used_rtv = False

    def reset_users(self):
        for user in self.values():
            user.reset()

user_manager = UserManager()


class MapCycleUser:
    def __init__(self, user_manager, player):
        self._user_manager = user_manager

        self.player = player

        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

        steamid = player.steamid.upper()
        self.session_user = session_user_manager.get_or_create(steamid)

    def reset(self):
        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

    def send_popup(self, popup):
        popup.send(self.player.index)

    def get_vote_denial_reason(self):
        if not config_manager['votemap_enable']:
            return strings_common['error_disabled']

        if status.vote_status != status.VoteStatus.IN_PROGRESS:
            return strings_common['error_not_in_progress']

        if popups.popup_main is None:
            return strings_common['error_not_in_progress']

        if (self.voted_map is not None and
                not config_manager['votemap_allow_revote']):

            return strings_common['error_already_voted'].tokenize(
                map=self.voted_map.name)

        return None

    def get_nominate_denial_reason(self):
        if not (config_manager['votemap_enable'] and
                config_manager['nominate_enable']):

            return strings_common['error_disabled']

        if status.vote_status != status.VoteStatus.NOT_STARTED:
            return strings_common['error_in_progress']

        if (self.nominated_map is not None and
                not config_manager['nominate_allow_revote']):

            return strings_common['error_already_nominated'].tokenize(
                map=self.nominated_map.name)

        return None

    def get_rtv_denial_reason(self):
        if not (config_manager['votemap_enable'] and
                config_manager['rtv_enable']):

            return strings_common['error_disabled']

        if status.vote_status != status.VoteStatus.NOT_STARTED:
            return strings_common['error_in_progress']

        if self.used_rtv:
            return strings_common['error_rtv_already_used']

        seconds = time() - status.map_start_time - config_manager['rtv_delay']
        if seconds < 0:
            return strings_common['error_rtv_too_soon'].tokenize(
                seconds=-seconds)

        return None

    def get_likemap_denial_reason(self):
        if not config_manager['likemap_enable']:
            return strings_common['error_disabled']

        if self.session_user.rating != 0:
            return strings_common['error_likemap_already_used']

        return None

    def get_nextmap_denial_reason(self):
        if not config_manager['nextmap_enable']:
            return strings_common['error_disabled']

        return None

    def get_timeleft_denial_reason(self):
        if not config_manager['timeleft_enable']:
            return strings_common['error_disabled']

        return None

    def vote_callback(self, map_):
        from ..map_cycle import check_if_enough_votes

        reason = self.get_vote_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self.voted_map = map_

        # ... chat message
        if 1 & config_manager['votemap_chat_reaction']:
            if 2 & config_manager['votemap_chat_reaction']:
                # Show both nickname and choice
                broadcast(
                    strings_common['chat_reaction3'],
                    player=self.player.name,
                    map=map_.name
                )
            else:
                # Show only nickname
                broadcast(
                    strings_common['chat_reaction1'],
                    player=self.player.name,
                )

        elif 2 & config_manager['votemap_chat_reaction']:
            # Show only choice
                broadcast(
                    strings_common['chat_reaction2'],
                    map=map_.name
                )

        # Check if all players have voted
        check_if_enough_votes()

    def nominate_callback(self, map_):
        reason = self.get_nominate_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self.nominated_map = map_

        # ... chat message
        broadcast(strings_common['nominated'],
                  player=self.player.name,
                  map=map_.name)

    def rtv_callback(self):
        from ..map_cycle import check_if_enough_rtv

        reason = self.get_rtv_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self.used_rtv = True

        # ... chat message
        broadcast(strings_common['used_rtv'], player=self.player.name)

        # Check RTV ratio
        check_if_enough_rtv()

    def likemap_callback(self, rating):
        reason = self.get_likemap_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        self.session_user.rating = rating

    def nextmap_callback(self):
        reason = self.get_nextmap_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        if status.next_map is None:
            tell(self.player, strings_common['nextmap_unknown'])

        else:
            tell(self.player, strings_common['nextmap_is'],
                 map=status.next_map.name)

    def timeleft_callback(self):
        reason = self.get_timeleft_denial_reason()
        if reason is not None:
            tell(self.player, reason)
            return

        if config_manager['timelimit'] == 0:
            tell(self.player, strings_common['timeleft_never'])
            return

        if status.round_end_needed:
            tell(self.player, strings_common['timeleft_last_round'])
            return

        delta = datetime.fromtimestamp(status.map_end_time) - datetime.now()
        tell(self.player, strings_common['timeleft_timeleft'],
             timeleft=str(delta))


def tell(players, message, **tokens):
    """Send a SayText2 message to a list of Player instances."""
    if isinstance(players, Player):
        players = (players, )

    player_indexes = [player.index for player in players]

    tokens.update(COLOR_SCHEME)

    message = message.tokenize(**tokens)
    message = strings_common['chat_base'].tokenize(
        message=message, **COLOR_SCHEME)

    SayText2(message=message).send(*player_indexes)
    return


def broadcast(message, **tokens):
    """Send a SayText2 message to all registered users."""
    tell([user.player for user in user_manager.values()], message, **tokens)


def init_likemap_popup():
    def likemap_select_callback(popup, index, option):
        user_manager[index].likemap_callback(option.value)

    popups.popup_likemap = SimpleRadioMenu(
        select_callback=likemap_select_callback)

    popups.popup_likemap.append(Text(strings_popups['rate_map']))

    choice_index = 1

    # First of all, add "I Don't Care" option if it's enabled
    if config_manager['likemap_whatever_option']:
        # Add to the list
        popups.popup_likemap.append(SimpleRadioOption(
            choice_index=choice_index,
            text=strings_popups['whatever'],
            value=0,
        ))
        choice_index += 1

    popups.popup_likemap.append(SimpleRadioOption(
        choice_index=choice_index,
        text=strings_popups['likemap_like'],
        value=1,
    ))
    choice_index += 1

    popups.popup_likemap.append(SimpleRadioOption(
        choice_index=choice_index,
        text=strings_popups['likemap_dislike'],
        value=-1,
    ))

init_likemap_popup()
