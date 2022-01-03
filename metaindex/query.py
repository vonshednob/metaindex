import re

from metaindex import sql
from metaindex import logger


class Query:
    """Represents a search query to obtain entries from the cache"""
    def __init__(self, root=None):
        self.root = root or Sequence()

    @classmethod
    def parse(cls, text, synonyms=None):
        """Accepts a human-written search term and builds a Query from it"""
        tokens = tokenize(text)
        sequence = Sequence()
        join = Term.AND

        for token in tokens:
            if token.lower() == 'and':
                join = Term.AND
                continue
            if token.lower() == 'or':
                join = Term.OR
                continue

            inverted = False
            if token.startswith('-') or token.startswith('not:'):
                inverted = True
                if token.startswith('-'):
                    token = token[1:]
                else:
                    token = token[4:]

            operator = None
            positions = [token.find(':'),
                         token.find('<'),
                         token.find('>')]
            operators = [op for op in sorted(positions) if op >= 0]

            if len(operators) > 0:
                operator = token[operators[0]]

            if operator is not None:
                key, value = token.split(operator, 1)
                if synonyms is not None:
                    key = synonyms.get(key, key)

                if operator == ':':
                    sequence.add(KeyValueTerm(key, value, join, inverted))
                    join = Term.AND

            elif token.endswith('?'):
                key = token[:-1]
                if synonyms is not None:
                    key = synonyms.get(key, key)
                sequence.add(KeyExistsTerm(key, join, inverted))
                join = Term.AND

            else:
                sequence.add(RegexTerm(token, join, inverted))
                join = Term.AND

        return Query(sequence)

    def __len__(self):
        return len(self.root.terms)

    def matches(self, metadata):
        """Given a multidict of metadata, this function tells whether or not the Query matches"""
        return self.root.matches(metadata)

    def as_sql(self):
        """Build an SQLite query

        Returns a tuple (query, args) to be passed to execute of an sqlite database."""

        if len(self.root.terms) > 0:
            expr, args = self.root.as_sql()
        else:
            expr = "select distinct `items`.`id` from `items`"
            args = []

        expr = "with `items` as (select * from `files` left join `metadata` on `files`.`id` = `metadata`.`id`) " \
               + expr

        logger.debug(f"Search with query ''{expr}'' and {args}")

        return (expr, args)


class Term:
    """Generic term"""

    OR = ' union '
    AND = ' intersect '

    def __init__(self, operator=None, inverted=False):
        self.inverted = inverted
        self.operator = operator or Term.AND

    def matches(self, metadata):
        raise NotImplementedError()

    def as_sql(self):
        raise NotImplementedError()


class RegexTerm(Term):
    """A regex"""
    def __init__(self, word, operator, inverted=False):
        super().__init__(operator, inverted)
        self.word = word

    def matches(self, metadata):
        if self.word not in sql.regex_cache:
            sql.regex_cache[self.word] = re.compile(self.word, re.IGNORECASE)
        regex = sql.regex_cache[self.word]
        matches = [regex.search(str(value)) is not None
                   for value in set(metadata.values())]
        if self.inverted:
            return not any(matches)
        return any(matches)

    def as_sql(self):
        if self.word not in sql.regex_cache:
            sql.regex_cache[self.word] = re.compile(self.word, re.IGNORECASE)

        # match against any value and even against the path
        return ("lower(`items`.`value`) REGEXP ?", [self.word])


class KeyValueTerm(Term):
    """This metadata key matches this regex"""
    def __init__(self, key, regex, operator, inverted):
        super().__init__(operator, inverted)
        self.key = key
        self.regex = regex

    def matches(self, metadata):
        if self.regex not in sql.regex_cache:
            sql.regex_cache[self.regex] = re.compile(self.regex, re.IGNORECASE)
        keys = self.key
        if not isinstance(keys, (list, tuple, set)):
            keys = [keys]
        matches = [sql.regex_cache[self.regex].search(value) is not None
                     for value in sum([metadata.getall(key, []) for key in keys], start=[])]
        # TODO - handle AND vs. OR
        if self.inverted:
            return not any(matches)
        return any(matches)

    def as_sql(self):
        if self.regex not in sql.regex_cache:
            sql.regex_cache[self.regex] = re.compile(self.regex, re.IGNORECASE)
        keycheck = " = ?"
        keys = [self.key]

        if isinstance(self.key, list):
            keycheck = " in (" + ", ".join(["?"]*len(self.key)) + ")"
            keys = self.key

        return (f"(`items`.`key` {keycheck} AND `items`.`value` REGEXP ?)", keys + [self.regex])


class KeyExistsTerm(Term):
    """A metadata key of this name exists"""
    def __init__(self, key, operator, inverted=False):
        super().__init__(operator, inverted)
        self.key = key

    def matches(self, metadata):
        keys = self.key
        if not isinstance(keys, (list, set, tuple)):
            keys = [keys]

        result = any(key in metadata for key in keys)

        if self.inverted:
            return not result
        return result

    def as_sql(self):
        keycheck = " = ?"
        keys = self.key
        if not isinstance(keys, (list, set, tuple)):
            keys = [self.key]

        if isinstance(self.key, list):
            keycheck = " in (" + ", ".join(["?"]*len(self.key)) + ")"
            keys = self.key

        return (f"`items`.`key` {keycheck}", keys)


class Sequence(Term):
    """A sequence of query terms.
    A term may be

     - RegexTerm (match *any* value in form of a regex),
     - Key (match all items that have this metadata key; syntax: "key?"),
     - KeyValue (match all items that have this metadata key and their value matches the regex: "key:regex"),
     - KeyEqualValue (match all items that have this metadata key with that value; syntax: "key=value"),
     - KeyLessValue (match all items that have this metadata key and the value is "less"
       than the given value; syntax: "key<value")
     - KeyGreaterValue (match all items that have this metadata key and the value is "greater"
       than the given value; syntax: "key>value")

    Any term may be negated by prepending a "-" or "not:".
    """

    def __init__(self, terms=None):
        super().__init__(None, False)
        self.terms = terms or []

    def add(self, term):
        self.terms.append(term)
        return self

    def matches(self, metadata):
        result = all(term.matches(metadata) for term in self.terms)
        if self.inverted:
            return not result
        return result

    def as_sql(self):
        if len(self.terms) == 0:
            return '', []

        expr = ""
        args = []
        for term in self.terms:
            if len(expr) > 0:
                if term.inverted:
                    expr += "except "
                else:
                    expr += term.operator
            subexpr, subargs = term.as_sql()
            expr += " select distinct `items`.`id` from `items` where " + subexpr
            args += subargs

        return (expr, args)


def tokenize(text):
    """Tokenize the given text. Returns the list of tokens.

    Splits up at spaces, and tabs,
    single and double quotes protect spaces/tabs,
    backslashes escape *any* subsequent character.
    """
    words = []

    word = ''
    quote = None
    escaped = False

    for letter in text:
        if escaped:
            word += letter
            escaped = False
        else:
            if letter == '\\':
                escaped = True
            elif quote is not None and letter == quote:
                quote = None
                words.append(word)
                word = ''
            elif quote is None and letter in " \t":
                words.append(word.strip())
                word = ''
            elif quote is None and letter in '"\'' and len(word.strip()) == 0:
                word = ''
                quote = letter
            else:
                word += letter

    if len(word.strip()) > 0:
        words.append(word.strip())

    return [word for word in words if len(word) > 0]

