# =============================================================================
# >> IMPORTS
# =============================================================================
# Custom Package
from controlled_cvars import ControlledConfigManager, InvalidValue
from controlled_cvars.handlers import (
    bool_handler, float_handler, int_handler, sound_nullable_handler)

# Map Cycle
from ..info import info
from .strings import config_strings


def uint_handler(cvar):
    value = int_handler(cvar)
    if value < 0:
        raise InvalidValue
    return value


def ufloat_handler(cvar):
    value = float_handler(cvar)
    if value < 0:
        raise InvalidValue
    return value


config_manager = ControlledConfigManager(
    info.name + "/main", cvar_prefix='mc_')

config_manager.section("Logging")
cvar_logging_level = config_manager.controlled_cvar(
    uint_handler,
    "logging_level",
    default=4,
    description=config_strings['logging_level'],
)
cvar_logging_areas = config_manager.controlled_cvar(
    uint_handler,
    "logging_areas",
    default=5,
    description=config_strings['logging_areas'],
)

config_manager.section("Maps Settings")
cvar_timelimit = config_manager.controlled_cvar(
    float_handler,
    "timelimit",
    default=-1,
    description=config_strings['timelimit'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="instant_change_level",
    default=0,
    description=config_strings['instant_change_level'],
)
config_manager.controlled_cvar(
    int_handler,
    name="max_extends",
    default=2,
    description=config_strings['max_extends'],
)
config_manager.controlled_cvar(
    ufloat_handler,
    name="extend_time",
    default=15,
    description=config_strings['extend_time'],
    min_value=1.0
)
config_manager.controlled_cvar(
    uint_handler,
    name="recent_maps_limit",
    default=2,
    description=config_strings['recent_maps_limit'],
)
config_manager.controlled_cvar(
    int_handler,
    name="new_map_timeout_days",
    default=5,
    description=config_strings['new_map_timeout_days'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="use_fullname",
    default=1,
    description=config_strings['use_fullname'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="workshop_maps_use_full_path",
    default=0,
    description=config_strings['workshop_maps_use_full_path'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="predict_missing_fullname",
    default=1,
    description=config_strings['predict_missing_fullname'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="fullname_skips_prefix",
    default=1,
    description=config_strings['fullname_skips_prefix'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="alphabetic_sort_by_fullname",
    default=0,
    description=config_strings['alphabetic_sort_by_fullname'],
)

config_manager.section("Votes Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="votemap_enable",
    default=1,
    description=config_strings['votemap_enable'],
)
config_manager.controlled_cvar(
    uint_handler,
    name="votemap_max_options",
    default=5,
    description=config_strings['votemap_max_options'],
)
config_manager.controlled_cvar(
    uint_handler,
    name="vote_duration",
    default=30,
    description=config_strings['vote_duration'],
)
cvar_scheduled_vote_time = config_manager.controlled_cvar(
    ufloat_handler,
    name="scheduled_vote_time",
    default=5,
    description=config_strings['scheduled_vote_time'],
)
config_manager.controlled_cvar(
    uint_handler,
    name="votemap_chat_reaction",
    default=3,
    description=config_strings['votemap_chat_reaction'],
    min_value=0,
    max_value=3,
)
config_manager.controlled_cvar(
    bool_handler,
    name="votemap_allow_revote",
    default=1,
    description=config_strings['votemap_allow_revote'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="votemap_whatever_option",
    default=1,
    description=config_strings['votemap_whatever_option'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="votemap_show_progress",
    default=1,
    description=config_strings['votemap_show_progress'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="votemap_progress_use_hudmsg",
    default=1,
    description=config_strings['votemap_progress_use_hudmsg'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="alphabetic_sort_enable",
    default=0,
    description=config_strings['alphabetic_sort_enable'],
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    name="sound_vote_start",
    default="admin_plugin/actions/startyourvoting.mp3",
    description=config_strings['sound_vote_start']
)
config_manager.controlled_cvar(
    sound_nullable_handler,
    name="sound_vote_end",
    default="admin_plugin/actions/endofvote.mp3",
    description=config_strings['sound_vote_end']
)

config_manager.section("Nomination (!nominate) Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="nominate_enable",
    default=1,
    description=config_strings['nominate_enable'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="nominate_allow_revote",
    default=1,
    description=config_strings['nominate_allow_revote'],
)

config_manager.section("RTV (!rtv) Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="rtv_enable",
    default=1,
    description=config_strings['rtv_enable'],
)
config_manager.controlled_cvar(
    ufloat_handler,
    name="rtv_needed",
    default=0.6,
    description=config_strings['rtv_needed'],
    min_value=0.0,
    max_value=1.0
)
config_manager.controlled_cvar(
    ufloat_handler,
    name="rtv_delay",
    default=30.0,
    description=config_strings['rtv_delay'],
)

config_manager.section("!nextmap Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="nextmap_enable",
    default=1,
    description=config_strings['nextmap_enable'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="nextmap_show_on_match_end",
    default=1,
    description=config_strings['nextmap_show_on_match_end'],
)

config_manager.section("!timeleft Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="timeleft_enable",
    default=1,
    description=config_strings['timeleft_enable'],
)
config_manager.controlled_cvar(
    bool_handler,
    name="timeleft_auto_lastround_warning",
    default=1,
    description=config_strings['timeleft_auto_lastround_warning'],
)

config_manager.section("Like/Dislike Settings")
config_manager.controlled_cvar(
    bool_handler,
    name="likemap_enable",
    default=1,
    description=config_strings['likemap_enable'],
)
config_manager.controlled_cvar(
    uint_handler,
    name="likemap_method",
    default=3,
    description=config_strings['likemap_method'],
    min_value=1,
    max_value=3
)
config_manager.controlled_cvar(
    bool_handler,
    name="likemap_whatever_option",
    default=1,
    description=config_strings['likemap_whatever_option'],
)
config_manager.controlled_cvar(
    ufloat_handler,
    name="likemap_survey_duration",
    default=10.0,
    description=config_strings['likemap_survey_duration'],
)

config_manager.write()
config_manager.execute()
