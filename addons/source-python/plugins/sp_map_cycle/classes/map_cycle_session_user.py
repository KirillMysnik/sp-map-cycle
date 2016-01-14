from time import time


class MapCycleSessionUserManager(dict):
    def get_or_create(self, steamid):
        if steamid not in self:
            self[steamid] = MapCycleSessionUser(steamid)
        return self[steamid]

    def get_map_ratings(self):
        for session_user in self.values():
            if session_user.rating == 0:
                continue

            yield session_user.rating

    def reset_map_ratings(self):
        for session_user in self.values():
            session_user.rating = 0

session_user_manager = MapCycleSessionUserManager()


class MapCycleSessionUser:
    def __init__(self, steamid):
        self.steamid = steamid
        self.current_user = None

        self.rating = 0
        self.session_time = 0

        self._since_round_start = False
        self._last_check_time = -1

    def reset_disconnect(self):
        self._since_round_start = False
        self._last_check_time = -1

    # Event handlers
    def on_round_start(self):

        # Check if this user is still connected to the server
        if self.current_user is None:

            # If not, no reason to continue
            return

        # Mark the user present to round start
        self._since_round_start = True

        # Has the user just connected?
        if self._last_check_time < 0:

            # If so, here's their first time control point
            self._last_check_time = time()

    def on_round_end(self, time_now):
        if not self._since_round_start:
            return

        self.session_time += time_now - self._last_check_time
        self._last_check_time = time_now
