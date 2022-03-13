import unittest
import configparser
import datetime
from pathlib import Path

from metaindex.configuration import Configuration, CONF_DEFAULTS
from metaindex.query import tokenize, Query
from metaindex.cache import Cache, MemoryCache, CacheBase
from metaindex.shared import CacheEntry


class TestTokenizer(unittest.TestCase):
    """Test suite for Query's tokenization function"""

    def test_simple_words(self):
        """Test the tokenization of terms"""
        text = '\\(there\\) once "was a"  \\"lady (in riga )'
        expected = ['(there)', 'once', 'was a', '\"lady', '(in', 'riga', ')']
        self.assertEqual(expected, tokenize(text))


class TestQueryParser(unittest.TestCase):
    """Test suite for Query.parse"""

    def test_simple(self):
        """Test for simple splitting into terms"""
        text = "look, albatross"
        query = Query.parse(text)

        self.assertEqual(2, len(query.root.terms))

    def test_keyvalue(self):
        """Basic parsing of key:value terms"""
        text = "title:albatross"
        query = Query.parse(text)

        self.assertEqual(query.root.terms[0].key, "title")
        self.assertEqual(query.root.terms[0].regex, "albatross")


class MatchingQueryBaseClass(unittest.TestCase):
    """Test suite for the Query.matches function"""
    def setUp(self):
        baseconfig = configparser.ConfigParser(interpolation=None)
        baseconfig.read_dict(CONF_DEFAULTS)
        baseconfig.set('General', 'cache', ':memory:')
        now = datetime.datetime.now()
        self.cache = self.setup_cache(baseconfig)
        if self.cache is None:
            return

        # fill with testable entries here
        self.cache.insert(CacheEntry('a',
                            {'extra.comment': ['something'],
                             'rules.tags': ['file'],
                             'extra.tags': ['data'],
                             'rules.title': ['Not a picture at all!'],
                            }, now))
        self.cache.insert(CacheEntry('b',
                            {'mimetype': ['image/png'],
                             'extra.title': ['Test picture', 'Not actually there'],
                            }, now))
        self.cache.insert(CacheEntry('c',
                            {'opf.title': ['A book with a title'],
                            }, now))

    def setup_cache(self, baseconfig):
        self.skipTest('Base class')
        return None

    def test_find_all(self):
        """Just find all entries with a blank query"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find(''))

        self.assertEqual(len(result), 3)

    def test_word(self):
        """Test for simple word queries"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('some'))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, Path('a'))

    def test_find_no_word(self):
        """Test that nothing is found when searching for a word that appears nowhere"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('nada'))

        self.assertEqual(len(result), 0)

    def test_find_regex(self):
        """Check for a simple regex match"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('s.+e[tT]hing'))

        self.assertEqual(len(result), 1)

    def test_find_no_regex(self):
        """Check for failing regex matches"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('si.+e[tT]hing'))

        self.assertEqual(len(result), 0)

    def test_simple_keyvalue(self):
        """A simple key value test case"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('rules.tags:file'))

        self.assertEqual(len(result), 1)

    def test_regex_keyvalue(self):
        """The value may be a regex, so test for it, too"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('extra.tags:d..a'))

        self.assertEqual(len(result), 1)

    def test_key_exists(self):
        """Test for the key existence operator"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('mimetype?'))

        self.assertEqual(len(result), 1)

    def test_synonym(self):
        """Test that synonyms are considered when doing key/value matches"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('title:picture'))

        self.assertEqual(len(result), 2)
        self.assertEqual(set(entry.path for entry in result), {Path('a'), Path('b')})

    def test_synonym_exists(self):
        """Test the existence checks for synonyms"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('tags?'))

        self.assertEqual(len(result), 1)

    def test_query_mimetype(self):
        """Test for querying by mimetype"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('mimetype:image/'))

        self.assertEqual(len(result), 1)

    def test_not_mimetype(self):
        """Test the inverted test for a property"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('not:mimetype:image/'))

        self.assertEqual(len(result), 2)

    def test_has_no_key(self):
        """Test that a key is not present"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('not:opf.title?'))

        self.assertEqual(len(result), 2)

    def test_more_conditions(self):
        """Test an actual sequence of conditions"""
        assert isinstance(self.cache, CacheBase)
        result = list(self.cache.find('title? not:mimetype?'))

        self.assertEqual(len(result), 2)
        self.assertEqual({r.path for r in result},
                         {Path('a'), Path('c')})


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


class TestMatchingQueryOnMemoryCache(MatchingQueryBaseClass):
    def setup_cache(self, baseconfig):
        cache = TestableMemoryCache(Configuration(baseconfig))
        cache.wait_for_reload()
        assert len(cache.entries_by_path) == 0
        return cache

class TestMatchingQueryOnSqlCache(MatchingQueryBaseClass):
    def setup_cache(self, baseconfig):
        cache = Cache(Configuration(baseconfig))
        return cache
