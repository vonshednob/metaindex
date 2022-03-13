import datetime
import pathlib
import os
import re
import fnmatch
import queue
import threading
import time

from metaindex import indexer
from metaindex import configuration
from metaindex import sql
from metaindex import stores
from metaindex import shared
from metaindex import ocr
from metaindex import logger
from metaindex.query import Query, QueryVisitor, Term
from metaindex.shared import CacheEntry


class CacheBase:
    """The basic Cache API"""
    def __init__(self, config=None):
        self.config = config or configuration.load()
        assert isinstance(self.config, configuration.Configuration)

        self.recursive_extra_metadata = \
                self.config.bool(configuration.SECTION_GENERAL,
                                 configuration.CONFIG_RECURSIVE_EXTRA_METADATA,
                                 "y")
        """Whether or not extra metadata is considered recursive"""

        self.ignore_dirs = self.config.list(configuration.SECTION_GENERAL,
                                            configuration.CONFIG_IGNORE_DIRS,
                                            "", separator="\n")
        """List of directories to ignore during indexing"""

        self.ignore_tags = self.config.list(configuration.SECTION_GENERAL,
                                            configuration.CONFIG_IGNORE_TAGS,
                                            "")
        """List of tags to not cache"""

        self.index_unknown = self.config.bool(configuration.SECTION_GENERAL,
                                              configuration.CONFIG_INDEX_UNKNOWN,
                                              "no")
        """Whether or not to index files when no indexers return successful"""

        ocr_opts = self.config.list(configuration.SECTION_GENERAL,
                                    configuration.CONFIG_OCR,
                                    "no")

        if len(ocr_opts) == 0 or ocr_opts[0].lower() in self.config.FALSE:
            ocr_opts = False
        elif ocr_opts[0].lower() in self.config.TRUE:
            ocr_opts = True

        self.ocr = ocr.Dummy()
        """The OCR facility, as configured by the user"""
        if ocr_opts:
            self.ocr = ocr.TesseractOCR(ocr_opts)

        fulltext_opts = self.config.list(configuration.SECTION_GENERAL,
                                         configuration.CONFIG_FULLTEXT,
                                         "no")
        if len(fulltext_opts) == 0 or fulltext_opts[0].lower() in self.config.FALSE:
            fulltext_opts = False
        elif fulltext_opts[0].lower() in self.config.TRUE:
            fulltext_opts = True

        self.extract_fulltext = fulltext_opts
        """Whether or not or for what files to run fulltext extraction"""

        self.ignore_file_patterns = []
        """Patterns of files to ignore"""
        self.accept_file_patterns = None
        """Patterns of files to index.
        If this option is set, **only** these files must be indexed and
        ``ignore_file_patterns`` can safely be ignored.
        """

        accept = self.config.list(configuration.SECTION_GENERAL,
                                  configuration.CONFIG_ACCEPT_FILES,
                                  '', separator="\n")
        ignore = self.config.list(configuration.SECTION_GENERAL,
                                  configuration.CONFIG_IGNORE_FILES,
                                  '', separator="\n")

        if len(accept) > 0:
            self.accept_file_patterns = [re.compile(fnmatch.translate(pattern.strip()), re.I)
                                         for pattern in accept]
        elif len(ignore) > 0:
            self.ignore_file_patterns = [re.compile(fnmatch.translate(pattern.strip()), re.I)
                                         for pattern in ignore]

    def refresh(self, paths=None, recursive=True, processes=None):
        """(Re-)Index all items found in the given paths or all cached items if paths is None.

        If any item in the list is a directory and recursive is True, all
        items inside that directory (including any all subdirectories) will
        be indexed, too.

        processes may be set to a number of processes that will be used in
        parallel to index the files. If left at None, there will be as many
        processes launched as CPUs are available.
        """
        raise NotImplementedError()

    def cleanup(self):
        """Find and remove all entries in the cache that refer to no longer existing files"""
        raise NotImplementedError()

    def clear(self):
        """Remove everything from the cache"""
        raise NotImplementedError()

    def forget(self, paths):
        """Remove all ``paths`` from the cache.

        :param paths: The list of paths to remove from cache."""
        raise NotImplementedError()

    def expire_metadata(self, paths):
        """Remove all metadata associated to these paths

        But keep the paths in the database.
        """
        raise NotImplementedError()

    def find(self, query):
        """Find all items matching this query.

        query may either be a human-written search term or a Query instance.

        Returns a list of (path to file, metadata, last_modified) tuples.
        """
        raise NotImplementedError()

    def get(self, paths):
        """Get metadata for all items of paths

        paths may also be a single path instead of a list of paths.

        If any element of paths is pointing to a directory and recursive is
        set to True, get will return the metadata for all elements inside
        that directory (and their subdirectories'), too.
        """
        raise NotImplementedError()

    def keys(self):
        """Get all metadata keys

        :rtype: ``list[str]``
        """
        raise NotImplementedError()

    def rename(self, path, new_path, is_dir=None):
        """Rename all entries in the database that are 'path' to 'new_path'

        If 'path' is pointing to a directory, all files in the subdirectories
        will be renamed correctly, too.
        That means that this operation can affect many rows and take some time.

        If you already renamed path to new_path, you have to provide the `is_dir`
        parameter to indicate whether the item you renamed is a directory or not!
        """
        raise NotImplementedError()

    def last_modified(self):
        """Return the date and time of the entry that most recently updated in the database.
        :rtype: ``datetime.datetime``
        """
        raise NotImplementedError()

    def insert(self, item):
        """Insert the CacheEntry ``entry`` into the cache.

        This operation will not modify the item in the filesystem nor update
        any other form of metadata persistency for the item.
        This function really only affects the cache.
        """
        raise NotImplementedError()

    def parse_extra_metadata(self, metafile):
        """Extract extra metadata from this file"""
        data = stores.get_for_collection(metafile)

        for filename in data.keys():
            data[filename][shared.IS_RECURSIVE] = data[filename][shared.IS_RECURSIVE] and \
                                                  self.recursive_extra_metadata

        return data

    def find_indexable_files(self, paths, recursive=True):
        """Find all files that can be indexed in the given paths

        :param paths: A list of paths to search through
        :param recursive: Whether or not any given directories should be indexed
                          recursively"""
        paths = [pathlib.Path(path).resolve() for path in paths]

        # filter out ignored directories
        paths = [path for path in paths
                 if not any(ignoredir in path.parts
                            for ignoredir in self.ignore_dirs)]

        dirs = [path for path in paths if path.is_dir()]
        files = {path for path in paths if path.is_file() and self._accept_file(path)}
        files |= {fn for fn in find_files(dirs, recursive, self.ignore_dirs)
                     if self._accept_file(fn)}

        return files

    def _accept_file(self, path):
        if any(ignoredir in path.parts[:-1] for ignoredir in self.ignore_dirs):
            return False
        if self.config.is_sidecar_file(path):
            return False
        pathstr = str(path)
        if self.accept_file_patterns is not None:
            return any(pattern.match(pathstr) for pattern in self.accept_file_patterns)
        return not any(pattern.match(pathstr) for pattern in self.ignore_file_patterns)


class Cache(CacheBase):
    CACHE_FILENAME = "index" + os.extsep + "db"

    def __init__(self, config=None):
        super().__init__(config)


        # create database connection
        location = self.config.get(configuration.SECTION_GENERAL,
                                   configuration.CONFIG_CACHE,
                                   configuration.CACHEPATH)
        if location != ':memory:':
            location = pathlib.Path(location).expanduser().resolve() / Cache.CACHE_FILENAME

            if not location.parent.exists():
                location.parent.mkdir(parents=True, exist_ok=True)

        self.database = sql.SqlAccess(location)

    def refresh(self, paths=None, recursive=True, processes=None):
        if paths is None:
            paths = self.database.files()

        elif isinstance(paths, (set, tuple)):
            paths = list(paths)

        elif not isinstance(paths, list):
            paths = [paths]

        if len(paths) == 0:
            return []

        files = self.find_indexable_files(paths, recursive)

        # cache of last_modified dates for files
        last_modified = {fn: shared.get_last_modified(fn) for fn in files}

        # obtain cached metadata
        last_cached = {entry.path: entry for entry in self.get(files)}

        indexer_result = indexer.index_files(files,
                                             self.config,
                                             processes,
                                             self.ocr,
                                             self.extract_fulltext,
                                             last_modified,
                                             last_cached)

        results = []
        for result in indexer_result:
            if not result.success and not self.index_unknown:
                continue
            result.info.last_modified = last_modified[result.filename]
            results.append(result.info)
        self.database.insert(results)
        return results

    def cleanup(self):
        self.database.purge([path
                             for path in self.database.files()
                             if not path.exists()])

    def clear(self):
        self.database.flush()

    def expire_metadata(self, paths):
        if paths is None:
            pass
        elif not isinstance(paths, list):
            paths = [paths]

        if isinstance(paths, list):
            paths = [pathlib.Path(path).resolve()
                     for path in paths]

        self.database.expire_metadata(paths)

    def rename(self, path, new_path, is_dir=None):
        if (is_dir is not None and is_dir) or path.is_dir():
            self.database.rename_dir(path, new_path)
        else:
            self.database.rename_file(path, new_path)

    def last_modified(self):
        return self.database.last_modified()

    def forget(self, paths):
        self.database.purge(paths)

    def find(self, query):
        if query is None or len(query) == 0:
            query = Query()

        elif isinstance(query, str):
            query = Query.parse(query, self.config.synonyms)

        elif not isinstance(query, Query):
            raise TypeError()

        return self.database.find(query)

    def get(self, paths):
        if not isinstance(paths, (list, set, tuple)):
            paths = [paths]

        paths = [pathlib.Path(path).resolve() for path in paths]

        return self.database.get(paths)

    def insert(self, item):
        self.database.insert([item])

    def keys(self):
        return self.database.keys()


class ThreadedCache(CacheBase):
    """Special version of Cache to be used in multi-threaded applications

    To use this, create an instance and execute ``start``.
    """
    GET = "get"
    FIND = "find"
    REFRESH = "refresh"
    INSERT = "insert"
    GET_KEYS = "get-keys"
    RENAME = "rename"
    FORGET = "forget"
    CLEAR = "clear"
    CLEANUP = "cleanup"
    LAST_MODIFIED = "last_modified"
    EXPIRE = "expire"

    BACKEND_TYPE = Cache

    def __init__(self, config):
        super().__init__(config)
        self.queue = queue.Queue()
        self._quit = False
        self.handler = threading.Thread(target=self.handler_loop)
        self.results = queue.Queue()
        self.single_call = threading.Lock()
        self.cache = None
        self._started = False

    @property
    def is_started(self):
        """Whether or not the thread has been started"""
        return self._started

    def find_indexable_files(self, paths, recursive=True):
        self.assert_started()
        assert self.cache is not None
        return self.cache.find_indexable_files(paths, recursive)

    def assert_started(self):
        """Ensure that the worker thread has been started"""
        if not self._started:
            raise RuntimeError("Not started")

    def get(self, paths):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.GET, paths))
            return self.results.get()

    def find(self, query):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.FIND, query))
            return self.results.get()

    def refresh(self, paths=None, recursive=True, processes=None):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.REFRESH, paths, recursive, processes))
            return self.results.get()

    def insert(self, item):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.INSERT, item))
            return self.results.get()

    def rename(self, path, new_path, is_dir=None):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.RENAME, path, new_path, is_dir))
            return self.results.get()

    def forget(self, paths):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.FORGET, paths))
            return self.results.get()

    def clear(self):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.CLEAR,))
            return self.results.get()

    def cleanup(self):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.CLEANUP,))
            return self.results.get()

    def expire_metadata(self, paths):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.EXPIRE, paths))
            return self.results.get()

    def keys(self):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.GET_KEYS,))
            return self.results.get()

    def last_modified(self):
        self.assert_started()
        with self.single_call:
            self.queue.put((self.LAST_MODIFIED,))
            return self.results.get()

    def start(self):
        """Launch the cache thread"""
        self.handler.start()

    def quit(self):
        """End the cache thread"""
        self._quit = True
        if self._started:
            self._started = False
            self.queue.put("")
            self.handler.join()

    def handler_loop(self):
        """The handler running in the separate thread.

        You do not need to call this. Call ``start`` instead.
        """
        if self._started:
            return
        self.cache = type(self).BACKEND_TYPE(self.config)
        self._started = True
        while not self._quit:
            item = self.queue.get()
            if len(item) < 1:
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
                    self.cache.insert(*args)
                elif command == self.LAST_MODIFIED:
                    result = self.cache.last_modified()
                elif command == self.GET_KEYS:
                    result = self.cache.keys()
                elif command == self.FORGET:
                    self.cache.forget(*args)
                elif command == self.CLEAR:
                    self.cache.clear()
                elif command == self.CLEANUP:
                    self.cache.cleanup()
                elif command == self.EXPIRE:
                    self.cache.expire_metadata(*args)
            except Exception as exc:
                result = exc

            self.results.put(result)


class MemoryCache(CacheBase):
    """Version of the threaded cache that uses in-memory caching of the database

    Upon initialisation this cache will obtain all entries from the database
    and try to keep the data in memory up to date.
    """
    BACKEND_TYPE = ThreadedCache

    def __init__(self, config):
        super().__init__(config)
        # TODO - refactor this into a proper directory tree
        #        to make several accesses (mostly directory-based)
        #        much faster
        self.entries_by_path = {}
        self.all_keys = set()
        self.last_read = datetime.datetime.min

        self.tcache = type(self).BACKEND_TYPE(config)
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

    def find_indexable_files(self, paths, recursive=True):
        return self.tcache.find_indexable_files(paths, recursive)

    def insert(self, item):
        with self.writing:
            self._do_insert(item)

        # run the actual renaming in the background though
        threading.Thread(target=lambda:
                self._persist_inserts([item])).start()

    def bulk_insert(self, inserts):
        """Insert a whole set of files and their metadata

        inserts is a list of (path, metadata, last_modified) tuples, just
        like the parameters that you would use for 'insert'.
        """
        with self.writing:
            for item in inserts:
                self._do_insert(item)

        threading.Thread(target=lambda: self._persist_inserts(inserts)).start()

    def _do_insert(self, item):
        # assumes you know what you are doing and self.writing is acquired
        item.ensure_last_modified()
        self.entries_by_path[item.path] = item
        self.all_keys |= set(self.entries_by_path[item.path].keys())

    def _persist_inserts(self, inserts):
        for item in inserts:
            self.tcache.insert(item)

    def forget(self, paths):
        if not isinstance(paths, (list, tuple, set)):
            paths = [paths]

        to_purge = []
        with self.writing:
            # ugh, this is soooo inefficient. see the todo in __init__
            # about refactoring this
            for path in paths:
                strpath = str(path)
                to_delete = [key for key in self.entries_by_path
                                 if str(key).startswith(strpath)]
                to_purge += to_delete
                for key in to_delete:
                    del self.entries_by_path[key]

        threading.Thread(target=lambda: self._forget_from_cache(to_purge)).start()

    def _forget_from_cache(self, to_delete):
        self.tcache.forget(to_delete)

    def clear(self):
        with self.writing:
            self.entries_by_path = {}
            self.all_keys = set()

            self.tcache.clear()

    def cleanup(self):
        with self.writing:
            to_forget = [path for path in self.entries_by_path
                         if not path.exists()]
            for path in to_forget:
                del self.entries_by_path[path]

        threading.Thread(target=lambda: self._forget_from_cache(to_forget)).start()

    def expire_metadata(self, paths):
        with self.writing:
            self.tcache.expire_metadata(paths)

    def last_modified(self):
        return max(v.last_modified for v in self.entries_by_path.values())

    def find(self, query):
        """Find all entries that match this query"""
        matcher = CacheEntryQueryVisitor()
        query = Query.parse(query, synonyms=self.config.synonyms)
        query.accept(matcher)

        return [e for e in self.entries_by_path.values()
                if matcher.matches(e)]

    def get(self, paths):
        """Get all entries for these paths (recursively)"""
        if not isinstance(paths, (list, tuple, set)):
            paths = [paths]

        return [entry
                for path, entry in self.entries_by_path.items()
                if any(path.is_relative_to(pathpattern)
                       for pathpattern in paths)]

    def bulk_rename(self, renames):
        """Run the rename operation for all renames

        See also below, `rename`.

        `renames` must be a tuple `(old_path, new_path)`.
        `old_path` can be a directory, moving all cached subentries
        accordingly, too.

        You may add a `is_dir` boolean value to prevent the lookup of whether
        or not `old_path` is a directory, i.e. `(old_path, new_path, is_dir)`.
        Use it if you *first* rename the path and then update the cache.
        """
        cache_renames = []
        if any(len(data) not in [2, 3] for data in renames):
            raise ValueError()

        for data in renames:
            if len(data) == 2:
                path, new_path = data
                is_dir = None
            elif len(data) == 3:
                path, new_path, is_dir = data
            else:
                raise ValueError()

            if not isinstance(new_path, pathlib.Path):
                new_path = pathlib.Path(new_path).resolve()
            if not isinstance(path, pathlib.Path):
                path = pathlib.Path(path).resolve()

            logger.debug("Rename %s to %s", path, new_path)
            if (is_dir is not None and is_dir) or path.is_dir():
                entries = [e for p, e in self.entries_by_path.items()
                           if p.is_relative_to(path)]
                for entry in entries:
                    del self.entries_by_path[entry.path]
                    assert path.parts == entry.path.parts[:len(path.parts)]
                    parts = new_path.parts + entry.path.parts[len(path.parts):]
                    new_entry_path = pathlib.Path(os.sep.join(parts)).resolve()
                    logger.debug(" ... renaming %s to %s", entry.path, new_entry_path)
                    new_entry = CacheEntry(new_entry_path,
                                           entry.metadata,
                                           entry.last_modified)
                    self.entries_by_path[new_entry_path] = new_entry

            elif path in self.entries_by_path:
                entry = self.entries_by_path[path]
                new_entry = CacheEntry(new_path,
                                       entry.metadata,
                                       entry.last_modified)
                del new_entry['filename']
                new_entry.add('filename', str(new_path.name))
                self.entries_by_path[new_path] = new_entry
                del self.entries_by_path[path]

            cache_renames.append((path, new_path))

        threading.Thread(target=lambda: self.do_rename(cache_renames)).start()

    def rename(self, path, new_path, is_dir=None):
        """Move all metadata entries for 'path' to 'new_path'.

        Convenience wrapper for bulk_rename.
        """
        self.bulk_rename([(path, new_path, is_dir)])

    def do_rename(self, renames):
        """A blocking rename function.

        Do not call this directly, but call 'rename' instead."""
        with self.writing:
            for path, new_path in renames:
                self.tcache.rename(path, new_path)

    def refresh(self, paths, recursive=True, processes=None):
        """(Re-)index these paths (recursively by default)"""
        if not isinstance(paths, (list, set, tuple)):
            paths = [paths]

        with self.reloading:
            with self.writing:
                self.tcache.refresh(paths, recursive, processes)
                if recursive:
                    for path in set(self.entries_by_path.keys()):
                        if any(path.is_relative_to(pathpattern) for pathpattern in paths):
                            del self.entries_by_path[path]
                else:
                    for path in paths:
                        if path in self.entries_by_path:
                            del self.entries_by_path[path]

                for entry in self.tcache.get(paths):
                    self.entries_by_path[entry.path] = entry
                    self.all_keys |= entry.metadata.keys()

    def keys(self):
        """Returns a set of all known metadata keys."""
        return self.all_keys

    def invalidate(self):
        """Invalidate the cached entries and reload"""
        self.entries_by_path = {}
        self.all_keys = set()
        self.reload()

    def reload(self):
        """Reload the data from the cache"""
        threading.Thread(target=self.do_reload).start()

    def do_reload(self):
        """A blocking reload function.

        Do not call this directly, but call 'invalidate' or 'reload' instead.
        """
        entries = {}
        keys = set()
        with self.reloading:
            attempt = 0
            while not self.tcache.is_started and attempt < 10:
                time.sleep(0.1)
                attempt += 1
            if not self.tcache.is_started:
                return

            for entry in self.tcache.find(''):
                entries[entry.path] = entry
                keys |= entry.metadata.keys()

            with self.writing:
                self.entries_by_path = entries
                self.all_keys = keys
                self.last_read = datetime.datetime.now()
                self.is_initialized = True

    def quit(self):
        """End the cache thread"""
        with self.writing:
            self.tcache.quit()
            self.tcache = ThreadedCache(self.config)
            self.entries_by_path = {}
            self.all_keys = set()


class CacheEntryQueryVisitor(QueryVisitor):
    """A QueryVisitor implementation to match against CacheEntry instances"""
    class Matcher:
        def __init__(self, visitor, element):
            self.visitor = visitor
            self.inverted = element.inverted
            self.operator = element.operator

        def match(self, item):
            raise NotImplementedError()

    class RegexMatcher(Matcher):
        def __init__(self, visitor, element):
            super().__init__(visitor, element)
            self.word = element.word

        def match(self, item):
            regex = self.visitor.regex_cache[self.word]
            matches = any(regex.search(str(value)) is not None
                          for value in set(value for value in item))
            if self.inverted:
                return not matches
            return matches

    class KeyExistsMatcher(Matcher):
        def __init__(self, visitor, element):
            super().__init__(visitor, element)
            self.keys = element.key
            if not isinstance(self.keys, (list, set, tuple)):
                self.keys = [self.keys]

        def match(self, item):
            result = any(key in item for key in self.keys)
            if self.inverted:
                return not result
            return result

    class KeyValueMatcher(Matcher):
        def __init__(self, visitor, element):
            super().__init__(visitor, element)
            self.keys = element.key
            self.regex = element.regex
            if not isinstance(self.keys, (list, tuple, set)):
                self.keys = [self.keys]

        def match(self, item):
            matches = any(sql.regex_cache[self.regex].search(str(value)) is not None
                          for value in sum([item[key] for key in self.keys], start=[]))
            if self.inverted:
                return not matches
            return matches

    class SequenceMatcher(Matcher):
        def __init__(self, visitor, element):
            super().__init__(visitor, element)
            self.matchers = []

        def match(self, item):
            # if len(self.matchers) > 1:
                #     breakpoint()
            results = []
            conjuncts = list(m.match(item) for m in self.matchers
                             if m.operator == Term.AND)
            disjuncts = list(m.match(item) for m in self.matchers
                             if m.operator == Term.OR)
            if len(conjuncts) > 0:
                results.append(all(conjuncts))
            if len(disjuncts) > 0:
                results.append(any(disjuncts))
            if len(conjuncts) == 0 and len(disjuncts) == 0:
                return True

            if self.operator == Term.AND:
                return all(results)
            return any(results)

    regex_cache = {}

    def __init__(self):
        self.sequence_stack = []
        self.root = None

    def on_regex(self, element):
        if element.word not in type(self).regex_cache:
            type(self).regex_cache[element.word] = re.compile(element.word, re.IGNORECASE)
        self.sequence_stack[-1].matchers.append(type(self).RegexMatcher(self, element))

    def on_key_exists(self, element):
        self.sequence_stack[-1].matchers.append(type(self).KeyExistsMatcher(self, element))

    def on_key_value(self, element):
        if element.regex not in type(self).regex_cache:
            sql.regex_cache[element.regex] = re.compile(element.regex, re.IGNORECASE)
        self.sequence_stack[-1].matchers.append(type(self).KeyValueMatcher(self, element))

    def on_sequence_start(self, element):
        self.sequence_stack.append(type(self).SequenceMatcher(self, element))

    def on_sequence_end(self, _):
        sequence = self.sequence_stack.pop(-1)
        if len(self.sequence_stack) == 0:
            self.root = sequence
        else:
            self.sequence_stack[-1].matchers.append(sequence)

    def matches(self, entry):
        if self.root is None:
            return True
        return self.root.match(entry)


def find_files(paths, recursive=True, ignore_dirs=None):
    """Find all files in these paths"""
    if not isinstance(paths, list):
        paths = [paths]
    if ignore_dirs is None:
        ignore_dirs = []

    pathqueue = list(paths)
    filenames = []

    while len(pathqueue) > 0:
        path = pathqueue.pop(0)

        if not isinstance(path, pathlib.Path):
            path = pathlib.Path(path)

        if not path.exists():
            continue

        for item in path.iterdir():
            if item.is_dir() and recursive and item.parts[-1] not in ignore_dirs:
                pathqueue.append(item)
                continue

            if item.is_file():
                filenames.append(item)

    return filenames


if __name__ == '__main__':
    logger.setup('DEBUG')
    cache = Cache()
    breakpoint()
