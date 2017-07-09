# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from datetime import datetime
from time import time

# Source-Python
from commands.typed import TypedServerCommand
from core import echo_console
from listeners.tick import GameThread

# Site-Package
from jinja2 import Environment
from jinja2 import FileSystemLoader

# Map Cycle
from .models import ServerMap as DB_ServerMap
from .orm import Session
from .paths import (
    DBDUMP_DIR, DBDUMP_HTML_PATH, DBDUMP_TXT_PATH, MAPCYCLE_TXT_PATH1,
    MAPS_DIR, TEMPLATES_DIR, WORKSHOP_DIR)


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
DB_SHOW_CAP = 40

j2env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
j2env.filters['strftime'] = (
    lambda timestamp: datetime.fromtimestamp(timestamp).strftime('%c'))
j2template_html = j2env.get_template('databasedump.html')
j2template_txt = j2env.get_template('databasedump.txt')

DBDUMP_DIR.makedirs_p()


# =============================================================================
# >> COMMANDS
# =============================================================================
@TypedServerCommand(['mc', 'help'])
def callback(command_info):
    echo_console("""mc help:
> mc help
Shows this help message

> mc reload_mapcycle
Reloads mapcycle.json

> mc rebuild_mapcycle
Creates new mapcycle.json based on mapcycle.txt (mapcycle_default.txt)

> mc db show [<starting ID>]
Prints contents of database.sqlite3. If the starting ID is given, shows the
contents only beginning from this ID.

> mc db dump_html
Dumps contents of the database to an HTML page:
<mod folder>/logs/source-python/map_cycle/databasedump.html

> mc db dump_txt
Dumps contents of the database to a text file:
<mod folder>/logs/source-python/map_cycle/databasedump.txt

> mc db save
Saves current maps list from memory to the database

> mc db load
Reloads data from the database into memory

> mc db set_old <map filename>
Marks the given map as old (no NEW! postfix)

> mc db set_old_all
Marks all known maps as old (no NEW! postfix)

> mc db forget_map <map filename>
Removes the given map from the database, doesn't remove the map from the
mapcycle.
Map will be added to the database again if it's still in mapcycle.

> mc scan_maps_folder [<map prefix> ...]
Scans contents of ../maps folder and puts scanned maps in mapcycle.txt.
You can then convert that mapcycle.txt to mapcycle.json by typing
'mc rebuild_mapcycle'.
If map prefixes are given, only maps that start with that prefix will be added
to the list.
Example:
mc scan_maps_folder de_ cs_ gg_
""")


@TypedServerCommand(['mc', 'reload_mapcycle'])
def callback(command_info):
    from ..map_cycle import (
        load_maps_from_db, reload_map_list, reload_mapcycle_json)

    try:
        reload_mapcycle_json()
        echo_console("Loaded JSON from mapcycle.json")
    except FileNotFoundError:
        echo_console("Error: Missing mapcycle.json, please rebuild it first")
        return

    try:
        reload_map_list()
    except RuntimeError as e:
        echo_console("Error: {}".format(e))
        return

    echo_console("Reloaded maps list from JSON")

    if load_maps_from_db():
        echo_console("Data from the database was reloaded")


@TypedServerCommand(['mc', 'rebuild_mapcycle'])
def callback(command_info):
    from ..map_cycle import build_json_from_mapcycle_txt

    try:
        build_json_from_mapcycle_txt()
    except FileNotFoundError:
        echo_console("Error: No mapcycle.txt nor mapcycle_default.txt found "
                     "in /cfg directory. You can create one automatically by "
                     "typing 'mc scan_maps_folder'.""")
    else:
        echo_console("mapcycle.json was rebuild")


@TypedServerCommand(['mc', 'db', 'show'])
def callback(command_info, start_id:int=0):
    session = Session()

    echo_console("+----+--------------------------------+--------------+-"
                 "------------------+")
    echo_console("| ID | Map File Name (w/o .bsp)       | Detected     | "
                 "Likes/Total       |")
    echo_console("+----+--------------------------------+--------------+-"
                 "------------------+")

    db_server_maps = session.query(DB_ServerMap).order_by(
        DB_ServerMap.detected)[start_id:start_id+DB_SHOW_CAP]

    for db_server_map in db_server_maps:
        echo_console("| {}| {}| {}| {}|".format(
            str(db_server_map.id).ljust(3)[:3],

            db_server_map.filename.ljust(31)[:31],

            datetime.fromtimestamp(db_server_map.detected)
                .strftime('%x').ljust(13)[:13],

            "{:.2f}".format(
                db_server_map.likes /
                (db_server_map.likes + db_server_map.dislikes)
            ).ljust(18)[:18] if (
                db_server_map.likes + db_server_map.dislikes != 0
            ) else "n/a".ljust(18),
        ))

    echo_console("+----+--------------------------------+--------------+-"
                 "------------------+")

    echo_console("* Only showing rows from {} to {}".format(
        start_id + 1, start_id + DB_SHOW_CAP))

    session.close()


@TypedServerCommand(['mc', 'db', 'dump_html'])
def callback(command_info):
    session = Session()

    j2template_html.stream(rows=session.query(DB_ServerMap).all(),
                           dumpdate=time()).dump(DBDUMP_HTML_PATH)

    echo_console("Dump written to {}".format(DBDUMP_HTML_PATH))
    session.close()


@TypedServerCommand(['mc', 'db', 'dump_txt'])
def callback(command_info):
    session = Session()

    j2template_txt.stream(rows=session.query(DB_ServerMap).all(),
                          dumpdate=time()).dump(DBDUMP_TXT_PATH)

    echo_console("Dump written to {}".format(DBDUMP_TXT_PATH))
    session.close()


@TypedServerCommand(['mc', 'db', 'save'])
def callback(command_info):
    from ..map_cycle import save_maps_to_db

    def save():
        save_maps_to_db()
        echo_console("Data was saved to the database")

    GameThread(target=save).start()


@TypedServerCommand(['mc', 'db', 'load'])
def callback(command_info):
    from ..map_cycle import load_maps_from_db

    def load():
        load_maps_from_db()
        echo_console("Data from the database was reloaded")

    GameThread(target=load).start()


@TypedServerCommand(['mc', 'db', 'set_old'])
def callback(command_info, map_name:str):
    session = Session()

    db_server_map = session.query(DB_ServerMap).filter_by(
        filename=map_name).first()

    if db_server_map is None:
        echo_console("Unknown map: {}".format(map_name))

    else:
        db_server_map.detected = 0
        session.commit()

        echo_console("Operation succeeded.")

    session.close()


@TypedServerCommand(['mc', 'db', 'set_old_all'])
def callback(command_info):
    session = Session()

    for db_server_map in session.query(DB_ServerMap).all():
        db_server_map.detected = 0

    session.commit()

    echo_console("Operation succeeded.")

    session.close()


@TypedServerCommand(['mc', 'db', 'forget_map'])
def callback(command_info, map_name:str):
    session = Session()

    db_server_map = session.query(DB_ServerMap).filter_by(
        filename=map_name).first()

    if db_server_map is None:
        echo_console("Unknown map: {}".format(map_name))

    else:
        session.delete(db_server_map)
        session.commit()

        echo_console("Operation succeeded.")

    session.close()


@TypedServerCommand(['mc', 'scan_maps_folder'])
def callback(command_info, *prefixes:str):
        if prefixes:
            prefixes = list(map(lambda prefix: prefix.lower(), prefixes))
            echo_console("Scanning maps only with the "
                         "following prefixes:\n{}".format(','.join(prefixes)))

            def is_valid_map(path):
                if path.ext.lower() != ".bsp":
                    return False

                map_name = path.namebase.lower()
                for prefix in prefixes:
                    if map_name.startswith(prefix):
                        return True

                return False

        else:
            echo_console("Scanning all maps...")

            def is_valid_map(path):
                return path.ext.lower() == ".bsp"

        rs = []

        for map_path in MAPS_DIR.files():
            if is_valid_map(map_path):
                rs.append(map_path.namebase.lower())

        if WORKSHOP_DIR.isdir():
            echo_console(
                "Found /maps/workshop dir! Scanning Steam Workshop maps...")

            for subdir_path in WORKSHOP_DIR.dirs():
                subdir_name = subdir_path.namebase.lower()

                for map_path in subdir_path.files():
                    map_name = map_path.namebase.lower()

                    if is_valid_map(map_path):
                        rs.append(f"workshop/{subdir_name}/{map_name}")

        with open(MAPCYCLE_TXT_PATH1, 'w') as f:
            for map_name in rs:
                f.write(map_name + '\n')

        echo_console("{} maps were scanned and written to "
                     "mapcycle.txt".format(len(rs)))
