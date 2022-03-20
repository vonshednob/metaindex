"""How to index some files using metaindex"""
import sys
from pathlib import Path

import metaindex


def index_files(files):
    """Just run the indexer on these files"""
    # we need at least the basic configuration
    config = metaindex.Configuration()

    # if you actually want to also load the user's config file/preferences,
    # do this instead:
    #   import metaindex.configuration
    #   config = metaindex.configuration.load()

    # find and load all additional humanizers and indexers
    config.load_addons()

    # loads the extra mimetypes from the configuration, if there are any
    config.load_mimetypes()

    results = metaindex.index_files(files, config)
    # index_files returns a list of each one IndexerResult per file
    assert all(isinstance(r, metaindex.IndexerResult) for r in results)

    # return the CacheEntry per IndexerResult (i.e. per file), but only if
    # that file's index run was successful
    return [result.info
            for result in results
            if result.success]


if __name__ == '__main__':
    # run the indexer on all files that were provided as commandline parameters
    userfiles = [Path(p) for p in sys.argv[1:]]
    print(index_files(userfiles))
