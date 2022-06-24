"""File indexer base class and API"""
import datetime
import pathlib
import mimetypes
import time
import sys
import os
from collections import namedtuple
from multiprocessing import Queue, Process, Event
from enum import IntEnum
try:
    from signal import SIGINT
except ImportError:
    SIGINT = None
try:
    from signal import CTRL_C_EVENT
except ImportError:
    CTRL_C_EVENT = None

from metaindex import shared
from metaindex import logger
from metaindex import configuration
from metaindex.ocr import Dummy


_registered_indexers = {}
_indexer_by_suffix = {}
_indexer_by_mimetype = {}
_generic_indexers = []


SKIPPED = 'skipped'


class Order(IntEnum):
    """Indexer execution order groups"""
    FIRST = 100
    EARLY = 250
    AVERAGE = 500
    LATE = 750
    LAST = 1000


def only_if_changed(fnc):
    """Use this decorator on ``IndexerBase.run`` to prevent indexers being
    re-run on files when they have not changed since the last run."""
    def wrapping(self, path, info, last_cached):
        if not self.changed_since_cached(path, last_cached):
            logger.debug(f"... skipping {path.name} since it has not changed")
            return self.reuse_cached(info, last_cached)
        return fnc(self, path, info, last_cached)
    return wrapping


class IndexerBase:
    """Base class for all file indexers

    When adding an indexer to metaindex, you should sublass from this.

    Make sure to define the class propertes ``NAME``, ``ACCEPT``, and
    ``PREFIX``.

    You can control when the indexer should be run (compared to others for
    the same file type), by defining the ``ORDER`` class property.
    """

    NAME = None
    """The name by which this indexer is registered"""

    ACCEPT = []
    """
    Specify what suffices or mimetypes are handled by this indexer, e.g.
    ``ACCEPT = ['.rst', '.md', 'text/html', 'image/']``
    anything starting with a ``.`` is assumed to be a suffix,
    everything else is assumed to be a mimetype.

    If the mimetype ends with ``/``, it is matched against the first part
    of the file's mimetype.

    If your indexer should run for all files, use ``ACCEPT = '*'``
    You must declare the prefix that is used for tag names of this indexer
    This may also be a tuple (or otherwise iterable) of prefixes.
    """

    PREFIX = None
    """What prefix a tag created by this indexer should receive."""

    ORDER = Order.AVERAGE
    """When to execute this indexer in the order of indexers"""

    def __init__(self, cache):
        """Create a new indexer with this configuration"""
        self.cache = cache

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)

        if None in [cls.PREFIX, cls.NAME]:
            # don't register an Indexer if it does not come
            # with a prefix or a name
            logger.debug("Not registering indexer %s", cls.__name__)
            return

        assert cls.NAME not in _registered_indexers
        _registered_indexers[cls.NAME] = cls

        accepts = cls.ACCEPT

        if isinstance(accepts, str) and accepts == '*':
            _generic_indexers.append(cls.NAME)
        else:
            if isinstance(accepts, str):
                accepts = [accepts]
            assert isinstance(accepts, list)

            for pattern in accepts:
                pattern = pattern.lower()

                if pattern.startswith('.') and len(pattern) > 1:
                    if pattern not in _indexer_by_suffix:
                        _indexer_by_suffix[pattern] = []
                    _indexer_by_suffix[pattern].append(cls.NAME)

                elif len(pattern) > 0:
                    if pattern.endswith('/') and len(pattern) > 1:
                        pattern = pattern[:-1]
                    if pattern not in _indexer_by_mimetype:
                        _indexer_by_mimetype[pattern] = []
                    _indexer_by_mimetype[pattern].append(cls.NAME)

    @property
    def ocr(self):
        return self.cache.ocr

    @property
    def fulltext(self):
        return self.cache.fulltext

    @property
    def config(self):
        return self.cache.config

    def should_ocr(self, path):
        return self._check_match(self.ocr.accept_list, path)

    def should_fulltext(self, path):
        return self._check_match(self.fulltext, path)

    def _check_match(self, acceptor, path):
        if not isinstance(acceptor, list):
            return bool(acceptor)

        if self.NAME in acceptor:
            return True

        for item in acceptor:
            if item.startswith('.') and path.suffix.lower() == item.lower():
                return True
            if '/' in item:
                mimetype, _ = mimetypes.guess_type(path.name, strict=False)
                if mimetype is not None and mimetype.lower().startswith(item.lower()):
                    return True

        return False

    def __lt__(self, other):
        return self.ORDER < other.ORDER

    @staticmethod
    def cached_dt(last_cached):
        """Return the datetime when this cache entry was created"""
        if last_cached is None:
            return datetime.datetime.min
        return last_cached.last_modified

    def changed_since_cached(self, path, last_cached):
        """Return True if the file at path has changed since it was cached
           last (according to last_cached)"""
        last_cached_dt = self.cached_dt(last_cached)
        return last_cached_dt <= datetime.datetime.min \
            or self.cache.last_modified(path) > last_cached_dt

    def reuse_cached(self, metadata, last_cached):
        """Updates metadata with the entries from last_cached for entries of this indexer

        The idea is that you can call ``return self.reuse_cached(metadata, last_cached)``
        from ``run(...)`` if you are skipping the execution of the indexer because nothing
        changed since the last time it was run.

        This function is used, for example, from ``@only_if_changed``.
        """
        prefix = self.PREFIX
        if isinstance(prefix, str):
            prefix = [prefix]
        for key, value in last_cached:
            if '.' not in key or key.split('.', 1)[0] not in prefix:
                continue
            metadata.add(key, value)

    def run(self, path, metadata, last_cached):
        """Execute this Indexer to run on the file at path.

        :param path: will be of type pathlib.Path.

        :param metadata: is the accumulated metadata already collected by other
                         indexers that ran before this one. You are expected to add your
                         metadata keys and values in here.
        :type info: ``metaindex.CacheEntry``

        :param last_cached: is the metadata from when this file was entered into
                            the cache the last time. You could use this
                            information to skip indexing, e.g. when the
                            ``last_modified`` of the file is older than the
                            cached entry.
        :type last_cached: ``CacheEntry``

        Consider using the ``@only_if_changed`` decorator if you want this
        indexer to only be run if the file has changed since the last run of
        any indexer.

        Be aware that each subprocess will create their own instance of your
        Indexer; if you have a cache, it will be different between the processes.
        """
        raise NotImplementedError()


IndexerResult = namedtuple('IndexerResult', ['filename', 'success', 'info'])


class IndexerRunner:
    """Configuration and caching for the run of an indexer"""
    def __init__(self, config=None, fulltext=False, last_modified=None, base_info=None):
        """Usually you will not have to create this instance yourself. ``index`` will
        do that for you.

        :param config: The configuration settings to use
        :type config: ``metaindex.configuration.Configuration``
        :param fulltext: Whether or not to extract fulltext.
        :param last_modified: A cache of last modification dates of files
        :type last_modified: ``dict[pathlib.Path]->datetime.datetime``
        :param base_info: The initial metadata information
        :type base_info: ``dict[pathlib.Path]->CacheEntry``
        """
        self.cached = {}
        self.fulltext = fulltext
        self.config = config or configuration.Configuration()
        self.ocr = config.ocr
        self._last_modified = last_modified or {}
        self.base_info = base_info or {}

        self.generic_indexers = [i for i in _generic_indexers
                                 if i not in config.ignore_indexers]
        self.registered_indexers = {k: v
                                    for k, v in _registered_indexers.items()
                                    if k not in config.ignore_indexers}
        self.indexer_by_suffix = {k: v
                                  for k, v in _indexer_by_suffix.items()
                                  if k not in config.ignore_indexers}
        self.indexer_by_mimetype = {k: v
                                    for k, v in _indexer_by_mimetype.items()
                                    if k not in config.ignore_indexers}

        # TODO - the list of blocked indexers should rather be parsed here than
        #        removing the indexers from the registry some time earlier
        for name in self.registered_indexers:
            # pre-load all
            self.get(name)

    def last_modified(self, filepath):
        """Return the last_modified date if ``filepath`` if it is in the cache"""
        return self._last_modified.get(pathlib.Path(filepath), datetime.datetime.min)

    def get(self, name):
        """Return the indexer instance by name

        :param name: Name of the indexer to obtain
        :return: The instance of the indexer requested
        :rtype: ``IndexerBase``
        """
        if name not in self.cached:
            self.cached[name] = self.registered_indexers[name](self)
        return self.cached[name]

    def index(self, files):
        """Index the given files

        :param files: The files to index
        :type files: ``list[pathlib.Path]``
        :return: a list of ``IndexerResult``
        """
        results = []

        for filename in files:
            filename = pathlib.Path(filename)

            if not filename.is_file():
                continue

            try:
                result = self.get_metadata(filename)
            except KeyboardInterrupt:
                return results
            except Exception as exc:
                logger.error("Indexing %s failed: %s", filename, exc)
                result = IndexerResult(filename, False, shared.CacheEntry(filename))

            results.append(result)

        return results

    def get_metadata(self, path):
        """Extract metadata from the file at `filename`"""
        logger.debug(f"Going for {path}")

        stat = path.stat()
        suffix = path.suffix[1:]
        mimetype, _ = mimetypes.guess_type(path, strict=False)
        info = shared.CacheEntry(path)
        info.add('size', stat.st_size)
        info.last_modified = datetime.datetime.fromtimestamp(stat.st_mtime)

        if mimetype is not None:
            info.add('mimetype', mimetype)

        delete_keys = set()
        applied_indexers = 0
        indexers = self.generic_indexers[:] \
                 + self.indexer_by_suffix.get(path.suffix.lower(), [])
        if mimetype is not None:
            for mtype in [mimetype, mimetype.split('/', 1)[0]]:
                indexers += self.indexer_by_mimetype.get(mtype, [])

        base_info = self.base_info.get(path, shared.CacheEntry(path))
        for handler in sorted(set(self.get(indexer) for indexer in indexers)):
            logger.debug(f"... running {type(handler).__name__}")

            initial_fields = len(info)
            handler.run(path, info, base_info)

            # Some fields have been added since?
            if len(info) > initial_fields:
                applied_indexers += 1

                # if an 'extra.' key's value is set to None explicitely,
                # it WILL be removed after the last indexer ran
                delete_keys |= {key_.split('.', 1)[1]
                                for key_, value in info
                                if value is None and key_.startswith(shared.EXTRA)}

        # remove ignored tags
        for keyname in self.config.ignore_tags:
            keyname = keyname.lower()
            if keyname.startswith('*'):
                for other, _ in info:
                    if other.endswith(keyname[1:]):
                        delete_keys.add(other)
            elif keyname.endswith('*'):
                for other, _ in info:
                    if other.startswith(keyname[:-1]):
                        delete_keys.add(other)
            else:
                delete_keys.add(keyname)

        for key_ in delete_keys | {shared.IS_RECURSIVE}:
            if key_ in info:
                del info[key_]

        success = applied_indexers > 0
        return IndexerResult(path, success, info)


class IndexerRunnerProcess(IndexerRunner, Process):
    def __init__(self, config=None, fulltext=False, last_modified=None, base_info=None):
        IndexerRunner.__init__(self, config, fulltext, last_modified, base_info)
        Process.__init__(self)
        self.files = []
        self.results = Queue()
        self.cancel = Event()

    def run(self):
        for file_ in self.files:
            if self.cancel.is_set():
                break
            results = self.index([file_])
            for result in results:
                self.results.put(result)


def get(name):
    """Get indexer by name

    :param name: The indexer to get
    :return: The indexer class or None
    """
    return _registered_indexers.get(name, None)


def index_files(files,
                baseconfig=None,
                processes=None,
                ocr=None,
                fulltext=False,
                last_modified=None,
                last_cached=None):
    """Run indexer on all files

    If you don't provide a ``baseconfig``, the user's (or system's) configuration
    file will be loaded. If you wish to not use the user's configuration settings,
    pass a new, empty ``metaindex.Configuration`` instance.

    When passing files to index, avoid passing sidecar files. You can use
    ``Configuration.is_sidecar_file`` to determine whether or not a file is a
    sidecar file.

    :param files: The files to index
    :param baseconfig: The metaindex configuration
    :param processes: How many processes to run in parallel (this parameter is
                      currently ignored)
    :param fulltext: Whether or not to extract fulltext
    :param last_modified: A cache of last_modified dates of file the indexer
                          may use instead of checking the last_modified date
                          per file on its own
    :param last_cached: The metadata information cache from previous runs.
    :type last_cached: ``list[IndexerResult]``

    :return: The ``IndexerResult`` for each of the files that were supposed to be indexed.
    :rtype: ``list[IndexerResult]``
    """
    from metaindex import indexers as _

    if baseconfig is None:
        baseconfig = configuration.load()

    if processes is None:
        processes = len(os.sched_getaffinity(0))
    if processes > len(files):
        processes = len(files)
    processes = 1

    results = []
    if processes > 1:
        logger.info("Using %s processes", processes)
        runners = []
        for _ in range(processes):
            runners.append(IndexerRunnerProcess(baseconfig,
                                                fulltext=fulltext,
                                                last_modified=last_modified,
                                                base_info=last_cached))

        for pos, file_ in enumerate(files):
            runner = pos % len(runners)
            runners[runner].files.append(file_)

        then = datetime.datetime.now()
        for runner in runners:
            runner.start()

        try:
            for runner in runners:
                runner.join()
        except KeyboardInterrupt:
            logger.fatal("Cancelling all running processes")
            for runner in runners:
                runner.cancel.set()
            time.sleep(0.5)
            signal = SIGINT
            if sys.platform.startswith('win'):
                signal = CTRL_C_EVENT
            for runner in runners:
                if runner.is_alive():
                    os.kill(runner.pid, signal)

        for runner in runners:
            try:
                if runner.is_alive():
                    runner.join()
            except KeyboardInterrupt:
                pass

        for runner in runners:
            while not runner.results.empty():
                item = runner.results.get_nowait()
                if item is not None:
                    results += [item]

    else:
        runner = IndexerRunner(baseconfig,
                               fulltext=fulltext,
                               last_modified=last_modified,
                               base_info=last_cached)

        then = datetime.datetime.now()
        results = runner.index(files)

    logger.info("Processed %s files in %s",
                len([v for v in results if v[1]]),
                datetime.datetime.now() - then)
    logger.debug("Successfully indexed: %s",
                 ', '.join([str(v[0]) for v in results if v[1]]))

    return results


if __name__ == '__main__':
    import sys

    logger.setup('DEBUG')
    config = configuration.load()

    index = index_files([pathlib.Path(i).expanduser() for i in sys.argv[1:]],
                        config)
