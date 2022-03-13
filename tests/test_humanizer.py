import configparser
import unittest
import datetime
from pathlib import Path

from metaindex import CacheEntry
from metaindex import humanize, register_humanizer
from metaindex.configuration import Configuration, CONF_DEFAULTS
from metaindex.cache import Cache, MemoryCache, CacheBase


@register_humanizer('*.round')
def format_pi(value):
    if isinstance(value, float) and abs(3.14 - value) < 0.001:
        return 'π'
    return None


class TestBasicHumanizers(unittest.TestCase):
    def test_humanize(self):
        self.assertEqual(humanize("who.cares", datetime.datetime(2004, 5, 16, 14, 8, 32)),
                         "2004-05-16 14:08:32")

    def test_humanized_cacheentry(self):
        entry = CacheEntry(Path("a.txt"),
                           [('audio.length', 123.0),
                            ('mp3.track', 3)],
                           datetime.datetime.now())
        self.assertEqual([str(v) for v in entry['audio.length']],
                         ['02:03'])
        self.assertEqual([str(v) for v in entry['mp3.track']],
                         ['3'])

    def test_custom_humanizer(self):
        entry = CacheEntry(Path("b.txt"),
                           [('extra.round', 3.14),
                            ('base.round', 3.15)],
                           datetime.datetime.now())
        self.assertEqual([str(v) for v in entry['extra.round']],
                         ['π'])
        self.assertEqual([str(v) for v in entry['base.round']],
                         ['3.15'])


class TestMemoryQueries(unittest.TestCase):
    def setUp(self):
        baseconfig = configparser.ConfigParser(interpolation=None)
        baseconfig.read_dict(CONF_DEFAULTS)
        baseconfig.set('General', 'cache', ':memory:')
        self.cache = TestableMemoryCache(Configuration(baseconfig))
        self.cache.wait_for_reload()

        self.cache.insert(CacheEntry(Path('a'),
                                     [('extra.round', 3.14),
                                      ('extra.content', 'seven')],
                                     datetime.datetime.now()))
        self.cache.insert(CacheEntry(Path('decoy'),
                                     [('extra.title', "i'm a decoy")],
                                     datetime.datetime.now()))

    def test_find_humanized_value(self):
        results = list(self.cache.find('π'))

        self.assertEqual(len(results), 1)

    def test_find_raw_value(self):
        results = list(self.cache.find('seven'))

        self.assertEqual(len(results), 1)

    def test_find_raw_from_humanized(self):
        results = list(self.cache.find('3.14'))

        self.assertEqual(len(results), 1)

    def test_dont_find_a_value(self):
        results = list(self.cache.find('nope'))

        self.assertEqual(len(results), 0)


class TestSqliteQueries(unittest.TestCase):
    def setUp(self):
        baseconfig = configparser.ConfigParser(interpolation=None)
        baseconfig.read_dict(CONF_DEFAULTS)
        baseconfig.set('General', 'cache', ':memory:')
        self.cache = Cache(Configuration(baseconfig))

        self.cache.insert(CacheEntry(Path('a'),
                                     [('extra.round', 3.14),
                                      ('extra.number', 'seven')],
                                     datetime.datetime.now()))
        self.cache.insert(CacheEntry(Path('decoy'),
                                     [('extra.title', "i'm a decoy")],
                                     datetime.datetime.now()))

    def test_find_humanized_value(self):
        results = list(self.cache.find('π'))

        self.assertEqual(len(results), 1)

    def test_find_raw_value(self):
        results = list(self.cache.find('seven'))

        self.assertEqual(len(results), 1)

    def test_find_raw_from_humanized(self):
        results = list(self.cache.find('3.14'))

        self.assertEqual(len(results), 1)

    def test_dont_find_a_value(self):
        results = list(self.cache.find('nope'))

        self.assertEqual(len(results), 0)

    def test_db_stores_raw_value(self):
        result = list(self.cache.find('π'))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['extra.round'][0].raw_value, 3.14)


class NoCacheBackend(CacheBase):
    """A fake cache backend providing the API but nothing else"""
    def __init__(self, _):
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


class TestableMemoryCache(MemoryCache):
    BACKEND_TYPE = NoCacheBackend
