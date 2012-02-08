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

    >>> assert 0 == parse_conf_value("0")
    >>> assert 123 == parse_conf_value("123")
    >>> assert True == parse_conf_value("True")
    >>> assert [1,2,3] == parse_conf_value("[1,2,3]")
    >>> assert "a string" == parse_conf_value("a string")
    >>> assert "0.1" == parse_conf_value("0.1")
    """
    intp = re.compile(r"^([0-9]|([1-9][0-9]+))$")
    boolp = re.compile(r"^(true|false)$", re.I)
    listp = re.compile(r"^(\[\s*((\S+),?)*\s*\])$")

    def matched(pat, s):
        m = pat.match(s)
        return m is not None

    if not s:
        return ""

    if matched(boolp, s):
        return bool(s)

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
    >>> parse_dist_option("fedora-16-i386")
    ('fedora', '16', 'i386', 'fedora-16-i386')
    >>> parse_dist_option("fedora-16-i386:fedora-extras-16-i386")
    ('fedora', '16', 'i386', 'fedora-extras-16-i386')
    >>> parse_dist_option("fedora-16-i386:fedora-extras-16-x86_64")
    ('fedora', '16', 'i386', 'fedora-extras-16-x86_64')
    >>> parse_dist_option("fedora-16-i386:fedora-extras")
    ('fedora', '16', 'i386', 'fedora-extras')
    """
    emh = "Invalid distribution label '%s'. " % dist

    tpl = dist.split(sep)
    label = tpl[0]

    assert "-" in label, emh + "Separator '-' not found"

    try:
        (name, ver, arch) = label.split("-")
    except ValueError:
        raise RuntimeError(
            emh + "Its format should be <name>-<ver>-<arch>: " + label
        )

    if len(tpl) < 2:
        bdist_label = label
    else:
        bdist_label = tpl[1]

        if len(tpl) > 2:
            logging.warn(
                emh + "Too many separator '-' found. Ignore the rest."
            )

    return (name, ver, arch, bdist_label)


def parse_dists_option(dists, sep=","):
    """Parse --dists option and returns [(dist, arch, bdist_label)].

    # d[:d.rfind("-")])
    #archs = [l.split("-")[-1] for l in labels]

    >>> parse_dists_option("fedora-16-i386")
    [('fedora', '16', 'i386', 'fedora-16-i386')]
    >>> parse_dists_option("fedora-16-i386:fedora-extras-16-i386")
    [('fedora', '16', 'i386', 'fedora-extras-16-i386')]
    >>> ss = ["fedora-16-i386:fedora-extras-16-i386"]
    >>> ss += ["rhel-6-i386:rhel-extras-6-i386"]
    >>> r = [('fedora', '16', 'i386', 'fedora-extras-16-i386')]
    >>> r += [('rhel', '6', 'i386', 'rhel-extras-6-i386')]
    >>> assert r == parse_dists_option(",".join(ss))
    """
    return [parse_dist_option(dist) for dist in dists.split(sep)]


# vim:sw=4 ts=4 et:
