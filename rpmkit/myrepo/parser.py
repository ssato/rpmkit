#
# Copyright (C) 2011 Red Hat, Inc.
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
import logging
import re


def parse_conf_value(s):
    """Simple and naive parser to parse value expressions in config files.

    >>> parse_conf_value("0")
    0
    >>> parse_conf_value("123")
    123
    >>> parse_conf_value("True")
    True
    >>> parse_conf_value("false")
    False
    >>> parse_conf_value("[1,2,3]")
    [1, 2, 3]
    >>> parse_conf_value("a string")
    'a string'
    >>> parse_conf_value("0.1")
    '0.1'
    """
    s = s.strip()  # strip white spaces.

    intp = re.compile(r"^([0-9]|([1-9][0-9]+))$")
    boolp = re.compile(r"^(true|false)$", re.I)
    listp = re.compile(r"^(\[\s*((\S+),?)*\s*\])$")

    def matched(pat, s):
        m = pat.match(s)
        return m is not None

    if not s:
        return ""

    if matched(boolp, s):
        return bool(re.match(s, 'true', re.I))

    if matched(intp, s):
        return int(s)

    if matched(listp, s):
        return eval(s)  # TODO: too danger. how to parse it safely?

    return s


def parse_dist_option(dist, sep=":"):
    """Parse dist_str and returns (dist, arch, bdist_label).

    SEE ALSO: parse_dists_option (below)

    >>> try:
    ...     parse_dist_option("invalid_dist_label.i386")
    ... except AssertionError:
    ...     pass
    >>> try:
    ...     parse_dist_option("feodra-16-x86_64:no-arch-dist")
    ... except AssertionError:
    ...     pass
    >>> try:
    ...     parse_dist_option("feodra-16-x86_64:invalid-arch-dist-i386")
    ... except AssertionError:
    ...     pass
    >>> parse_dist_option("fedora-16-i386")
    ('fedora', '16', 'i386', 'fedora-16')
    >>> parse_dist_option("fedora-16-i386:fedora-extras-16-i386")
    ('fedora', '16', 'i386', 'fedora-extras-16')
    """
    emh = "Invalid distribution label '%s'. " % dist

    tpl = dist.split(sep)
    label = tpl[0]

    assert "-" in label, emh + "Separator '-' not found"

    try:
        (name, ver, arch) = label.split("-")
    except ValueError:
        raise RuntimeError(
            emh + "Its format must be <name>-<ver>-<arch>: " + label
        )

    if len(tpl) < 2:
        bdist = name + '-' + ver
    else:
        blabel = tpl[1]
        try:
            (bdist, barch) = blabel.rsplit('-', 1)
            assert barch == arch, "Build arch and dist's arch not match"
        except ValueError:
            raise RuntimeError(
                emh + "Build dist's format must be <distname>-<arch>: " \
                    + blabel
            )

        if len(tpl) > 2:
            logging.warn(
                emh + "Too many separator '%s' found. Ignore the rest." % sep
            )

    return (name, ver, arch, bdist)


def parse_dists_option(dists, sep=","):
    """Parse --dists option and returns [(dist, arch, bdist_label)].

    # d[:d.rfind("-")])
    #archs = [l.split("-")[-1] for l in labels]

    >>> parse_dists_option("fedora-16-i386")
    [('fedora', '16', 'i386', 'fedora-16')]
    >>> parse_dists_option("fedora-16-i386:fedora-extras-16-i386")
    [('fedora', '16', 'i386', 'fedora-extras-16')]
    >>> ss = ["fedora-16-i386:fedora-extras-16-i386"]
    >>> ss += ["rhel-6-i386:rhel-extras-6-i386"]
    >>> r = [('fedora', '16', 'i386', 'fedora-extras-16')]
    >>> r += [('rhel', '6', 'i386', 'rhel-extras-6')]
    >>> assert r == parse_dists_option(",".join(ss))
    """
    return [parse_dist_option(dist) for dist in dists.split(sep)]


# vim:sw=4 ts=4 et:
