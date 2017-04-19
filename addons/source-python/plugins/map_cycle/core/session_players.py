# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from time import time


# =============================================================================
# >> CLASSES
# =============================================================================
class SessionPlayerManager(dict):
    def __missing__(self, steamid):
        self[steamid] = SessionPlayer(steamid)
        return self[steamid]

    def get_map_ratings(self):
        for session_player in self.values():
            if session_player.rating == 0:
                continue

            yield session_player.rating

    def reset_map_ratings(self):
        for session_player in self.values():
            session_player.rating = 0

# The singleton object of the SessionPlayerManager class
session_players = SessionPlayerManager()


class SessionPlayer:
    def __init__(self, steamid):
        self.steamid = steamid

        self.rating = 0
        self.session_time = 0

        self._since_round_start = False
        self._last_check_time = -1

    def player_disconnect_callback(self):
        self._since_round_start = False
        self._last_check_time = -1

    def round_start_callback(self):
        self._since_round_start = True
        if self._last_check_time < 0:
            self._last_check_time = time()

    def round_end_callback(self):
        if not self._since_round_start:
            return

        time_now = time()
        self.session_time += time_now - self._last_check_time
        self._last_check_time = time_now
