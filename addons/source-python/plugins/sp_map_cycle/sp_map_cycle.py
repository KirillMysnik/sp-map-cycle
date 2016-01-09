from datetime import datetime
from json import load as json_load, dump as json_dump
from random import shuffle
from time import time
from warnings import warn

from commands.server import ServerCommand
from config.manager import ConfigManager
from core import echo_console
from cvars import ConVar
from events import Event
from engines.server import engine_server, global_vars
from engines.sound import Sound, SOUND_FROM_WORLD
from entities.entity import Entity
from filters.players import PlayerIter
from listeners import OnClientActive, OnLevelInit
from listeners.tick import Delay
from loggers import LogManager
from memory import get_virtual_function
from memory.hooks import PreHook
from menus import PagedMenu, PagedOption
from messages import SayText2
from paths import CFG_PATH, GAME_PATH
from players.entity import Player
from players.helpers import userid_from_index
from stringtables.downloads import Downloadables
from translations.strings import TranslationStrings

from sp_map_cycle.db import connect, insert, select, update
from sp_map_cycle.info import info
from sp_map_cycle.recursive_translations import BaseLangStrings
from sp_map_cycle.recursive_translations import ColoredRecursiveTranslationStrings
from sp_map_cycle.recursive_translations import RecursiveTranslationStrings
from sp_map_cycle.spmc_commands import spmc_commands


# Map color variables in translation files to actual RGB values
COLOR_SCHEME = {
    'tag': "#242,242,242",
    'lightgreen': "#4379B7",
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
MAPCYCLE_JSON_FILE = GAME_PATH / 'cfg' / "mapcycle.json"

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


strings_common = BaseLangStrings(
    info.basename + "/strings", base=ColoredRecursiveTranslationStrings)

strings_config = BaseLangStrings(
    info.basename + "/config", base=TranslationStrings)

strings_mapnames = BaseLangStrings(
    info.basename + "/mapnames", base=TranslationStrings)

strings_popups = BaseLangStrings(
    info.basename + "/popups", base=RecursiveTranslationStrings)

with ConfigManager(info.basename, cvar_prefix='spmc_') as config_manager:
    config_manager.section("Logging")
    cvar_logging_level = config_manager.cvar(
        name="logging_level",
        default=4,
        description=strings_config['logging_level']
    )
    cvar_logging_areas = config_manager.cvar(
        name="logging_areas",
        default=5,
        description=strings_config['logging_areas']
    )
    config_manager.section("Maps settings")
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
        min_value=1.0
    )
    cvar_recent_maps_limit = config_manager.cvar(
        name="recent_maps_limit",
        default=2,
        description=strings_config['recent_maps_limit'],
        min_value=0
    )
    cvar_new_map_timeout_days = config_manager.cvar(
        name="new_map_timeout_days",
        default=5,
        description=strings_config['new_map_timeout_days'],
        min_value=-1,
    )
    config_manager.section("Votes settings")
    cvar_vote_duration = config_manager.cvar(
        name="vote_duration",
        default=30,
        description=strings_config['vote_duration'],
        min_value=5.0,
    )
    cvar_scheduled_vote_time = config_manager.cvar(
        name="scheduled_vote_time",
        default=5,
        description=strings_config['scheduled_vote_time'],
        min_value=0.0
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
        description=strings_config['predict_missing_fullname']
    )
    cvar_fullname_skips_prefix = config_manager.cvar(
        name="fullname_skips_prefix",
        default=1,
        description=strings_config['fullname_skips_prefix']
    )
    cvar_chat_reaction = config_manager.cvar(
        name="chat_reaction",
        default=3,
        description=strings_config['chat_reaction'],
        min_value=0,
        max_value=3
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

log = LogManager(info.basename, cvar_logging_level, cvar_logging_areas)


class CorruptJSONFile(Exception):
    """Raised when mapcycle.json doesn't contain a list"""
    pass


class InvalidMapJSON(Warning):
    """Used to warn and skip a single map in mapcycle.json"""
    pass


class InvalidCVarValue(Warning):
    """Used to warn improper configuration"""
    pass


def insert_tokens(
        translation_strings,
        base=RecursiveTranslationStrings,
        **tokens):

    rs = base()
    for key, value in translation_strings.items():
        rs[key] = value

    rs.tokens.update(tokens)
    return rs


def tell(players, message, with_tag=True, **tokens):
    """Sends a SayText2 message to a list of Player instances"""
    for color_token, color_value in COLOR_SCHEME.items():
        tokens['color_'+color_token] = color_value

    if isinstance(players, Player):
        players = (players, )

    player_indexes = [player.index for player in players]

    if isinstance(message, TranslationStrings):
        if with_tag:
            tokens['message'] = message
            message = strings_common['chat_tag']

        SayText2(message=message).send(*player_indexes, **tokens)
        return

    raise TypeError("Unknown message class: {}".format(type(message)))


def broadcast(message, with_tag=True, **tokens):
    """Sends a SayText2 message to all human players"""
    tell(PlayerIter('human'), message, with_tag, **tokens)


users = {}


class MapCycleUser:
    def __init__(self, player):
        self.player = player

        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

    def reset(self):
        self.voted_map = None
        self.nominated_map = None
        self.used_rtv = False

    def send_popup(self, popup):
        popup.send(self.player.index)

    def vote_callback(self, map_):
        self.voted_map = map_

        chat_reaction = cvar_chat_reaction.get_int()
        if 1 & chat_reaction:
            if 2 & chat_reaction:
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

        elif 2 & chat_reaction:
            # Show only choice
                broadcast(
                    strings_common['chat_reaction2'],
                    map=map_.name
                )

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
        self.detected = 0
        self.force_old = False
        self.likes = 0
        self.dislikes = 0
        self.in_database = False

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

        # Not used because we haven't implemented VPK support yet
        return (GAME_PATH / 'maps' / self.filename).isfile()

    @property
    def played_recently(self):
        return self.filename in recent_map_names

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
                             likes=(
                                 insert_tokens(
                                     strings_popups['likes'],
                                     likes=self.likes
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


class MapCycleExtendEntry(MapCycleItem):
    @property
    def name(self):
        return strings_popups['extend']


map_cycle_extend_entry = MapCycleExtendEntry()
mapcycle_json = None


def reload_mapcycle_json():
    if not MAPCYCLE_JSON_FILE.isfile():
        raise FileNotFoundError("Missing mapcycle.json")

    global mapcycle_json
    with open(str(MAPCYCLE_JSON_FILE)) as f:    # TODO: Do we need str() here?
        mapcycle_json = json_load(f)


def build_json_from_mapcycle_txt():
    mapcycle_txt = GAME_PATH / 'cfg' / cvar_mapcyclefile.get_string()
    if not mapcycle_txt.isfile():
        mapcycle_txt = GAME_PATH / 'cfg' / DEFAULT_MAPCYCLEFILE
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
    with open(str(MAPCYCLE_JSON_FILE), 'w') as f:
        json_dump(rs, f, indent=4)


def load_maps_from_db():
    conn = connect()
    if conn is None:
        warn(IOError("Couldn't establish connection to the database"))
        return False

    rows = select(
        conn, 'maps', ('filename', 'detected', 'force_old', 'likes'))

    c1 = 0
    for row in rows:
        map_ = maps.get(row['filename'])
        if map_ is None:
            continue

        map_.in_database = True
        map_.detected = row['detected']
        map_.force_old = bool(row['force_old'])
        map_.likes = row['likes']
        map_.dislikes = row['dislikes']

        c1 += 1

    conn.commit()
    conn.close()

    log.log_debug("load_maps_from_db: {} records were loaded".format(c1))

    return True


def save_maps_to_db():
    conn = connect()
    if conn is None:
        warn(IOError("Couldn't establish connection to the database"))
        return False

    c1 = c2 = 0
    for map_ in maps.values():
        if map_.in_database:
            update(conn, 'maps', {
                'detected': map_.detected,
                'force_old': map_.force_old,
                'likes': map_.likes,
                'dislikes': map_.dislikes,
            }, where='filename=?', args=(map_.filename.lower(), ))
            c1 += 1
        else:
            insert(conn, 'maps', {
                'filename': map_.filename.lower(),
                'detected': int(time()),
                'force_old': map_.force_old,
                'likes': map_.likes,
                'dislikes': map_.dislikes,
            })
            c2 += 1

    conn.commit()
    conn.close()

    log.log_debug("save_maps_to_db: {} records were updated, {} new records "
                  "were added".format(c1, c2))

    return True


def reload_map_list():
    if not isinstance(mapcycle_json, list):
        raise CorruptJSONFile("Parsed object is not a list")

    maps.clear()
    for i, json_dict in enumerate(mapcycle_json):
        try:
            filename = json_dict['filename']
        except KeyError:
            warn(InvalidMapJSON("Map #{}: missing 'filename' key"))
            continue

        if filename.lower() in maps:
            warn(CorruptJSONFile("Duplicate maps '{}'".format(filename)))
            continue

        if engine_server.is_map_valid(filename):
            log.log_debug("Adding valid map {}".format(filename))

            maps[filename.lower()] = MapCycleMap(json_dict)


def reload_maps_from_mapcycle():
    # Load JSON
    try:

        # Try to load mapcycle.json
        reload_mapcycle_json()

        log.log_debug("Loaded mapcycle.json (first try)")
    except FileNotFoundError:

        # If it fails, build mapcycle.json from the mapcyclefile file
        build_json_from_mapcycle_txt()

        # And then load mapcycle.json again, this time it
        # must succeed
        reload_mapcycle_json()

        log.log_debug("Loaded mapcycle.json (after building it)")

    # Create MapCycleMap list using loaded JSON
    reload_map_list()

    # Fill maps properties with data from the database
    load_maps_from_db()


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

    # Set by change_level() if it's waiting for round end to
    # change the map
    round_end_needed = False

    @classmethod
    def can_extend(cls):
        return cls.used_extends < cvar_max_extends.get_int()


mp_timelimit_old_value = 0


def load():
    log.log_debug("Entered load()...")

    # Hot plug: detect users
    for player in PlayerIter('human'):
        users[player.userid] = MapCycleUser(player)

    reload_maps_from_mapcycle()

    log.log_debug("Reloaded map list from JSON")

    # Also mark current level name (if it's loaded) as a recently played
    if global_vars.map_name:
        recent_map_names.append(global_vars.map_name)
        log.log_debug("Current level name is {}".format(recent_map_names[-1]))

    # We think that the level is loaded with us
    Status.map_start_time = time()
    log.log_debug("Level start time: {}".format(
                  datetime.fromtimestamp(
                      Status.map_start_time
                  ).strftime('%X')))

    # Save old mp_timelimit value
    global mp_timelimit_old_value
    mp_timelimit_old_value = cvar_mp_timelimit.get_float()

    # If spmc_timelimit equals to -1, grab the value from mp_timelimit
    if cvar_timelimit.get_int() == -1:
        cvar_timelimit.set_float(mp_timelimit_old_value)

        log.log_debug("spmc_timelimit was -1, set to the value of "
                      "mp_timelimit (mp_timelimit = {})".format(
                          mp_timelimit_old_value
                      ))

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

    # Schedule level changing - this can be later cancelled by map extensions
    schedule_change_level()

    # ... chat message
    broadcast(strings_common['loaded'])


def unload():
    log.log_debug("Entered unload()...")

    # Restore mp_timelimit to its original (or changed) value
    cvar_mp_timelimit.set_float(mp_timelimit_old_value)

    # Update database
    save_maps_to_db()

    # ... chat message
    broadcast(strings_common['unloaded'])


delay_scheduled_vote = None
delay_changelevel = None
delay_end_vote = None
popup_main = None


def launch_vote(scheduled=False):
    if Status.vote_status not in (
            Status.VoteStatus.NOT_STARTED,
            Status.VoteStatus.ENDED):   # For scheduled votes after extension

        return      # TODO: Maybe put a warning or an exception here?

    log.log_debug("Launching the vote (scheduled={})".format(scheduled))

    Status.vote_status = Status.VoteStatus.IN_PROGRESS

    # TODO: Should we get rid of delays cancelling if we are already
    # checking VoteStatus?
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_end_vote   # We will assign to this later
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Popup callback
    def select_callback(popup, player_index, option):
        user = users[userid_from_index(player_index)]
        user.vote_callback(option.value)

    # Create new popup
    global popup_main
    popup_main = PagedMenu(select_callback=select_callback,
                  title=strings_popups['choose_map'])

    # Only add "Extend this map..." option to scheduled votes
    if scheduled:

        # Reset votes count for this entry
        map_cycle_extend_entry.votes = 0

        # Decide if it's selectable and highlighted
        selectable = Status.can_extend()

        # Add to the list
        popup_main.append(PagedOption(
                                 text=map_cycle_extend_entry.name,
                                 value=map_cycle_extend_entry,
                                 highlight=selectable,
                                 selectable=selectable))

    # Now to the actual maps
    for map_ in maps.values():

        # Reset votes count for this map
        map_.votes = 0

        # Add the map to the popup
        if map_.played_recently:
            popup_main.append(PagedOption(
                                     text=map_.full_caption,
                                     value=map_,
                                     highlight=False,
                                     selectable=False))

            log.log_debug("Added new map to the vote: {} "
                          "(selectable=False)".format(map_.filename))

        else:
            popup_main.append(PagedOption(text=map_.full_caption, value=map_))

            log.log_debug("Added new map to the vote: {} "
                          "(selectable=True)".format(map_.filename))

    # Send popup to players
    for user in users.values():
        user.send_popup(popup_main)

    # Define vote end
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

    log.log_debug("Finishing the vote...")

    Status.vote_status = Status.VoteStatus.ENDED

    # Delay might still be running if the vote finished prematurely
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    global popup_main
    if popup_main is not None:
        popup_main.close()
        popup_main = None

    for user in users.values():
        if user.voted_map is not None:
            user.voted_map.votes += 1

    if Status.can_extend():
        candidate_maps = tuple(maps.values()) + (map_cycle_extend_entry, )
    else:
        candidate_maps = maps.values()

    result_maps = sorted(
        candidate_maps, key=lambda map_: map_.votes, reverse=True)

    # Leave only maps with max votes number
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
        log.log_debug("Winner map: extend-this-map option")
    else:
        log.log_debug("Winner map: {}".format(winner_map.filename))

    # ... chat message
    if isinstance(winner_map, MapCycleExtendEntry):
        Status.used_extends += 1
        broadcast(strings_common['map_extended'], time=str(cvar_extend_time.get_int()))

    else:
        broadcast(strings_common['map_won'], map=winner_map.name)

    # ... sound
    if cvar_sound_vote_end.get_string() != "":
        Sound(recipients=[user.player.index for user in users.values()],
              index=SOUND_FROM_WORLD,
              sample=cvar_sound_vote_end.get_string()).play()


def set_next_map(map_):
    # First of all, check if we actually need to extend the current map
    if isinstance(map_, MapCycleExtendEntry):
        log.log_debug("Extending current level...")

        # In that case we cancel and relaunch delay_changelevel...
        global delay_changelevel
        if delay_changelevel is not None and delay_changelevel.running:
            delay_changelevel.cancel()

        schedule_change_level(was_extended=True)

        # ... and then cancel and schedule a new vote
        if delay_scheduled_vote is not None and delay_scheduled_vote.running:
            delay_scheduled_vote.cancel()

        schedule_vote(was_extended=True)
        return

    log.log_debug("Setting next map to {}...".format(map_.filename))

    # If we don't need to extend current map, set a new next map
    Status.next_map = map_


def schedule_change_level(was_extended=False):
    # Do we even need to change levels?
    if cvar_timelimit.get_int() == 0:

        # If not, no reason to continue
        return

    log.log_debug(
        "Scheduling change_level (was_extended={})".format(was_extended))

    if was_extended:
        seconds = cvar_extend_time.get_float() * 60 + EXTRA_SECONDS_AFTER_VOTE
    else:
        seconds = cvar_timelimit.get_float() * 60 + EXTRA_SECONDS_AFTER_VOTE

    global delay_changelevel
    delay_changelevel = Delay(seconds, change_level)

    log.log_debug("We will end the game in {} seconds.".format(seconds))


def schedule_vote(was_extended=False):
    # Do we even need scheduled votes?
    if cvar_timelimit.get_int() == 0:

        # If not, no reason to continue
        return

    log.log_debug(
        "Scheduling the vote (was_extended={})".format(was_extended))

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
                   cvar_scheduled_vote_time.get_float() * 60 -
                   cvar_vote_duration.get_int())

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
                   cvar_scheduled_vote_time.get_float() * 60 -
                   cvar_vote_duration.get_int())

    # Schedule the vote
    global delay_scheduled_vote
    delay_scheduled_vote = Delay(seconds, launch_vote, scheduled=True)

    log.log_debug("Scheduled vote starts in {} seconds".format(seconds))


def change_level(round_end=False):
    if Status.next_map is None:
        raise RuntimeError("It's already time to change the level, "
                           "but next map is yet to be decided")

    if cvar_instant_change_level.get_bool() or round_end:
        log.log_debug("Ending the game...")

        game_end_entity = Entity.find_or_create('game_end')
        game_end_entity.end_game()

    else:
        log.log_debug("Waiting for the round end to end the game...")

        Status.round_end_needed = True


@OnLevelInit
def listener_on_level_init(map_name):
    log.log_debug(
        "Entered OnLevelInit listener (map_name={})...".format(map_name))

    # Reset MapCycleUser instances
    for user in users.values():
        user.reset()

    # Cancel delays if any
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_changelevel   # We will assign to this a few lines later
    if delay_changelevel is not None and delay_changelevel.running:
        delay_changelevel.cancel()

    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Update database
    save_maps_to_db()

    # Reload maps
    reload_maps_from_mapcycle()

    # Unsend popups
    global popup_main
    if popup_main is not None:
        popup_main.close()
        popup_main = None

    # Add current map names to recent_map_names
    # TODO: Won't we have dupes because we also add map_name if load()?
    global recent_map_names
    recent_map_names.append(map_name)

    # And then cap recent_map_names
    recent_map_names = recent_map_names[
                           len(recent_map_names) -
                           cvar_recent_maps_limit.get_int():
                       ]

    log.log_debug("Recent map names: {}".format(','.join(recent_map_names)))

    # Reset Status
    Status.vote_status = Status.VoteStatus.NOT_STARTED
    Status.next_map = None
    Status.map_start_time = time()
    Status.used_extends = 0

    # Schedule regular vote
    schedule_vote(was_extended=False)

    # Schedule level changing - this can be later cancelled by map extensions
    schedule_change_level(was_extended=False)


@Event('round_end')
def on_round_end(game_event):
    if Status.round_end_needed:
        log.log_debug("round_end event, time to change the level")
        change_level(round_end=True)


@OnClientActive
def listener_on_client_active(index):
    player = Player(index)
    users[player.userid] = MapCycleUser(player)


@Event('player_disconnect')
def on_player_disconnect(game_event):
    userid = game_event.get_int('userid')
    if userid not in users:
        return

    del users[userid]


engine_server_changelevel = get_virtual_function(engine_server, 'ChangeLevel')


@PreHook(engine_server_changelevel)
def hook_on_pre_change_level(args):
    if Status.next_map is not None:
        args[1] = Status.next_map.filename


@ServerCommand('spmc')
def command_on_spmc(command):
    current_command = spmc_commands['spmc']
    i = 0
    for i in range(1, command.get_arg_count()):
        next_command = current_command.registered_commands.get(
            command[i].lower())

        if next_command is None:
            break

        current_command = next_command

    args = []
    for j in range(i + 1, command.get_arg_count()):
        args.append(command[j])

    if current_command is spmc_commands['spmc']:
        echo_console("Unknown SPMC command: 'spmc {}'\n"
                     "Type 'spmc help' to get help".format(' '.join(args)))
        return

    current_command.callback(args)
