# Changelog

This file contains the changes made between released versions.

The format is based on [Keep a changelog](https://keepachangelog.com/) and the versioning tries to follow
[Semantic Versioning](https://semver.org).

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

