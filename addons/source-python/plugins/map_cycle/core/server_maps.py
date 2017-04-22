# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from datetime import datetime

# Map Cycle
from .cvars import config_manager
from .strings import map_names_strings, popups_strings


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def time_fit(now, mins, maxs):
    """Return True if `now` fits in the given minutes interval."""
    if mins >= maxs:
        return time_fit(now, mins, 24 * 60) or time_fit(now, 0, max)

    return mins <= now < maxs


# =============================================================================
# >> CLASSES
# =============================================================================
class ServerMapManager(dict):
    def __init__(self):
        super().__init__()

        self.recent_map_names = []

    def create(self, dict_):
        filename = dict_['filename'].lower()
        self[filename] = ServerMap(dict_)
        return self[filename]

    def cap_recent_maps(self):
        self.recent_map_names = self.recent_map_names[
            len(self.recent_map_names) -
            config_manager['recent_maps_limit']:
        ]

# The singleton object of the ServerMapManager class
server_map_manager = ServerMapManager()


class BaseServerMap:
    def __init__(self):
        self.votes = 0
        self.nominations = 0
        self.filename = None

    @property
    def name(self):
        raise NotImplementedError


class ServerMap(BaseServerMap):
    def __init__(self, dict_):
        super().__init__()

        self._minutes1 = None
        self._minutes2 = None

        self.filename = dict_['filename']
        self._fullname = dict_.get('fullname')
        self.detected = 0
        self.likes = 0
        self.dislikes = 0
        self.man_hours = 0.0
        self.av_session_len = 0.0
        self.in_database = False

        if 'timerestrict' in dict_:
            restr1 , restr2 = dict_['timerestrict'].split(',')
            hour1, minute1 = map(int, restr1.split(':'))
            hour2, minute2 = map(int, restr2.split(':'))

            self._minutes1 = hour1 * 60 + minute1
            self._minutes2 = hour2 * 60 + minute2

    def _predict_fullname(self):
        sep_index = self.filename.find('_')
        prefix = self.filename[:sep_index] if sep_index > -1 else None
        name = self.filename[sep_index+1:]

        if config_manager['fullname_skips_prefix']:
            return name.replace('_', ' ').title()

        if prefix is None:
            return name.title()

        return "{} {}".format(prefix.upper(), name.replace('_', ' ').title())

    @property
    def name(self):
        if not config_manager['use_fullname']:
            return self.filename

        if self._fullname is not None:
            return self._fullname

        if self.filename in map_names_strings:
            return map_names_strings[self.filename]

        if config_manager['predict_missing_fullname']:
            return self._predict_fullname()

        return self.filename

    @property
    def played_recently(self):
        return self.filename in server_map_manager.recent_map_names

    @property
    def full_caption(self):
        return popups_strings['caption_default'].tokenized(
            prefix=(popups_strings['prefix_recent'] if
                    self.played_recently else ""),

            map=self.name,

            postfix=(popups_strings['postfix_new'] if self.is_new else ""),

            postfix2=popups_strings['postfix_nominated'].tokenized(
                nominations=self.nominations) if self.nominations > 0 else "",

            postfix3=popups_strings['likes'].tokenized(likes=self.rating_str),
        )

    @property
    def is_new(self):
        days_cap = config_manager['new_map_timeout_days']
        if days_cap < 0:
            return False

        if not self.in_database:
            return True

        detected_dt = datetime.fromtimestamp(self.detected)
        now_dt = datetime.now()

        return (now_dt - detected_dt).days <= days_cap

    @property
    def is_hidden(self):
        if self._minutes1 is None or self._minutes2 is None:
            return False

        now = datetime.now()
        now = now.hour * 60 + now.minute
        return not time_fit(now, self._minutes1, self._minutes2)

    @property
    def rating(self):
        method = config_manager['likemap_method']
        if method == 1:
            return self.likes

        if method == 2:
            return self.likes - self.dislikes

        if method == 3:
            if self.likes == 0:
                return 0

            # Let me divide it, hold my beer
            if self.dislikes == 0:
                return 1

            return self.likes / (self.likes + self.dislikes)

    @property
    def rating_str(self):
        if not config_manager['likemap_enable']:
            return ""

        if config_manager['likemap_method'] == 1:
            return str(self.likes)

        if config_manager['likemap_method'] == 2:
            return str(self.likes - self.dislikes)

        if config_manager['likemap_method'] == 3:
            if self.likes == 0:
                return "0.0%"

            # Hold my beer once again
            if self.dislikes == 0:
                return "100.0%"

            return "{:.2f}".format(
                self.likes / (self.likes + self.dislikes) * 100)


class ExtendEntry(BaseServerMap):
    @property
    def name(self):
        return popups_strings['extend']

# The singleton object of the ExtendEntry class
extend_entry = ExtendEntry()


class WhateverEntry(BaseServerMap):
    @property
    def name(self):
        return popups_strings['whatever']

# The singleton object of the WhateverEntry class
whatever_entry = WhateverEntry()
