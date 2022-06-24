"""Collection sidecar file indexers"""
from metaindex import logger
from metaindex import json
from metaindex import opf
from metaindex import configuration
from metaindex import shared
from metaindex.indexer import IndexerBase, Order

try:
    from metaindex import yaml
except ImportError:
    yaml = None


class CollectionSidecarIndexer(IndexerBase):
    """Abstract collection sidecar indexer"""
    PREFIX = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug(f"Creating a new {self.NAME}")

        # cached metadata for collection metadata, pathlib.Path -> multidict
        self.collection_cache = {}
        self.cached_sidecar_files = set()

        self.collection_metadata = self.cache.config.list(
            configuration.SECTION_GENERAL,
            configuration.CONFIG_COLLECTION_METADATA,
            '')
        self.recursive_metadata = self.cache.config.bool(
            configuration.SECTION_GENERAL,
            configuration.CONFIG_RECURSIVE_EXTRA_METADATA,
            'yes')

    def run(self, path, metadata, last_cached):
        raise NotImplementedError()

    def find_collection_sidecars(self, path, suffix):
        """Walk upwards the directory structure and yield all existing collection metadata files"""
        sidecars = []
        pathptr = path
        if pathptr.is_file():
            pathptr = path.parent
        while True:
            for filename in self.collection_metadata:
                sidecar = pathptr / (filename + suffix)
                if sidecar.exists():
                    sidecars.append(sidecar)
            if not self.recursive_metadata or pathptr == pathptr.parent:
                break
            pathptr = pathptr.parent

        return sidecars

    def cache_collection_sidecars(self, path, store):
        """Fill the cache with the sidecar files' contents"""
        assert self.PREFIX is not None
        for sidecar in self.find_collection_sidecars(path, store.SUFFIX):
            if sidecar in self.cached_sidecar_files:
                continue
            self.cached_sidecar_files.add(sidecar)

            self.collection_cache[sidecar.parent] = shared.CacheEntry(sidecar.parent)
            for filepath, extra in store.get_for_collection(sidecar).items():
                if filepath not in self.collection_cache:
                    self.collection_cache[filepath] = shared.CacheEntry(filepath)
                self.collection_cache[filepath].update(extra)

    def get_collection_metadata(self, path, suffix):
        meta = shared.CacheEntry(path)

        for sidecar in reversed(self.find_collection_sidecars(path, suffix)):
            if sidecar.parent not in self.collection_cache:
                logger.info("A sidecar file has been added while the indexer was running. "
                            "That file is ignored until the next rerun.")
                continue
            extra = self.collection_cache[sidecar.parent]
            if sidecar.parent != path.parent and \
               not (self.recursive_metadata and
                    any(v for k, v in extra if k == shared.IS_RECURSIVE)):
                continue
            meta.update(extra)

        if path in self.collection_cache:
            meta.update(self.collection_cache[path])

        return meta

    def run_with_store(self, store, path, metadata, _):
        assert self.PREFIX is not None
        self.cache_collection_sidecars(path, store)

        extra = self.get_collection_metadata(path, store.SUFFIX)

        # check for direct sidecar file
        sidecar = path.parent / (path.stem + store.SUFFIX)
        if sidecar.is_file() and sidecar != path:
            extra.update(store.get(sidecar))

        for key, value in extra:
            if key != shared.IS_RECURSIVE:
                metadata.add(key, value)


class JsonSidecarIndexer(CollectionSidecarIndexer):
    """JSON collection sidecar indexer"""
    NAME = 'json-sidecar'
    ACCEPT = '*'
    PREFIX = ''
    ORDER = Order.LAST

    def run(self, path, metadata, last_cached):
        return self.run_with_store(json, path, metadata, last_cached)


class OpfSidecarIndexer(CollectionSidecarIndexer):
    """OPF collection sidecar indexer"""
    NAME = 'opf-sidecar'
    ACCEPT = '*'
    PREFIX = ''
    ORDER = Order.LAST

    def run(self, path, metadata, _):
        self.cache_collection_sidecars(path, opf)
        for key, value in self.get_collection_metadata(path, opf.SUFFIX):
            if key != shared.IS_RECURSIVE:
                metadata.add(key, value)


if yaml is not None:
    class YamlSidecarIndexer(CollectionSidecarIndexer):
        """YAML collection sidecar indexer"""
        NAME = 'yaml-sidecar'
        ACCEPT = '*'
        PREFIX = ''
        ORDER = Order.LAST

        def run(self, path, metadata, last_cached):
            return self.run_with_store(yaml, path, metadata, last_cached)
