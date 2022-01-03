import collections
import datetime
import pathlib
import sqlite3
import os
import re
import fnmatch
import queue
import threading

import multidict

from metaindex import indexer
from metaindex import configuration
from metaindex import sql
from metaindex import stores
from metaindex import shared
from metaindex import ocr
from metaindex import logger
from metaindex.query import Query


class Cache:
    CACHE_FILENAME = "index" + os.extsep + "db"

    TYPE_DATETIME = 'd'
    TYPE_INT = 'i'
    TYPE_FLOAT = 'f'
    TYPE_STR = None

    Entry = collections.namedtuple('Entry',
                                   ['path', 'metadata', 'last_modified'],
                                   defaults=[multidict.MultiDict(), datetime.datetime.min])

    def __init__(self, config=None):
        self.config = config or configuration.load()
        self.db = None

        self.recursive_extra_metadata = config.bool("General", "recursive-extra-metadata", "y")
        self.ignore_dirs = config.list('General', 'ignore-directories', "", separator="\n")
        self.ignore_tags = config.list('General', 'ignore-tags', "")

        ocr_opts = config.list("General", "ocr", "no")
        if len(ocr_opts) == 0 or ocr_opts[0].lower() in config.FALSE:
            ocr_opts = False
        elif ocr_opts[0].lower() in config.TRUE:
            ocr_opts = True

        if ocr_opts:
            self.ocr = ocr.TesseractOCR(ocr_opts)
        else:
            self.ocr = ocr.Dummy()

        fulltext_opts = config.list("General", "fulltext", "no")
        if len(fulltext_opts) == 0 or fulltext_opts[0].lower() in config.FALSE:
            fulltext_opts = False
        elif fulltext_opts[0].lower() in config.TRUE:
            fulltext_opts = True

        self.extract_fulltext = fulltext_opts

        self.ignore_file_patterns = None
        self.accept_file_patterns = None

        accept = config.list('General', 'accept-files', '', separator="\n")
        ignore = config.list('General', 'ignore-files', '', separator="\n")

        if len(accept) > 0:
            self.accept_file_patterns = [re.compile(fnmatch.translate(pattern.strip()), re.I) for pattern in accept]
        elif len(ignore) > 0:
            self.ignore_file_patterns = [re.compile(fnmatch.translate(pattern.strip()), re.I) for pattern in ignore]

        self._open_db()

    def refresh(self, paths=None, recursive=True, processes=None):
        """(Re-)Index all items found in the given paths or all cached items if paths is None.

        If any item in the list is a directory and recursive is True, all
        items inside that directory (including any all subdirectories) will
        be indexed, too.

        processes may be set to a number of processes that will be used in
        parallel to index the files. If left at None, there will be as many
        processes launched as CPUs are available.
        """
        if paths is None:
            paths = [row['path'] for row in self.db.execute("select `path` from `files`")]

        elif isinstance(paths, (set, tuple)):
            paths = list(paths)

        elif not isinstance(paths, list):
            paths = [paths]

        if len(paths) == 0:
            return multidict.MultiDict()

        files = self.find_indexable_files(paths, recursive)

        # cache of last_modified dates for files
        last_modified = dict([(fn, shared.get_last_modified(fn)) for fn in files])

        # obtain cached metadata
        last_cached = dict([(entry.path, entry) for entry in self.get(files)])

        indexer_result = indexer.index_files(files,
                                             processes,
                                             self.ocr,
                                             self.extract_fulltext,
                                             self.config,
                                             last_modified,
                                             last_cached)

        for filename, success, info in indexer_result:
            if not success:
                continue
            self.insert(filename, info, last_modified[filename])

    def cleanup(self):
        """Find and remove all entries in the cache that refer to no longer existing files"""
        to_delete_ids = []

        for row in self.db.execute("select `id`, `path` from files"):
            path = pathlib.Path(row['path'])

            if not path.exists():
                to_delete_ids.append(row['id'])

        self.forget_ids(to_delete_ids)

    def find_indexable_files(self, paths, recursive=True):
        paths = [pathlib.Path(path).expanduser().resolve() for path in paths]

        # filter out ignored directories
        paths = [path for path in paths if not any([ignoredir in path.parts for ignoredir in self.ignore_dirs])]

        dirs = [path for path in paths if path.is_dir()]
        files = {path for path in paths if path.is_file() and self._accept_file(path)}
        files |= {fn for fn in find_files(dirs, recursive) if self._accept_file(fn)}

        return files

    def _accept_file(self, path):
        if any([ignoredir in path.parts[:-1] for ignoredir in self.ignore_dirs]):
            return False
        if self.config.is_sidecar_file(path):
            return False
        pathstr = str(path)
        if self.accept_file_patterns is not None:
            return any([pattern.match(pathstr) for pattern in self.accept_file_patterns])
        return not any([pattern.match(pathstr) for pattern in self.ignore_file_patterns])

    def clear(self):
        """Remove everything from the cache"""
        with self.db:
            self.db.execute("delete from metadata")
            self.db.execute("delete from files")

    def forget_ids(self, ids):
        """Delete these IDs from the cache"""
        with self.db:
            id_set = ", ".join(["?"]*len(ids))
            self.db.execute(f"delete from metadata where id in ({id_set})", ids)
            self.db.execute(f"delete from files where id in ({id_set})", ids)

    def expire_metadata(self, paths, recursive=True):
        """Remove all metadata associated to these paths

        But keep the paths in the database.
        """
        if paths is None:
            self.db.execute("update `files` set `last_modified` = ?", (sql.MIN_DATE,))
            return

        elif not isinstance(paths, list):
            paths = [paths]

        paths = [pathlib.Path(path).expanduser().resolve() for path in paths]

        query = 'update `files` set `last_modified` = ? where `path` in (' + \
                ", ".join(["?"]*len(paths)) + ")"
        self.db.execute(query, [sql.MIN_DATE] + [str(path) for path in paths])

    def last_modified(self):
        """Return the date and time of the entry that most recently updated in the database.

        This is pretty much the 'last modified' date of the database itself.
        """
        query = 'select max(last_modified) from files'
        for row in self.db.execute(query):
            return sql.str_to_dt(row[0])

    def forget(self, paths, recursive=True):
        """Remove all paths from the cache

        If recursive is True, all items in subdirectories are removed from the
        cache, too."""
        raise NotImplementedError()

    def find(self, query):
        """Find all items matching this query.

        query may either be a human-written search term or a Query instance.

        Returns a list of (path to file, metadata, last_modified) tuples.
        """
        if query is None or len(query) == 0:
            query = Query()

        elif isinstance(query, str):
            query = Query.parse(query, self.config.synonyms)

        elif not isinstance(query, Query):
            raise TypeError()

        qry, args = query.as_sql()
        ids = [row['id'] for row in self.db.execute(qry, args)]
        
        return self._resolve_ids(ids)

    def get(self, paths, recursive=True):
        """Get metadata for all items of paths

        paths may also be a single path instead of a list of paths.

        If any element of paths is pointing to a directory and recursive is
        set to True, get will return the metadata for all elements inside
        that directory (and their subdirectories'), too.
        """
        if not isinstance(paths, (list, set, tuple)):
            paths = [paths]

        paths = [pathlib.Path(path).expanduser().resolve() for path in paths]
        
        args = [str(path) for path in paths if not path.is_dir()]
        if len(args) == 0:
            return []

        query = "select distinct `files`.`id` from `files` where `files`.`path` in (" \
                + ", ".join(["?"]*len(args)) + ")"

        ids = [row['id'] for row in self.db.execute(query, args)]

        return self._resolve_ids(ids)

    def keys(self):
        """Returns a set of all known metadata keys."""
        return {row['key'] for row in self.db.execute("select distinct `key` from `metadata`")}

    def insert(self, path, metadata, last_modified=None):
        """Insert the metadata for item at path into the cache.

        This operation will not modify the item in the filesystem nor update
        any other form of metadata persistency for the item.
        This function really only affects the cache.
        """
        # determine rowid, create new entry if there is none yet
        rowids = [row['id']
                 for row in self.db.execute("select `id` from `files` where `path` = ?",
                                            (str(path), ))]
        if last_modified is None:
            last_modified = shared.get_last_modified(path)

        if len(rowids) == 0:
            with self.db:
                result = self.db.execute("insert into `files`(`path`, `last_modified`) values(?, ?)",
                                         (str(path), sql.dt_to_str(last_modified)))
                rowid = result.lastrowid
            logger.debug(f"{path.name} not in cache yet. New ID is {rowid}")
        else:
            rowid = rowids[0]
            self.db.execute("update `files` set `last_modified` = ? where `id` = ?",
                            (sql.dt_to_str(last_modified), rowid))

        # clear existing metadata and write the current
        with self.db:
            self.db.execute("delete from `metadata` where `id` = ?", (rowid, ))

            for key in metadata.keys():
                if key in self.ignore_tags:
                    continue

                values = sum([value if isinstance(value, list) else [value]
                              for value in metadata.getall(key)
                              if value is not None], start=[])

                for value in values:
                    type_ = None
                    if isinstance(value, datetime.datetime):
                        type_ = Cache.TYPE_DATETIME
                        value = sql.dt_to_str(value)
                    elif isinstance(value, int):
                        type_ = Cache.TYPE_INT
                        value = str(value)
                    elif isinstance(value, float):
                        type_ = Cache.TYPE_FLOAT
                        value = str(value)
                    elif not isinstance(value, str):
                        logger.error(f"Unexpected type {type(value)} for key {key}, skipping")
                        logger.debug(f"Unexpected type {type(value)} for key {key} with value {value}")
                        continue
                    self.db.execute("insert into `metadata` values(?, ?, ?, ?)",
                                    (rowid, key, type_, value))

    def parse_extra_metadata(self, metafile):
        """Extract extra metadata from this file"""
        data = stores.get_for_collection(metafile)

        for filename in data.keys():
            data[filename][shared.IS_RECURSIVE] = data[filename][shared.IS_RECURSIVE] and \
                                                  self.recursive_extra_metadata
        
        return data

    def _resolve_ids(self, ids):
        result = {}
        query = "select files.path, files.last_modified, metadata.* from `files` " \
                " left join `metadata` on `files`.`id` = `metadata`.`id` " \
                " where `files`.`id` in (" + ", ".join(["?"]*len(ids)) + ")"
        for row in self.db.execute(query, ids):
            id_ = row['id']
            if id_ not in result:
                last_modified = sql.str_to_dt(row['last_modified'])
                result[id_] = Cache.Entry(pathlib.Path(row['path']), multidict.MultiDict(), last_modified)

            key, value = self._translate_row(row)
            if not isinstance(key, str):
                logger.error(f"Unexpected key type {type(key)}")
                key = str(key)
            result[id_][1].add(key, value)

        return [v for v in result.values()]

    def _translate_row(self, row):
        key, type_, value = row['key'], row['type'], row['value']
        
        if type_ == Cache.TYPE_DATETIME:
            value = sql.str_to_dt(value)
        elif type == Cache.TYPE_INT:
            value = int(value)
        elif type == Cache.TYPE_FLOAT:
            value = float(value)

        return key, value

    def _open_db(self):
        if self.db is not None:
            self.db.close()

        location = self.config.path('General', 'cache', configuration.CACHEPATH) / Cache.CACHE_FILENAME
        if not location.parent.exists():
            location.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(location)
        self.db.row_factory = sqlite3.Row
        self.db.create_function('REGEXP', 2, sql.regexp)

        with self.db:
            self.db.execute(sql.CREATE_FILE_TABLE)
            self.db.execute(sql.CREATE_META_TABLE)

    def _find_sidecar_files(self, files):
        """Find all sidecar files for these files

        Returns a dict with the mapping of path -> [sidecar files] containing
        all existing sidecar files"""
        sfiles = dict([(file_, [fn for fn in stores.sidecars_for(file_)
                                   if fn.exists()]) for file_ in files])
        return dict([pair for pair in sfiles.items() if len(pair[1]) > 0])

    def _find_collection_sidecar_files(self, files):
        """Find all collection sidecar files for these files

        Returns a dict with the mapping of path -> [sidecar files] containing
        all existing sidecar files"""
        queue = {f.parent for f in files}
        if self.recursive_extra_metadata:
            to_visit = set()
            # find all parent directories
            while len(queue) > 0:
                path = queue.pop()
                to_visit.add(path)
                if path.parent != path and path.parent not in to_visit:
                    queue.add(path.parent)
        sfiles = dict([(base, [base / fn for fn in self.collection_metadata
                                         if (base / fn).exists()])
                       for base in to_visit])
        return dict([pair for pair in sfiles.items() if len(pair[1]) > 0])


class ThreadedCache:
    """Special version of Cache to be used in multi-threaded applications

    To use this, create an instance and execute ``start``.
    """
    GET = "get"
    FIND = "find"
    REFRESH = "refresh"
    INSERT = "insert"
    LAST_MODIFIED = "last_modified"

    def __init__(self, config):
        self.config = config
        self.queue = queue.Queue()
        self._quit = False
        self.handler = threading.Thread(target=self.handler_loop)
        self.results = queue.Queue()
        self.single_call = threading.Lock()
        self.cache = None

    def get(self, paths, recursive=True):
        with self.single_call:
            self.queue.put((self.GET, paths, recursive))
            return self.results.get()

    def find(self, query):
        with self.single_call:
            self.queue.put((self.FIND, query))
            return self.results.get()

    def refresh(self, paths, recursive=True, processes=None):
        with self.single_call:
            self.queue.put((self.REFRESH, paths, recursive, processes))
            return self.results.get()

    def insert(self, path, metadata, last_modified=None):
        with self.single_call:
            self.queue.put((self.INSERT, path, metadata, last_modified))
            return self.results.get()

    def last_modified(self):
        """Return the date and time of the most recently touched file that's known to the database

        This is pretty much equivalent to the 'last_modified' date of the database itself."""
        with self.single_call:
            self.queue.put((self.LAST_MODIFIED,))
            return self.results.get()

    def start(self):
        """Launch the cache thread"""
        self.handler.start()

    def quit(self):
        """End the cache thread"""
        self._quit = True
        self.queue.put("")
        self.handler.join()

    def handler_loop(self):
        self.cache = Cache(self.config)
        while not self._quit:
            item = self.queue.get()
            if len(item) < 2:
                continue

            command = item[0]
            args = item[1:]
            result = None

            try:
                if command == self.GET:
                    result = self.cache.get(*args)
                elif command == self.FIND:
                    result = self.cache.find(*args)
                elif command == self.REFRESH:
                    result = self.cache.refresh(*args)
                elif command == self.INSERT:
                    result = self.cache.insert(*args)
                elif command == self.LAST_MODIFIED:
                    result = self.cache.last_modified()
            except Exception as exc:
                result = exc

            self.results.put(result)


class MemoryCache:
    """Version of the threaded cache that uses in-memory caching of the database

    Upon initialisation this cache will obtain all entries from the database
    and try to keep the data in memory up to date.
    """
    def __init__(self, config):
        self.config = config
        self.entries_by_path = {}
        self.last_read = datetime.datetime.min

        self.tcache = ThreadedCache(config)
        self.writing = threading.Lock()
        self.reloading = threading.Lock()
        self.is_initialized = False

    def is_busy(self):
        """Whether or not the cache is busy reading from the database"""
        return self.writing.locked()

    def wait_for_write(self):
        """Wait until any currently pending write operation is completed"""
        with self.writing:
            # this will wait until it could acquire the lock and return again at once
            pass

    def wait_for_reload(self):
        """Wait until any currently pending reload operation is completed"""
        with self.reloading:
            # this will wait until it could acquire the lock and return again at once
            pass

    def check_dirty(self):
        """Check whether or not the database is more recent than this cache

        This call will return immediately.

        This call may return False even if it doesn't know for sure that the cache is dirty.

        However, if it returns True, you can be sure that the cache is dirty (i.e. no longer valid).
        """
        if self.writing.locked() or self.tcache.single_call.locked():
            return False

        last_modified = self.tcache.last_modified()
        return self.last_read > last_modified

    def start(self):
        """Call this before attempting any queries."""
        self.tcache.start()
        self.invalidate()

    def insert(self, path, metadata, last_modified=None):
        """Insert/update metadata for path"""
        with self.writing:
            if last_modified is None:
                last_modified = shared.get_last_modified(path)
            self.tcache.insert(path, metadata, last_modified)
            self.entries_by_path[path] = Cache.Entry(path, metadata, last_modified)

    def find(self, query):
        """Find all entries that match this query"""
        matcher = Query.parse(query, synonyms=self.config.synonyms)

        for entry in self.entries_by_path.values():
            if matcher.matches(entry.metadata):
                yield entry

    def get(self, paths, recursive=True):
        """Get all entries for these paths (recursively)"""
        if recursive:
            for path, entry in self.entries_by_path.items():
                if not any(path.is_relative_to(pathpattern) for pathpattern in paths):
                    continue
                yield entry
        else:
            for path in paths:
                if path in self.entries_by_path:
                    yield self.entries_by_path[path]

    def refresh(self, paths, recursive=True, processes=None):
        """(Re-)index these paths (recursively by default)"""
        with self.writing:
            self.tcache.refresh(paths, recursive, processes)
            if recursive:
                for path in self.entries_by_path:
                    if any(path.is_relative_to(pathpattern) for pathpattern in paths):
                        del self.entries_by_path[path]
            else:
                for path in paths:
                    if path in self.entries_by_path:
                        del self.entries_by_path[path]

    def invalidate(self):
        """Invalidate the cached entries and reload"""
        self.entries_by_path = {}
        self.reload()

    def reload(self):
        """Reload the data from the cache"""
        threading.Thread(target=self.do_reload).start()

    def do_reload(self):
        """A blocking reload function.

        Do not call this directly, but call 'invalidate' or 'reload' instead.
        """
        entries = {}
        with self.reloading:
            for entry in self.tcache.find(''):
                entries[entry.path] = entry

            with self.writing:
                self.entries_by_path = entries
                self.last_read = datetime.datetime.now()
                self.is_initialized = True

    def quit(self):
        """End the cache thread"""
        with self.writing:
            self.tcache.quit()
            self.tcache = ThreadedCache(self.config)
            self.entries_by_path = {}


def find_files(paths, recursive=True):
    """Find all files in these paths"""
    if not isinstance(paths, list):
        paths = [paths]

    pathqueue = list(paths)
    filenames = []

    while len(pathqueue) > 0:
        path = pathqueue.pop(0)

        if not isinstance(path, pathlib.Path):
            path = pathlib.Path(path)

        if not path.exists():
            continue

        for item in path.iterdir():
            if item.is_dir() and recursive:
                pathqueue.append(item)
                continue

            if item.is_file():
                filenames.append(item)

    return filenames


if __name__ == '__main__':
    logger.setup('DEBUG')
    cache = Cache()
    breakpoint()
