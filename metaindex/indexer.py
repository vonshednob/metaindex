import datetime
import pathlib
import mimetypes

import multidict

from metaindex import ocr
from metaindex import shared
from metaindex import logger
from metaindex import configuration


_registered_indexers = {}
_indexer_by_suffix = {}
_indexer_by_mimetype = {}
_generic_indexers = []


# ``_base_info`` is a dictionary of filename -> multidict of metadata from the
# cache. It may be ``None`` to enforce full indexing.
_base_info = None
ocr_facility = ocr.Dummy()
app_config = configuration.Configuration()


SKIPPED = 'skipped'


class Order:
    FIRST = 100
    EARLY = 250
    AVERAGE = 500
    LATE = 750
    LAST = 1000


def only_if_changed(fnc):
    def wrapping(self, path, info, last_cached):
        if not self.changed_since_cached(path, last_cached):
            logger.debug(f"... skipping {path.name} since it has not changed")
            return self.reuse_cached(last_cached)
        return fnc(self, path, info, last_cached)
    return wrapping


class Indexer:
    # The name by which this indexer is registered
    NAME = None
    # specify what suffices or mimetypes are handled by this indexer, e.g.
    # ACCEPT = ['.rst', '.md', 'text/html', 'image/']
    # anything starting with a . is expected to be a suffix,
    # everything else is expected to be a mimetype.
    # If the mimetype ends with /, it is matched against the first part
    # of the file's mimetype
    # If your indexer should run for all files, use ACCEPT = '*'
    ACCEPT = []
    # You must declare the prefix that is used for tag names of this indexer
    # This may also be a tuple (or otherwise iterable) of prefixes.
    PREFIX = None
    # When to execute this indexer in the order of indexers
    ORDER = Order.AVERAGE

    def __init__(self, cache):
        """Create a new indexer with this configuration"""
        self.cache = cache

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
        last_cached_dt = Indexer.cached_dt(last_cached)
        return last_cached_dt <= datetime.datetime.min \
            or self.cache.last_modified(path) > last_cached_dt

    def reuse_cached(self, last_cached):
        """Returns the tuple True, dict(), the latter containing all entries
           from last_cached produced by this indexer

        The idea is that you can call ``return self.reuse_cached(last_cached)`` from ``run(...)``
        if you are skipping the execution of the indexer because nothing changed since the last time
        it was run.

        This function is used, for example, from ``@only_if_changed``.
        """
        prefix = self.PREFIX
        if isinstance(prefix, str):
            prefix = [prefix]
        return (True,
                multidict.MultiDict([(k, v)
                                     for k, v in last_cached.metadata.items()
                                     if '.' in k and k.split('.', 1)[0] in prefix]))

    def run(self, path, info, last_cached):
        """Execute this Indexer to run on the file at path.

        ``path`` will be of type pathlib.Path.

        ``info`` is the previously collected metadata as a multidict this is
        purely informative and should not be returned.

        ``last_cached`` is the metadata from when this file was entered into
        the cache the last time. You could use this information to skip
        indexing, e.g. when the last_modified of the file is older than the
        cached entry.

        Return the tuple (success, metadata). success being True or False,
        metadata being a multidict.Multidict or a dict.

        Consider using the ``@only_if_changed`` decorator if you want this
        indexer to only be run if the file has changed since the last run of
        any indexer.

        Be aware that each subprocess will create their own instance of the
        Indexer.
        """
        raise NotImplementedError()


def registered_indexer(cls):
    """Decorator to register an indexer"""
    assert issubclass(cls, Indexer)

    global _registered_indexers
    global _indexer_by_suffix
    global _indexer_by_mimetype
    global _generic_indexers

    assert cls.PREFIX is not None
    assert cls.NAME is not None
    assert cls.NAME not in _registered_indexers
    _registered_indexers[cls.NAME] = cls

    if isinstance(cls.ACCEPT, str) and cls.ACCEPT == '*':
        _generic_indexers.append(cls.NAME)
    else:
        for pattern in cls.ACCEPT:
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

    return cls


def remove_indexers(names):
    global _registered_indexers
    global _indexer_by_suffix
    global _indexer_by_mimetype
    global _generic_indexers

    if len(names) == 0:
        return

    for name in names:
        if name in _registered_indexers:
            del _registered_indexers[name]

    _indexer_by_suffix = {key: [value for value in values if value not in names]
                          for key, values in _indexer_by_suffix.items()}
    _indexer_by_mimetype = {key: [value for value in values if value not in names]
                            for key, values in _indexer_by_mimetype.items()}
    _generic_indexers = [value for value in _generic_indexers if value not in names]


class IndexerCache:
    def __init__(self, ocr, fulltext, config, last_modified, base_info=None):
        self.cached = {}
        self.ocr = ocr
        self.fulltext = fulltext
        self.config = config
        self._last_modified = last_modified
        self.base_info = base_info or {}

    def last_modified(self, filepath):
        return self._last_modified.get(filepath, datetime.datetime.min)

    def get(self, name):
        if name not in self.cached:
            self.cached[name] = _registered_indexers[name](self)
        return self.cached[name]


def get(name):
    """Get indexer by name"""
    return _registered_indexers.get(name, None)


def get_metadata(filename, indexer_cache):
    """Extract metadata from the file at `filename`"""
    assert isinstance(filename, pathlib.Path)

    global ocr_facility
    global obtain_fulltext
    global app_config

    logger.debug(f"Going for {filename}")

    stat = filename.stat()
    suffix = filename.suffix[1:]
    mimetype, _ = mimetypes.guess_type(filename, strict=False)
    info = multidict.MultiDict({'size': stat.st_size,
                                'last_accessed': datetime.datetime.fromtimestamp(stat.st_atime),
                                'last_modified': datetime.datetime.fromtimestamp(stat.st_mtime)})

    if mimetype is None:
        logger.debug(f"Unknown mimetype for {suffix}")
        return False, info

    info['mimetype'] = mimetype
    delete_keys = set()
    applied_indexers = 0
    indexers = _generic_indexers[:] \
             + _indexer_by_suffix.get(filename.suffix.lower(), [])
    for mtype in [mimetype, mimetype.split('/', 1)[0]]:
        indexers += _indexer_by_mimetype.get(mtype, [])

    for handler in sorted([indexer_cache.get(indexer) for indexer in indexers]):
        logger.debug(f"... running {handler}")
        success, extra = handler.run(filename,
                                     info.copy(),
                                     indexer_cache.base_info.get(filename, None))

        delete_keys |= {key_.split('.', 1)[1]
                        for key_, value in extra.items()
                        if value is None and key_.startswith('extra.')}

        if success:
            applied_indexers += 1
            info.extend(extra)

    for key_ in delete_keys | {shared.IS_RECURSIVE}:
        info.popall(key_, True)

    success = applied_indexers > 0
    return success, info


def indexer(filenames):
    """Takes a list of filenames and tries to extract the metadata for all

    Returns a dictionary mapping filename to a dictionary with the metadata.
    """
    global ocr_facility
    global obtain_fulltext
    global app_config
    global _base_info
    global _last_modified

    indexer_cache = IndexerCache(ocr_facility,
                                 obtain_fulltext,
                                 app_config,
                                 _last_modified,
                                 _base_info)
    for name in _registered_indexers.keys():
        # pre-load all
        indexer_cache.get(name)

    result = []

    for filename in filenames:
        filename = pathlib.Path(filename)

        if not filename.is_file():
            continue

        success, info = get_metadata(filename, indexer_cache)

        result.append((filename, success, info))

    return result


def index_files(files,
                processes=None,
                ocr_=None,
                fulltext=False,
                config=None,
                last_modified=None,
                last_cached=None):
    """Run indexer on all files"""
    global ocr_facility
    global obtain_fulltext
    global app_config
    global _last_modified
    global _base_info

    if ocr is not None:
        ocr_facility = ocr_
    if last_modified is None:
        _last_modified = {}
    else:
        _last_modified = last_modified
    _base_info = last_cached
    app_config = config or configuration.Configuration()
    obtain_fulltext = fulltext

    if processes is None:
        processes = 1

    then = datetime.datetime.now()
    if processes > 0:
        index_result = indexer(files)
    else:
        raise NotImplementedError()

    logger.info("Processed %s files in %s",
                len([v for v in index_result if v[1]]),
                datetime.datetime.now() - then)
    logger.debug("Successfully indexed: %s",
                 ', '.join([str(v[0]) for v in index_result if v[1]]))

    return index_result


if __name__ == '__main__':
    import sys

    logger.setup('DEBUG')

    index = index_files([pathlib.Path(i).expanduser() for i in sys.argv[1:]])
