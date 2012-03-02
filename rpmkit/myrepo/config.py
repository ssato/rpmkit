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
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.parser as P
import rpmkit.utils as U
import rpmkit.Bunch as B
import rpmkit.environ as E

import ConfigParser as cp
import glob
import itertools as IT
import logging
import os
import os.path


def get_timeout(config):
    """
    :param config: Configuration object :: B.Bunch
    """
    U.typecheck(config, B.Bunch)

    timeo = config.get("timeout", None)
    if timeo:
        return timeo
    else:
        if U.is_local(config.server):
            return G.LOCAL_TIMEOUT
        else:
            return G.REMOTE_TIMEOUT


def _init_by_defaults():
    archs = E.list_archs()
    distributions_full = E.list_dists()
    dists = ["%s-%s" % E.get_distribution()]
    distributions = ["%s-%s" % da for da in IT.product(dists, archs)]

    defaults = G.REPO_DEFAULT

    defaults.update({
        "server": E.hostname(),
        "user": E.get_username(),
        "email":  E.get_email(),
        "fullname": E.get_fullname(),
        "dists_full": ",".join(distributions_full),
        "dists": ",".join(distributions),
        "genconf": True,
    })

    defaults["distribution_choices"] = defaults["dists_full"]  # save it.
    defaults["timeout"] = get_timeout(defaults)

    return defaults


def _init_by_config_file(config=None, profile=None):
    """
    Initialize default values for options by loading config files.

    :param config: Config file's path :: str
    :param profile: Custom profile as needed :: str
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
            logging.info("Loading config: " + c)
            cparser.read(c)
            loaded = True

    if not loaded:
        return {}

    d = cparser.items(profile) if profile else cparser.defaults().iteritems()

    return B.Bunch((k, P.parse_conf_value(v)) for k, v in d)


def init(config_path=None):
    cfg = _init_by_defaults()
    cfg.update(_init_by_config_file(config_path))

    return cfg


# vim:sw=4 ts=4 et:
