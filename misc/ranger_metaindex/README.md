Integration into ranger
=======================

metaindex can be integrated into the command line file manager
[ranger](https://github.com/ranger/ranger).


Installation
------------

Just copy this `ranger_metaindex` folder into your ranger configuration folder.
It’s usually located at `$HOME/.config/ranger/plugins/` (the plugins folder
might not yet exist).


Linemode
--------

`metaindex_linemode.py` is a linemode for ranger. When used it will show the
title of a file instead of the filename (and fall back to the filename if no
title is given).

To use the linemode, update ranger’s configuration file (usually at
`$HOME/.config/ranger/rc.conf`) to include this line:

    default_linemode metaindex

Or try it in any folder with tagged files by typing `:linemode metaindex`.

This linemode will show fancy icons per file if the
[devicons](https://github.com/alexanderjeurissen/ranger_devicons) linemode is
installed, too.


Commands
--------

Coming soon. Probably.


Caveat
------

ranger_metaindex will use the default configuration file when trying to access
the metaindex cache file! You will have to change that manually in
`linemode_metaindex.py` (see `MetaIndexLinemode.__init__`) if you use a
non-standard location.

