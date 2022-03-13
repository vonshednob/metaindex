"""Some SQL Accessors, helpers, and constants"""
import datetime
import re
import sqlite3
import pathlib
from collections import namedtuple

from . import shared
from .query import QueryVisitor, Term


SQL_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
MIN_DATE = "0001-01-01T00:00:00"


class SqlAccess:
    """Basic SQLite wrapper"""
    TYPE_DATETIME = 'd'
    TYPE_INT = 'i'
    TYPE_FLOAT = 'f'
    TYPE_STR = None

    CREATE_FILE_TABLE = f"""
      create table if not exists `files`
          (`id` integer primary key autoincrement,
           `path` text unique,
           `last_modified` varchar(19) default "{MIN_DATE}")
    """
    CREATE_META_TABLE = """
      create table if not exists `metadata`
          (`id` integer references `files`(`id`) on delete cascade,
           `key` varchar(50) not null,
           `type` varchar(1) default null,
           `value` text not null,
           unique (`id`, `key`, `value`) on conflict ignore)
    """
    SELECT_METADATA_BASE_QUERY = """
      select `path`, `last_modified`, `metadata`.*
      from `files` left outer join `metadata` on `files`.`id` = `metadata`.`id`
    """

    def __init__(self, uri):
        """Create a persistent SQL access.

        :param uri: The location of the database. For example a path location
                    or ``:memory:``."""
        self.db = sqlite3.connect(uri)
        self.db.row_factory = sqlite3.Row
        self.db.create_function('REGEXP', 2, regexp)

        with self.db:
            self.db.execute(type(self).CREATE_FILE_TABLE)
            self.db.execute(type(self).CREATE_META_TABLE)

    def files(self):
        """Get all paths of files in the database

        :return: List of all file paths cached in the database
        :rtype: ``list[pathlib.Path]``
        """
        with self.db:
            return [pathlib.Path(row['path'])
                    for row in self.db.execute('select `id`, `path` from `files`')]

    def last_modified(self):
        """Get the timestamp of the most recently modified file in the database

        :rtype: ``datetime.datetime``
        """
        with self.db:
            query = 'select max(last_modified) from files'
            for row in self.db.execute(query):
                return str_to_dt(row[0])

    def keys(self):
        """Returns a set of all known metadata keys."""
        with self.db:
            return {row['key']
                    for row in self.db.execute("select distinct `key` from `metadata`")} | \
                   shared.CacheEntry.AUTO_KEYS

    def find(self, query):
        """Find and return all entries that match the query

        :param query: the search query to run
        :type query: ``metaindex.query.Query``
        :rtype: ``list[shared.CacheEntry]``
        """
        visitor = SqlQueryVisitor()
        query.accept(visitor)
        sqlquery, args = visitor.sqlquery, visitor.args
        with self.db:
            ids = [row['id'] for row in self.db.execute(sqlquery, args)]
            if len(ids) == 0:
                return []

            placeholder = ", ".join(["?"]*len(ids))

            sqlquery = type(self).SELECT_METADATA_BASE_QUERY + \
                       f" where `files`.`id` in ({placeholder})"

            results = {}
            for row in self.db.execute(sqlquery, ids):
                id_ = row['id']
                if id_ not in results:
                    last_modified = str_to_dt(row['last_modified'])
                    results[id_] = shared.CacheEntry(pathlib.Path(row['path']),
                                                    last_modified=last_modified)
                key = row['key']
                if key is None:
                    continue
                value = self._translate_row(row)
                results[id_].add(key, value)
        return list(results.values())

    def get(self, paths):
        """Get the metadata of these paths

        :param paths: list of paths to query
        :rtype: ``list[shared.CacheEntry]``
        """
        results = {}
        with self.db:
            for path in paths:
                pathresults = {}
                path = str(path)
                query = type(self).SELECT_METADATA_BASE_QUERY + \
                        " where substr(`path`, 1, ?) = ?"

                for row in self.db.execute(query, (len(path), path)):
                    id_ = row['id']

                    # found an entry twice
                    if id_ in results:
                        continue

                    if id_ not in pathresults:
                        last_modified = str_to_dt(row['last_modified'])
                        pathresults[id_] = shared.CacheEntry(pathlib.Path(row['path']),
                                                             last_modified=last_modified)
                    key = row['key']
                    if key is None:
                        continue
                    value = self._translate_row(row)
                    pathresults[id_].add(key, value)

                results.update(pathresults)
        return list(results.values())

    def _translate_row(self, row):
        type_, value = row['type'], row['value']

        if type_ == type(self).TYPE_DATETIME:
            value = str_to_dt(value)
        elif type == type(self).TYPE_INT:
            value = int(value)
        elif type == type(self).TYPE_FLOAT:
            value = float(value)
        else:
            value = str(value)

        return value

    def insert(self, items):
        """Insert ``items`` in the database

        This will overwrite all existing entries (by path) in the database.

        :param items: A list of ``CacheEntry`` to insert
        :return: Number of inserted entries
        """
        if len(items) == 0:
            return 0

        with self.db:
            # flush existing entries
            ids = set()
            query = "select `id` from `files` where `path` = ?"
            for item in items:
                ids |= {row['id']
                        for row in self.db.execute(query, (str(item.path),))}
            if len(ids) > 0:
                placeholder = ", ".join(["?"]*len(ids))
                self.db.execute(f"delete from `metadata` where `id` in ({placeholder})",
                                list(ids))
                self.db.execute(f"delete from `files` where `id` in ({placeholder})",
                                list(ids))

            # add all items
            for item in items:
                query = "insert into `files`(`path`, `last_modified`) values(?, ?)"
                result = self.db.execute(query,
                                         (str(item.path), dt_to_str(item.last_modified)))
                row_id = result.lastrowid

                for key, value in item:
                    if key in shared.CacheEntry.AUTO_KEYS:
                        continue

                    query = "insert into `metadata` values (?, ?, ?, ?)"
                    rawvalue = value.raw_value

                    if isinstance(rawvalue, int):
                        type_ = type(self).TYPE_INT
                        rawvalue = str(rawvalue)
                    elif isinstance(value, float):
                        type_ = type(self).TYPE_FLOAT
                        rawvalue = str(rawvalue)
                    elif isinstance(value, datetime.datetime):
                        type_ = type(self).TYPE_DATETIME
                        rawvalue = dt_to_str(rawvalue)
                    else:
                        type_ = type(self).TYPE_STR
                        rawvalue = str(rawvalue)

                    self.db.execute(query,
                                    (row_id, key, type_, rawvalue))
            return len(items)

    def flush(self):
        """Flush the entire database"""
        with self.db:
            self.db.execute("delete from metadata")
            self.db.execute("delete from files")

    def purge(self, paths):
        """Remove all entries with these paths from the database

        If a path points to a directory instead of a file, all
        files in all subdirectories will be removed, too.

        :param files: List of paths
        """
        if len(paths) == 0:
            return

        with self.db:
            ids = set()
            # match all files that start with the path
            pathquery = "select `id` from `files` where substr(`path`, 1, ?) = ?"
            for path in paths:
                path = str(path)
                ids |= {row['id']
                        for row in self.db.execute(pathquery, (len(path), path))}

            id_set = ", ".join(["?"]*len(ids))
            ids = list(ids)
            self.db.execute(f"delete from metadata where id in ({id_set})", ids)
            self.db.execute(f"delete from files where id in ({id_set})", ids)

    def expire_metadata(self, paths):
        """Mark the metadata of these paths as expired

        Expiring does not remove the data from the database, only marks it as
        very, very old.

        If a paths is pointing to a directory instead of a file, all metadata
        of all items in all the subdirectories will be expired, too.

        If ``paths`` is ``None``, all metadata will be expired.

        :param paths: the paths to expire, ``None`` will expire all metadata
        """

        if paths is None:
            with self.db:
                self.db.execute("update `files` set `last_modified` = ?",
                                (MIN_DATE,))
            return

        with self.db:
            for path in paths:
                strpath = str(path)
                self.db.execute("update `files` set `last_modified` = ? "
                                "where substr(`path`, 1, ?) = ?",
                                (MIN_DATE, len(strpath), strpath))

    def rename_file(self, old_path, new_path):
        """Rename a file from ``old_path`` to ``new_path``

        Only affects the database, no files on the filesystem are renamed"""
        with self.db:
            self.db.execute("update `files` set `path` = ? where `path` = ?",
                            (str(new_path), str(old_path)))

    def rename_dir(self, old_path, new_path):
        """Rename a directory from ``old_path`` to ``new_path``

        Only affects the database, no directories on the filesystem are renamed"""
        stroldpath = str(old_path)

        with self.db:
            query = 'select `id`, `path` from `files` where substr(`path`, 1, ?) = ?'
            id_path = [(row[0], pathlib.Path(row[1]))
                       for row in self.db.execute(query, (len(stroldpath), stroldpath))]
            id_path = [(id_,
                        (new_path / path.relative_to(old_path)).resolve())
                        for id_, path in id_path]
            for id_, newpath in id_path:
                self.db.execute('update `files` set `path` = ? where `id` = ?',
                                (str(newpath), id_))


SqlTerm = namedtuple('SqlTerm',
                     ['expression', 'args', 'inverted', 'operator'])


class SqlQueryVisitor(QueryVisitor):
    OR = ' union '
    AND = ' intersect '
    OPERATOR_MAPPING = {Term.OR: ' union ',
                        Term.AND: ' intersect '}

    def __init__(self):
        self.sequence_stack = []
        self.sqlquery = ''
        self.args = []

    def on_sequence_start(self, _):
        self.sequence_stack.append([])

    def on_sequence_end(self, element):
        sequence = self.sequence_stack.pop(-1)

        expr = ''
        args = []

        if len(self.sqlquery) > 0:
            expr += self.OPERATOR_MAPPING[element.operator]

        for index, subterm in enumerate(sequence):
            subexpr = ''
            if index > 0:
                if subterm.inverted:
                    expr += ' except '
                else:
                    expr += self.OPERATOR_MAPPING[subterm.operator]
            elif subterm.inverted:
                expr += ' select distinct `metadata`.`id` from `metadata` except '
            expr += ' select distinct `metadata`.`id` from `metadata` where '
            subexpr += subterm.expression
            expr += subexpr
            args += subterm.args

        if len(expr) > 0:
            if len(self.sqlquery) > 0:
                self.sqlquery += self.OPERATOR_MAPPING[element.operator]
            self.sqlquery += expr
            self.args += args

        if len(self.sequence_stack) == 0 and len(self.sqlquery) == 0:
            self.sqlquery = 'select distinct `metadata`.`id` from `metadata`'

    def on_key_value(self, element):
        if element.regex not in regex_cache:
            regex_cache[element.regex] = re.compile(element.regex, re.IGNORECASE)
        keycheck = " = ?"
        keys = [element.key]

        if isinstance(element.key, list):
            keys = element.key
            keycheck = " in (" + ", ".join(["?"]*len(keys)) + ")"

        expr = f"(`metadata`.`key` {keycheck} AND `metadata`.`value` REGEXP ?)"
        term = SqlTerm(expr,
                       keys + [element.regex],
                       element.inverted,
                       element.operator)
        self.sequence_stack[-1].append(term)

    def on_key_exists(self, element):
        keys = element.key
        if isinstance(keys, (tuple, set)):
            keys = list(keys)
        if not isinstance(keys, list):
            keys = [keys]

        keycheck = " in (" + ", ".join(["?"]*len(keys)) + ")"

        term = SqlTerm(f"`metadata`.`key` {keycheck}",
                       keys,
                       element.inverted,
                       element.operator)
        self.sequence_stack[-1].append(term)

    def on_regex(self, element):
        if element.word not in regex_cache:
            regex_cache[element.word] = re.compile(element.word, re.IGNORECASE)

        # match against any value and even against the path
        term = SqlTerm("lower(`metadata`.`value`) REGEXP ?",
                       [element.word],
                       element.inverted,
                       element.operator)
        self.sequence_stack[-1].append(term)


# This is a cache of compiled regular expressions for use
# in SQLite queries
regex_cache = {}


def regexp(expr, item):
    """Regular expression support for sqlite.

    This function will be executed when regular expression is called from
    within sqlite3 through REGEXP.
    """
    global regex_cache

    if not isinstance(item, str):
        return False

    if expr not in regex_cache:
        regex_cache[expr] = re.compile(expr)

    result = regex_cache[expr].search(item)
    matches = result is not None

    return matches


def str_to_dt(text):
    """Convert text to naive datetime, expecting the SQL_DATETIME_FORMAT

    Returns datetime.datetime.min in case of errors"""
    try:
        return datetime.datetime.strptime(text, SQL_DATETIME_FORMAT)
    except ValueError:
        return datetime.datetime.min


def dt_to_str(dt):
    """Convert a datetime to text representation for use in the database"""
    return dt.strftime(SQL_DATETIME_FORMAT)
