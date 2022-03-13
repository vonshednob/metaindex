Options
=======

General parameters are:

  ``-c configuration file``
    Use this configuration file instead of the one from the default
    location.

  ``-h``
    Show the help.

  ``-l loglevel``
    Set the level of details shown in logging. Your options are ``fatal``,
    ``error``, ``warning``, ``info``, and ``debug``. Defaults to ``warning``.

  ``--list``
    List all available indexers and exit.

metaindex operates in one of the modes ``index`` or ``find``.

If you want to try the experimental filesystem mode, there is also ``fs``.


Find
----

This is the main operation used to search for files::

  metaindex find [-l directory] [-f [-k]] [-t [tags]] [--] [search queries]

The options to this command are

  ``-t [tags]``
    Metadata tags that you wish to see per found file.

  ``-l directory``
    If this option is provided, metaindex will create this directory (or use
    the existing directory only if it is empty) and create a symbolic link
    to all files that matches this search.

  ``-f``
    Enforce the use of ``-l``’s ``directory``, even if it is not empty.
    Still, metaindex will only work with that directory if it contains only
    symbolic links (e.g. a previous search result)!
    If ``-f`` is provided, all symbolic links in ``directory`` will be
    deleted and the links of this search will be put in place.

  ``-k``
    When you use ``-l`` and ``-f``, ``-k`` will keep all existing links in
    the search directory. That means you can accumulate search results in
    one directory.

  ``search queries``
    The terms to search for. If left empty, all files will be found. See
    below in section `Search Query Syntax`_ for the details on search
    queries.
    If the search query is only given as ``-``, metaindex will read the search
    query from stdin.


Index
-----

This is the operation to index files and store that information in the
cache::

  metaindex index [-C] [-r] [-p processes] [-i [paths]]

The options to this command are

  ``-C``
    Clear the cache. If combined with other options, the flushing of the
    cache will happen first.

  ``-m``
    Remove missing files. When a file, that's in the index, can not be
    found on disk anymore, it will be removed when this option is enabled.
    By default this option is disabled.

  ``-i [paths]``
    Run the indexer on these paths. If no paths are provided, all paths in
    the cache are revisited and checked for changes.
    If ``paths`` is ``-``, the list of files will be read from stdin, one
    file per line.

  ``-p processes``
    By default metaindex will run as many indexer processes in parallel as
    CPUs are available on the computer. This parameter allows you to define
    how many indexers may be run at the same time.

  ``-r``
    Run the indexer recursively. That means to visit all files in all
    subdirectories of the paths in the ``-i`` parameter.


Filesystem (fs)
---------------

On Linux you can try the experimental feature of mounting a FuseFS that
will give you a structured access to your files through their metadata::

  metaindex fs [command] [mount point]

The only supported command so far is ``mount``.

It is very experimental and not very useful, but at the same time will not
break any of your files as it only provides a read-only view on your tagged
files.

