from datetime import datetime
import os
from time import time

from core import echo_console
from paths import GAME_PATH, LOG_PATH
from listeners.tick import GameThread

from jinja2 import Environment
from jinja2 import FileSystemLoader

from .info import info

from .models.server_map import ServerMap as DB_ServerMap

from .resource.paths import MC_DATA_PATH

from .resource.sqlalchemy import Session


MAPS_FOLDER = GAME_PATH / 'maps'
MAPCYCLETXT = GAME_PATH / 'cfg' / 'mapcycle.txt'
DBDUMP_PATH = LOG_PATH / info.basename
DBDUMPHTML = DBDUMP_PATH / 'databasedump.html'
DBDUMPTXT = DBDUMP_PATH / 'databasedump.txt'
TEMPLATES_DIR = MC_DATA_PATH / 'templates'
DB_SHOW_CAP = 40


os.makedirs(DBDUMP_PATH, exist_ok=True)

j2env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
j2env.filters['strftime'] = lambda timestamp: datetime.fromtimestamp(timestamp).strftime('%c')
j2template_html = j2env.get_template('databasedump.html')
j2template_txt = j2env.get_template('databasedump.txt')


class MCCommand:
    def __init__(self, name, parent=None):
        self.registered_commands = {}
        if parent is not None:
            parent.registered_commands[name] = self

    def callback(self, *args):
        raise NotImplementedError


class MCCommandHelp(MCCommand):
    def callback(self, args):
        echo_console("""mc help:
> mc help
Shows this help message

> mc reload-mapcycle
Reloads mapcycle.json

> mc rebuild-mapcycle
Creates new mapcycle.json based on mapcycle.txt (mapcycle_default.txt)

> mc db show [<starting ID>]
Prints contents of database.sqlite3. If the starting ID is given, shows the
contents only beginning from this ID.

> mc db dump-html
Dumps contents of database.sqlite3 to an HTML page:
<mod folder>/logs/source-python/map_cycle/databasedump.html

> mc db dump-txt
Dumps contents of database.sqlite3 to a text file:
<mod folder>/logs/source-python/map_cycle/databasedump.txt

> mc db save
Saves current maps list from memory to the database

> mc db load
Reloads data from the database into memory

> mc db set-force-old <map filename>
Marks the given map as old (no NEW! postfix)

> mc db set-force-old-all
Marks all known maps as old (no NEW! postfix)

> mc db unset-force-old-flag <map filename>
Restores 'new' flag for the given map based on its detection date.
The flag may not be restored if the map is actually old, but you can make
database forget such map by typing 'mc db forget-map <map filename>'.

> mc db forget-map <map filename>
Removes the given map from the database, doesn't remove the map from the mapcycle.
Map will be added to the database again if it's still in mapcycle.

> mc scan-maps-folder [<map prefix> ...]
Scans contents of ../maps folder and puts scanned maps in mapcycle.txt.
You can then convert that mapcycle.txt to mapcycle.json by typing 'mc rebuild-mapcycle'.
If map prefixes are given, only maps that start with that prefix will be added to the list.
Example:
mc scan-maps-folder de_ cs_ gg_
""")


class MCCommandReloadMapCycle(MCCommand):
    def callback(self, args):
        from .map_cycle import load_maps_from_db
        from .map_cycle import reload_mapcycle_json
        from .map_cycle import reload_map_list
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


class MCCommandRebuildMapCycle(MCCommand):
    def callback(self, args):
        from .map_cycle import build_json_from_mapcycle_txt
        try:
            build_json_from_mapcycle_txt()
        except FileNotFoundError:
            echo_console("""Error: No mapcycle.txt nor mapcycle_default.txt found in cfg directory.
You can create one automatically by typing 'mc scan-maps-folder'.""")
        else:
            echo_console("mapcycle.json was rebuild")


class MCCommandDB(MCCommand):
    def callback(self, args):
        echo_console("Not enough parameters, type 'mc help' to get help")


class MCCommandShowDatabase(MCCommand):
    def callback(self, args):
        start = int(args[0]) if args else 0

        session = Session()

        echo_console("+----+--------------------------------+----------+--------+-------------+")
        echo_console("| ID | Map File Name (w/o .bsp)       | Detected | Old?** | Likes/Total |")
        echo_console("+----+--------------------------------+----------+--------+-------------+")

        db_server_maps = session.query(DB_ServerMap).order_by(
            DB_ServerMap.detected)[start:start+DB_SHOW_CAP]

        for db_server_map in db_server_maps:
            echo_console("| {}| {}| {}| {}| {}|".format(
                str(db_server_map.id).ljust(3)[:3],
                db_server_map.filename.ljust(31)[:31],
                datetime.fromtimestamp(db_server_map.detected).strftime('%x').ljust(9)[:9],
                "YES".ljust(7) if db_server_map.force_old else "NO".ljust(7),
                ("{:.2f}".format(db_server_map.likes/(db_server_map.likes+db_server_map.dislikes)).ljust(12)[:12] if
                 (db_server_map.likes+db_server_map.dislikes) != 0 else "n/a".ljust(12)),
            ))

        echo_console("+----+--------------------------------+----------+--------+-------------+")
        echo_console("* Only showing rows from {} to {}".format(start + 1, start + DB_SHOW_CAP))
        echo_console("** Only shows if the map was marked old via 'mc db set-force-old' command")

        session.close()


class MCCommandDumpDatabaseHTML(MCCommand):
    def callback(self, args):
        session = Session()

        j2template_html.stream(rows=session.query(DB_ServerMap).all(),
                               dumpdate=time()).dump(DBDUMPHTML)

        echo_console("Dump written to {}".format(DBDUMPHTML))
        session.close()


class MCCommandDumpDatabaseText(MCCommand):
    def callback(self, args):
        session = Session()

        j2template_txt.stream(rows=session.query(DB_ServerMap).all(),
                              dumpdate=time()).dump(DBDUMPTXT)

        echo_console("Dump written to {}".format(DBDUMPTXT))
        session.close()


class MCCommandSaveToDatabase(MCCommand):
    def callback(self, args):
        from .map_cycle import save_maps_to_db

        def save():
            save_maps_to_db()
            echo_console("Data was saved to the database")

        GameThread(target=save).start()


class MCCommandLoadFromDatabase(MCCommand):
    def callback(self, args):
        from .map_cycle import load_maps_from_db

        def load():
            load_maps_from_db()
            echo_console("Data from the database was reloaded")

        GameThread(target=load).start()


class MCCommandSetForceOld(MCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'mc help' to get help")
            return

        session = Session()

        db_server_map = session.query(DB_ServerMap).filter_by(
            filename=filename).first()

        if db_server_map is None:
            echo_console("Unknown map: {}".format(filename))

        else:
            db_server_map.force_old = True
            session.commit()

            echo_console("Operation succeeded.")

        session.close()


class MCCommandSetForceOldAll(MCCommand):
    def callback(self, args):
        session = Session()

        for db_server_map in session.query(DB_ServerMap).all():
            db_server_map.force_old = True

        session.commit()

        echo_console("Operation succeeded.")

        session.close()


class MCCommandUnsetForceOld(MCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'mc help' to get help")
            return

        session = Session()

        db_server_map = session.query(DB_ServerMap).filter_by(
            filename=filename).first()

        if db_server_map is None:
            echo_console("Unknown map: {}".format(filename))

        else:
            db_server_map.force_old = False
            session.commit()

            echo_console("Operation succeeded.")

        session.close()


class MCCommandForgetMap(MCCommand):
    def callback(self, args):
        try:
            filename = args.pop(0)
        except IndexError:
            echo_console("Not enough parameters, type 'mc help' to get help")
            return

        session = Session()

        db_server_map = session.query(DB_ServerMap).filter_by(
            filename=filename).first()

        if db_server_map is None:
            echo_console("Unknown map: {}".format(filename))

        else:
            session.delete(db_server_map)
            session.commit()

            echo_console("Operation succeeded.")

        session.close()


class MCScanMapsFolder(MCCommand):
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

                map_name = os.path.splitext(filename)[0].lower()
                for prefix in prefixes:
                    if map_name.startswith(prefix):
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

mc_commands = {}
mc_commands['mc'] = MCCommand('mc')
mc_commands['help'] = MCCommandHelp('help', mc_commands['mc'])
mc_commands['reload-mapcycle'] = MCCommandReloadMapCycle('reload-mapcycle', mc_commands['mc'])
mc_commands['rebuild-mapcycle'] = MCCommandRebuildMapCycle('rebuild-mapcycle', mc_commands['mc'])
mc_commands['db'] = MCCommandDB('db', mc_commands['mc'])
mc_commands['db show'] = MCCommandShowDatabase('show', mc_commands['db'])
mc_commands['db dump-html'] = MCCommandDumpDatabaseHTML('dump-html', mc_commands['db'])
mc_commands['db dump-txt'] = MCCommandDumpDatabaseText('dump-txt', mc_commands['db'])
mc_commands['db save'] = MCCommandSaveToDatabase('save', mc_commands['db'])
mc_commands['db load'] = MCCommandLoadFromDatabase('load', mc_commands['db'])
mc_commands['db set-force-old'] = MCCommandSetForceOld('set-force-old', mc_commands['db'])
mc_commands['db set-force-old-all'] = MCCommandSetForceOldAll('set-force-old-all', mc_commands['db'])
mc_commands['db unset-force-old'] = MCCommandUnsetForceOld('unset-force-old', mc_commands['db'])
mc_commands['db forget-map'] = MCCommandForgetMap('forget-map', mc_commands['db'])
mc_commands['scan-maps-folder'] = MCScanMapsFolder('scan-maps-folder', mc_commands['mc'])
