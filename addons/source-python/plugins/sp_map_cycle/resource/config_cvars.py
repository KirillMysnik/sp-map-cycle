from config.manager import ConfigManager

from ..info import info

from .strings import strings_config


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
    config_manager.section("Maps Settings")
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
        min_value=0
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
    cvar_use_fullname = config_manager.cvar(
        name="use_fullname",
        default=1,
        description=strings_config['use_fullname'],
        min_value=0
    )
    cvar_predict_missing_fullname = config_manager.cvar(
        name="predict_missing_fullname",
        default=1,
        description=strings_config['predict_missing_fullname'],
        min_value=0
    )
    cvar_fullname_skips_prefix = config_manager.cvar(
        name="fullname_skips_prefix",
        default=1,
        description=strings_config['fullname_skips_prefix'],
        min_value=0
    )
    cvar_alphabetic_sort_by_fullname = config_manager.cvar(
        name="alphabetic_sort_by_fullname",
        default=0,
        description=strings_config['alphabetic_sort_by_fullname'],
        min_value=0
    )
    config_manager.section("Votes Settings")
    cvar_votemap_enable = config_manager.cvar(
        name="votemap_enable",
        default=1,
        description=strings_config['votemap_enable'],
        min_value=0
    )
    cvar_votemap_max_options = config_manager.cvar(
        name="votemap_max_options",
        default=5,
        description=strings_config['votemap_max_options'],
        min_value=0
    )
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
    cvar_votemap_chat_reaction = config_manager.cvar(
        name="votemap_chat_reaction",
        default=3,
        description=strings_config['votemap_chat_reaction'],
        min_value=0,
        max_value=3
    )
    cvar_votemap_allow_revote = config_manager.cvar(
        name="votemap_allow_revote",
        default=1,
        description=strings_config['votemap_allow_revote'],
        min_value=0
    )
    cvar_votemap_whatever_option = config_manager.cvar(
        name="votemap_whatever_option",
        default=1,
        description=strings_config['votemap_whatever_option'],
        min_value=0
    )
    cvar_alphabetic_sort_enable = config_manager.cvar(
        name="alphabetic_sort_enable",
        default=0,
        description=strings_config['alphabetic_sort_enable'],
        min_value=0
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
    config_manager.section("Nomination (!nominate) Settings")
    cvar_nominate_enable = config_manager.cvar(
        name="nominate_enable",
        default=1,
        description=strings_config['nominate_enable'],
        min_value=0
    )
    cvar_nominate_allow_revote = config_manager.cvar(
        name="nominate_allow_revote",
        default=1,
        description=strings_config['nominate_allow_revote'],
        min_value=0
    )
    config_manager.section("RTV (!rtv) Settings")
    cvar_rtv_enable = config_manager.cvar(
        name="rtv_enable",
        default=1,
        description=strings_config['rtv_enable'],
        min_value=0
    )
    cvar_rtv_needed = config_manager.cvar(
        name="rtv_needed",
        default=0.6,
        description=strings_config['rtv_needed'],
        min_value=0.0,
        max_value=1.0
    )
    cvar_rtv_delay = config_manager.cvar(
        name="rtv_delay",
        default=30.0,
        description=strings_config['rtv_delay'],
        min_value=0.0
    )
    config_manager.section("!nextmap Settings")
    cvar_nextmap_enable = config_manager.cvar(
        name="nextmap_enable",
        default=1,
        description=strings_config['nextmap_enable'],
        min_value=0
    )
    cvar_nextmap_show_on_match_end = config_manager.cvar(
        name="nextmap_show_on_match_end",
        default=1,
        description=strings_config['nextmap_show_on_match_end'],
        min_value=0
    )
    config_manager.section("!timeleft Settings")
    cvar_timeleft_enable = config_manager.cvar(
        name="timeleft_enable",
        default=1,
        description=strings_config['timeleft_enable'],
        min_value=0
    )
    cvar_timeleft_auto_lastround_warning = config_manager.cvar(
        name="timeleft_auto_lastround_warning",
        default=1,
        description=strings_config['timeleft_auto_lastround_warning'],
        min_value=0
    )
    config_manager.section("Like/Dislike Settings")
    cvar_likemap_enable = config_manager.cvar(
        name="likemap_enable",
        default=1,
        description=strings_config['likemap_enable'],
        min_value=0
    )
    cvar_likemap_method = config_manager.cvar(
        name="likemap_method",
        default=3,
        description=strings_config['likemap_method'],
        min_value=1,
        max_value=3
    )
    cvar_likemap_whatever_option = config_manager.cvar(
        name="likemap_whatever_option",
        default=1,
        description=strings_config['likemap_whatever_option'],
        min_value=0
    )
    cvar_likemap_survey_duration = config_manager.cvar(
        name="likemap_survey_duration",
        default=10.0,
        description=strings_config['likemap_survey_duration'],
        min_value=0.0,
    )
