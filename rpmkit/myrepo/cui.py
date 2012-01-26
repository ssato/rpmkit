#
# myrepo.py - Manage your yum repo and RPMs:
#
#  * Setup your own yum repos
#  * build SRPMs and deploy SRPMs and RPMs into your repos.
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
# Requirements: createrepo, ssh, packagemaker (see below)
#
# SEE ALSO: createrepo(8)
# SEE ALSO: https://github.com/ssato/packagemaker
#
import rpmkit.myrepo.environ as E
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.repo as R
import rpmkit.myrepo.repoops as RO
import rpmkit.myrepo.shell as SH
import rpmkit.myrepo.utils as U

import ConfigParser as cp
import glob
import itertools as IT
import logging
import operator
import optparse
import os
import os.path
import re
import sys
import threading
import time


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
        return eval(s)  # TODO: too danger. safer parsing should be needed.

    return s


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

    d = profile and cparser.items(profile) or cparser.defaults().iteritems()

    return dict((k, parse_conf_value(v)) for k, v in d)


def init_defaults():
    dists_full = E.list_dists()
    archs = E.list_archs()

    dists = ["%s-%s" % E.get_distribution()]

    distributions_full = ["%s-%s" % da for da in IT.product(dists_full, archs)]
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


def parse_dist_option(dist_str, sep=":"):
    """Parse dist_str and returns (dist, arch, bdist_label).

    SEE ALSO: parse_dists_option (below)

    >>> try:
    ...     parse_dist_option("invalid_dist_label.i386")
    ... except AssertionError:
    ...     pass
    >>> parse_dist_option("fedora-14-i386")
    ('fedora-14', 'i386', 'fedora-14-i386')
    >>> parse_dist_option("fedora-14-i386:fedora-my-additions-14-i386")
    ('fedora-14', 'i386', 'fedora-my-additions-14-i386')
    >>> parse_dist_option("fedora-14-i386:fedora-my-additions-14-x86_64")
    ('fedora-14', 'i386', 'fedora-my-additions-14-x86_64')
    >>> parse_dist_option("fedora-14-i386:fedora-my-additions")
    ('fedora-14', 'i386', 'fedora-my-additions')
    """
    tpl = dist_str.split(sep)
    label = tpl[0]

    assert "-" in label, "Invalid distribution label ('-' not found): " + label

    (dist, arch) = label.rsplit("-", 1)

    if len(tpl) < 2:
        bdist_label = label
    else:
        bdist_label = tpl[1]

        if len(tpl) > 2:
            m = "Invalid format: too many '%s' in dist_str: %s. " + \
                "Ignore the rest"
            logging.warn(m % (sep, dist_str))

    return (dist, arch, bdist_label)


def parse_dists_option(dists_str, sep=","):
    """Parse --dists option and returns [(dist, arch, bdist_label)].

    # d[:d.rfind("-")])
    #archs = [l.split("-")[-1] for l in labels]

    >>> parse_dists_option("fedora-14-i386")
    [('fedora-14', 'i386', 'fedora-14-i386')]
    >>> parse_dists_option("fedora-14-i386:fedora-my-additions-14-i386")
    [('fedora-14', 'i386', 'fedora-my-additions-14-i386')]
    >>> ss = ["fedora-14-i386:fedora-my-additions-14-i386"]
    >>> ss += ["rhel-6-i386:rhel-my-additions-6-i386"]
    >>> parse_dists_option(",".join(ss))
    [('fedora-14', 'i386', 'fedora-my-additions-14-i386'), ('rhel-6', 'i386', 'rhel-my-additions-6-i386')]
    """
    return [parse_dist_option(dist_str) for dist_str in dists_str.split(sep)]


def create_repos_from_dists_option(dists_s):
    """
    :param dists_s:  str represents target distributions

    see also: parse_dists_option
    """
    dabs = parse_dists_option(dists_s)  # [(dist, arch, bdist_label)]
    repos = []

    for dist, dists in IT.groupby(dabs, operator.itemgetter(0)):  # d[0]: dist
        dists = list(dists)  # it's a generator and has internal state.

        archs = [d[1] for d in dists]  # d[1]: arch
        bdist_label = [d[2] for d in dists][0]  # d[2]: bdist_label

        repo = R.Repo(
            config["server"],
            config["user"],
            config["email"],
            config["fullname"],
            dist,
            archs,
            config["name"],
            config["subdir"],
            config["topdir"],
            config["baseurl"],
            config["signkey"],
            bdist_label,
            config["metadata_expire"],
            config["timeout"],
        )

        repos.append(repo)

    return repos


def opt_parser():
    defaults = init_defaults()
    distribution_choices = defaults["dists_full"]  # save it.

    defaults.update(init_defaults_by_conffile())

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...] [ARGS]

Commands: i[init], b[uild], d[eploy], u[pdate]

Examples:
  # initialize your yum repos:
  %prog init -s yumserver.local -u foo -m foo@example.com -F "John Doe"

  # build SRPM:
  %prog build packagemaker-0.1-1.src.rpm

  # build SRPM and deploy RPMs and SRPMs into your yum repos:
  %prog deploy packagemaker-0.1-1.src.rpm
  %prog d --dists rhel-6-x86_64 packagemaker-0.1-1.src.rpm
  """
    )

    for k in ("verbose", "quiet", "debug"):
        if not defaults.get(k, False):
            defaults[k] = False

    p.set_defaults(**defaults)

    p.add_option("-C", "--config", help="Configuration file")
    p.add_option("-T", "--timeout", type="int",
        help="Timeout [sec] for each operations [%default]")

    p.add_option("-s", "--server", help="Server to provide your yum repos.")
    p.add_option("-u", "--user", help="Your username on the server [%default]")
    p.add_option("-m", "--email",
        help="Your email address or its format string [%default]")
    p.add_option("-F", "--fullname", help="Your full name [%default]")

    p.add_option("", "--dists",
        help="Comma separated distribution labels including arch "
        "(optionally w/ build (mock) distribution label). "
        "Options are some of " + distribution_choices + " [%default] "
        "and these combinations: e.g. fedora-16-x86_64, "
        "rhel-6-i386:my-custom-addon-rhel-6-i386"
    )

    p.add_option("-q", "--quiet", action="store_true", help="Quiet mode")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    p.add_option("", "--debug", action="store_true", help="Debug mode")

    iog = optparse.OptionGroup(p, "Options for 'init' command")
    iog.add_option('', "--name",
        help="Name of your yum repo or its format string [%default].")
    iog.add_option("", "--subdir",
        help="Repository sub dir name [%default]")
    iog.add_option("", "--topdir",
        help="Repository top dir or its format string [%default]")
    iog.add_option('', "--baseurl",
        help="Repository base URL or its format string [%default]")
    iog.add_option('', "--signkey",
        help="GPG key ID if signing RPMs to deploy")
    p.add_option_group(iog)

    return p


def do_command(cmd, repos, srpm=None, wait=SH.WAIT_FOREVER):
    f = getattr(RO, cmd)
    threads = []

    if srpm is not None:
        R.is_noarch(srpm)  # make a result cache

    for repo in repos:
        args = srpm is None and (repo, ) or (repo, srpm)

        thread = threading.Thread(target=f, args=args)
        thread.start()

        threads.append(thread)

    time.sleep(G.MIN_TIMEOUT)

    for thread in threads:
        # it will block.
        thread.join(wait)

        # Is there any possibility thread still live?
        if thread.is_alive():
            logging.info("Terminating the thread")

            thread.join()


def main(argv=sys.argv):
    (CMD_INIT, CMD_UPDATE, CMD_BUILD, CMD_DEPLOY) = \
        ("init", "update", "build", "deploy")

    logformat = "%(asctime)s [%(levelname)-4s] myrepo: %(message)s"
    logdatefmt = "%H:%M:%S"  # too much? "%a, %d %b %Y %H:%M:%S"

    logging.basicConfig(format=logformat, datefmt=logdatefmt)

    p = opt_parser()
    (options, args) = p.parse_args(argv[1:])

    if options.verbose:
        logging.getLogger().setLevel(logging.INFO)
    elif options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif options.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    else:
        logging.getLogger().setLevel(logging.WARN)

    if not args:
        p.print_usage()
        sys.exit(1)

    a0 = args[0]
    if a0.startswith('i'):
        cmd = CMD_INIT

    elif a0.startswith('u'):
        cmd = CMD_UPDATE

    elif a0.startswith('b'):
        cmd = CMD_BUILD
        assert len(args) >= 2, \
            "'%s' command requires an argument to specify srpm[s]" % cmd

    elif a0.startswith('d'):
        cmd = CMD_DEPLOY
        assert len(args) >= 2, \
            "'%s' command requires an argument to specify srpm[s]" % cmd

    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)

    if options.config:
        params = init_defaults()
        params.update(init_defaults_by_conffile(options.config))

        p.set_defaults(**params)

        # re-parse to overwrite configurations with given options.
        (options, args) = p.parse_args()

    config = options.__dict__.copy()

    srpms = args[1:]
    repos = create_repos_from_dists_option(config["dists"])

    if srpms:
        for srpm in srpms:
            do_command(cmd, repos, srpm)
    else:
        do_command(cmd, repos)

    sys.exit()


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4 ts=4 et:
