from datetime import datetime
from json import load as json_load
from json import dump as json_dump
from random import shuffle
from time import time
from warnings import warn

from colors import Color
from commands.server import ServerCommand
from core import echo_console
from cvars import ConVar
from events import Event
from engines.server import engine_server
from engines.server import global_vars
from engines.sound import Sound
from engines.sound import SOUND_FROM_WORLD
from entities.entity import Entity
from filters.players import PlayerIter
from listeners import OnClientActive
from listeners import OnClientDisconnect
from listeners import OnLevelInit
from listeners import OnLevelShutdown
from listeners.tick import Delay
from loggers import LogManager
from memory import get_virtual_function
from memory.hooks import PreHook
from menus import PagedMenu
from menus import PagedOption
from messages import HudMsg
from paths import CFG_PATH
from paths import GAME_PATH
from players.entity import Player
from players.helpers import userid_from_index
from stringtables.downloads import Downloadables

from .db import connect
from .db import insert
from .db import select
from .db import update
from .info import info
from .no_spam_say_command import NoSpamSayCommand
from .spmc_commands import spmc_commands

from .classes.map_cycle_item import map_cycle_extend_entry
from .classes.map_cycle_item import map_cycle_whatever_entry
from .classes.map_cycle_item import map_manager

from .classes.map_cycle_session_user import session_user_manager

from .classes.map_cycle_user import broadcast
from .classes.map_cycle_user import tell
from .classes.map_cycle_user import user_manager

from .namespaces import popups
from .namespaces import status

from .resource.config_cvars import cvar_alphabetic_sort_by_fullname
from .resource.config_cvars import cvar_alphabetic_sort_enable
from .resource.config_cvars import cvar_extend_time
from .resource.config_cvars import cvar_instant_change_level
from .resource.config_cvars import cvar_likemap_enable
from .resource.config_cvars import cvar_likemap_survey_duration
from .resource.config_cvars import cvar_logging_level
from .resource.config_cvars import cvar_logging_areas
from .resource.config_cvars import cvar_nextmap_show_on_match_end
from .resource.config_cvars import cvar_rtv_needed
from .resource.config_cvars import cvar_scheduled_vote_time
from .resource.config_cvars import cvar_sound_vote_start
from .resource.config_cvars import cvar_sound_vote_end
from .resource.config_cvars import cvar_timeleft_auto_lastround_warning
from .resource.config_cvars import cvar_timelimit
from .resource.config_cvars import cvar_vote_duration
from .resource.config_cvars import cvar_votemap_max_options
from .resource.config_cvars import cvar_votemap_whatever_option

from .resource.strings import insert_tokens
from .resource.strings import strings_common
from .resource.strings import strings_popups


NEXTMAP_MSG_COLOR = Color(124, 173, 255)
NEXTMAP_MSG_X = -1
NEXTMAP_MSG_Y = 0.05
NEXTMAP_MSG_EFFECT = 2
NEXTMAP_MSG_FADEIN = 0.05
NEXTMAP_MSG_FADEOUT = 0
NEXTMAP_MSG_HOLDTIME = 10
NEXTMAP_MSG_FXTIME = 0


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
    """Raised when mapcycle.json doesn't contain a list."""
    pass


class InvalidMapJSON(Warning):
    """Used to warn and skip a single map in mapcycle.json."""
    pass


class InvalidCVarValue(Warning):
    """Used to warn improper configuration."""
    pass


class PlayersCannotVote(Warning):
    """Used to warn cases when there're no maps to vote for."""
    pass


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

    c1 = 0
    try:
        rows = select(
            conn,
            'maps',
            (
                'filename',
                'detected',
                'force_old',
                'likes',
                'dislikes'
            )
        )

        for row in rows:
            map_ = map_manager.get(row['filename'])
            if map_ is None:
                continue

            map_.in_database = True
            map_.detected = row['detected']
            map_.force_old = bool(row['force_old'])
            map_.likes = row['likes']
            map_.dislikes = row['dislikes']

            c1 += 1

    finally:
        conn.close()

    log.log_debug("load_maps_from_db: {} records were loaded".format(c1))

    return True


def save_maps_to_db():
    conn = connect()
    if conn is None:
        warn(IOError("Couldn't establish connection to the database"))
        return False

    c1 = c2 = 0

    try:
        detected = int(time())
        for map_ in map_manager.values():
            if map_.in_database:
                update(
                    conn,
                    'maps',
                    {
                        'detected': map_.detected,
                        'force_old': map_.force_old,
                        'likes': map_.likes,
                        'dislikes': map_.dislikes,
                        'man_hours': map_.man_hours,
                        'av_session_length': map_.av_session_length,
                    },
                    where='filename=?',
                    args=(map_.filename.lower(), ),
                    commit=False,
                )
                c1 += 1
            else:
                insert(
                    conn,
                    'maps',
                    {
                        'filename': map_.filename.lower(),
                        'detected': detected,
                        'force_old': map_.force_old,
                        'likes': map_.likes,
                        'dislikes': map_.dislikes,
                        'man_hours': map_.man_hours,
                        'av_session_length': map_.av_session_length,
                    },
                    commit=False,
                )
                map_.in_database = True
                map_.detected = detected

                c2 += 1

        conn.commit()

    finally:
        conn.close()

    log.log_debug("save_maps_to_db: {} records were updated, {} new records "
                  "were added".format(c1, c2))

    return True


def reload_map_list():
    if not isinstance(mapcycle_json, list):
        raise CorruptJSONFile("Parsed object is not a list")

    # Check if vote has not started yet - useful to prevent things
    # getting dirty because of 'spmc reload-mapcycle'
    if status.vote_status != status.VoteStatus.NOT_STARTED:
         raise RuntimeError("Vote has already started or even ended, "
                            "can't execute reload_map_list() now")

    map_manager.clear()
    for i, json_dict in enumerate(mapcycle_json):
        try:
            filename = json_dict['filename']
        except KeyError:
            warn(InvalidMapJSON("Map #{}: missing 'filename' key"))
            continue

        if filename.lower() in map_manager:
            warn(CorruptJSONFile("Duplicate maps '{}'".format(filename)))
            continue

        if engine_server.is_map_valid(filename):
            map_manager.create(json_dict)

    log.log_debug("Added {} valid maps".format(len(map_manager)))

    # Now rebuild nomination menu
    def select_callback(popup, player_index, option):
        user = user_manager.get_by_index(player_index)
        user.nominate_callback(option.value)

    popups.popup_nominate = PagedMenu(select_callback=select_callback,
                               title=strings_popups['nominate_map'])

    maps_ = list(map_manager.values())
    for map_ in sorted(maps_, key=lambda map_: map_.filename):
        selectable = not map_.played_recently
        popups.popup_nominate.append(PagedOption(
            text=map_.name,
            value=map_,
            highlight=selectable,
            selectable=selectable))

    log.log_debug("Added {} maps to the !nominate menu".format(len(maps_)))


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


mp_timelimit_old_value = 0


def load():
    log.log_debug("Entered load()...")

    # Hot plug: detect users
    for player in PlayerIter('human'):
        user_manager.create(player)

    reload_maps_from_mapcycle()

    log.log_debug("Reloaded map list from JSON")

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

    # Also mark current level name (if it's loaded) as a recently played
    if global_vars.map_name:
        map_name = global_vars.map_name
        map_manager.recent_map_names.append(global_vars.map_name)
        log.log_debug("Current level name is {}".format(map_name))

        status.current_map = map_manager.get(map_name)

        if status.current_map is None:
            log.log_debug("Current map '{}' is not "
                          "from mapcycle.json!".format(map_name))

        # We think that the level is loaded with us
        status.map_start_time = time()
        log.log_debug("Level start time: {}".format(
                      datetime.fromtimestamp(
                          status.map_start_time
                      ).strftime('%X')))

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
delay_likemap_survey = None


def launch_vote(scheduled=False):
    if status.vote_status != status.VoteStatus.NOT_STARTED:
        return      # TODO: Maybe put a warning or an exception here?

    log.log_debug("Launching the vote (scheduled={})".format(scheduled))

    status.vote_status = status.VoteStatus.IN_PROGRESS

    # Cancel any scheduled votes in case somebody called us directly
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_end_vote   # We will assign to this later
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Cancel likemap survey
    if delay_likemap_survey is not None and delay_likemap_survey.running:
        delay_likemap_survey.cancel()

    # And unsend that popup from all players
    popups.popup_likemap.close()

    # Reset maps
    for map_ in map_manager.values():
        map_.votes = 0
        map_.nominations = 0

    # Popup callback
    def select_callback(popup, player_index, option):
        user = user_manager.get_by_index(player_index)
        user.vote_callback(option.value)

    # Create new popup
    popups.popup_main = PagedMenu(select_callback=select_callback,
                           title=strings_popups['choose_map'])

    # First of all, add "I Don't Care" option if it's enabled
    if cvar_votemap_whatever_option.get_bool():

        # Reset votes so that it doesn't increment infinitely
        map_cycle_whatever_entry.votes = 0

        # Add to the list
        popups.popup_main.append(PagedOption(
            text=map_cycle_whatever_entry.name,
            value=map_cycle_whatever_entry,
        ))

    # Only add "Extend this map..." option to scheduled votes
    if scheduled:

        # Reset votes count for this entry
        map_cycle_extend_entry.votes = 0

        # Decide if it's selectable and highlighted
        selectable = status.can_extend()

        # Add to the list
        popups.popup_main.append(PagedOption(
            text=map_cycle_extend_entry.name,
            value=map_cycle_extend_entry,
            highlight=selectable,
            selectable=selectable
        ))

    # Now to the actual maps
    # Count nominations
    for nominated_map in user_manager.get_nominated_maps():
        nominated_map.nominations += 1

    user_manager.reset_nominated_maps()

    maps_ = map_manager.values()

    # Filter hidden maps out
    maps_ = list(filter(lambda map_: not map_.hidden, maps_))

    if not maps_:
        warn(PlayersCannotVote("Please add more maps to the server or "
                               "reconfigure Source.Python Map Cycle"))
        return

    # Check if we need to do an initial alphabetic sort
    if cvar_alphabetic_sort_enable.get_bool():

        # Sort by name (alphabetically)
        if cvar_alphabetic_sort_by_fullname.get_bool():
            maps_ = sorted(maps_, key=lambda map_: map_.name)
        else:
            maps_ = sorted(maps_, key=lambda map_: map_.filename)
    else:

        # Shuffle
        shuffle(maps_)

    # Now sort by rating (likes, likes - dislikes or likes:dislikes)
    if cvar_likemap_enable.get_bool():
        maps_ = sorted(maps_, key=lambda map_: map_.rating, reverse=True)

    # Now separate new and old maps
    maps_ = sorted(maps_, key=lambda map_: map_.isnew, reverse=True)

    # Now sort by nominations
    maps_ = sorted(maps_, key=lambda map_: map_.nominations, reverse=True)

    # Now put recently played maps to the end
    maps_ = sorted(maps_, key=lambda map_: map_.played_recently)

    # Cap options
    max_options = cvar_votemap_max_options.get_int()
    if max_options > 0:
        maps_ = maps_[:max_options]

    # Fill popup with the maps
    for map_ in maps_:
        # Add the map to the popup
        selectable = not map_.played_recently
        popups.popup_main.append(PagedOption(
            text=map_.full_caption,
            value=map_,
            highlight=selectable,
            selectable=selectable
        ))

    log.log_debug("Added {} maps to the vote".format(len(maps_)))

    # Send popup to players
    for user in user_manager.values():
        user.send_popup(popups.popup_main)

    # Define vote end
    delay_end_vote = Delay(cvar_vote_duration.get_int(), finish_vote)

    # ... sound
    if cvar_sound_vote_start.get_string() != "":
        Sound(
            sample=cvar_sound_vote_start.get_string(),
            index=SOUND_FROM_WORLD
        ).play(*[user.player.index for user in user_manager.values()])

    # ... chat message
    broadcast(strings_common['vote_started'])


def finish_vote():
    if status.vote_status != status.VoteStatus.IN_PROGRESS:
        return      # TODO: Same, warning/exception may fit better here?

    log.log_debug("Finishing the vote...")

    status.vote_status = status.VoteStatus.ENDED

    # Delay might still be running if the vote finished prematurely
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    if popups.popup_main is not None:
        popups.popup_main.close()
        popups.popup_main = None

    for voted_map in user_manager.get_voted_maps():
        voted_map.votes += 1

    user_manager.reset_voted_maps()

    maps_ = map_manager.values()
    maps_ = filter(lambda map_: not map_.hidden, maps_)

    if status.can_extend():
        candidate_maps = tuple(maps_) + (map_cycle_extend_entry, )
    else:
        candidate_maps = maps_

    candidate_maps = sorted(
        candidate_maps, key=lambda map_: map_.votes, reverse=True)

    if not candidate_maps:
        # If there're no maps on the server, there's not much we can do
        log.log_debug("No maps to choose from in finish_vote()! "
                      "Cancelling change_level...")

        broadcast(strings_common['no_choice'])

        global delay_changelevel
        if delay_changelevel and delay_changelevel.running:
            delay_changelevel.cancel()
            delay_changelevel = None

        return

    # Leave only maps with max votes number
    result_maps = []
    for map_ in candidate_maps:
        if map_.votes == candidate_maps[0].votes:
            result_maps.append(map_)

    # If you ever want to implement VIP/Premium features into
    # !rtv and keep it fair, here's the place:
    result_maps = list(result_maps)
    shuffle(result_maps)

    winner_map = result_maps[0]
    set_next_map(winner_map)

    # ... chat message
    if isinstance(winner_map, type(map_cycle_extend_entry)):
        log.log_debug("Winner map: extend-this-map option")

        status.used_extends += 1
        broadcast(strings_common['map_extended'], time=str(cvar_extend_time.get_int()))

    else:
        log.log_debug("Winner map: {}".format(winner_map.filename))

        broadcast(strings_common['map_won'], map=winner_map.name)

    # ... sound
    if cvar_sound_vote_end.get_string() != "":
        Sound(
            sample=cvar_sound_vote_end.get_string(),
            index=SOUND_FROM_WORLD
        ).play(*[user.player.index for user in user_manager.values()])


def set_next_map(map_):
    # First of all, check if we actually need to extend the current map
    if isinstance(map_, type(map_cycle_extend_entry)):
        log.log_debug("Extending current level...")

        # Set NOT_STARTED state so that they can nominate maps and stuff
        status.vote_status = status.VoteStatus.NOT_STARTED

        # Reset RTV for each user
        user_manager.reset_rtv()

        # Cancel and relaunch delay_changelevel...
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
    status.next_map = map_


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

    status.map_end_time = time() + seconds

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

    # Schedule likemap survey
    survey_duration = cvar_likemap_survey_duration.get_int()
    if survey_duration > 0:
        seconds = max(0, seconds - survey_duration)
        global delay_likemap_survey
        delay_likemap_survey = Delay(seconds, launch_likemap_survey)

        log.log_debug(
            "Scheduled likemap survey in {} seconds".format(seconds))


def change_level(round_end=False):
    if status.next_map is None:
        raise RuntimeError("It's already time to change the level, "
                           "but next map is yet to be decided")

    if cvar_instant_change_level.get_bool() or round_end:
        log.log_debug("Ending the game...")

        game_end_entity = Entity.find_or_create('game_end')
        game_end_entity.end_game()

    else:
        log.log_debug("Waiting for the round end to end the game...")

        status.round_end_needed = True

        if cvar_timeleft_auto_lastround_warning.get_bool():
            broadcast(strings_common['timeleft_last_round'])


def check_if_enough_votes():
    for user in user_manager.values():
        if user.voted_map is None:
            return
    finish_vote()


def check_if_enough_rtv():
    try:
        ratio = user_manager.count_rtv()
    except ZeroDivisionError:
        return

    if ratio >= cvar_rtv_needed.get_float():
        # Cancel change_level delay if any
        global delay_changelevel
        if delay_changelevel is not None and delay_changelevel.running:
            delay_changelevel.cancel()

        # Relaunch change_level delay
        seconds = cvar_vote_duration.get_int() + EXTRA_SECONDS_AFTER_VOTE
        delay_changelevel = Delay(seconds, change_level)

        launch_vote(scheduled=False)


def launch_likemap_survey():
    log.log_debug("Launching mass likemap survey")

    for user in user_manager.values():
        reason = user.get_likemap_denial_reason()
        if reason is None:
            user.send_popup(popups.popup_likemap)


@OnLevelInit
def listener_on_level_init(map_name):
    log.log_debug(
        "Entered OnLevelInit listener (map_name={})...".format(map_name))

    # Reset MapCycleUser instances
    user_manager.reset_users()

    # Cancel delays if any
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_changelevel   # We will assign to this a few lines later
    if delay_changelevel is not None and delay_changelevel.running:
        delay_changelevel.cancel()

    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    # Reset Status
    status.vote_status = status.VoteStatus.NOT_STARTED
    status.next_map = None
    status.map_start_time = time()
    status.used_extends = 0

    # Update database
    save_maps_to_db()

    # Reload maps
    reload_maps_from_mapcycle()

    # Set current map in Status
    status.current_map = map_manager.get(map_name.lower())

    if status.current_map is None:
        log.log_debug("Current map '{}' is not "
                      "from mapcycle.json!".format(map_name))

    # Unsend popups
    if popups.popup_main is not None:
        popups.popup_main.close()
        popups.popup_main = None

    # Add current map names to recent_map_names
    map_manager.recent_map_names.append(map_name)

    # And then cap recent_map_names
    map_manager.cap_recent_maps()

    log.log_debug(
        "Recent map names: {}".format(
            ','.join(map_manager.recent_map_names)
        )
    )

    # Schedule regular vote
    schedule_vote(was_extended=False)

    # Schedule level changing - this can be later cancelled by map extensions
    schedule_change_level(was_extended=False)


@OnLevelShutdown
def listener_on_level_shutdown():
    log.log_debug("Entered OnLevelShutdown listener")

    # Calculate map ratings
    if status.current_map is not None:
        for rating in session_user_manager.get_map_ratings():
            if rating == 1:
                status.current_map.likes += 1

            elif rating == -1:
                status.current_map.dislikes += 1

    session_user_manager.reset_map_ratings()


@Event('round_end')
def on_round_end(game_event):
    if status.round_end_needed:
        log.log_debug("round_end event, time to change the level")
        change_level(round_end=True)
        status.round_end_needed = False


@Event('cs_win_panel_match')
def on_cs_win_panel_match(game_event):
    if status.next_map is None:
        return

    if not cvar_nextmap_show_on_match_end.get_bool():
        return

    hud_msg = HudMsg(
        insert_tokens(
            strings_popups['nextmap_msg'],
            map=status.next_map.name
        ),
        color1=NEXTMAP_MSG_COLOR,
        x=NEXTMAP_MSG_X,
        y=NEXTMAP_MSG_Y,
        effect=NEXTMAP_MSG_EFFECT,
        fade_in=NEXTMAP_MSG_FADEIN,
        fade_out=NEXTMAP_MSG_FADEOUT,
        hold_time=NEXTMAP_MSG_HOLDTIME,
        fx_time=NEXTMAP_MSG_FXTIME
    )
    hud_msg.send(*[user.player.index for user in user_manager.values()])
    broadcast(strings_common['nextmap_msg'], map=status.next_map.name)


@OnClientActive
def listener_on_client_active(index):
    player = Player(index)
    if player.is_fake_client():
        return

    user_manager.create(player)


@OnClientDisconnect
def listener_on_client_disconnect(index):
    userid = userid_from_index(index)
    user = user_manager.get(userid)
    if user is not None:
        user.session_user.reset_disconnect()
        del user_manager[userid]

    if status.vote_status == status.VoteStatus.NOT_STARTED:
        check_if_enough_rtv()

    elif status.vote_status == status.VoteStatus.IN_PROGRESS:
        check_if_enough_votes()


engine_server_changelevel = get_virtual_function(engine_server, 'ChangeLevel')


@PreHook(engine_server_changelevel)
def hook_on_pre_change_level(args):
    log.log_debug("Hooked ChangeLevel...")
    # Set our own next map
    if status.next_map is not None:
        args[1] = status.next_map.filename


@ServerCommand('spmc')
def command_on_spmc(command):
    current_command = spmc_commands['spmc']
    i = 0
    for i in range(1, command.get_arg_count()):
        next_command = current_command.registered_commands.get(
            command[i].lower())

        if next_command is None:
            i -= 1
            break

        current_command = next_command

    args = []
    for j in range(i + 1, command.get_arg_count()):
        args.append(command[j])

    if current_command is spmc_commands['spmc']:
        echo_console("Unknown SPMC command. Type 'spmc help' to get help")
        return

    current_command.callback(args)


@ServerCommand('spmc_launch_vote')
def command_on_spmc_force_vote(command):
    launch_vote(scheduled=False)


@NoSpamSayCommand(('!votemap', 'votemap'))
def say_command_on_votemap(command, index, teamonly):
    user = user_manager.get_by_index(index)
    reason = user.get_vote_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_main)


@NoSpamSayCommand(('!nominate', 'nominate'))
def say_command_on_nominate(command, index, teamonly):
    user = user_manager.get_by_index(index)
    reason = user.get_nominate_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_nominate)


@NoSpamSayCommand(('!rtv', 'rtv', 'rockthevote', '!rockthevote'))
def say_command_on_rtv(command, index, teamonly):
    user = user_manager.get_by_index(index)
    user.rtv_callback()


@NoSpamSayCommand('!likemap')
def say_command_on_likemap(command, index, teamonly):
    user = user_manager.get_by_index(index)
    reason = user.get_likemap_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_likemap)


@NoSpamSayCommand(('!nextmap', 'nextmap'))
def say_command_on_nextmap(command, index, teamonly):
    user = user_manager.get_by_index(index)
    user.nextmap_callback()


@NoSpamSayCommand(('!timeleft', 'timeleft'))
def say_command_on_nextmap(command, index, teamonly):
    user = user_manager.get_by_index(index)
    user.timeleft_callback()
