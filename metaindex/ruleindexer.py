import re

import multidict

from metaindex import logger
from metaindex import shared
from metaindex.indexer import registered_indexer, Indexer, Order


class ParseError(RuntimeError): pass


class DuplicateFindError(ParseError): pass


class RegExParseError(ParseError):
    def __init__(self, linenr, exc):
        super().__init__(f"Error in regular expression in line {linenr}: {exc}")


class UnusedFindsError(ParseError):
    def __init__(self, names):
        if len(names) == 1:
            text = f"Find directive '{names[0]}' is never used"
        else:
            text = f"Find directives {', '.join(sorted(names))} are never used"
        super().__init__(text)


class UndefinedFindError(ParseError):
    def __init__(self, attr, name):
        super().__init__(f"Set '{attr}' uses '{name}' which is never defined as 'find'")


class RuleSet:
    @staticmethod
    def parse(text, prefix):
        rules = RuleSet(prefix)
        rule = Rule(prefix)

        for linenr, line in enumerate(text.split("\n")):
            linenr += 1
            line = line.strip()
            if len(line) == 0 or ' ' not in line:
                continue

            if line.startswith('#') or line.startswith(';'):
                continue

            directive, line = line.split(' ', 1)

            if directive == 'match':
                if not rule.is_empty:
                    rule.check()
                    rules.append(rule)
                rule = Rule(prefix)
                rule.parse_conditions(line, linenr)
            elif directive == 'find':
                rule.parse_find(line, linenr)
            elif directive == 'set':
                rule.parse_set(line, linenr)
            else:
                logger.warning(f"Unknown directive '{directive}' in line {linenr}")

        if not rule.is_empty:
            rule.check()
            rules.append(rule)

        return rules

    def __init__(self, prefix):
        self.rules = []
        self.prefix = prefix

    def __getitem__(self, key):
        return self.rules[key]

    def __len__(self):
        return len(self.rules)

    def append(self, value):
        self.rules.append(value)

    def run(self, fulltext, checkmatch=True):
        attrs = multidict.MultiDict()
        for rule in self.rules:
            if checkmatch and not rule.match(fulltext):
                continue
            attrs.extend(rule.run(fulltext))
        return attrs


class Rule:
    @staticmethod
    def parse(text, prefix):
        """Convenience method to parse a textual representation of rules"""
        return RuleSet.parse(text, prefix)

    def __init__(self, prefix):
        self.conditions = []
        self.finds = {}
        self.sets = {}
        self.prefix = prefix

    @property
    def is_empty(self):
        """True if no conditions, nor sets are defined"""
        return len(self.conditions) == 0 and len(self.sets) == 0

    def match(self, fulltext):
        """Return True if all regexs of the match directive match this fulltext"""
        return all([expr.search(fulltext) is not None
                    for expr in self.conditions])

    def run(self, fulltext):
        """Run the find and set rules on fulltext.

        This function will NOT check whether or not match() is actually true.
        
        Returns a dictionary of attributes mapped to a set of values found
        in the fulltext to match.
        """
        attrs = multidict.MultiDict()
        found = {}
        for findname, regex in self.finds.items():
            for match in regex.finditer(fulltext):
                if findname not in attrs:
                    found[findname] = set()
                groups = match.groups()
                if groups is not None:
                    found[findname] = groups[-1]

        for attrname, values in self.sets.items():
            for value in values:
                if isinstance(value, re.Pattern):
                    values = set()
                    for match in value.finditer(fulltext):
                        groups = match.groups()
                        if groups is not None and len(groups) > 0:
                            values.add(groups[-1])
                    value = values
                elif isinstance(value, str):
                    value = {value.format(**found),}

                if len(value) == 0:
                    continue

                for v in value:
                    attrs.add(self.prefix + attrname, v)

        return attrs

    def check(self):
        """Check that all 'find's are used and no 'set' uses an undefined 'find'"""
        findkeys = set(self.finds.keys())
        for findname in self.finds.keys():
            for name in self.sets.keys():
                for value in self.sets[name]:
                    if isinstance(value, str):
                        if '{'+findname+'}' in value and findname in findkeys:
                            findkeys.remove(findname)
        for name in self.sets.keys():
            for value in self.sets[name]:
                if isinstance(value, str):
                    try:
                        expanded = value.format(**self.finds)
                    except KeyError as exc:
                        raise UndefinedFindError(name, exc)

        if len(findkeys) > 0:
            raise UnusedFindsError(list(findkeys))

    def parse_conditions(self, text, linenr):
        self.conditions = []

        tokens = self.tokenize(text)
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]

            if token == 'and':
                # "and" is only decorational for now
                idx += 1
            else:
                lead = token[0]
                tokens[idx] = token[1:]
                regexparts = []
                flags = 0
                # merge the tokens that belong to the same regex
                while True:
                    token = tokens[idx]
                    if token.endswith(lead) or token.endswith(lead + 'i'):
                        if token.endswith('i'):
                            flags = re.IGNORECASE
                            token = token[:-1]
                        regexparts.append(token[:-1])
                        break
                    if idx + 1 >= len(tokens):
                        raise RegExParseError(linenr, f"Unexpected end of regular expression")
                    regexparts.append(token)
                    idx += 1
                try:
                    regex = re.compile(' '.join(regexparts), flags)
                except re.error as exc:
                    raise RegExParseError(linenr, exc)
                self.conditions.append(regex)
                idx += 1

    def parse_find(self, text, linenr):
        if ' ' not in text:
            logger.warning(f"Incomplete 'find' directive in {linenr}")
            return
        name, regex = text.split(' ', 1)

        if name in self.finds:
            raise DuplicateFindError(f"Duplicate name '{name}' in line {linenr}")
        if not regex.startswith('/') or (not regex.endswith('/') and not regex.endswith('/i')):
            raise RegExParseError(linenr, "Expression is not surrounded by '/'")

        flags = 0
        if regex.endswith('i'):
            flags = re.IGNORECASE
            regex = regex[:-1]

        try:
            regex = re.compile(regex[1:-1], flags)
        except re.error as exc:
            raise RegExParseError(linenr, exc)
        self.finds[name] = regex

    def parse_set(self, text, linenr):
        if ' ' not in text:
            logger.warning(f"Incomplete 'set' directive in {linenr}")
            return

        name, value = text.split(' ', 1)
        if name.startswith('"'):
            if '"' not in value:
                raise ParseError(f"Missing \" in set on line {linenr}")
            trailing, value = value.split('"', 1)
            name = name[1:] + " " + trailing
        value = value.strip()

        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith('/') and (value.endswith('/') or value.endswith('/i')):
            flags = 0
            if value.endswith('i'):
                value = value[:-1]
                flags = re.IGNORECASE

            try:
                value = re.compile(value[1:-1], flags)
            except re.error as exc:
                raise RegExParseError(linenr, exc)

        if name not in self.sets:
            self.sets[name] = set()
        self.sets[name].add(value)

    @staticmethod
    def tokenize(text):
        token = ''
        tokens = []
        escaped = False

        for char in text:
            if escaped:
                token += char
                escaped = False
            elif char == '\\':
                escaped = True
            elif char in " \t\n":
                tokens.append(token)
                token = ''
            else:
                token += char
        tokens.append(token)

        return [token for token in tokens if len(token) > 0]


@registered_indexer
class RuleIndexer(Indexer):
    NAME = 'rule-based'
    PREFIX = 'rules'
    ORDER = Order.LAST
    ACCEPT = '*'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.rules = []
        self.rules_changed = None
        section = 'Indexer:' + self.NAME
        if section in self.config:
            for entry in self.config[section]:
                fullpath = self.config.path(section, entry)
                if fullpath is None or not fullpath.is_file():
                    continue
                if self.rules_changed is None:
                    self.rules_changed = shared.get_last_modified(fullpath)
                else:
                    self.rules_changed = max(self.rules_changed, shared.get_last_modified(fullpath))
                ruleset = Rule.parse(fullpath.read_text(), self.PREFIX + '.')
                self.rules += ruleset

    def run(self, path, info, last_cached):
        # various reasons to not continue:
        # no rules defined
        # or no fulltext in the previously obtained metadata
        if len(self.rules) == 0:
            logger.debug("... skipping: no rules")
            return False, {}

        # TODO: if there have been rules before, but no more, maybe it should
        # be considered a successful run, but clear out the previous finds

        fulltext = ''
        # find fulltext first in the most recent metadata, and as fallback then in the cached
        fields = [info]
        if last_cached is not None:
            fields += [last_cached.metadata]

        for field in fields:
            fulltext = shared.get_all_fulltext(field)
            if len(fulltext) > 0:
                break

        if len(fulltext) == 0:
            logger.debug("... skipping: no fulltext")
            return False, {}

        # if the rules file changed since the cache entry was created
        # and the file has not changed since the cache entry was created
        # we don't have to continue
        if self.cached_dt(last_cached) > self.rules_changed and \
           not self.changed_since_cached(path, last_cached):
            logger.debug("... skipping: no change to rules or file")
            return self.reuse_cached(last_cached)
    
        extra = multidict.MultiDict()

        for rule in self.rules:
            if rule.match(fulltext):
                extra.extend(rule.run(fulltext))
                break
        
        return len(extra) > 0, extra

