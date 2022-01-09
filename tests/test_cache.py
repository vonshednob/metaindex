"""Test suite for the Cache API"""
import os
import configparser
import datetime
import unittest
import pathlib

from multidict import MultiDict

from metaindex import logger
from metaindex import cache
from metaindex import configuration
from metaindex import indexers as _


THIS = pathlib.Path(__file__).resolve()
HERE = pathlib.Path(__file__).parent


def make_entry(path, metadata, last_modified=None):
    """Create a new entry from the given path, metadata, and the optional last_modified

    ``metadata`` is a sequence of (key, value) tuples.

    If ``last_modified`` is not provided, datetime.datetime.now will be used instead.
    """
    return cache.Cache.Entry(pathlib.Path(path).resolve(),
                             MultiDict(metadata),
                             last_modified or datetime.datetime.now())


class NoCacheBackend:
    """A fake cache backend providing the API but nothing else"""
    def __init__(self):
        self.is_started = True

    def find(self, *_):
        return []

    def get(self, *_):
        return []

    def rename(self, *_):
        pass

    def insert(self, *_):
        pass

    def refresh(self, *_):
        pass

    def last_modified(self):
        return datetime.datetime.min

    def keys(self, *_):
        return set()

    def start(self):
        pass

    def quit(self):
        pass


class TestCacheBase(unittest.TestCase):
    """Base class for all test cases"""

    def setUp(self):
        conf = configparser.ConfigParser(interpolation=None)
        conf.read_dict(configuration.CONF_DEFAULTS)

        general = conf[configuration.SECTION_GENERAL]
        general[configuration.CONFIG_CACHE] = ':memory:'
        general[configuration.CONFIG_INDEX_UNKNOWN] = 'yes'

        logger.setup('ERROR')

        self.config = configuration.Configuration(conf)
        self.cache = self.cache_setup()

        if self.cache is None:
            return

        self.cache.insert(HERE / 'a',
                          MultiDict([('identifier', 'a')]),
                          datetime.datetime.now())
        self.cache.insert(THIS,
                          MultiDict([('title', 'Test case')]),
                          None)

    def cache_setup(self):
        self.skipTest("Base class")
        return None

    def test_count_all_entries(self):
        self.assertEqual(len(self.cache.find('')), 2)

    def test_get(self):
        result = self.cache.get(HERE / 'a')
        self.assertEqual(len(result), 1)

    def test_file_rename(self):
        """Rename a single file in the database"""
        self.cache.rename(HERE / 'a', HERE / 'b')
        result = self.cache.get(HERE / 'b')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, HERE / 'b')

    def test_keys(self):
        results = self.cache.keys()

        self.assertEqual(len(results), 2)
        self.assertEqual(set(results), {'identifier', 'title'})

    def test_dir_rename(self):
        """Rename the ../metaindex directory to ../new_name
        and check that the database renames all found entries correctly
        """
        here_changed = pathlib.Path(os.sep.join(HERE.parts[:-2] +
                                                ('new_name', HERE.parts[-1]))).resolve()
        self.cache.rename(HERE, here_changed)
        result = self.cache.find('')

        self.assertEqual(len(result), 2)
        self.assertTrue(all(entry.path.is_relative_to(here_changed)
                            for entry in result))


class TestOnlyKnown(TestCacheBase):
    """Test to index only known file types"""

    def cache_setup(self):
        self.config.set(configuration.SECTION_GENERAL,
                        configuration.CONFIG_INDEX_UNKNOWN,
                        'no')
        return cache.Cache(self.config)

    def test_refresh(self):
        self.cache.refresh(HERE)
        self.assertEqual(len(self.cache.find('')), 2)


class TestCache(TestCacheBase):
    """The tests for the base Cache"""

    def cache_setup(self):
        return cache.Cache(self.config)

    def test_refresh(self):
        self.cache.refresh(HERE)
        result = self.cache.get(THIS)
        self.assertEqual(len(result), 1)
        self.assertIn('mimetype', result[0].metadata)


class TestMemoryCache(TestCacheBase):
    """The tests for the MemoryCache"""

    def cache_setup(self):
        memcache = cache.MemoryCache(self.config)
        memcache.tcache = NoCacheBackend()
        memcache.start()
        memcache.wait_for_reload()
        return memcache

    def tearDown(self):
        self.cache.quit()
