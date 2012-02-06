#
# misc utility routines
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
import rpmkit.memoize as M
import rpmkit.tenjinwrapper as T

import os.path
import platform
import re


memoize = M.memoize


def compile_template(tmpl_name, context={}):
    #return T.template_compile(os.path.join("1/myrepo", tmpl_name), context)
    return T.template_compile(tmpl_name, context)


@memoize
def list_archs(arch=None):
    """List 'normalized' architecutres this host (mock) can support.
    """
    default = ["x86_64", "i386"]   # This order should be kept.
    ia32_re = re.compile(r"i.86")  # i386, i686, etc.

    if arch is None:
        arch = platform.machine()

    if ia32_re.match(arch) is not None:
        return ["i386"]
    else:
        return default


@memoize
def list_dists():
    """List available dist names, e.g. ["fedora-14", "rhel-6"]
    """
    mockdir = "/etc/mock"
    arch = list_archs()[0]
    reg = re.compile("%s/(?P<dist>.+)-%s.cfg" % (mockdir, arch))

    return [
        reg.match(c).groups()[0] for c in \
            sorted(glob.glob("%s/*-%s.cfg" % (mockdir, arch)))
    ]


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


# vim:sw=4 ts=4 et:
