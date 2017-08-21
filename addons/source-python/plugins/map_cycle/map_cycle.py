# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from datetime import datetime
import json
from random import shuffle
from time import time
from warnings import warn

# Source.Python
from colors import Color
from core import echo_console
from cvars import ConVar
from events import Event
from engines.server import engine_server, global_vars
from entities.entity import Entity
from listeners import OnLevelInit, OnLevelShutdown
from listeners.tick import Delay, GameThread
from loggers import LogManager
from memory import get_virtual_function
from memory.hooks import PreHook
from menus import PagedMenu, PagedOption, SimpleOption, SimpleMenu, Text
from messages import HudMsg
from paths import GAME_PATH
from stringtables.downloads import Downloadables

# Custom Package
from spam_proof_commands.say import SayCommand
from spam_proof_commands.server import ServerCommand

# Map Cycle
from .core.cvars import (
    config_manager, cvar_logging_areas, cvar_logging_level,
    cvar_scheduled_vote_time, cvar_timelimit)
from .core.mcplayers import broadcast, mcplayers, tell
from .core.models import ServerMap as DB_ServerMap
from .core.orm import Base, engine, Session
from .core.paths import (
    DEFAULT_MAPCYCLE_TXT_PATH, DOWNLOADLIST_PATH, MAPCYCLE_JSON_PATH,
    MAPCYCLE_TXT_PATH1, MAPCYCLE_TXT_PATH2)
from .core.server_maps import extend_entry, server_map_manager, whatever_entry
from .core.session_players import session_players
from .core.status import status, VoteStatus
from .core.strings import common_strings, popups_strings
from .core.vote_progress_bar import vote_progress_bar
from .core import mc_commands
from .info import info


# =============================================================================
# >> FUNCTIONS
# =============================================================================
def init_popups():
    @nomination_popup.register_select_callback
    def select_callback(popup, index, option):
        mcplayers[index].nominate_callback(option.value)

    @likemap_popup.register_select_callback
    def select_callback(popup, index, option):
        mcplayers[index].likemap_callback(option.value)

    @main_popup.register_select_callback
    def select_callback(popup, index, option):
        option.value.votes += 1
        vote_progress_bar.count_vote(option.value)
        mcplayers[index].vote_callback(option.value)

    likemap_popup.append(Text(popups_strings['rate_map']))

    choice_index = 1

    # First of all, add "I Don't Care" option if it's enabled
    if config_manager['likemap_whatever_option']:

        # Add to the list
        likemap_popup.append(SimpleOption(
            choice_index=choice_index,
            text=popups_strings['whatever'],
            value=0,
        ))
        choice_index += 1

    likemap_popup.append(SimpleOption(
        choice_index=choice_index,
        text=popups_strings['likemap_like'],
        value=1,
    ))
    choice_index += 1

    likemap_popup.append(SimpleOption(
        choice_index=choice_index,
        text=popups_strings['likemap_dislike'],
        value=-1,
    ))


def reload_mapcycle_json():
    if not MAPCYCLE_JSON_PATH.isfile():
        raise FileNotFoundError("Missing mapcycle.json")

    global mapcycle_json
    with open(MAPCYCLE_JSON_PATH) as f:
        mapcycle_json = json.load(f)


def build_json_from_mapcycle_txt():
    if (GAME_PATH / 'cfg' / cvar_mapcyclefile.get_string()).isfile():
        mapcycle_txt = GAME_PATH / 'cfg' / cvar_mapcyclefile.get_string()

    elif MAPCYCLE_TXT_PATH1.isfile():
        mapcycle_txt = MAPCYCLE_TXT_PATH1

    elif MAPCYCLE_TXT_PATH2.isfile():
        mapcycle_txt = MAPCYCLE_TXT_PATH2

    elif DEFAULT_MAPCYCLE_TXT_PATH.isfile():
        mapcycle_txt = DEFAULT_MAPCYCLE_TXT_PATH

    else:
        raise FileNotFoundError("Couldn't find mapcycle file anywhere")

    rs = []
    with open(mapcycle_txt) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith("//"):
                continue

            rs.append({
                'filename': line,
            })

    with open(MAPCYCLE_JSON_PATH, 'w') as f:
        json.dump(rs, f, indent=4)


def load_maps_from_db():
    session = Session()

    for db_server_map in session.query(DB_ServerMap).all():
        map_ = server_map_manager.get(db_server_map.filename)
        if map_ is None:
            continue

        map_.in_database = True
        map_.detected = db_server_map.detected
        map_.likes = db_server_map.likes
        map_.dislikes = db_server_map.dislikes

    session.close()


def save_maps_to_db():
    detected = int(time())

    session = Session()
    for server_map in server_map_manager.values():
        db_server_map = session.query(DB_ServerMap).filter_by(
            filename=server_map.filename.lower()).first()

        if db_server_map is None:
            server_map.detected = detected
            server_map.in_database = True

            db_server_map = DB_ServerMap()
            db_server_map.filename = server_map.filename.lower()
            db_server_map.detected = detected

            session.add(db_server_map)

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
    if status.vote_status != VoteStatus.NOT_STARTED:
        raise RuntimeError("Vote has already started or even ended, "
                           "can't execute reload_map_list now")

    server_map_manager.clear()
    for i, json_dict in enumerate(mapcycle_json):
        try:
            filename = json_dict['filename']
        except KeyError:
            warn("Map #{}: missing 'filename' key")
            continue

        if filename.lower() in server_map_manager:
            warn("Duplicate maps '{}'".format(filename))
            continue

        if not engine_server.is_map_valid(filename):
            warn("Engine says that '' is not a valid map".format(filename))
            continue

        server_map_manager.create(json_dict)

    logger.log_debug("Added {} valid maps".format(len(server_map_manager)))

    # Now rebuild nomination menu
    nomination_popup.clear()
    for server_map in sorted(
            server_map_manager.values(),
            key=lambda server_map: server_map.filename):

        selectable = not server_map.played_recently
        nomination_popup.append(PagedOption(
            text=server_map.name,
            value=server_map,
            highlight=selectable,
            selectable=selectable
        ))

    logger.log_debug("Added {} maps to the !nominate menu".format(
        len(server_map_manager.values())))


def reload_maps_from_mapcycle():
    # Load JSON
    try:
        # Try to load mapcycle.json
        reload_mapcycle_json()

        logger.log_debug("Loaded mapcycle.json (first try)")

    except FileNotFoundError:

        # If it fails, build mapcycle.json from the mapcyclefile file
        build_json_from_mapcycle_txt()

        # And then load mapcycle.json again, this time it
        # must succeed
        reload_mapcycle_json()

        logger.log_debug("Loaded mapcycle.json (after building it)")

    # Create MapCycleMap list using loaded JSON
    reload_map_list()

    # Fill maps properties with data from the database
    load_maps_from_db()


def launch_vote(scheduled=False):
    if status.vote_status != VoteStatus.NOT_STARTED:
        return      # TODO: Maybe put a warning or an exception here?

    logger.log_debug("Launching the vote (scheduled={})".format(scheduled))

    status.vote_status = VoteStatus.IN_PROGRESS
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
    likemap_popup.close()

    # Reset maps
    whatever_entry.votes = 0
    extend_entry.votes = 0
    for server_map in server_map_manager.values():
        server_map.votes = 0
        server_map.nominations = 0

    # Create new popup
    main_popup.clear()

    # First of all, add "I Don't Care" option if it's enabled
    if config_manager['votemap_whatever_option']:

        # Add to the list
        main_popup.append(PagedOption(
            text=whatever_entry.name,
            value=whatever_entry,
        ))

    # Only add "Extend this map..." option to scheduled votes
    if scheduled:

        # Decide if it's selectable and highlighted
        selectable = status.can_extend()

        # Add to the list
        main_popup.append(PagedOption(
            text=extend_entry.name,
            value=extend_entry,
            highlight=selectable,
            selectable=selectable
        ))

    # Now to the actual maps
    # Count nominations
    for nominated_map in mcplayers.get_nominated_maps():
        nominated_map.nominations += 1

    mcplayers.reset_nominated_maps()

    server_maps = server_map_manager.values()

    # Filter hidden maps out
    server_maps = list(filter(
        lambda server_map: not server_map.is_hidden, server_maps))

    if not server_maps:
        warn("Please add more maps to the server or reconfigure Map Cycle")
        return

    # Do we need to do an initial alphabetic sort?
    if config_manager['alphabetic_sort_enable']:

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
        main_popup.append(PagedOption(
            text=server_map.full_caption,
            value=server_map,
            highlight=selectable,
            selectable=selectable
        ))

    logger.log_debug("Added {} maps to the vote".format(len(server_maps)))

    # Send popup to players
    for mcplayer in mcplayers.values():
        if mcplayer.is_bot():
            continue

        mcplayer.send_popup(main_popup)

    # Define vote end
    delay_end_vote = Delay(config_manager['vote_duration'], finish_vote)

    # Start KeyHintProgress
    vote_progress_bar.start()

    # ... sound
    if config_manager['sound_vote_start'] is not None:
        config_manager['sound_vote_start'].play()

    # ... chat message
    broadcast(common_strings['vote_started'])


def finish_vote():
    if status.vote_status != VoteStatus.IN_PROGRESS:
        return      # TODO: Same, warning/exception may fit better here?

    logger.log_debug("Finishing the vote...")

    status.vote_status = VoteStatus.ENDED

    # Delay might still be running if the vote finished prematurely
    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    main_popup.close()

    # Stop KeyHintProgress
    vote_progress_bar.stop()

    # Recount votes to prevent reconnected players from messing things up
    # We only counted votes before to display them in the HintText area
    for server_map in server_map_manager.values():
        server_map.votes = 0

    for server_map in mcplayers.get_voted_maps():
        server_map.votes += 1

    mcplayers.reset_voted_maps()

    server_maps = server_map_manager.values()
    server_maps = filter(
        lambda server_map: not server_map.is_hidden, server_maps)

    if status.can_extend():
        candidate_maps = tuple(server_maps) + (extend_entry, )
    else:
        candidate_maps = server_maps

    candidate_maps = sorted(
        candidate_maps, key=lambda server_map: server_map.votes, reverse=True)

    if not candidate_maps:

        # If there're no maps on the server, there's not much we can do
        logger.log_debug("No maps to choose from in finish_vote()!")

        broadcast(common_strings['no_choice'])

        if delay_changelevel and delay_changelevel.running:
            logger.log_debug("Cancelling change_level...")

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
    if winner_map is extend_entry:
        logger.log_debug("Winner map: extend-this-map option")

        status.used_extends += 1
        broadcast(common_strings['map_extended'].tokenized(
            time=config_manager['extend_time']))

    else:
        logger.log_debug("Winner map: {}".format(winner_map.filename))

        broadcast(common_strings['map_won'].tokenized(map=winner_map.name))

    # ... sound
    if config_manager['sound_vote_end'] is not None:
        config_manager['sound_vote_end'].play()


def set_next_map(server_map):

    # First of all, check if we actually need to extend the current map
    if server_map is extend_entry:
        logger.log_debug("Extending current level...")

        # Set NOT_STARTED state so that they can nominate maps and stuff
        status.vote_status = VoteStatus.NOT_STARTED

        # Reset RTV for each user
        mcplayers.reset_rtv()

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

    logger.log_debug("Setting next map to {}...".format(server_map.filename))

    # If we don't need to extend current map, set a new next map
    status.next_map = server_map


def schedule_change_level(was_extended=False):

    # Do we even need to change levels?
    if config_manager['timelimit'] == 0:

        # If not, no reason to continue
        return

    logger.log_debug(
        "Scheduling change_level (was_extended={})".format(was_extended))

    if was_extended:
        seconds = config_manager['extend_time'] * 60 + EXTRA_SECONDS_AFTER_VOTE
    else:
        seconds = config_manager['timelimit'] * 60 + EXTRA_SECONDS_AFTER_VOTE

    global delay_changelevel
    delay_changelevel = Delay(seconds, change_level)

    status.map_end_time = time() + seconds

    logger.log_debug("We will end the game in {} seconds.".format(seconds))


def schedule_vote(was_extended=False):

    # Do we even need scheduled votes?
    if config_manager['timelimit'] == 0:

        # If not, no reason to continue
        return

    logger.log_debug(
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

            warn("mc_scheduled_vote_time exceeds or equals to mc_extend_time, "
                 "falling back to {}".format(new_value))

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

            warn("mc_scheduled_vote_time exceeds or equals to mc_timelimit, "
                 "falling back to {}".format(new_value))

            cvar_scheduled_vote_time.set_float(new_value)

        # Calculate time to start the vote in
        seconds = (config_manager['timelimit'] * 60 -
                   config_manager['scheduled_vote_time'] * 60 -
                   config_manager['vote_duration'])

    # Schedule the vote
    global delay_scheduled_vote
    delay_scheduled_vote = Delay(seconds, launch_vote, args=(True, ))

    logger.log_debug("Scheduled vote starts in {} seconds".format(seconds))

    # Schedule likemap survey
    if config_manager['likemap_survey_duration'] > 0:
        seconds = max(0, seconds - config_manager['likemap_survey_duration'])
        global delay_likemap_survey
        delay_likemap_survey = Delay(seconds, launch_likemap_survey)

        logger.log_debug(
            "Scheduled likemap survey in {} seconds".format(seconds))


def change_level(round_end=False):
    if status.next_map is None:
        raise RuntimeError("It's already time to change the level, "
                           "but next map is yet to be decided")

    if config_manager['instant_change_level'] or round_end:
        logger.log_debug("Ending the game...")

        game_end_entity = Entity.find_or_create('game_end')
        game_end_entity.end_game()

    else:
        logger.log_debug("Waiting for the round end to end the game...")

        status.round_end_needed = True

        if config_manager['timeleft_auto_lastround_warning']:
            broadcast(common_strings['timeleft_last_round'])


def check_if_enough_votes():
    for mcplayer in mcplayers.values():
        if mcplayer.is_bot():
            continue

        if mcplayer.voted_map is None:
            return

    finish_vote()


def check_if_enough_rtv():
    try:
        ratio = mcplayers.count_rtv_ratio()
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
    logger.log_debug("Launching mass likemap survey")

    for mcplayer in mcplayers.values():
        if mcplayer.is_bot():
            continue

        reason = mcplayer.get_likemap_denial_reason()
        if reason is not None:
            continue

        mcplayer.send_popup(likemap_popup)


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
NEXTMAP_MSG_COLOR = Color(124, 173, 255)
NEXTMAP_MSG_X = -1
NEXTMAP_MSG_Y = 0.05
NEXTMAP_MSG_EFFECT = 2
NEXTMAP_MSG_FADEIN = 0.05
NEXTMAP_MSG_FADEOUT = 0
NEXTMAP_MSG_HOLDTIME = 10
NEXTMAP_MSG_FXTIME = 0
NEXTMAP_MSG_CHANNEL = 3

# Used for SpamProofCommands
ANTI_SPAM_TIMEOUT_SERVER = 1.0
ANTI_SPAM_TIMEOUT_PLAYER = 1.0

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

with open(DOWNLOADLIST_PATH) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        downloadables.add(line)


# Save original mp_timelimit value
mp_timelimit_old_value = 0

logger = LogManager(info.name, cvar_logging_level, cvar_logging_areas)

mapcycle_json = None

# Delays
delay_scheduled_vote = None
delay_changelevel = None
delay_end_vote = None
delay_likemap_survey = None

# Popups
nomination_popup = PagedMenu(title=popups_strings['nominate_map'])
likemap_popup = SimpleMenu()
main_popup = PagedMenu(title=popups_strings['choose_map'])

# ChangeLevel function (to hook)
engine_server_changelevel = get_virtual_function(engine_server, 'ChangeLevel')


# =============================================================================
# >> CLASSES
# =============================================================================
class CorruptJSONFile(Exception):
    """Raised when mapcycle.json doesn't contain a list."""
    pass


# =============================================================================
# >> SYNCHRONOUS DATABASE OPERATIONS
# =============================================================================
Base.metadata.create_all(engine)


# =============================================================================
# >> LOAD & UNLOAD FUNCTIONS
# =============================================================================
def load():
    logger.log_debug("Entered load()...")

    reload_maps_from_mapcycle()

    logger.log_debug("Reloaded map list from JSON")

    # Save old mp_timelimit value
    global mp_timelimit_old_value
    mp_timelimit_old_value = cvar_mp_timelimit.get_float()

    # If mc_timelimit equals to -1, grab the value from mp_timelimit
    if config_manager['timelimit'] < 0:
        cvar_timelimit.set_float(mp_timelimit_old_value)

        logger.log_debug(
            "mc_timelimit was -1, set to the value of mp_timelimit "
            "(mp_timelimit = {})".format(mp_timelimit_old_value))

    if mp_timelimit_old_value < 0:
        warn("mp_timelimit is negative, can't grab value from it")

        cvar_timelimit.set_float(NEGATIVE_TIMELIMIT_FALLBACK_VALUE)

    # We don't need mp_timelimit to change the maps for us
    cvar_mp_timelimit.set_float(0.0)

    # Also mark current level name (if it's loaded) as a recently played
    if global_vars.map_name:
        map_name = global_vars.map_name
        server_map_manager.recent_map_names.append(global_vars.map_name)
        logger.log_debug("Current level name is {}".format(map_name))

        status.current_map = server_map_manager.get(map_name)

        if status.current_map is None:
            logger.log_debug("Current map '{}' is not "
                          "from mapcycle.json!".format(map_name))

        # We think that the level is loaded with us
        status.map_start_time = time()
        logger.log_debug("Level start time: {}".format(
            datetime.fromtimestamp(
                status.map_start_time
            ).strftime('%X')))

        # Schedule the vote, it will be scheduled as if the map is loaded
        # with us
        schedule_vote()

        # Schedule level changing - this can be later cancelled
        # by map extensions
        schedule_change_level()

    # Init popups
    init_popups()

    # ... chat message
    broadcast(common_strings['loaded'])


def unload():
    logger.log_debug("Entered unload()...")

    # Restore mp_timelimit to its original (or changed) value
    cvar_mp_timelimit.set_float(mp_timelimit_old_value)

    # Update database
    save_maps_to_db()

    # ... chat message
    broadcast(common_strings['unloaded'])


# =============================================================================
# >> COMMANDS
# =============================================================================
@ServerCommand(ANTI_SPAM_TIMEOUT_SERVER, 'mc_launch_vote')
def cmd_mc_launch_vote(command):
    if status.vote_status != VoteStatus.NOT_STARTED:
        echo_console(
            "Can't launch the vote as it has already started or ended")

        return

    launch_vote(scheduled=False)
    echo_console("Map vote has been launched")


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!votemap', 'votemap'))
def cmd_votemap(command, index, team_only):
    mcplayer = mcplayers[index]
    reason = mcplayer.get_vote_denial_reason()
    if reason is not None:
        tell(mcplayer.player, reason)
        return

    mcplayer.send_popup(main_popup)


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!nominate', 'nominate'))
def cmd_nominate(command, index, team_only):
    mcplayer = mcplayers[index]
    reason = mcplayer.get_nominate_denial_reason()
    if reason is not None:
        tell(mcplayer.player, reason)
        return

    mcplayer.send_popup(nomination_popup)


@SayCommand(
    ANTI_SPAM_TIMEOUT_PLAYER, ('!rtv', 'rtv', 'rockthevote', '!rockthevote'))
def cmd_rockthevote(command, index, team_only):
    mcplayers[index].rtv_callback()


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, '!likemap')
def cmd_likemap(command, index, team_only):
    mcplayer = mcplayers[index]
    reason = mcplayer.get_likemap_denial_reason()
    if reason is not None:
        tell(mcplayer.player, reason)
        return

    mcplayer.send_popup(likemap_popup)


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!nextmap', 'nextmap'))
def cmd_nextmap(command, index, team_only):
    mcplayer = mcplayers[index]
    mcplayer.nextmap_callback()


@SayCommand(ANTI_SPAM_TIMEOUT_PLAYER, ('!timeleft', 'timeleft'))
def cmd_timeleft(command, index, team_only):
    mcplayer = mcplayers[index]
    mcplayer.timeleft_callback()


# =============================================================================
# >> EVENTS
# =============================================================================
@Event('round_end')
def on_round_end(game_event):
    if status.round_end_needed:
        logger.log_debug("round_end event, time to change the level")
        change_level(round_end=True)
        status.round_end_needed = False


@Event('cs_win_panel_match')
def on_cs_win_panel_match(game_event):

    # Check if the vote is still in progress
    if status.vote_status == VoteStatus.IN_PROGRESS:
        logger.log_debug("on_cs_win_panel_match: vote was still in "
                         "progress, finishing")

        finish_vote()

    # Check if next map is decided
    if status.next_map is None:
        logger.log_debug("on_cs_win_panel_match: no next_map defined!")

        return

    if config_manager['nextmap_show_on_match_end']:
        # HudMsg
        hud_msg = HudMsg(
            common_strings['nextmap_msg'].tokenized(map=status.next_map.name),
            color1=NEXTMAP_MSG_COLOR,
            x=NEXTMAP_MSG_X,
            y=NEXTMAP_MSG_Y,
            effect=NEXTMAP_MSG_EFFECT,
            fade_in=NEXTMAP_MSG_FADEIN,
            fade_out=NEXTMAP_MSG_FADEOUT,
            hold_time=NEXTMAP_MSG_HOLDTIME,
            fx_time=NEXTMAP_MSG_FXTIME,
            channel=NEXTMAP_MSG_CHANNEL,
        )
        hud_msg.send()

        # SayText2
        broadcast(common_strings['nextmap_msg'].tokenized(
            map=status.next_map.name))


# =============================================================================
# >> LISTENERS
# =============================================================================
@OnLevelInit
def listener_on_level_init(map_name):
    logger.log_debug(
        "Entered OnLevelInit listener (map_name={})...".format(map_name))

    # Reset MCPlayer instances
    mcplayers.reset_all()

    # Clear SessionPlayerManager
    session_players.clear()

    # Cancel delays if any
    if delay_scheduled_vote is not None and delay_scheduled_vote.running:
        delay_scheduled_vote.cancel()

    global delay_changelevel   # We will assign to this a few lines later
    if delay_changelevel is not None and delay_changelevel.running:
        delay_changelevel.cancel()

    if delay_end_vote is not None and delay_end_vote.running:
        delay_end_vote.cancel()

    if delay_likemap_survey is not None and delay_likemap_survey.running:
        delay_likemap_survey.cancel()

    # Reset Status
    status.vote_status = VoteStatus.NOT_STARTED
    status.next_map = None
    status.map_start_time = time()
    status.used_extends = 0

    # Update database
    GameThread(target=save_maps_to_db).start()

    # Reload maps
    reload_maps_from_mapcycle()

    # Set current map in Status
    status.current_map = server_map_manager.get(map_name.lower())

    if status.current_map is None:
        logger.log_debug("Current map '{}' is not "
                         "from mapcycle.json!".format(map_name))

    # Unsend popups
    main_popup.close()

    # Add current map names to recent_map_names
    server_map_manager.recent_map_names.append(map_name)

    # And then cap recent_map_names
    server_map_manager.cap_recent_maps()

    logger.log_debug(
        "Recent map names: {}".format(','.join(
            server_map_manager.recent_map_names)))

    # Schedule regular vote
    schedule_vote(was_extended=False)

    # Schedule level changing - this can be later cancelled by map extensions
    schedule_change_level(was_extended=False)


@OnLevelShutdown
def listener_on_level_shutdown():
    logger.log_debug("Entered OnLevelShutdown listener")

    # Calculate map ratings
    if status.current_map is not None:
        for rating in session_players.get_map_ratings():
            if rating == 1:
                status.current_map.likes += 1

            elif rating == -1:
                status.current_map.dislikes += 1

    session_players.reset_map_ratings()


# =============================================================================
# >> HOOKS
# =============================================================================
@PreHook(engine_server_changelevel)
def pre_engine_server_changelevel(args):
    logger.log_debug("Hooked ChangeLevel...")

    # Set our own next map
    if status.next_map is not None:
        args[1] = status.next_map.filename


# =============================================================================
# >> EXTERNAL API
# =============================================================================
# Doing it here because this API imports stuff from our main module
from . import external
