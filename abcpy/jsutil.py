"""Small helpers that reproduce JavaScript semantics needed by the port.

The abcjs code base relies on a number of JavaScript behaviours (loose
truthiness, out-of-range indexing returning ``undefined``, ``parseInt`` and
``parseFloat`` leniency, ``Number.toString`` formatting...).  Those are
collected here so that the rest of the port can stay close to the original.
"""

import json
import math
import re

NaN = float("nan")


class Obj(dict):
    """A dict that also allows attribute access.

    Missing attributes return ``None`` (the equivalent of JavaScript's
    ``undefined``), assigning an attribute stores a key and deleting an
    attribute removes the key if it is present.  Like a JavaScript object, an
    ``Obj`` is always truthy, even when it is empty.  Because it is a real
    ``dict``, parsed tunes can be serialized with :mod:`json` directly.
    """

    __slots__ = ()

    def __missing__(self, key):
        # obj[key] for a missing key is None, like JavaScript's undefined.
        return None

    def __bool__(self):
        # JavaScript objects are always truthy, even when empty.
        return True

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        self.pop(name, None)

    def __copy__(self):
        return Obj(self)

    def __deepcopy__(self, memo):
        import copy
        return Obj({k: copy.deepcopy(v, memo) for k, v in self.items()})

    def __repr__(self):
        return dict.__repr__(self)


def obj(*args, **kwargs):
    return Obj(*args, **kwargs)


def to_obj(value):
    """Recursively convert plain dicts into :class:`Obj`."""
    if isinstance(value, dict) and not isinstance(value, Obj):
        return Obj((k, to_obj(v)) for k, v in value.items())
    if isinstance(value, Obj):
        for k in list(value.keys()):
            value[k] = to_obj(value[k])
        return value
    if isinstance(value, list):
        for i in range(len(value)):
            value[i] = to_obj(value[i])
        return value
    return value


def assign(*sources):
    """Equivalent of ``Object.assign({}, a, b, ...)``."""
    ret = Obj()
    for s in sources:
        if s:
            ret.update(s)
    return ret


def truthy(v):
    """JavaScript truthiness."""
    if v is None or v is False:
        return False
    if isinstance(v, bool):
        return True
    if isinstance(v, (int, float)):
        return v != 0 and not (isinstance(v, float) and math.isnan(v))
    if isinstance(v, str):
        return len(v) > 0
    return True


def at(seq, i):
    """``seq[i]`` with JavaScript semantics: ``None`` when out of range."""
    if seq is None or i is None:
        return None
    try:
        if isinstance(i, float):
            if i != i or i != int(i):
                return None
            i = int(i)
        if i < 0 or i >= len(seq):
            return None
        return seq[i]
    except (TypeError, IndexError):
        return None


def js_set(lst, i, value):
    """Assign ``lst[i] = value`` growing the list with ``None`` holes like JS."""
    while len(lst) <= i:
        lst.append(None)
    lst[i] = value


def last(arr):
    if not arr:
        return None
    return arr[-1]


def substring(s, start, end=None):
    """``String.prototype.substring``."""
    n = len(s)
    if start is None or (isinstance(start, float) and start != start):
        start = 0
    if end is None:
        end = n
    elif isinstance(end, float) and end != end:
        end = 0
    start = int(min(max(start, 0), n))
    end = int(min(max(end, 0), n))
    if start > end:
        start, end = end, start
    return s[start:end]


def substr(s, start, length=None):
    """``String.prototype.substr``."""
    n = len(s)
    if start < 0:
        start = max(n + start, 0)
    if length is None:
        return s[start:]
    if length <= 0:
        return ""
    return s[start:start + length]


def index_of(seq, item, start=0):
    try:
        return seq.index(item, start)
    except ValueError:
        return -1


def last_index_of(s, item):
    return s.rfind(item)


_int_re = re.compile(r"^[\s﻿]*([+-]?)(0[xX][0-9a-fA-F]+|\d+)")
_float_re = re.compile(r"^[\s﻿]*([+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))")


def parse_int(s, radix=10):
    """``parseInt``: returns an int, or NaN when no digits are found."""
    if isinstance(s, bool):
        s = "true" if s else "false"
    if isinstance(s, (int, float)):
        if isinstance(s, float) and (s != s or math.isinf(s)):
            return NaN
        s = js_str(s)
    if s is None:
        return NaN
    m = _int_re.match(str(s))
    if not m:
        return NaN
    sign = -1 if m.group(1) == "-" else 1
    digits = m.group(2)
    if digits[:2] in ("0x", "0X"):
        if radix not in (10, 16):
            return 0 * sign
        return sign * int(digits, 16)
    return sign * int(digits)


def parse_float(s):
    """``parseFloat``: returns a float/int, or NaN."""
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return s
    if s is None:
        return NaN
    m = _float_re.match(str(s))
    if not m:
        return NaN
    t = m.group(1)
    if t.endswith("Infinity"):
        return -math.inf if t.startswith("-") else math.inf
    v = float(t)
    return v


def is_nan(x):
    return isinstance(x, float) and x != x


def number(x):
    """``Number(x)`` for the common cases."""
    if x is None:
        return NaN
    if isinstance(x, bool):
        return 1 if x else 0
    if isinstance(x, (int, float)):
        return x
    if isinstance(x, str):
        t = x.strip()
        if t == "":
            return 0
        try:
            return float(t) if any(c in t for c in ".eE") else int(t)
        except ValueError:
            return NaN
    if isinstance(x, list):
        if len(x) == 0:
            return 0
        if len(x) == 1:
            return number(x[0]) if not isinstance(x[0], list) else number(x[0])
        return NaN
    return NaN


def js_str(x):
    """String conversion with JavaScript rules (``"" + x``)."""
    if x is None:
        return "undefined"
    if x is True:
        return "true"
    if x is False:
        return "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if x != x:
            return "NaN"
        if math.isinf(x):
            return "Infinity" if x > 0 else "-Infinity"
        if x == int(x) and abs(x) < 1e21:
            return str(int(x))
        r = repr(x)
        if "e" in r or "E" in r:
            mant, exp = r.split("e")
            exp = int(exp)
            if -7 < exp < 21:
                # expand to a plain decimal like JS does
                d = mant.replace("-", "").replace(".", "")
                neg = x < 0
                point = (mant.replace("-", "").index(".") if "." in mant else len(mant.replace("-", ""))) + exp
                if point <= 0:
                    s = "0." + "0" * (-point) + d
                elif point >= len(d):
                    s = d + "0" * (point - len(d))
                else:
                    s = d[:point] + "." + d[point:]
                return ("-" if neg else "") + s
            return mant + "e" + ("+" if exp > 0 else "-") + str(abs(exp))
        # Python uses scientific notation for small numbers earlier than JS
        return r
    if isinstance(x, list):
        return ",".join("" if v is None else js_str(v) for v in x)
    if isinstance(x, dict):
        return "[object Object]"
    return str(x)


def js_round(x):
    """``Math.round``."""
    if x is None or is_nan(x):
        return NaN
    if isinstance(x, float) and math.isinf(x):
        return x
    return int(math.floor(x + 0.5))


def to_fixed(x, digits=0):
    """``Number.prototype.toFixed`` (sufficient for drawing coordinates)."""
    if is_nan(x):
        return "NaN"
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(1).scaleb(-digits)
    # JavaScript rounds the exact binary value (so 1.005 is "1.00"), halves away from zero.
    v = Decimal(float(x)).quantize(q, rounding=ROUND_HALF_UP)
    s = format(v, "f")
    if x < 0 and not s.startswith("-"):
        s = "-" + s
    return s


def js_mod(a, b):
    """JavaScript ``%`` (sign of the dividend)."""
    if b == 0:
        return NaN
    r = math.fmod(a, b)
    if isinstance(a, int) and isinstance(b, int):
        return int(r)
    return r


def to_int32(x):
    """ToInt32 conversion used by bitwise operators."""
    if x is None or is_nan(x) or (isinstance(x, float) and math.isinf(x)):
        return 0
    x = int(x) & 0xFFFFFFFF
    if x >= 0x80000000:
        x -= 0x100000000
    return x


def json_clone(value):
    """``JSON.parse(JSON.stringify(value))``."""
    return to_obj(json.loads(json.dumps(value, default=_json_default)))


def _json_default(o):
    return None


def strip(s):
    return re.sub(r"[\s﻿]+$", "", re.sub(r"^[\s﻿]+", "", s))


def js_trim(s):
    return strip(s)


def js_split(s, sep):
    """``String.prototype.split`` with a string separator."""
    if sep == "":
        return list(s)
    return s.split(sep)


def js_sort(arr, cmp):
    import functools
    arr.sort(key=functools.cmp_to_key(lambda a, b: _cmp_sign(cmp(a, b))))
    return arr


def _cmp_sign(v):
    if v is None or is_nan(v):
        return 0
    return -1 if v < 0 else (1 if v > 0 else 0)


def js_keys(d):
    """``Object.keys`` ordering: integer-like keys ascending first, then insertion order."""
    ints = []
    others = []
    for k in d.keys():
        if isinstance(k, int):
            ints.append(k)
        elif isinstance(k, str) and k.isdigit() and (k == "0" or not k.startswith("0")) and len(k) < 10:
            ints.append(k)
        else:
            others.append(k)
    ints.sort(key=lambda k: int(k))
    return ints + others


def stringify(value, **kwargs):
    """``JSON.stringify`` analogue that understands :class:`Obj`."""
    return json.dumps(value, default=_json_default, ensure_ascii=False, **kwargs)


def js_floor(x):
    """``Math.floor``: NaN and infinities pass through instead of raising."""
    if x is None:
        return NaN
    if isinstance(x, float) and (x != x or math.isinf(x)):
        return x
    return math.floor(x)


def js_ceil(x):
    """``Math.ceil``: NaN and infinities pass through instead of raising."""
    if x is None:
        return NaN
    if isinstance(x, float) and (x != x or math.isinf(x)):
        return x
    return math.ceil(x)


class JSObj:
    """Base class for engraver objects: reading a missing attribute gives ``None`` (JS ``undefined``)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return None

    def __bool__(self):
        return True


def jdel(o, name):
    """``delete o[name]`` for dicts and objects."""
    if isinstance(o, dict):
        o.pop(name, None)
    else:
        o.__dict__.pop(name, None)


def jget(o, name):
    """``o[name]`` for dicts and objects (``None`` when missing)."""
    if o is None:
        return None
    if isinstance(o, dict):
        return o.get(name)
    return getattr(o, name, None)


def jset(o, name, value):
    if isinstance(o, dict):
        o[name] = value
    else:
        setattr(o, name, value)


def _cmpnum(v):
    if v is None:
        return NaN
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def gt(a, b):
    """``a > b`` with JavaScript semantics for undefined/NaN (always false)."""
    a, b = _cmpnum(a), _cmpnum(b)
    try:
        return a > b
    except TypeError:
        return False


def lt(a, b):
    a, b = _cmpnum(a), _cmpnum(b)
    try:
        return a < b
    except TypeError:
        return False


def ge(a, b):
    a, b = _cmpnum(a), _cmpnum(b)
    try:
        return a >= b
    except TypeError:
        return False


def le(a, b):
    a, b = _cmpnum(a), _cmpnum(b)
    try:
        return a <= b
    except TypeError:
        return False


def add(a, b):
    """``a + b`` for numbers where either may be undefined (giving NaN)."""
    if a is None or b is None:
        return NaN
    return a + b


def js_max(*args):
    """``Math.max``."""
    best = -math.inf
    for a in args:
        a = _cmpnum(a)
        if a != a:
            return NaN
        if a > best:
            best = a
    return best


def js_min(*args):
    """``Math.min``."""
    best = math.inf
    for a in args:
        a = _cmpnum(a)
        if a != a:
            return NaN
        if a < best:
            best = a
    return best


def obj_copy(value):
    """A copy of ``value`` where every (nested) dict is an :class:`Obj` (lists are copied too).

    Used for the option dictionaries passed in by users, so that they are not modified.
    """
    if isinstance(value, dict):
        return Obj((k, obj_copy(v)) for k, v in value.items())
    if isinstance(value, list):
        return [obj_copy(v) for v in value]
    return value
