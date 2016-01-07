from random import shuffle
from time import time
from datetime import datetime
from json import load as json_load, dump as json_dump
from warnings import warn

from config.manager import ConfigManager
from cvars import ConVar
from events import Event
from engines.server import engine_server, global_vars
from engines.sound import Sound, SOUND_FROM_WORLD
from filters.players import PlayerIter
from listeners import OnLevelInit
from listeners.tick import Delay
from menus import PagedMenu, PagedOption
from messages import SayText2
from paths import CFG_PATH, GAME_PATH
from players.entity import PlayerEntity
from players.helpers import userid_from_index
from stringtables.downloads import Downloadables
from translations.strings import LangStrings, TranslationStrings

from sp_map_cycle.info import info
from sp_map_cycle.rgba_chat import process_string as rgba_process_string


# Map color variables in translation files to actual RGB values
COLOR_SCHEME = {
    'lightgreen': "#255,137,0",
    'green': "#255,137,0",
    'default': "#242,242,242",
    'error': "#FF3636",
}

# List some unusual map prefixes
MAP_PREFIXES = [
    'ba_jail_',  # double prefix, deprecated version of jb_
]

# mapcycle_default.txt - in case we don't find mapcyclefile
DEFAULT_MAPCYCLEFILE = "mapcycle_default.txt"

# mapcycle.json
MAPCYCLE_JSON_FILE = CFG_PATH / "mapcycle.json"

# List of files to upload to players
DOWNLOADLIST = CFG_PATH / info.basename / "downloadlist.txt"

# Fallback value if either spmc_timelimit or mp_timelimit were invalid
# Take a look at load()
NEGATIVE_TIMELIMIT_FALLBACK_VALUE = 60.0

# Fallback value if spmc_scheduled_vote_time exceeds or
# equals to spmc_timelimit.
# Current spmc_timelimit value will be multiplied by this fallback value
# and then applied to spmc_scheduled_vote_time.
# Take a look at schedule_vote()
INVALID_SCHEDULED_VOTE_TIME_FALLBACK_VALUE = 0.33

# We will add extra seconds after vote ends to prevent
# instant level changing when the vote ends
EXTRA_SECONDS_AFTER_VOTE = 5.0

strings_common = LangStrings(info.basename + "/strings")
strings_config = LangStrings(info.basename + "/config")
strings_mapnames = LangStrings(info.basename + "/mapnames")

with ConfigManager(info.basename, cvar_prefix='spmc_') as config_manager:
    cvar_timelimit = config_manager.cvar(
        name="timelimit",
        default=-1,
        description=strings_config['timelimit'],
        min_value=-1.0
    )
    cvar_instant_change_level = config_manager.cvar(
        name="instant_change_level",
        default=0,
        description=strings_config['instant_change_level'],
    )
    cvar_vote_duration = config_manager.cvar(
        name="vote_duration",
        default=30,
        description=strings_config['vote_duration'],
        min_value=0.0,
    )
    cvar_scheduled_vote_time = config_manager.cvar(
        name="scheduled_vote_time",
        default=5,
        description=strings_config['scheduled_vote_time'],
        min_value=0.0
    )
    cvar_max_extends = config_manager.cvar(
        name="max_extends",
        default=2,
        description=strings_config['max_extends'],
        min_value=-1.0
    )
    cvar_extend_time = config_manager.cvar(
        name="extend_time",
        default=15,
        description=strings_config['extend_time'],
        min_value=5.0
    )
    cvar_recent_maps_limit = config_manager.cvar(
        name="recent_maps_limit",
        default=2,
        description=strings_config['recent_maps_limit'],
        min_value=0
    )
    cvar_use_fullname = config_manager.cvar(
        name="use_fullname",
        default=1,
        description=strings_config['use_fullname']
    )
    # Note how variable name differs from cvar name below
    cvar_predict_fullname = config_manager.cvar(
        name="predict_missing_fullname",
        default=1,
        description=strings_config['predict_fullname']
    )
    cvar_fullname_skips_prefix = config_manager.cvar(
        name="fullname_skips_prefix",
        default=1,
        description=strings_config['fullname_skips_prefix']
    )
    cvar_sound_vote_start = config_manager.cvar(
        name="sound_vote_start",
        default="admin_plugin/actions/startyourvoting.mp3",
        description=strings_config['sound_vote_start']
    )
    cvar_sound_vote_end = config_manager.cvar(
        name="sound_vote_end",
        default="admin_plugin/actions/endofvote.mp3",
        description=strings_config['sound_vote_end']
    )

cvar_mapcyclefile = ConVar('mapcyclefile')
cvar_mp_timelimit = ConVar('mp_timelimit')

# While sound cvars may be changed in real time, we only detect
# files to upload to players on plugin load
downloadables = Downloadables()

with open(str(DOWNLOADLIST)) as f:   # TODO: Do we need str() here?
    for line in f:
        line = line.strip()
        if not line:
            continue
        downloadables.add(line)


class CorruptJSONFile(Exception):
    """Raised when mapcycle.json doesn't contain a list"""
    pass


class InvalidMapJSON(Warning):
    """Used to warn and skip a single map in mapcycle.json"""
    pass


class InvalidCVarValue(Warning):
    """Used to warn improper configuration"""
    pass


def tell(players, message, **tokens):
    """Sends a SayText2 message to a list of PlayerEntity instances"""
    for color_token, color_value in COLOR_SCHEME.items():
        tokens['color_'+color_token] = color_value

    if isinstance(players, PlayerEntity):
        players = (players, )

    player_indexes = [player.index for player in players]

    if isinstance(message, SayText2):
        message.send(*player_indexes, **tokens)
        return

    if isinstance(message, TranslationStrings):
        SayText2(message=message).send(*player_indexes, **tokens)
        return

    raise TypeError("Unknown message class: {}".format(type(message)))


def broadcast(message, **tokens):
    """Sends a SayText2 message to all human players"""
    if isinstance(message, TranslationStrings):
        message = SayText2(message=message)

    tell(PlayerIter('human'), message, **tokens)


users = {}


class MapCycleUser:
    def __init__(self, player):
        self.player = player

        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

        self._received_popups = []

    def reset(self):
        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

    def send_popup(self, popup):
        self._received_popups.append(popup)
        popup.send(self.player.index)

    def unsend_popups(self):
        for popup in self._received_popups:
            popup.unsend(self.player.index)

        self._received_popups.clear()


maps = {}
recent_map_names = []


class MapCycleItem:
    def __init__(self):
        self.votes = 0
        self.nominations = 0

    @property
    def name(self):
        raise NotImplementedError


class MapCycleMap(MapCycleItem):
    def __init__(self, json_dict):
        super().__init__()

        self.filename = json_dict['filename']
        self._fullname = json_dict.get('fullname')

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
        if cvar_predict_fullname.get_bool():

            # If we are allowed to do so, then do it
            return self._predict_fullname()

        # Finally, just return the file name
        return self.filename

    @property
    def exists(self):
        return (GAME_PATH / 'maps' / self.filename).isfile()


class MapCycleExtendEntry(MapCycleItem):
    @property
    def name(self):
        return strings_common['popup_extend']


map_cycle_extend_entry = MapCycleExtendEntry()


mapcycle_json = None


def reload_mapcycle_json():
    if not MAPCYCLE_JSON_FILE.isfile():
        raise FileNotFoundError("Missing mapcycle.json")

    global mapcycle_json
    with open(str(MAPCYCLE_JSON_FILE)) as f:    # TODO: Do we need str() here?
        mapcycle_json = json_load(f)


def build_json_from_mapcycle_txt():
    mapcycle_txt = CFG_PATH / cvar_mapcyclefile.get_string()
    if not mapcycle_txt.isfile():
        mapcycle_txt = CFG_PATH / DEFAULT_MAPCYCLEFILE
        if not mapcycle_txt.isfile():
            raise FileNotFoundError("Missing {}".format(DEFAULT_MAPCYCLEFILE))

    rs = []
    with open(str(mapcycle_txt)) as f:  # TODO: Do we need str() here?
        for line in f:
            line = line.strip()
            if not line:
                continue

            rs.append({
                'filename': line,
            })

    # TODO: Do we need str() below?
    with open(str(MAPCYCLE_JSON_FILE), 'r') as f:
        json_dump(rs, f)


def reload_map_list():
    if not isinstance(mapcycle_json, list):
        raise CorruptJSONFile("Parsed object is not a list")

    maps.clear()
    for i, json_dict in enumerate(mapcycle_json):
        try:
            filename = mapcycle_json['filename']
        except KeyError:
            warn(InvalidMapJSON("Map #{}: missing 'filename' key"))
            continue

        map_ = MapCycleMap(json_dict)
        if map_.exists:
            maps[filename] = map_


class Status:
    class VoteStatus:
        NOT_STARTED = 0
        IN_PROGRESS = 1
        ENDED = 2

    # Current vote status
    vote_status = VoteStatus.NOT_STARTED

    # Next map (MapCycleMap) to change to, used by change_level()
    next_map = None

    # time() when current map started, used by !timeleft command
    map_start_time = 0

    # How many times "Extend this map..." option has won, used
    used_extends = 0

    # Becomes True after the round ends until new round starts,
    # used by change_level()
    #round_end = False

    # Set by change_level() if it's waiting for round end to
    # change the map
    round_end_needed = False

    @classmethod
    def can_extend(cls):
        return cls.used_extends < cvar_max_extends.get_int()


def load():
    # Hot plug: detect users
    for player in PlayerIter('human'):
        users[player.userid] = MapCycleUser(player)

    # Load JSON
    try:

        # Try to load mapcycle.json
        reload_mapcycle_json()
    except FileNotFoundError:

        # If it fails, build mapcycle.json from the mapcyclefile file
        build_json_from_mapcycle_txt()

        # And then load mapcycle.json again, this time it
        # must succeed
        reload_mapcycle_json()

    # Create MapCycleMap list using loaded JSON
    reload_map_list()

    # Also mark current level name (if it's loaded) as a recently played
    if global_vars.map_name:
        recent_map_names.append(global_vars.map_name)

    # We think that the level is loaded with us
    Status.map_start_time = time()

    # If spmc_timelimit equals to -1, grab the value from mp_timelimit
    if cvar_timelimit.get_int() == -1:
        cvar_timelimit.set_float(cvar_mp_timelimit.get_float())

    # Two cases to catch:
    # 1. spmc_timelimit was (-1; 0)
    # 2. spmc_timelimit was set to -1 and mp_timelimit was negative
    if cvar_timelimit.get_float() < 0:
        warn(InvalidCVarValue("{} is negative (and doesn't equal to -1), "
                              "falling back to {}".format(
            cvar_timelimit._name, NEGATIVE_TIMELIMIT_FALLBACK_VALUE)))

        cvar_timelimit.set_float(NEGATIVE_TIMELIMIT_FALLBACK_VALUE)

    # We don't need mp_timelimit to change the maps for us
    cvar_mp_timelimit.set_float(0.0)

    # Schedule the vote, it will be scheduled as if the map is loaded
    # with us
    schedule_vote()


def unload():
    # Restore mp_timelimit to its original (or changed) value
    cvar_mp_timelimit.set_float(cvar_timelimit.get_float())


delay_scheduled_vote = None
delay_changelevel = None
delay_end_vote = None


def launch_vote(scheduled=False):
    if Status.vote_status != Status.VoteStatus.NOT_STARTED:
        return      # TODO: Maybe put a warning or an exception here?

    Status.vote_status = Status.VoteStatus.IN_PROGRESS

    # TODO: Should we get rid of delays cancelling if we are already
    # checking VoteStatus?
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Popup callback
    def select_callback(popup, player_index, option):
        user = users[userid_from_index(player_index)]
        user.voted_map = option.value

    # Create new popup
    popup = PagedMenu(select_callback=select_callback,
                  title=strings_common['popup_choose_map'])

    # Only add "Extend this map..." option to scheduled votes
    if scheduled:

        # Reset votes count for this entry
        map_cycle_extend_entry.votes = 0

        # Decide if it's selectable and highlighted
        selectable = Status.can_extend()

        # Add to the list
        popup.append(PagedOption(
                                 text=map_cycle_extend_entry.name,
                                 value=map_cycle_extend_entry,
                                 highlight=selectable,
                                 selectable=selectable))

    # Now to the actual maps
    for map_ in maps.values():

        # Reset votes count for this map
        map_.votes = 0

        # Decide if it's selectable and highlighted
        selectable = map_.filename not in recent_map_names

        # Add to the list
        popup.append(PagedOption(
                                 text=map_.name,
                                 value=map_,
                                 highlight=selectable,
                                 selectable=selectable))

    # Send popup to players
    for user in users.values():
        user.send_popup(popup)

    # Define vote end
    global delay_end_vote
    delay_end_vote = Delay(cvar_vote_duration.get_int(), finish_vote)

    # ... sound
    if cvar_sound_vote_start.get_string() != "":
        Sound(recipients=[user.player.index for user in users.values()],
              index=SOUND_FROM_WORLD,
              sample=cvar_sound_vote_start.get_string()).play()

    # ... chat message
    broadcast(strings_common['vote_started'])


def finish_vote():
    if Status.vote_status != Status.VoteStatus.IN_PROGRESS:
        return      # TODO: Same, warning/exception may fit better here?

    # Delay might still be running if the vote finished prematurely
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    for user in users.values():
        user.unsend_popups()
        if user.voted_map is not None:
            user.voted_map.votes += 1

    if Status.can_extend():
        candidate_maps = tuple(maps.values()) + (map_cycle_extend_entry, )
    else:
        candidate_maps = maps.values()

    result_maps = sorted(
        candidate_maps, key=lambda map_: map_.votes, reverse=True)

    # Check if any map recieved at least 1 vote
    if result_maps[0].votes == 0:
        # If not, choose between what we have
        result_maps = list(maps.values())

    else:
        # If so, leave only maps with max votes number
        new_result_maps = []
        for map_ in result_maps:
            if map_.votes == result_maps[0].votes:
                new_result_maps.append(map_)
        result_maps = new_result_maps

    # If you ever want to implement VIP/Premium features into
    # !rtv and keep it fair, here's the place:
    shuffle(result_maps)

    winner_map = result_maps[0]
    set_next_map(winner_map)

    if isinstance(winner_map, MapCycleExtendEntry):
        Status.used_extends += 1
        broadcast(strings_common['map_extended'], time=cvar_extend_time.get_int())

    else:
        broadcast(strings_common['map_won'], map=winner_map.filename)

    if cvar_sound_vote_end.get_string() != "":
        Sound(recipients=[user.player.index for user in users.values()],
              index=SOUND_FROM_WORLD,
              sample=cvar_sound_vote_end.get_string()).play()


def set_next_map(map_):
    # First of all, check if we actually need to extend the current map
    if isinstance(map_, MapCycleExtendEntry):

        # In that case we cancel and relaunch delay_changelevel...
        global delay_changelevel
        if delay_changelevel is not None and delay_changelevel.running:
            delay_changelevel.cancel()

        delay_changelevel = Delay(
            cvar_extend_time.get_float() * 60 + EXTRA_SECONDS_AFTER_VOTE,
            change_level
        )

        # ... and then cancel and schedule a new vote
        if delay_scheduled_vote is not None and delay_scheduled_vote.running:
            delay_scheduled_vote.cancel()

        schedule_vote(was_extended=True)
        return

    # If we don't need to extend current map, set a new next map
    Status.next_map = map_

    # Note that we use 'changelevel' to actually change the map, but we also
    # set some backup cvars in case we miss our opportunity to change the map

    # We don't use ConVars here because we don't want to create
    # SM/ES cvars - or maybe there's a way to check if the cvar exists?
    engine_server("sm_nextmap {}".format(map_.filename))
    engine_server("eventscripts_nextmapoverride {}".format(map_.filename))


def schedule_vote(was_extended=False):

    # We need to decide if we schedule vote from round start or
    # from map extension
    if was_extended:

        # If from extension, then the total time left is in
        # spmc_extend_time

        # But we need to check that spmc_scheduled_vote_time does not
        # exceed it
        if (cvar_scheduled_vote_time.get_float() >=
                cvar_extend_time.get_float()):

            new_value = (cvar_extend_time.get_float() *
                         INVALID_SCHEDULED_VOTE_TIME_FALLBACK_VALUE)

            warn(InvalidCVarValue("{} exceeds or equals to {}, "
                                  "falling back to {}".format(
                cvar_scheduled_vote_time._name,
                cvar_extend_time._name,
                new_value
            )))

            cvar_scheduled_vote_time.set_float(new_value)

        # Calculate time to start the vote in
        seconds = (cvar_extend_time.get_float() * 60 -
                   cvar_scheduled_vote_time.get_float() * 60)

    else:

        # But if it's just a regular scheduled vote, then the total time left
        # is in spmc_timelimit

        # But then again, we need to check spmc_scheduled_vote_time against
        # spmc_timelimit
        if cvar_scheduled_vote_time.get_float() >= cvar_timelimit.get_float():
            new_value = (cvar_timelimit.get_float() *
                         INVALID_SCHEDULED_VOTE_TIME_FALLBACK_VALUE)

            warn(InvalidCVarValue("{} exceeds or equals to {}, "
                                  "falling back to {}".format(
                cvar_scheduled_vote_time._name,
                cvar_timelimit._name,
                new_value
            )))

            cvar_scheduled_vote_time.set_float(new_value)

        # Calculate time to start the vote in
        seconds = (cvar_timelimit.get_float() * 60 -
                   cvar_scheduled_vote_time.get_float() * 60)

    # Schedule the vote
    global delay_scheduled_vote
    delay_scheduled_vote = Delay(seconds, launch_vote, scheduled=True)


def change_level():
    if Status.next_map is None:
        raise RuntimeError("It's already time to change the level, "
                           "but next map is yet to be decided")




@OnLevelInit
def listener_on_level_init(map_name):
    # Reset MapCycleUser instances
    for user in users.values():
        user.reset()
        user.unsend_popups()

    # Cancel delays if any
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_changelevel   # We will assign to this a few lines later
    if delay_changelevel is not None and delay_changelevel.running:
        delay_changelevel.cancel()

    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Add current map names to recent_map_names
    # TODO: Won't we have dupes because we also add map_name if load()?
    global recent_map_names
    recent_map_names.append(map_name)

    # And then cap recent_map_names
    recent_map_names = recent_map_names[-cvar_recent_maps_limit.get_int():]

    # Reset Status
    Status.vote_status = Status.VoteStatus.NOT_STARTED
    Status.next_map = None
    Status.map_start_time = time()
    Status.used_extends = 0

    # Schedule regular vote
    schedule_vote(was_extended=False)

    # Schedule level changing - this can be later cancelled by map extensions
    delay_changelevel = Delay(
        cvar_extend_time.get_float() * 60 + EXTRA_SECONDS_AFTER_VOTE,
        change_level
    )
