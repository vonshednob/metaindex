"""Search query abstraction"""
import re

from metaindex import logger


class QueryVisitor:
    """Visitor for search queries"""

    def on_sequence_start(self, element):
        """When visiting a Sequence element"""

    def on_sequence_end(self, element):
        """When leaving a Sequence element"""

    def on_key_value(self, element):
        """When visiting a KeyValueTerm element"""

    def on_key_exists(self, element):
        """When visiting a KeyExistsTerm element"""

    def on_regex(self, element):
        """When visiting a RegexTerm element"""


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

    def accept(self, visitor):
        self.root.accept(visitor)

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

    OR = 'or'
    AND = 'and'

    def __init__(self, operator=None, inverted=False):
        self.inverted = inverted
        self.operator = operator or Term.AND

    def accept(self, visitor):
        """Welcome this QueryVisitor"""
        raise NotImplementedError()


class RegexTerm(Term):
    """A regex"""
    def __init__(self, word, operator, inverted=False):
        super().__init__(operator, inverted)
        self.word = word

    def accept(self, visitor):
        visitor.on_regex(self)


class KeyValueTerm(Term):
    """This metadata key matches this regex"""
    def __init__(self, key, regex, operator, inverted):
        super().__init__(operator, inverted)
        self.key = key
        self.regex = regex

    def accept(self, visitor):
        visitor.on_key_value(self)


class KeyExistsTerm(Term):
    """A metadata key of this name exists"""
    def __init__(self, key, operator, inverted=False):
        super().__init__(operator, inverted)
        self.key = key

    def accept(self, visitor):
        visitor.on_key_exists(self)


class Sequence(Term):
    """A sequence of query terms.
    A term may be

     - RegexTerm (match *any* value in form of a regex),
     - Key (match all items that have this metadata key; syntax: "key?"),
     - KeyValue (match all items that have this metadata key and their
       value matches the regex: "key:regex"),
     - KeyEqualValue (match all items that have this metadata key with that
       value; syntax: "key=value"),
     - KeyLessValue (match all items that have this metadata key and the value
       is "less" than the given value; syntax: "key<value")
     - KeyGreaterValue (match all items that have this metadata key and the
       value is "greater" than the given value; syntax: "key>value")

    Any term may be negated by prepending a "-" or "not:".
    """

    def __init__(self, terms=None):
        super().__init__(None, False)
        self.terms = terms or []

    def add(self, term):
        self.terms.append(term)
        return self

    def accept(self, visitor):
        visitor.on_sequence_start(self)
        for term in self.terms:
            term.accept(visitor)
        visitor.on_sequence_end(self)

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
