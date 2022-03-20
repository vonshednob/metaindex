# Changelog

This file contains the changes made between released versions.

The format is based on [Keep a changelog](https://keepachangelog.com/) and the versioning tries to follow
[Semantic Versioning](https://semver.org).

## 1.1.0
### Changed
- Creating a `Configuration` instance will start with the configuration defaults
- Some properties moved from ``CacheBase`` to ``Configuration``
- The exiv/image indexer expands values that are lists or dictionaries

### Added
- `final` directive for rule based indexer

### Fixed
- Rule based indexer was a bit broken
- Epub indexer follows the standard to determine the root OPF file(s)
- Addons were not able to use user-installed system packages


## 1.0.1
### Fixed
- The SQL backend stored the humanized value instead of the raw value


## 1.0.0
### Changed
- Dropped `multidict` dependency
- Introduction of `shared.CacheEntry` (instead of a named tuple)
- ``IndexerBase`` API changed

### Added
- Support for humanizers
- ABC notation metadata indexing


## 0.8.0
### Added
- `bulk_rename` operation in `MemoryCache`.
- Implemented `forget` in all caches

### Fixed
- When querying all sidecar files for a file, metaindex would return the file itself, when asking this for a sidecar file (odd scenario, still bad)


## 0.7.1
### Fixed
- `find_all_sidecar_files` would not return *all* sidecar files (ignoring those that are not writable)
- `General.ignore-dirs`, as documented, is now actually considered

### Changed
- Added a few more files and directories to `ignore-dirs` and `ignore-files`
- Fixed the unit tests on file collection


## 0.7.0
### Added
- Function to insert a whole set of new files in the MemoryCache

## 0.6.0
### Added
- Function to iterate through all sidecar files of a file
- Function to rename entries in the database
- `stores.as_collection` to ease the pain when writing collection metadata sidecars

### Changed
- The filename is no longer stored as a separate metadata tag in the database

## 0.5.1
### Fixed
- Collection metadata files could be missed in some cases

## 0.5.0
### Added
- `ThreadedCache` and `MemoryCache` both support the `keys` function, too

### Fixed
- `MemoryCache`'s refresh function would forget the refreshed files
- Various issues where MemoryCache's API would not be quite the same as
  Cache's API.

## 0.4.0
### Added
- MemoryCache for fast queries in multi-threaded applications
- `Query.matches` to run a query against metadata and see if the query
  matches

## 0.3.0
### Added
- ThreadedCache for use of the cache in multi-threaded applications

### Changed
- Major refactoring of the cache.refresh routine
- Sidecar files are now handled via indexers (running last in order)
- Logging is no longer done through the default logger

## 0.2.0
### Added
- Indexer that applies rules to the fulltext of a document to extract meta data
- OCR support
- YAML style metadata files are supported
- Indexer addons

### Changed
- API for `Indexer` changed slightly
- `stores.get`, `stores.get_for_collection` accept byte streams, too

### Removed
- `add`, `remove`, and `edit` commandline parameters are gone. Use
  metaindexmanager for these functions instead


## 0.1.0
- Initial release

