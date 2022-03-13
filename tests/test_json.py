"""Test JSON sidecar functionality"""
import unittest
import tempfile
import json
from pathlib import Path

from metaindex.json import get, get_for_collection, store
from metaindex.shared import IS_RECURSIVE
from metaindex import CacheEntry


class TestJsonSidecars(unittest.TestCase):
    def test_direct_sidecar(self):
        test_blob = """{"title": "test", "tags": ["a", "b"]}"""

        with tempfile.TemporaryDirectory() as tmpdir:
            basepath = Path(tmpdir)
            jsonfile = basepath / "test.json"

            jsonfile.write_text(test_blob)

            entry = get(jsonfile)

        self.assertIn("extra.title", entry)
        self.assertIn("extra.tags", entry)
        self.assertEqual(entry['extra.title'], ['test'])
        self.assertEqual(entry['extra.tags'], ['a', 'b'])

    def test_collection_sidecar(self):
        test_blob = """{"that.txt": {"title": "its a file"},
                        "other.txt": {"tags": ["file"]},
                        "*": {"contributor": "vim"}}"""
        with tempfile.TemporaryDirectory() as tmpdir:
            basepath = Path(tmpdir)
            jsonfile = basepath / "collection.json"
            jsonfile.write_text(test_blob)

            entries = get_for_collection(jsonfile)

        self.assertEqual(len(entries), 3)
        self.assertIn(basepath, entries)
        self.assertIn(basepath / "that.txt", entries)
        self.assertEqual(entries[basepath]['extra.contributor'], ['vim'])

    def test_flat_collection_sidecar(self):
        test_blob = """{"contributor": ["vim", "git"]}"""
        with tempfile.TemporaryDirectory() as tmpdir:
            basepath = Path(tmpdir)
            jsonfile = basepath / "collection.json"
            jsonfile.write_text(test_blob)

            entries = get_for_collection(jsonfile)

        self.assertEqual(len(entries), 1)
        self.assertIn(basepath, entries)
        self.assertEqual(entries[basepath]['extra.contributor'], ['vim', 'git'])

    def test_store_direct(self):
        entry = CacheEntry("that.txt",
                           [('extra.title', 'a title'),
                            ('extra.title', 'subtitle'),
                            ('text.word-count', 400)])
        with tempfile.TemporaryDirectory() as tmpdir:
            basepath = Path(tmpdir)
            jsonfile = basepath / "that.json"

            store(entry, jsonfile)

            self.assertTrue(jsonfile.is_file())
            blob = json.loads(jsonfile.read_text())

        self.assertTrue(isinstance(blob, dict))
        self.assertEqual(len(blob), 1)
        self.assertIn("title", blob)
        self.assertEqual(len(blob['title']), 2)
        self.assertEqual(set(blob['title']),
                         {'a title', 'subtitle'})

    def test_store_collection(self):
        entries = [
            CacheEntry("that.txt",
                       [('extra.title', 'a title'),
                        ('extra.title', 'subtitle'),
                        ('text.word-count', 400)]),
            CacheEntry("this.txt",
                       [('extra.tags', 'test'),
                        ('extra.useless', True)]),
            CacheEntry("",
                       [(IS_RECURSIVE, True),
                        ('extra.subject', 'tagged')])
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            basepath = Path(tmpdir)

            # update the paths
            for entry in entries:
                entry.path = basepath / entry.path

            jsonfile = basepath / "metadata.json"

            store(entries, jsonfile)

            self.assertTrue(jsonfile.is_file())
            blob = json.loads(jsonfile.read_text())

        self.assertTrue(isinstance(blob, dict))
        self.assertEqual(len(blob), 3)
        self.assertIn("**", blob)
        self.assertIn("that.txt", blob)
        self.assertEqual(blob["**"]["subject"], ["tagged"])
