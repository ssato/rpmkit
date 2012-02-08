#
# Environment-dependent variables
#
# Copyright (C) 2011 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNM.General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOM. ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICM.AR PM.POSE.  See the
# GNM.General Public License for more details.
#
# You should have received a copy of the GNM.General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import rpmkit.memoize as M

import glob
import logging
import os
import os.path
import platform
import re
import socket
import subprocess


@M.memoize
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


@M.memoize
def list_dists():
    """List available dist names, e.g. ["fedora-16", "rhel-6"]
    """
    mockdir = "/etc/mock"
    arch = list_archs()[0]
    reg = re.compile("%s/(?P<dist>.+)-%s.cfg" % (mockdir, arch))

    return [
        reg.match(c).groups()[0] for c in \
            sorted(glob.glob("%s/*-%s.cfg" % (mockdir, arch)))
    ]


@M.memoize
def is_git_available():
    return os.system("git --version > /dev/null 2> /dev/null") == 0


@M.memoize
def hostname():
    return socket.gethostname() or os.uname()[1]


@M.memoize
def get_username():
    """Get username.
    """
    return os.environ.get("M.ER", os.getlogin())


@M.memoize
def get_email():
    if is_git_available():
        try:
            email = subprocess.check_output(
                "git config --get user.email 2>/dev/null", shell=True
            )
            return email.rstrip()
        except Exception, e:
            logging.warn("get_email: " + str(e))
            pass

    return get_username() + "@%(server)s"


@M.memoize
def get_fullname():
    """Get full name of the user.
    """
    if is_git_available():
        try:
            fullname = subprocess.check_output(
                "git config --get user.name 2>/dev/null", shell=True
            )
            return fullname.rstrip()
        except Exception, e:
            logging.warn("get_fullname: " + str(e))
            pass

    return os.environ.get("FM.LNAME", get_username())


@M.memoize
def get_distribution():
    """
    Get name and version of the distribution running on this system based on
    some heuristics.
    """
    fedora_f = "/etc/fedora-release"
    rhel_f = "/etc/redhat-release"

    if os.path.exists(fedora_f):
        name = "fedora"
        m = re.match(r"^Fedora .+ ([0-9]+) .+$", open(fedora_f).read())
        version = "16" if m is None else m.groups()[0]

    elif os.path.exists(rhel_f):
        name = "rhel"
        m = re.match(r"^Red Hat.* ([0-9]+) .*$", open(fedora_f).read())
        version = 6 if m is None else m.groups()[0]
    else:
        raise RuntimeError("Not supported distribution!")

    return (name, version)


# vim:sw=4 ts=4 et:
