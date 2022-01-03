import unittest
import configparser
import datetime

from multidict import MultiDict

from metaindex.configuration import Configuration, CONF_DEFAULTS
from metaindex.query import tokenize, Query
from metaindex.cache import Cache, MemoryCache


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


class TestMatchingQuery(unittest.TestCase):
    """Test suite for the Query.matches function"""
    def setUp(self):
        baseconfig = configparser.ConfigParser(interpolation=None)
        baseconfig.read_dict(CONF_DEFAULTS)
        baseconfig.set('General', 'cache', 'memory:///')
        now = datetime.datetime.now()
        self.cache = MemoryCache(Configuration(baseconfig))
        self.cache.wait_for_reload()
        assert len(self.cache.entries_by_path) == 0

        # fill with testable entries here
        self.cache.entries_by_path = {
            'a': Cache.Entry('a',
                             MultiDict([
                                 ('extra.comment', 'something'),
                                 ('rules.tags', 'file'),
                                 ('extra.tags', 'data'),
                                 ('rules.title', 'Not a picture at all!'),
                                 ]), now),
            'b': Cache.Entry('b',
                             MultiDict([
                                 ('mimetype', 'image/png'),
                                 ('extra.title', 'Test picture'),
                                 ('extra.title', 'Not actually there'),
                                 ]), now),
            'c': Cache.Entry('c',
                             MultiDict([
                                 ('opf.title', 'A book with a title'),
                                 ]), now),
        }

    def test_find_all(self):
        """Just find all entries with a blank query"""
        result = list(self.cache.find(''))

        self.assertEqual(len(result), len(self.cache.entries_by_path))

    def test_word(self):
        """Test for simple word queries"""
        result = list(self.cache.find('some'))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, 'a')

    def test_find_no_word(self):
        """Test that nothing is found when searching for a word that appears nowhere"""
        result = list(self.cache.find('nada'))

        self.assertEqual(len(result), 0)

    def test_find_regex(self):
        """Check for a simple regex match"""
        result = list(self.cache.find('s.+e[tT]hing'))

        self.assertEqual(len(result), 1)

    def test_find_no_regex(self):
        """Check for failing regex matches"""
        result = list(self.cache.find('si.+e[tT]hing'))

        self.assertEqual(len(result), 0)

    def test_simple_keyvalue(self):
        """A simple key value test case"""
        result = list(self.cache.find('rules.tags:file'))

        self.assertEqual(len(result), 1)

    def test_regex_keyvalue(self):
        """The value may be a regex, so test for it, too"""
        result = list(self.cache.find('extra.tags:d..a'))

        self.assertEqual(len(result), 1)

    def test_key_exists(self):
        """Test for the key existence operator"""
        result = list(self.cache.find('mimetype?'))

        self.assertEqual(len(result), 1)

    def test_synonym(self):
        """Test that synonyms are considered when doing key/value matches"""
        result = list(self.cache.find('title:picture'))

        self.assertEqual(len(result), 2)
        self.assertEqual(set(entry.path for entry in result), {'a', 'b'})

    def test_synonym_exists(self):
        """Test the existence checks for synonyms"""
        result = list(self.cache.find('tags?'))

        self.assertEqual(len(result), 1)
