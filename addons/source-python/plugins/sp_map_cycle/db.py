import sqlite3

from paths import BASE_PATH

from sp_map_cycle.info import info


# Path to our database file
SQLITE_DATABASE = str(BASE_PATH / 'plugins' / info.basename / "database.sqlite3")
TABLE_PREFIX = ''


def connect():
    """
    Connect to the database.

    Return None if there is an exception, return connection object otherwise.
    """
    try:
        return sqlite3.connect(SQLITE_DATABASE)

    except sqlite3.Error:
        return None


def create_table(conn, table, columns, column_types=(), args=(), commit=True):
    """
    Create a table in the database if such table does not exist.

    Arguments:
    conn -- connection object
    table -- table name
    columns -- either an iterable of columns names or an iterable of tuples
        (columnName, columnType)
    columnTypes -- iterable of column types if previous argument was only
        used to provide column names
    args -- arguments to pass to .execute() method
    """
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    temp = []
    if len(columns) == len(column_types):
        for column, column_type in zip(columns, column_types):
            temp.append("{} {}".format(column, column_type))

    else:
        for column, column_type in columns:
            temp.append("{} {}".format(column, column_type))

    q = "CREATE TABLE IF NOT EXISTS {} ({})".format(table, ', '.join(temp))

    cur.execute(q, args)

    if commit:
        conn.commit()


def insert(conn, table, data, args=(), commit=True):
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    keys, values = zip(*data.items())

    q = "INSERT INTO {} ({}) VALUES ({})".format(
        table, ', '.join(keys), ', '.join(('?', ) * len(values)))

    cur.execute(q, values +	tuple(args))

    if commit:
        conn.commit()

    return cur.rowcount


def update(conn, table, data, where, args=(), commit=True):
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    keys, values = zip(*data.items())
    temp = []
    for column in keys:
        temp.append("{}=?".format(column))

    q = "UPDATE {} SET {} WHERE {}".format(table, ', '.join(temp), where)

    cur.execute(q, values + tuple(args))

    if commit:
        conn.commit()

    return cur.rowcount


def delete(conn, table, where, args=(), commit=True):
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    q = "DELETE FROM {} WHERE {}".format(table, where)

    cur.execute(q, args)

    if commit:
        conn.commit()

    return cur.rowcount


def select_all(conn, table, where=None, order=None, limit=None, args=()):
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    q = "SELECT * FROM {}".format(table)

    if where:
        q += " WHERE {}".format(where)

    if order:
        q += " ORDER BY {}".format(order)

    if limit:
        q += " LIMIT {}".format(limit)

    cur.execute(q, args)

    for row in cur:
        yield row


def select(conn, table, columns, where=None, order=None, limit=None, args=()):
    table = "{}{}".format(TABLE_PREFIX, table)
    cur = conn.cursor()

    q = "SELECT {} FROM {}".format(', '.join(columns), table)

    if where:
        q += " WHERE {}".format(where)

    if order:
        q += " ORDER BY {}".format(order)

    if limit:
        q += " LIMIT {}".format(limit)

    cur.execute(q, args)

    for row in cur:
        yield dict(zip(columns, row))


conn = connect()
c = conn.cursor()

create_table(conn, 'maps', (
    'filename',     'detected',     'force_old',    'likes',    'dislikes',
), (
    'TEXT',         'INTEGER',      'INTEGER',      'INTEGER',  'INTEGER',
))

conn.close()