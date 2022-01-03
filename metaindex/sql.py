"""Some SQL helpers and constants"""
import datetime
import re


SQL_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
MIN_DATE = "0001-01-01T00:00:00"
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

