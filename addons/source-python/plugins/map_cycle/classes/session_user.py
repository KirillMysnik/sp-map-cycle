from time import time


class SessionUserManager(dict):
    def get_or_create(self, steamid):
        if steamid not in self:
            self[steamid] = SessionUser(steamid)

        return self[steamid]

    def get_map_ratings(self):
        for session_user in self.values():
            if session_user.rating == 0:
                continue

            yield session_user.rating

    def reset_map_ratings(self):
        for session_user in self.values():
            session_user.rating = 0

session_user_manager = SessionUserManager()


class SessionUser:
    def __init__(self, steamid):
        self.steamid = steamid

        self.rating = 0
        self.session_time = 0

        self._since_round_start = False
        self._last_check_time = -1

    def reset_disconnect(self):
        self._since_round_start = False
        self._last_check_time = -1

    def on_round_start(self):
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
