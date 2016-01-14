from datetime import datetime

from ..resource.config_cvars import cvar_fullname_skips_prefix
from ..resource.config_cvars import cvar_likemap_enable
from ..resource.config_cvars import cvar_likemap_method
from ..resource.config_cvars import cvar_new_map_timeout_days
from ..resource.config_cvars import cvar_predict_missing_fullname
from ..resource.config_cvars import cvar_recent_maps_limit
from ..resource.config_cvars import cvar_use_fullname

from ..resource.strings import insert_tokens
from ..resource.strings import strings_mapnames
from ..resource.strings import strings_popups


# List some unusual map prefixes
MAP_PREFIXES = [
    'ba_jail_',  # double prefix, deprecated version of jb_
]


def fits(now, mins, maxs):
    """Return True if `now` fits in the given minutes interval."""
    if mins >= maxs:
        # 1440 = 24 * 60
        return fits(now, mins, 1440) or fits(now, 0, maxs)

    return mins <= now < maxs


class MapCycleMapManager(dict):
    recent_map_names = []

    def create(self, json_dict):
        filename = json_dict['filename'].lower()
        self[filename] = MapCycleMap(self, json_dict)
        return self[filename]

    def cap_recent_maps(self):
        self.recent_map_names = self.recent_map_names[
                                    len(self.recent_map_names) -
                                    cvar_recent_maps_limit.get_int():
                                ]


map_manager = MapCycleMapManager()


class MapCycleItem:
    def __init__(self):
        self.votes = 0
        self.nominations = 0

    @property
    def name(self):
        raise NotImplementedError


class MapCycleMap(MapCycleItem):
    def __init__(self, map_manager, json_dict):
        super().__init__()

        self._map_manager = map_manager
        self._minutes1 = None
        self._minutes2 = None
        self.filename = json_dict['filename']
        self._fullname = json_dict.get('fullname')
        self.detected = 0
        self.force_old = False
        self.likes = 0
        self.dislikes = 0
        self.man_hours = 0.0
        self.av_session_length = 0.0
        self.in_database = False

        if 'timerestrict' in json_dict:
            restr1, restr2 = json_dict['timerestrict'].split(',')
            hour1, minute1 = map(int, restr1.split(':'))
            hour2, minute2 = map(int, restr2.split(':'))

            self._minutes1 = hour1 * 60 + minute1
            self._minutes2 = hour2 * 60 + minute2

    def _predict_fullname(self):
        for prefix in MAP_PREFIXES:
            if self.filename.startswith(prefix):
                name = self.filename[len(prefix):]
                break

        else:
            sep_index = self.filename.find('_')
            prefix = self.filename[:sep_index] if sep_index > -1 else None
            name = self.filename[sep_index+1:]

        if cvar_fullname_skips_prefix.get_bool():
            return name.replace('_', ' ').title()

        if prefix is None:
            return name.title()

        return "{} {}".format(prefix.upper(), name.replace('_', ' ').title())

    @property
    def name(self):
        # Firstly check if we need to use full names at all
        if not cvar_use_fullname.get_bool():

            # If not, just return file name
            return self.filename

        # Then we need to check if there was a full name defined in JSON
        if self._fullname is not None:

            # If so, we return it as the one with the highest priority
            return self._fullname

        # After that we try to get full name from mapnames.ini
        strings_mapname = strings_mapnames.get(self.filename)
        if strings_mapname is not None:

            # If there's one, return it
            return strings_mapname

        # Last chance: maybe we can just guess the full name of the map?
        if cvar_predict_missing_fullname.get_bool():

            # If we are allowed to do so, then do it
            return self._predict_fullname()

        # Finally, just return the file name
        return self.filename

    @property
    def played_recently(self):
        return self.filename in self._map_manager.recent_map_names

    @property
    def full_caption(self):
        return insert_tokens(strings_popups['caption_default'],
                             prefix=(strings_popups['prefix_recent'] if
                                     self.played_recently else ""),
                             map=self.name,
                             postfix=(strings_popups['postfix_new'] if
                                      self.isnew else ""),
                             postfix2=(
                                 insert_tokens(
                                     strings_popups['postfix_nominated'],
                                     nominations=self.nominations
                                 ) if self.nominations > 0 else ""),
                             postfix3=(
                                 insert_tokens(
                                     strings_popups['likes'],
                                     likes=self.rating_str
                                 )
                             ))

    @property
    def isnew(self):
        if self.force_old:
            return False

        days_cap = cvar_new_map_timeout_days.get_int()
        if days_cap == -1:
            return False

        if not self.in_database:
            return True

        detected_dt = datetime.fromtimestamp(self.detected)
        now_dt = datetime.now()

        return (now_dt - detected_dt).days <= days_cap

    @property
    def hidden(self):
        if self._minutes1 is None or self._minutes2 is None:
            return False

        now = datetime.now()
        now = now.hour * 60 + now.minute
        return not fits(now, self._minutes1, self._minutes2)

    @property
    def rating(self):
        method = cvar_likemap_method.get_int()
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
        if not cvar_likemap_enable.get_bool():
            return ""

        method = cvar_likemap_method.get_int()
        if method == 1:
            return str(self.likes)

        if method == 2:
            return str(self.likes - self.dislikes)

        if method == 3:
            if self.likes == 0:
                return "0.0%"

            # Let me divide it, hold my beer
            if self.dislikes == 0:
                return "100.0%"

            return "{:.2f}".format(
                self.likes / (self.likes + self.dislikes) * 100)


class MapCycleExtendEntry(MapCycleItem):
    @property
    def name(self):
        return strings_popups['extend']


class MapCycleWhateverEntry(MapCycleItem):
    @property
    def name(self):
        return strings_popups['whatever']


map_cycle_extend_entry = MapCycleExtendEntry()
map_cycle_whatever_entry = MapCycleWhateverEntry()
