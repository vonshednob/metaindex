# Changelog

This file contains the changes made between released versions.

The format is based on [Keep a changelog](https://keepachangelog.com/) and the versioning tries to follow
[Semantic Versioning](https://semver.org).

## Not released yet
### Changed
- Use [PyPDF](https://pypi.org/project/pypdf/) instead of pdfminer for PDF indexing
- `OCRFacility.run` can be given a language to work with to prevent guessing
- Collection and side-car files are processed first now, instead of last to allow defining languages
- The optional `callback`, that can be used to inspect the status of the indexer, sees the un-`reduce`d `CacheEntry`. Makes it more useful for testing rule indexers and such.
- Timestamp-like occurrences (like `filetags.date`) have been split into `.date` and `.time`. You can search each respectively with `date:` or `time:`

### Added
- `OCRFacility` can be queried for supported languages
- Another level of verbosity when indexing: `-vvvvv`, prints also all found metadata

### Fixed
- Server could crash when read-only connections were made and the cache directory doesn’t exist yet
- Some code duplication removed for writing YAML and JSON sidecar files


## 2.1.1
### Changed
- Server will return results even if the match score is very low

### Fixed
- The rule based indexer will be more resilient against non-matching `find` directives

## 2.1.0
### Added
- Configuration option for server, `index-new-tags`


## 2.0.0
### Changed
- Drastic refactoring, back-end changed to xapian

## 1.5.0
### Changed
- Updated the ABC indexer to match the specs of version 2.1 better


## 1.4.0
### Changed
- `Cache.cleanup` accepts a list of paths to limit the clean-up to
- `metaindex index -m` expects a list of paths to clean up.

### Added
- Support for metadata from GPX files
- Support for metadata from OpenDocument files (`odt`, `ods`, etc.)
- Support for office open XML files (`docx`, etc.)


## 1.3.0
### Changed
- `CacheEntry.__contains__` allows to check for presence of a tag with a particular value
- When logging to a file, metaindex will now rotate the log file at a 4 KB size limit
- `resolve_sidecar_for` can ignore existing collection sidecars


## 1.2.0
### Added
- Indexer for HTML files (metadata)
- Indexer for ComicBook files using ComicInfo.xml (cbz, cbt, cbr if `python-unrar` is installed)
- File size humanizer
- Support special value `*` in synonym definitions and `ignore-tags` to expand the existing definition

### Fixed
- The JSON sidecar writer could break when encountering unexpected metadata types (like datetime)

### Changed
- Changed default synonym 'tags' to 'tag'


## 1.1.1
### Fixed
- Audio indexer did not expect that mutagen can return lists of values per key


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

