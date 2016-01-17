from time import time

from listeners.tick import Delay
from messages import HintText

from .map_cycle_item import MapCycleWhateverEntry
from .map_cycle_item import map_manager

from .map_cycle_user import user_manager

from ..namespaces import status

from ..resource.config_cvars import cvar_show_vote_progress
from ..resource.config_cvars import cvar_vote_duration

from ..resource.strings import strings_popups


EXCLUDE_ENTRY_CLASSES = [MapCycleWhateverEntry, ]
REFRESH_INTERVAL = 1


def format_map(map_):
    return "-//-" if map_ is None else map_.name


class KeyHintProgress:
    def __init__(self):
        self._refresh_delay = None
        self._message = None
        self._users_total = 0
        self._users_voted = 0

    def count_vote(self, map_):
        self._users_voted += 1

        for exception in EXCLUDE_ENTRY_CLASSES:
            if isinstance(map_, exception):
                return

        maps = list(filter(
            lambda map_: map_.votes,
            sorted(
                map_manager.values(), key=lambda map_: map_.votes, reverse=True
            )
        ))

        map_tokens = {}
        if len(maps) > 0:
            map_tokens['map1'] = strings_popups['vote_progress_map_with_votes'].tokenize(
                map=maps[0].name,
                votes=maps[0].votes,
            )
            if len(maps) > 1:
                map_tokens['map2'] = strings_popups['vote_progress_map_with_votes'].tokenize(
                    map=maps[1].name,
                    votes=maps[1].votes,
                )
                if len(maps) > 2:
                    map_tokens['map3'] = strings_popups['vote_progress_map_with_votes'].tokenize(
                        map=maps[2].name,
                        votes=maps[2].votes,
                    )
                else:
                    map_tokens['map3'] = strings_popups['vote_progress_map_without_votes']
            else:
                map_tokens['map2'] = strings_popups['vote_progress_map_without_votes']
                map_tokens['map3'] = strings_popups['vote_progress_map_without_votes']
        else:
            map_tokens['map1'] = strings_popups['vote_progress_map_without_votes']
            map_tokens['map2'] = strings_popups['vote_progress_map_without_votes']
            map_tokens['map3'] = strings_popups['vote_progress_map_without_votes']

        self._message = strings_popups['vote_progress'].tokenize(
            users_voted=self._users_voted,
            users_total=self._users_total,
            **map_tokens
        )

        self.refresh()

    def refresh(self):

        # We must cancel delay in case we were called from .count_vote
        if self._refresh_delay is not None and self._refresh_delay.running:
            self._refresh_delay.cancel()

        # Check our cvar - we do this this late to allow on-line
        # alteration of this cvar (during the vote)
        if not cvar_show_vote_progress.get_bool():
            return

        # Send KeyHint
        if self._message:

            # Calculate seconds left
            timeleft = int(
                status.vote_start_time + cvar_vote_duration.get_int() - time()
            )

            # Send HintText
            HintText(
                self._message.tokenize(timeleft='{:02d}:{:02d}'.format(
                    timeleft // 60, timeleft % 60
                ))
            ).send(
                *[user.player.index for user in user_manager.values()]
            )

        # Schedule next refresh
        self._refresh_delay = Delay(REFRESH_INTERVAL, self.refresh)

    def start(self):
        self._users_total = len(user_manager)
        self._users_voted = 0

        self._message = strings_popups['vote_progress'].tokenize(
            users_voted=self._users_voted,
            users_total=self._users_total,
            map1=strings_popups['vote_progress_map_without_votes'],
            map2=strings_popups['vote_progress_map_without_votes'],
            map3=strings_popups['vote_progress_map_without_votes'],
        )

        self.refresh()

    def stop(self):
        if self._refresh_delay is not None and self._refresh_delay.running:
            self._refresh_delay.cancel()


keyhint_progress = KeyHintProgress()
