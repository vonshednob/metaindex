"""CacheEntry API test cases"""
import unittest
import datetime
from pathlib import Path

from metaindex import CacheEntry
from metaindex.shared import MetadataValue


class TestCacheEntry(unittest.TestCase):
    def test_update(self):
        entry = CacheEntry(Path('a'),
                           [('tags', 'foo'),
                            ('title', 'bar')])
        other = CacheEntry(Path('b'),
                           [('tags', 'blah'),
                            ('size', 42)])

        entry.update(other)

        self.assertEqual(len(entry), 4)


    def test_contains_key(self):
        entry = CacheEntry(Path('a'),
                           [('tag', 'foo'),
                            ('title', 'bar')])
        self.assertFalse('type' in entry)
        self.assertTrue('tag' in entry)
        self.assertTrue('title' in entry)

    def test_contains_key_value(self):
        entry = CacheEntry(Path('a'),
                           [('tag', 'foo'),
                            ('title', 'bar')])
        self.assertFalse(('tag', 'bar') in entry)
        self.assertTrue(('tag', 'foo') in entry)
        self.assertTrue(('title', 'bar') in entry)

    def test_contains_key_humanized(self):
        entry = CacheEntry(Path('a'),
                           [('tag', MetadataValue('3.14', 'pi')),
                            ('title', MetadataValue('raw'))])
        self.assertTrue(('tag', MetadataValue('3.14')) in entry)
        self.assertTrue(('title', 'raw') in entry)
        self.assertFalse(('tag', MetadataValue('3.15', 'pi')) in entry)
        self.assertTrue(('tag', MetadataValue('3.14', 'pi')) in entry)
        self.assertFalse(('tag', 'pi') in entry)
        self.assertTrue(('tag', '3.14') in entry)

    def test_add_last_modified(self):
        entry = CacheEntry(Path('a'),
                           [('tags', 'foo'),
                            ('title', 'bar')])
        now = datetime.datetime.now()

        self.assertEqual(entry['last_modified'], [datetime.datetime.min])

        entry.add('last_modified', now)

        self.assertEqual(entry['last_modified'], [now])

    def test_update_last_modified(self):
        entry = CacheEntry(Path('a'),
                           [('tags', 'foo'),
                            ('title', 'bar')])
        now = datetime.datetime.now()
        other = CacheEntry(Path('a'),
                           [],
                           now)

        self.assertEqual(entry['last_modified'], [datetime.datetime.min])
        entry.update(other)
        self.assertEqual(entry['last_modified'], [now])

    def test_no_update_last_modified(self):
        now = datetime.datetime.now()
        entry = CacheEntry(Path('a'),
                           [('tags', 'foo'),
                            ('title', 'bar')],
                           now)
        other = CacheEntry(Path('a'),
                           [])

        self.assertEqual(entry['last_modified'], [now])
        entry.update(other)
        self.assertEqual(entry['last_modified'], [now])
