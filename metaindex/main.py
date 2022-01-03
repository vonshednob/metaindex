import argparse
import sys
import os
import pathlib
import mimetypes
import json
import shutil
import shlex
import subprocess
import tempfile
import importlib

from metaindex import configuration
from metaindex import stores
from metaindex import indexer
from metaindex import indexers
from metaindex import logger
from metaindex.cache import Cache
from metaindex.find import find

try:
    from metaindex.fuse import metaindex_fs
except ImportError:
    metaindex_fs = None


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('-c', '--config',
                        default=None,
                        type=str,
                        help="The configuration file to use. Defaults "
                            f"to {configuration.CONFIGFILE}.")

    parser.add_argument('-l', '--log-level',
                        default='warning',
                        choices=['debug', 'info', 'warning', 'error', 'fatal'],
                        help=f"The level of logging. Defaults to %(default)s.")

    parser.add_argument('--log-file',
                        default=None,
                        type=str,
                        help=f"Write the log to this file instead of stderr.")

    parser.add_argument('--list',
                        action="store_true",
                        default=False,
                        help="List all available file indexers")

    subparsers = parser.add_subparsers(dest='command')

    indexparser = subparsers.add_parser('index')

    indexparser.add_argument('-r', '--recursive',
                             default=False,
                             action='store_true',
                             help='Go through all subdirectories of any paths')

    indexparser.add_argument('-f', '--force',
                             default=False,
                             action="store_true",
                             help="Enforce indexing, even if the files on disk "
                                  "have not changed.")

    indexparser.add_argument('-m', '--flush-missing',
                             default=False,
                             action="store_true",
                             help="Remove files from cache that can no longer be "
                                  "found on disk.")

    indexparser.add_argument('-i', '--index',
                             nargs='*',
                             type=str,
                             help="Path(s) to index. If you provide none, all "
                                  "cached items will be refreshed. If you pass "
                                  "- the files will be read from stdin, one "
                                  "file per line.")

    indexparser.add_argument('-p', '--processes',
                             type=int,
                             default=None,
                             help="Number of indexers to run at the same time. "
                                  "Defaults to the number of CPUs that are available.")

    indexparser.add_argument('-C', '--clear',
                             default=False,
                             action='store_true',
                             help="Remove all entries from the cache")

    findparser = subparsers.add_parser('find')

    findparser.add_argument('-t', '--tags',
                            nargs='*',
                            help="Print these metadata tags per file, if they "
                                 "are set. If you provide -t, but no tags, all "
                                 "will be shown.")

    findparser.add_argument('-f', '--force',
                            default=False,
                            action='store_true',
                            help="When creating symlinks, accept a non-empty "
                                 "directory if it only contains symbolic links.")

    findparser.add_argument('-l', '--link',
                            type=str,
                            default=None,
                            help="Create symbolic links to all files inside "
                                 "the given directory.")

    findparser.add_argument('-k', '--keep',
                            default=False,
                            action='store_true',
                            help="Together with --force: do not delete existing "
                                 "links but extend with the new search result.")

    findparser.add_argument('query',
                            nargs='*',
                            help="The search query. If the query is - it will "
                                 "be read from stdin.")

    if metaindex_fs is not None:
        fsparser = subparsers.add_parser('fs')
        
        fsparser.add_argument('action',
                              choices=('mount', 'unmount', 'umount'),
                              help="The command to control the filesystem")
        fsparser.add_argument('mountpoint',
                              type=str,
                              help="Where to mount the metaindex filesystem.")

    result = parser.parse_args()

    if result.list:
        pass
    elif result.command is None:
        parser.print_help()

    return result


def run():
    args = parse_args()
    logger.setup(level=args.log_level.upper(), filename=args.log_file)

    config = configuration.load(args.config)

    if args.list:
        for name in sorted(indexer._registered_indexers.keys()):
            print(name)
        return 0

    elif args.command == "index":
        cache = Cache(config)
        if args.clear:
            cache.clear()
        if args.flush_missing:
            cache.cleanup()

        index = args.index
        if index == ['-']:
            index = [file_ for file_ in sys.stdin.read().split("\n") if len(file_) > 0]

        elif index == []:
            index = None

        if args.force:
            cache.expire_metadata(index)

        cache.refresh(index, args.recursive, args.processes)

        return 0

    elif args.command == "find":
        return find(config, args)

    elif args.command == 'fs' and metaindex_fs is not None:
        return metaindex_fs(config, args)

    return -1

