from datetime import datetime
import os
from time import time

from jinja2 import Environment
from jinja2 import FileSystemLoader

from core import echo_console
from paths import BASE_PATH
from paths import GAME_PATH
from paths import LOG_PATH

from sp_map_cycle.db import connect
from sp_map_cycle.db import delete
from sp_map_cycle.db import select
from sp_map_cycle.db import update
from sp_map_cycle.info import info


MAPS_FOLDER = str(GAME_PATH / 'maps')
MAPCYCLETXT = str(GAME_PATH / 'cfg' / 'mapcycle.txt')
DBDUMP_PATH = LOG_PATH / info.basename
DBDUMPHTML = DBDUMP_PATH / 'databasedump.html'
DBDUMPTXT = DBDUMP_PATH / 'databasedump.txt'
TEMPLATES_DIR = str(BASE_PATH / 'plugins' / info.basename / 'templates')
DB_SHOW_CAP = 40


os.makedirs(DBDUMP_PATH, exist_ok=True)

j2env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
j2env.filters['strftime'] = lambda timestamp: datetime.fromtimestamp(timestamp).strftime('%c')
j2template_html = j2env.get_template('databasedump.html')


class SPMCCommand:
    def __init__(self, name, parent=None):
        self.registered_commands = {}
        if parent is not None:
            parent.registered_commands[name] = self

    def callback(self, *args):
        raise NotImplementedError


class SPMCCommandHelp(SPMCCommand):
    def callback(self, args):
        echo_console("""spmc help:
> spmc help
Shows this help message

> spmc reload-mapcycle
Reloads mapcycle.json

> spmc rebuild-mapcycle
Creates new mapcycle.json based on mapcycle.txt (mapcycle_default.txt)

> spmc db show [<starting ID>]
Prints contents of database.sqlite3. If the starting ID is given, shows the
contents only beginning from this ID.

> spmc db dump-html
Dumps contents of database.sqlite3 to an HTML page:
<mod folder>/logs/source-python/sp_map_cycle/databasedump.html

> spmc db save
Saves current maps list from memory to the database

> spmc db load
Reloads data from the database into memory

> spmc db set-force-old <map filename>
Marks the given map as old (no NEW! postfix)

> spmc db set-force-old-all
Marks all known maps as old (no NEW! postfix)

> spmc db unset-force-old-flag <map filename>
Restores 'new' flag for the given map based on its detection date.
The flag may not be restored if the map is actually old, but you can make
database forget such map by typing 'spmc db forget-map <map filename>'.

> spmc db forget-map <map filename>
Removes the given map from the database, doesn't remove the map from the mapcycle.
Map will be added to the database again if it's still in mapcycle.

> spmc scan-maps-folder [<map prefix> ...]
Scans contents of ../maps folder and puts scanned maps in mapcycle.txt.
You can then convert that mapcycle.txt to mapcycle.json by typing 'spmc rebuild-mapcycle'.
If map prefixes are given, only maps that start with that prefix will be added to the list.
Example:
spmc scan-maps-folder de_ cs_ gg_
""")


class SPMCCommandReloadMapCycle(SPMCCommand):
    def callback(self, args):
        from sp_map_cycle.sp_map_cycle import load_maps_from_db
        from sp_map_cycle.sp_map_cycle import reload_mapcycle_json
        from sp_map_cycle.sp_map_cycle import reload_map_list
        try:
            reload_mapcycle_json()
            echo_console("Loaded JSON from mapcycle.json")
        except FileNotFoundError:
            echo_console("Error: Missing mapcycle.json, please rebuild it first")
        else:
            try:
                reload_map_list()
            except RuntimeError as e:
                echo_console("Error: {}".format(e))
            else:
                echo_console("Reloaded maps list from JSON")

                if load_maps_from_db():
                    echo_console("Data from the database was reloaded")


class SPMCCommandRebuildMapCycle(SPMCCommand):
    def callback(self, args):
        from sp_map_cycle.sp_map_cycle import build_json_from_mapcycle_txt
        try:
            build_json_from_mapcycle_txt()
        except FileNotFoundError:
            echo_console("""Error: No mapcycle.txt nor mapcycle_default.txt found in cfg directory.
You can create one automatically by typing 'spmc scan-maps-folder'.""")
        else:
            echo_console("mapcycle.json was rebuild")


class SPMCCommandDB(SPMCCommand):
    def callback(self, args):
        echo_console("Not enough parameters, type 'spmc help' to get help")


class SPMCCommandShowDatabase(SPMCCommand):
    def callback(self, args):
        start = int(args[0]) if args else 1

        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            echo_console("+----+--------------------------------+----------+--------+-------------+")
            echo_console("| ID | Map File Name (w/o .bsp)       | Detected | Old?** | Likes/Total |")
            echo_console("+----+--------------------------------+----------+--------+-------------+")

            for row in select(
                    conn,
                    'maps',
                    ('rowid', 'filename', 'detected', 'force_old', 'likes', 'dislikes'),
                    limit=DB_SHOW_CAP,
                    offset=start-1
            ):

                echo_console("| {}| {}| {}| {}| {}|".format(
                    str(row['rowid']).ljust(3)[:3],
                    row['filename'].ljust(31)[:31],
                    datetime.fromtimestamp(row['detected']).strftime('%x').ljust(9)[:9],
                    "YES".ljust(7) if row['force_old'] else "NO".ljust(7),
                    ("{:.2f}".format(row['likes']/(row['dislikes']+row['likes'])).ljust(12)[:12] if
                     (row['dislikes']+row['likes']) != 0 else "n/a".ljust(12)),
                ))

            echo_console("+----+--------------------------------+----------+--------+-------------+")
            echo_console("* Only showing rows from {} to {}".format(start, start + DB_SHOW_CAP))
            echo_console("** Only shows if the map was marked old via 'spmc db set-force-old' command")

        finally:
            conn.close()


class SPMCCommandDumpDatabaseHTML(SPMCCommand):
    def callback(self, args):
        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            rows = select(
                conn,
                'maps',
                (
                        'rowid',
                        'filename',
                        'detected',
                        'force_old',
                        'likes',
                        'dislikes',
                        'man_hours',
                        'av_session_length'
                ),
            )

            j2template_html.stream(rows=rows, dumpdate=time()).dump(DBDUMPHTML)

            echo_console("Dump written to {}".format(DBDUMPHTML))

        finally:
            conn.close()


class SPMCCommandSaveToDatabase(SPMCCommand):
    def callback(self, args):
        from sp_map_cycle.sp_map_cycle import save_maps_to_db
        if save_maps_to_db():
            echo_console("Data was saved to the database")


class SPMCCommandLoadFromDatabase(SPMCCommand):
    def callback(self, args):
        from sp_map_cycle.sp_map_cycle import load_maps_from_db
        if load_maps_from_db():
            echo_console("Data from the database was reloaded")


class SPMCCommandSetForceOld(SPMCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'spmc help' to get help")
            return

        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            if update(
                    conn,
                    'maps',
                    {'force_old': True},
                    where='filename=?',
                    args=(filename.lower(), )
            ) > 0:

                echo_console("Operation succeeded.")

            else:
                echo_console("Error: Unknown map: {}".format(filename.lower(), ))

        finally:
            conn.close()


class SPMCCommandSetForceOldAll(SPMCCommand):
    def callback(self, args):
        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            if update(
                    conn,
                    'maps',
                    {'force_old': True},
            ) > 0:

                echo_console("Operation succeeded.")

            else:
                echo_console("Error: No known maps in the database.")

        finally:
            conn.close()


class SPMCCommandUnsetForceOld(SPMCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'spmc help' to get help")
            return

        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            if update(
                    conn,
                    'maps',
                    {'force_old': False},
                    where='filename=?',
                    args=(filename.lower(), )
            ) > 0:

                echo_console("Operation succeeded.")

            else:
                echo_console("Error: Unknown map: {}".format(filename.lower(), ))

        finally:
            conn.close()


class SPMCCommandForgetMap(SPMCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'spmc help' to get help")
            return

        conn = connect()
        if conn is None:
            echo_console("Could not connect to the database")
            return

        try:
            if delete(
                    conn,
                    'maps',
                    where='filename=?',
                    args=(filename.lower(), )
            ) > 0:

                echo_console("Operation succeeded.")

            else:
                echo_console("Error: Unknown map: {}".format(filename.lower(), ))

        finally:
            conn.close()


class SPMCScanMapsFolder(SPMCCommand):
    def callback(self, args):
        if args:
            prefixes = list(map(lambda prefix: prefix.lower(), args))
            echo_console("Scanning only maps with the "
                         "following prefixes:\n{}".format(','.join(prefixes)))

            def is_valid_map(filename):
                if not os.path.isfile(os.path.join(MAPS_FOLDER, filename)):
                    return False

                if not os.path.splitext(filename)[1].lower().endswith('.bsp'):
                    return False

                mapname = os.path.splitext(filename)[0].lower()
                for prefix in prefixes:
                    if mapname.startswith(prefix):
                        return True

                return False

        else:
            echo_console("Scanning all maps...")

            def is_valid_map(filename):
                if not os.path.isfile(os.path.join(MAPS_FOLDER, filename)):
                    return False

                return os.path.splitext(filename)[1].lower().endswith('.bsp')

        rs = []
        for filename in os.listdir(MAPS_FOLDER):
            if is_valid_map(filename):
                rs.append(os.path.splitext(filename)[0].lower())

        with open(MAPCYCLETXT, 'w') as f:
            for mapname in rs:
                f.write(mapname + '\n')

        echo_console("{} maps were scanned and written to "
                     "mapcycle.txt".format(len(rs)))


spmc_commands = {}
spmc_commands['spmc'] = SPMCCommand('spmc')
spmc_commands['help'] = SPMCCommandHelp('help', spmc_commands['spmc'])
spmc_commands['reload-mapcycle'] = SPMCCommandReloadMapCycle('reload-mapcycle', spmc_commands['spmc'])
spmc_commands['rebuild-mapcycle'] = SPMCCommandRebuildMapCycle('rebuild-mapcycle', spmc_commands['spmc'])
spmc_commands['db'] = SPMCCommandDB('db', spmc_commands['spmc'])
spmc_commands['db show'] = SPMCCommandShowDatabase('show', spmc_commands['db'])
spmc_commands['db dump-html'] = SPMCCommandDumpDatabaseHTML('dump-html', spmc_commands['db'])
spmc_commands['db save'] = SPMCCommandSaveToDatabase('save', spmc_commands['db'])
spmc_commands['db load'] = SPMCCommandLoadFromDatabase('load', spmc_commands['db'])
spmc_commands['db set-force-old'] = SPMCCommandSetForceOld('set-force-old', spmc_commands['db'])
spmc_commands['db set-force-old-all'] = SPMCCommandSetForceOldAll('set-force-old-all', spmc_commands['db'])
spmc_commands['db unset-force-old'] = SPMCCommandUnsetForceOld('unset-force-old', spmc_commands['db'])
spmc_commands['db forget-map'] = SPMCCommandForgetMap('forget-map', spmc_commands['db'])
spmc_commands['scan-maps-folder'] = SPMCScanMapsFolder('scan-maps-folder', spmc_commands['spmc'])
