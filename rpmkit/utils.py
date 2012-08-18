#
# misc utility routines
#
# Copyright (C) 2011, 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from rpmkit.memoize  import memoize

import datetime
import itertools
import operator
import os.path

try:
    from functools import reduce as foldl
except ImportError:
    foldl = reduce

try:
    chain_from_iterable = itertools.chain.from_iterable
except AttributeError:
    # Borrowed from library doc, 9.7.1 Itertools functions:
    def _from_iterable(iterables):
        for it in iterables:
            for element in it:
                yield element

    chain_from_iterable = _from_iterable


def typecheck(obj, expected_type_or_class):
    """Type checker.

    :param obj: Target object to check type
    :param expected_type_or_class: Expected type or class of $obj
    """
    if not isinstance(obj, expected_type_or_class):
        m = "Expected %s but got %s type. obj=%s" % (
            repr(expected_type_or_class), type(obj), str(obj),
        )
        raise TypeError(m)


def is_local(fqdn_or_hostname):
    """
    >>> is_local("localhost")
    True
    >>> is_local("localhost.localdomain")
    True
    >>> is_local("repo-server.example.com")
    False
    >>> is_local("127.0.0.1")  # special case:
    False
    """
    return fqdn_or_hostname.startswith("localhost")


def is_foldable(xs):
    """@see http://www.haskell.org/haskellwiki/Foldable_and_Traversable

    >>> is_foldable([])
    True
    >>> is_foldable(())
    True
    >>> is_foldable(x for x in range(3))
    True
    >>> is_foldable(None)
    False
    >>> is_foldable(True)
    False
    >>> is_foldable(1)
    False
    """
    return isinstance(xs, (list, tuple)) or callable(getattr(xs, "next", None))


def _concat(xss):
    """
    >>> _concat([[]])
    []
    >>> _concat((()))
    []
    >>> _concat([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> _concat([[1,2,3],[4,5,[6,7]]])
    [1, 2, 3, 4, 5, [6, 7]]
    >>> _concat(((1,2,3),(4,5,[6,7])))
    [1, 2, 3, 4, 5, [6, 7]]
    >>> _concat(((1,2,3),(4,5,[6,7])))
    [1, 2, 3, 4, 5, [6, 7]]
    >>> _concat((i, i*2) for i in range(3))
    [0, 0, 1, 2, 2, 4]
    """
    return list(chain_from_iterable(xs for xs in xss))


def _flatten(xss):
    """
    >>> _flatten([])
    []
    >>> _flatten([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> _flatten([[1,2,[3]],[4,[5,6]]])
    [1, 2, 3, 4, 5, 6]

    tuple:

    >>> _flatten([(1,2,3),(4,5)])
    [1, 2, 3, 4, 5]

    generator expression:

    >>> _flatten((i, i * 2) for i in range(0,5))
    [0, 0, 1, 2, 2, 4, 3, 6, 4, 8]
    """
    if is_foldable(xss):
        return foldl(operator.add, (_flatten(xs) for xs in xss), [])
    else:
        return [xss]


def _unique(xs, cmp=cmp, key=None):
    """Returns new sorted list of no duplicated items.

    >>> _unique([])
    []
    >>> _unique([0, 3, 1, 2, 1, 0, 4, 5])
    [0, 1, 2, 3, 4, 5]
    """
    if xs == []:
        return xs

    ys = sorted(xs, cmp=cmp, key=key)

    if ys == []:
        return ys

    ret = [ys[0]]

    for y in ys[1:]:
        if y == ret[-1]:
            continue
        ret.append(y)

    return ret


def uniq(iterable, cmp=cmp, key=None):
    """
    Safer version of the above.
    """
    acc = []
    for x in iterable:
        if x not in acc:
            acc.append(x)

    return acc


# FIXME: Looks like bad effects if memoized. Not memoized for a while
concat = _concat
flatten = _flatten
unique = _unique
uniq = _unique


def timeit(f, *args, **kwargs):
    start = datetime.datetime.now()
    ret = f(*args, **kwargs)
    end = datetime.datetime.now()
    return (ret, end - start)


# vim:sw=4:ts=4:et:
