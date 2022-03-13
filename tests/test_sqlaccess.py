"""Test cases for SqlAccess"""
import datetime
import unittest
from pathlib import Path

from metaindex import CacheEntry
from metaindex import Query
from metaindex.sql import SqlAccess, MIN_DATE, str_to_dt


class TestBaseCases(unittest.TestCase):
    def setUp(self):
        self.db = SqlAccess(":memory:")
        self.now = datetime.datetime.now().replace(microsecond=0)
        self.earlier = self.now - datetime.timedelta(minutes=4)
        self.min_date = str_to_dt(MIN_DATE)

    def test_files(self):
        self.test_insert()

        files = self.db.files()

        self.assertEqual({Path('/usr/share/doc/root.md'),
                          Path('/tmp/a.txt'),
                          Path('/tmp/b.txt')},
                         set(files))

    def test_last_modified(self):
        self.test_insert()

        last_modified = self.db.last_modified()

        self.assertEqual(last_modified, self.earlier)

    def test_keys(self):
        self.test_insert()

        keys = self.db.keys()

        self.assertEqual({'extra.tag', 'extra.title',
                          'extra.author',
                          'filename', 'size', 'last_modified'},
                         keys)

    def test_find(self):
        self.test_insert()
        result = self.db.find(Query())

        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(e, CacheEntry) for e in result))

        for entry in result:
            if entry.path == Path('/tmp/a.txt'):
                self.assertIn('extra.tag', entry)
                self.assertEqual(entry['extra.tag'], ['test'])
            elif entry.path == Path('/tmp/b.txt'):
                self.assertIn('extra.title', entry)
                self.assertEqual(set(entry['extra.title']),
                                 set(['tree', 'parrot']))
            elif entry.path == Path('/usr/share/doc/root.md'):
                self.assertIn('size', entry)
            else:
                self.fail(f"{entry.path} should not be here")

    def test_get(self):
        self.test_insert()

        results = self.db.get([Path('/usr/share/doc/root.md'),
                               Path('/tmp/b.txt'),
                               Path('/no/such/file.txt')])
        self.assertEqual({Path('/usr/share/doc/root.md'),
                          Path('/tmp/b.txt')},
                         {entry.path for entry in results})

    def test_insert(self):
        result = self.db.insert([
                     CacheEntry(Path('/tmp/a.txt'),
                                [('extra.tag', 'test'),
                                 ('extra.title', 'nothing really')],
                                self.earlier),
                     CacheEntry(Path('/tmp/b.txt'),
                                [('extra.title', 'parrot'),
                                 ('extra.title', 'tree'),
                                 ('extra.author', 'Caithlynn')],
                                self.now - datetime.timedelta(hours=3)),
                     CacheEntry(Path('/usr/share/doc/root.md'),
                                [('extra.title', 'Description of file hierarchy concept'),
                                 ('size', 42)],
                                self.now - datetime.timedelta(days=14))])
        self.assertEqual(result, 3)

    def test_flush(self):
        self.test_insert()

        self.db.flush()

        self.assertEqual(len(self.db.find(Query())), 0)

    def test_purge(self):
        self.test_insert()

        self.db.purge([Path('/tmp/a.txt'), Path('/usr/share/doc/root.md')])

        result = self.db.find(Query())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, Path('/tmp/b.txt'))

    def test_expire_metadata(self):
        self.test_insert()

        self.db.expire_metadata([Path('/usr/share/doc/root.md'),
                                 Path('/tmp/b.txt')])

        results = {entry.path: entry.last_modified
                   for entry in self.db.find(Query())}
        expected = {Path('/tmp/a.txt'): self.earlier,
                    Path('/usr/share/doc/root.md'): self.min_date,
                    Path('/tmp/b.txt'): self.min_date}

        self.assertEqual(results, expected)

    def test_rename_file(self):
        self.test_insert()

        self.db.rename_file(Path('/tmp/a.txt'), Path('/tmp/new.txt'))

        results = self.db.find(Query())

        self.assertEqual({Path('/usr/share/doc/root.md'),
                          Path('/tmp/b.txt'),
                          Path('/tmp/new.txt')},
                         {entry.path for entry in results})

    def test_rename_dir(self):
        self.test_insert()

        self.db.rename_dir(Path('/tmp'), Path('/var/other'))

        results = self.db.find(Query())

        self.assertEqual({Path('/usr/share/doc/root.md'),
                          Path('/var/other/b.txt'),
                          Path('/var/other/a.txt')},
                         {entry.path for entry in results})
