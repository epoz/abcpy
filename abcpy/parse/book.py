"""Splits a string containing a book of ABC tunes (port of ``abc_parse_book.js``)."""

import re

from ..jsutil import Obj, strip


def book_parser(book):
    """Return ``{'header': directives, 'tunes': [{abc, startPos, pure, title, id}, ...]}``."""
    directives = ""
    initial_white_space = re.match(r"(\s*)", book)
    book = strip(book)
    tune_strings = book.split("\nX:")
    # Put back the X: that we lost when splitting the tunes.
    for i in range(1, len(tune_strings)):
        tune_strings[i] = "X:" + tune_strings[i]
    # Keep track of the character position each tune starts with. If the string starts with white space, count that, too.
    pos = len(initial_white_space.group(0)) if initial_white_space else 0
    tunes = []
    for tune in tune_strings:
        tunes.append(Obj(abc=tune, startPos=pos))
        pos += len(tune) + 1  # We also lost a newline when splitting, so count that.
    if len(tunes) > 1 and not tunes[0].abc.startswith('X:'):
        # If there is only one tune, the X: might be missing, otherwise assume the top of the file is "intertune"
        # There could be file-wide directives in this, if so, we need to insert it into each tune.
        d = tunes.pop(0)
        for line in d.abc.split('\n'):
            if line.startswith('%%'):
                directives += line + '\n'
    header = directives

    # Now, the tune ends at a blank line, so truncate it if needed. There may be "intertune" stuff.
    for tune in tunes:
        m = re.search(r"\n[ \t]*\n", tune.abc)  # blank line includes lines with only white space.
        end = m.start() if m else -1
        if end > 0:
            tune.abc = tune.abc[0:end]
        tune.pure = tune.abc
        tune.abc = directives + tune.abc

        # for the user's convenience, parse and store the title separately. The title is between the first T: and the next \n
        tune.title = ""
        title = tune.pure.split("T:")
        if len(title) > 1:
            title = title[1].split("\n")
            tune.title = strip(title[0])

        # for the user's convenience, parse and store the id separately. The id is between the first X: and the next \n
        # (JS substring semantics: with no newline this is substring(2, -1) == substring(0, 2))
        tune.id = strip(_substring(tune.pure, 2, tune.pure.find("\n")))

    return Obj(header=header, tunes=tunes)


def _substring(s, a, b):
    from ..jsutil import substring
    return substring(s, a, b)
