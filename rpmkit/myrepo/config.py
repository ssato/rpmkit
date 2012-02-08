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
import rpmkit.myrepo.environ as E
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.parser as P
import rpmkit.myrepo.repo as R
import rpmkit.myrepo.utils as U

import ConfigParser as cp
import glob
import itertools as IT
import logging
import os
import os.path


def init_defaults_0():
    archs = E.list_archs()
    distributions_full = E.list_dists()
    dists = ["%s-%s" % E.get_distribution()]
    distributions = ["%s-%s" % da for da in IT.product(dists, archs)]

    defaults = {
        "server": E.hostname(),
        "user": E.get_username(),
        "email":  E.get_email(),
        "fullname": E.get_fullname(),
        "dists_full": ",".join(distributions_full),
        "dists": ",".join(distributions),
        "name": R.Repo.name,
        "subdir": R.Repo.subdir,
        "topdir": R.Repo.topdir,
        "baseurl": R.Repo.baseurl,
        "signkey": R.Repo.signkey,
        "metadata_expire": R.Repo.metadata_expire,
    }

    if U.is_local(defaults["server"]):
        timeout = G.LOCAL_TIMEOUT
    else:
        timeout = G.REMOTE_TIMEOUT

    defaults["timeout"] = timeout

    return defaults


def init_defaults_by_conffile(config=None, profile=None):
    """
    Initialize default values for options by loading config files.
    """
    if config is None:
        # Is there case that $HOME is empty?
        home = os.environ.get("HOME", os.curdir)

        confs = ["/etc/myreporc"]
        confs += sorted(glob.glob("/etc/myrepo.d/*.conf"))
        confs += [os.environ.get("MYREPORC", os.path.join(home, ".myreporc"))]
    else:
        confs = (config,)

    cparser = cp.SafeConfigParser()
    loaded = False

    for c in confs:
        if os.path.exists(c):
            logging.info("Loading config: %s" % c)
            cparser.read(c)
            loaded = True

    if not loaded:
        return {}

    d = cparser.items(profile) if profile else cparser.defaults().iteritems()

    return dict((k, P.parse_conf_value(v)) for k, v in d)


def init_defaults(config=None):
    defaults = init_defaults_0()
    defaults["distribution_choices"] = defaults["dists_full"]  # save it.

    defaults.update(init_defaults_by_conffile(config))

    return defaults


# vim:sw=4 ts=4 et:
