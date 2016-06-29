from datetime import datetime
from json import dump as json_dump, load as json_load
from random import shuffle
from time import time
from warnings import warn

from colors import Color
from core import echo_console
from cvars import ConVar
from events import Event
from engines.server import engine_server, global_vars
from entities.entity import Entity
from filters.players import PlayerIter
from listeners import (
    OnClientActive, OnClientDisconnect, OnLevelInit, OnLevelShutdown)

from listeners.tick import Delay, GameThread
from loggers import LogManager
from memory import get_virtual_function
from memory.hooks import PreHook
from menus import PagedMenu, PagedOption
from messages import HudMsg
from paths import CFG_PATH, GAME_PATH
from players.entity import Player
from stringtables.downloads import Downloadables

from spam_proof_commands.say import SayCommand
from spam_proof_commands.server import ServerCommand

from .info import info

from .mc_commands import mc_commands

from .classes.keyhint_progress import keyhint_progress

from .classes.server_map import (
    map_cycle_extend_entry, map_cycle_whatever_entry, map_manager)

from .classes.session_user import session_user_manager

from .classes.user import broadcast, tell, user_manager

from .models.server_map import ServerMap as DB_ServerMap

from .namespaces import popups, status

from .resource.config_cvars import (
    config_manager, cvar_logging_areas, cvar_logging_level,
    cvar_scheduled_vote_time, cvar_timelimit)

from .resource.sqlalchemy import Base, engine, Session

from .resource.strings import strings_common, strings_popups


Base.metadata.create_all(engine)


NEXTMAP_MSG_COLOR = Color(124, 173, 255)
NEXTMAP_MSG_X = -1
NEXTMAP_MSG_Y = 0.05
NEXTMAP_MSG_EFFECT = 2
NEXTMAP_MSG_FADEIN = 0.05
NEXTMAP_MSG_FADEOUT = 0
NEXTMAP_MSG_HOLDTIME = 10
NEXTMAP_MSG_FXTIME = 0


# Used for SpamProofCommands
ANTI_SPAM_TIMEOUT_SERVER = 1.0
ANTI_SPAM_TIMEOUT_PLAYER = 1.0

# mapcycle_default.txt - in case we don't find mapcyclefile
DEFAULT_MAPCYCLEFILE = "mapcycle_default.txt"

# mapcycle.json
MAPCYCLE_JSON_FILE = GAME_PATH / 'cfg' / "mapcycle.json"

# List of files to upload to players
DOWNLOADLIST = CFG_PATH / info.basename / "downloadlist.txt"

# Fallback value if either mc_timelimit or mp_timelimit were invalid
# Take a look at load()
NEGATIVE_TIMELIMIT_FALLBACK_VALUE = 60.0

# Fallback value if mc_scheduled_vote_time exceeds or equals to mc_timelimit.
# Current mc_timelimit value will be multiplied by this fallback value
# and then applied to mc_scheduled_vote_time.
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
    with open(mapcycle_txt) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith('//'):
                continue

            rs.append({
                'filename': line,
            })

    with open(MAPCYCLE_JSON_FILE, 'w') as f:
        json_dump(rs, f, indent=4)


def load_maps_from_db():
    session = Session()

    for db_server_map in session.query(DB_ServerMap).all():
        map_ = map_manager.get(db_server_map.filename)
        if map_ is None:
            continue

        map_.in_database = True
        map_.detected = db_server_map.detected
        map_.force_old = db_server_map.force_old
        map_.likes = db_server_map.likes
        map_.dislikes = db_server_map.dislikes

    session.close()


def save_maps_to_db():
    detected = int(time())

    session = Session()
    for server_map in map_manager.values():
        db_server_map = session.query(DB_ServerMap).filter_by(
            filename=server_map.filename.lower()).first()

        if db_server_map is None:
            server_map.detected = detected
            server_map.in_database = True

            db_server_map = DB_ServerMap()
            db_server_map.filename = server_map.filename.lower()
            db_server_map.detected = detected

            session.add(db_server_map)

        db_server_map.force_old = server_map.force_old
        db_server_map.likes = server_map.likes
        db_server_map.dislikes = server_map.dislikes
        db_server_map.man_hours = server_map.man_hours
        db_server_map.av_session_len = server_map.av_session_len

    session.commit()
    session.close()


def reload_map_list():
    if not isinstance(mapcycle_json, list):
        raise CorruptJSONFile("Parsed object is not a list")

    # Check if vote has not started yet - useful to prevent things from
    # getting dirty because of 'mc reload-mapcycle'
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
    def select_callback(popup, index, option):
        user = user_manager[index]
        user.nominate_callback(option.value)

    popups.popup_nominate = PagedMenu(select_callback=select_callback,
                                      title=strings_popups['nominate_map'])

    server_maps = list(map_manager.values())
    for server_map in sorted(
            server_maps, key=lambda server_map: server_map.filename):

        selectable = not server_map.played_recently
        popups.popup_nominate.append(PagedOption(
            text=server_map.name,
            value=server_map,
            highlight=selectable,
            selectable=selectable))

    log.log_debug(
        "Added {} maps to the !nominate menu".format(len(server_maps)))


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

    # If mc_timelimit equals to -1, grab the value from mp_timelimit
    if config_manager['timelimit'] < 0:
        cvar_timelimit.set_float(mp_timelimit_old_value)

        log.log_debug(
            "mc_timelimit was -1, set to the value of mp_timelimit "
            "(mp_timelimit = {})".format(mp_timelimit_old_value))

    if mp_timelimit_old_value < 0:
        warn(InvalidCVarValue(
            "mp_timelimit is negative, can't grab value from it"))

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

        # Schedule level changing - this can be later cancelled
        # by map extensions
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
    status.vote_start_time = time()

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
    map_cycle_whatever_entry.votes = 0
    map_cycle_extend_entry.votes = 0
    for server_map in map_manager.values():
        server_map.votes = 0
        server_map.nominations = 0

    # Popup callback
    def select_callback(popup, index, option):
        # Increment votes counter for this map
        option.value.votes += 1

        # KeyHint stats
        keyhint_progress.count_vote(option.value)

        # User callback
        user_manager[index].vote_callback(option.value)

    # Create new popup
    popups.popup_main = PagedMenu(select_callback=select_callback,
                                  title=strings_popups['choose_map'])

    # First of all, add "I Don't Care" option if it's enabled
    if config_manager['votemap_whatever_option']:

        # Add to the list
        popups.popup_main.append(PagedOption(
            text=map_cycle_whatever_entry.name,
            value=map_cycle_whatever_entry,
        ))

    # Only add "Extend this map..." option to scheduled votes
    if scheduled:

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

    server_maps = map_manager.values()

    # Filter hidden maps out
    server_maps = list(filter(
        lambda server_map: not server_map.is_hidden, server_maps))

    if not server_maps:
        warn(PlayersCannotVote("Please add more maps to the server or "
                               "reconfigure Map Cycle"))
        return

    # Do we need to do an initial alphabetic sort?
    if config_manager['alphabetic_sort_enabled']:

        # Sort by name (alphabetically)
        if config_manager['alphabetic_sort_by_fullname']:
            server_maps = sorted(
                server_maps, key=lambda server_map: server_map.name)
        else:
            server_maps = sorted(
                server_maps, key=lambda server_map: server_map.filename)

    else:

        # Shuffle
        shuffle(server_maps)

    # Now sort by rating (likes, likes - dislikes or likes:dislikes)
    if config_manager['likemap_enable']:
        server_maps = sorted(
            server_maps,
            key=lambda server_map: server_map.rating, reverse=True)

    # Now separate new and old maps
    server_maps = sorted(
        server_maps, key=lambda server_map: server_map.is_new, reverse=True)

    # Now sort by nominations
    server_maps = sorted(
        server_maps,
        key=lambda server_map: server_map.nominations, reverse=True)

    # Now put recently played maps to the end
    server_maps = sorted(
        server_maps, key=lambda server_map: server_map.played_recently)

    # Cap options
    if config_manager['votemap_max_options'] > 0:
        server_maps = server_maps[:config_manager['votemap_max_options']]

    # Fill popup with the maps
    for server_map in server_maps:

        # Add the map to the popup
        selectable = not server_map.played_recently
        popups.popup_main.append(PagedOption(
            text=server_map.full_caption,
            value=server_map,
            highlight=selectable,
            selectable=selectable
        ))

    log.log_debug("Added {} maps to the vote".format(len(server_maps)))

    # Send popup to players
    for user in user_manager.values():
        user.send_popup(popups.popup_main)

    # Define vote end
    delay_end_vote = Delay(config_manager['vote_duration'], finish_vote)

    # Start KeyHintProgress
    keyhint_progress.start()

    # ... sound
    if config_manager['sound_vote_start'] is not None:
        config_manager['sound_vote_start'].play(
            *[user.player.index for user in user_manager.values()])

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

    # Stop KeyHintProgress
    keyhint_progress.stop()

    # Recount votes to prevent reconnected players from messing things up
    # We only counted votes before to display them in KeyHint area
    for server_map in map_manager.values():
        server_map.votes = 0

    for voted_map in user_manager.get_voted_maps():
        voted_map.votes += 1

    user_manager.reset_voted_maps()

    server_maps = map_manager.values()
    server_maps = filter(
        lambda server_map: not server_map.is_hidden, server_maps)

    if status.can_extend():
        candidate_maps = tuple(server_maps) + (map_cycle_extend_entry, )
    else:
        candidate_maps = server_maps

    candidate_maps = sorted(
        candidate_maps, key=lambda server_map: server_map.votes, reverse=True)

    if not candidate_maps:

        # If there're no maps on the server, there's not much we can do
        log.log_debug("No maps to choose from in finish_vote()!")

        broadcast(strings_common['no_choice'])

        if delay_changelevel and delay_changelevel.running:
            log.log_debug("Cancelling change_level...")

            delay_changelevel.cancel()

        return

    # Leave only maps with max votes number
    result_maps = []
    for server_map in candidate_maps:
        if server_map.votes == candidate_maps[0].votes:
            result_maps.append(server_map)

    # If you ever want to implement VIP/Premium features into
    # !rtv and keep it fair, here's the place:
    shuffle(result_maps)

    winner_map = result_maps[0]
    set_next_map(winner_map)

    # ... chat message
    if isinstance(winner_map, type(map_cycle_extend_entry)):
        log.log_debug("Winner map: extend-this-map option")

        status.used_extends += 1
        broadcast(
            strings_common['map_extended'], time=config_manager['extend_time'])

    else:
        log.log_debug("Winner map: {}".format(winner_map.filename))

        broadcast(strings_common['map_won'], map=winner_map.name)

    # ... sound
    if config_manager['sound_vote_end'] is not None:
        config_manager['sound_vote_end'].play(
            *[user.player.index for user in user_manager.values()])


def set_next_map(server_map):

    # First of all, check if we actually need to extend the current map
    if isinstance(server_map, type(map_cycle_extend_entry)):
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

    log.log_debug("Setting next map to {}...".format(server_map.filename))

    # If we don't need to extend current map, set a new next map
    status.next_map = server_map


def schedule_change_level(was_extended=False):

    # Do we even need to change levels?
    if config_manager['timelimit'] == 0:

        # If not, no reason to continue
        return

    log.log_debug(
        "Scheduling change_level (was_extended={})".format(was_extended))

    if was_extended:
        seconds = config_manager['extend_time'] * 60 + EXTRA_SECONDS_AFTER_VOTE
    else:
        seconds = config_manager['timelimit'] * 60 + EXTRA_SECONDS_AFTER_VOTE

    global delay_changelevel
    delay_changelevel = Delay(seconds, change_level)

    status.map_end_time = time() + seconds

    log.log_debug("We will end the game in {} seconds.".format(seconds))


def schedule_vote(was_extended=False):

    # Do we even need scheduled votes?
    if config_manager['timelimit'] == 0:

        # If not, no reason to continue
        return

    log.log_debug(
        "Scheduling the vote (was_extended={})".format(was_extended))

    # We need to decide if we schedule vote from round start or
    # from map extension
    if was_extended:

        # If from extension, then the total time left is in mc_extend_time

        # But we need to check that mc_scheduled_vote_time does not
        # exceed it
        if (config_manager['scheduled_vote_time'] >=
                config_manager['extend_time']):

            new_value = (config_manager['extend_time'] *
                         INVALID_SCHEDULED_VOTE_TIME_FALLBACK_VALUE)

            warn(InvalidCVarValue(
                "mc_scheduled_vote_time exceeds or equals to mc_extend_time, "
                "falling back to {}".format(new_value)))

            cvar_scheduled_vote_time.set_float(new_value)

        # Calculate time to start the vote in
        seconds = (config_manager['extend_time'] * 60 -
                   config_manager['scheduled_vote_time'] * 60 -
                   config_manager['vote_duration'])

    else:

        # But if it's just a regular scheduled vote, then the total time left
        # is in mc_timelimit

        # But then again, we need to check mc_scheduled_vote_time against
        # mc_timelimit
        if (config_manager['scheduled_vote_time'] >=
                config_manager['timelimit']):

            new_value = (config_manager['timelimit'] *
                         INVALID_SCHEDULED_VOTE_TIME_FALLBACK_VALUE)

            warn(InvalidCVarValue(
                "mc_scheduled_vote_time exceeds or equals to mc_timelimit, "
                "falling back to {}".format(new_value)))

            cvar_scheduled_vote_time.set_float(new_value)

        # Calculate time to start the vote in
        seconds = (config_manager['timelimit'] * 60 -
                   config_manager['scheduled_vote_time'] * 60 -
                   config_manager['vote_duration'])

    # Schedule the vote
    global delay_scheduled_vote
    delay_scheduled_vote = Delay(seconds, launch_vote, scheduled=True)

    log.log_debug("Scheduled vote starts in {} seconds".format(seconds))

    # Schedule likemap survey
    if config_manager['likemap_survey_duration'] > 0:
        seconds = max(0, seconds - config_manager['likemap_survey_duration'])
        global delay_likemap_survey
        delay_likemap_survey = Delay(seconds, launch_likemap_survey)

        log.log_debug(
            "Scheduled likemap survey in {} seconds".format(seconds))


def change_level(round_end=False):
    if status.next_map is None:
        raise RuntimeError("It's already time to change the level, "
                           "but next map is yet to be decided")

    if config_manager['instant_change_level'] or round_end:
        log.log_debug("Ending the game...")

        game_end_entity = Entity.find_or_create('game_end')
        game_end_entity.end_game()

    else:
        log.log_debug("Waiting for the round end to end the game...")

        status.round_end_needed = True

        if config_manager['timeleft_auto_lastround_warning']:
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

    if ratio >= config_manager['rtv_needed']:

        # Cancel change_level delay if any
        global delay_changelevel
        if delay_changelevel is not None and delay_changelevel.running:
            delay_changelevel.cancel()

        # Relaunch change_level delay
        seconds = config_manager['vote_duration'] + EXTRA_SECONDS_AFTER_VOTE
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
    GameThread(target=save_maps_to_db).start()

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
        "Recent map names: {}".format(','.join(map_manager.recent_map_names)))

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

    for user in user_manager.values():
        user_manager.delete(user.player.index)


@Event('round_end')
def on_round_end(game_event):
    if status.round_end_needed:
        log.log_debug("round_end event, time to change the level")
        change_level(round_end=True)
        status.round_end_needed = False


@Event('cs_win_panel_match')
def on_cs_win_panel_match(game_event):

    # Check if the vote is still in progress
    if status.vote_status == status.VoteStatus.IN_PROGRESS:
        log.log_debug("on_cs_win_panel_match: vote was still in "
                      "progress, finishing")

        finish_vote()

    # Check if next map is decided
    if status.next_map is None:
        log.log_debug("on_cs_win_panel_match: no next_map defined!")

        return

    # Check if we need to show it on player screens
    if not config_manager['nextmap_show_on_match_end']:
        return

    # HudMsg
    hud_msg = HudMsg(
        strings_popups['nextmap_msg'].tokenize(
                map=status.next_map.name),
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

    # SayText2
    broadcast(strings_common['nextmap_msg'], map=status.next_map.name)


@OnClientActive
def listener_on_client_active(index):
    player = Player(index)
    if player.is_fake_client():
        return

    user_manager.create(player)


@OnClientDisconnect
def listener_on_client_disconnect(index):
    if index in user_manager:
        user_manager.delete(index)

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


@ServerCommand(ANTI_SPAM_TIMEOUT_SERVER, 'mc')
def command_on_mc(command):
    current_command = mc_commands['mc']
    i = 0
    for i in range(1, len(command)):
        next_command = current_command.registered_commands.get(
            command[i].lower())

        if next_command is None:
            i -= 1
            break

        current_command = next_command

    args = []
    for j in range(i + 1, len(command)):
        args.append(command[j])

    if current_command is mc_commands['mc']:
        echo_console("Unknown MC command. Type 'mc help' to get help")
        return

    current_command.callback(args)


@ServerCommand(ANTI_SPAM_TIMEOUT_SERVER, 'mc_launch_vote')
def command_on_mc_force_vote(command):
    if status.vote_status != status.VoteStatus.NOT_STARTED:
        echo_console("Can't launch the vote as it has "
                     "already started or ended")

        return

    launch_vote(scheduled=False)

    echo_console("Map vote has been launched")


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!votemap', 'votemap'))
def say_command_on_votemap(command, index, team_only):
    user = user_manager[index]
    reason = user.get_vote_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_main)


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!nominate', 'nominate'))
def say_command_on_nominate(command, index, team_only):
    user = user_manager[index]
    reason = user.get_nominate_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_nominate)


@SayCommand(
    ANTI_SPAM_TIMEOUT_PLAYER, ('!rtv', 'rtv', 'rockthevote', '!rockthevote'))
def say_command_on_rtv(command, index, team_only):
    user_manager[index].rtv_callback()


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, '!likemap')
def say_command_on_likemap(command, index, team_only):
    user = user_manager[index]
    reason = user.get_likemap_denial_reason()
    if reason is not None:
        tell(user.player, reason)
        return

    user.send_popup(popups.popup_likemap)


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!nextmap', 'nextmap'))
def say_command_on_nextmap(command, index, team_only):
    user = user_manager[index]
    user.nextmap_callback()


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!timeleft', 'timeleft'))
def say_command_on_nextmap(command, index, team_only):
    user = user_manager[index]
    user.timeleft_callback()
