#
# cui module
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
import rpmkit.myrepo.commands as CMD
import rpmkit.myrepo.config as C
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.parser as P
import rpmkit.myrepo.repo as R
import rpmkit.Bunch as B

import itertools
import logging
import operator
import optparse
import sys
import threading
import time


def _listify_arch(dname, dver, darch, bdist):
    """
    >>> _listify_arch('fedora', '16', 'x86_64', 'fedora-16')
    ['fedora', '16', ['x86_64'], 'fedora-16']
    """
    return [dname, dver, [darch], bdist]


def _degenerate_dists_g(dists):
    """
    Degenerate dists by bdist. (It is needed to avoid building noarch srpms
    multiple times.)

    >>> d0 = ('fedora', '16', 'x86_64', 'fedora-16')
    >>> d1 = ('fedora', '16', 'i386', 'fedora-16')
    >>> d2 = ('rhel', '6', 'x86_64', 'rhel-6')
    >>> list(_degenerate_dists_g([d0, d1]))
    [('fedora', '16', ['x86_64', 'i386'], 'fedora-16')]
    >>> ds2 = [
    ...    ('fedora', '16', ['x86_64', 'i386'], 'fedora-16'),
    ...    ('rhel', '6', ['x86_64'], 'rhel-6')
    ... ]
    >>> list(_degenerate_dists_g([d0, d1, d2])) == ds2
    True
    """
    key_f = operator.itemgetter(3)  # to extract bdist from dist.
    bds = [(bdist, list(ds)) for bdist, ds in itertools.groupby(dists, key_f)]

    for bd in bds:
        bdist = bd[0]
        dists = bd[1]

        dist0 = dists[0]
        archs = [d[2] for d in dists]

        (dname, dver) = dist0[:2]

        yield (dname, dver, archs, bdist)


def create_repos_from_dists_option_g(config, degenerate=False):
    """
    :param config:  Configuration parameters :: B.Bunch
    :param degenerate:  Is the dists to be degenerated?

    see also: rpmkit.myrepo.parser.parse_dists_option
    """
    dists_s = config.dists
    logging.debug("config.dists=" + dists_s)

    # dists :: [(dist_name, dist_ver, dist_arch, bdist)]
    dists = P.parse_dists_option(dists_s)
    logging.debug("dists: " + str(dists))

    if degenerate:
        dists = _degenerate_dists_g(dists)
    else:
        dists = (_listify_arch(*d) for d in dists)

    for dist in dists:
        (dname, dver, archs, bdist) = dist

        logging.debug(
            "Creating repo: dname=%s, dver=%s, archs=%s, bdist=%s" % \
                (dname, dver, archs, bdist)
        )
        yield R.Repo(
            config.server,
            config.user,
            config.email,
            config.fullname,
            dname,
            dver,
            archs,
            config.name,
            config.subdir,
            config.topdir,
            config.baseurl,
            config.signkey,
            bdist,
            config.metadata_expire,
            config.timeout,
            config.genconf,
        )


def opt_parser():
    defaults = C.init()
    distribution_choices = defaults["distribution_choices"]

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...] [SRPM]

Commands: i[init], b[uild], d[eploy], u[pdate], genc[onf]

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
    iog.add_option('', "--genconf", action="store_true",
        help="Run genconf command automatically after initialization finished")
    iog.add_option('', "--no-genconf", action="store_false", dest="genconf",
        help="Do not run genconf command after initialization finished")
    p.add_option_group(iog)

    return p


def do_command(cmd, repos_g, srpm=None):
    """
    :param cmd: sub command name :: str
    :param repos_g: Repository objects (generator)
    :param srpm: path to the target src.rpm :: str
    """
    f = getattr(CMD, cmd)
    threads = []

    for repo in repos_g:
        args = (repo, ) if srpm is None else (repo, srpm)

        thread = threading.Thread(target=f, args=args)
        thread.start()

        threads.append(thread)

    time.sleep(G.MIN_TIMEOUT)

    for thread in threads:
        # it will block.
        thread.join()

        # Is there any possibility thread still live?
        if thread.is_alive():
            logging.info("Terminating the thread")

            thread.join()


def main(argv=sys.argv):
    (CMD_INIT, CMD_UPDATE, CMD_BUILD, CMD_DEPLOY, CMD_GEN_CONF_RPMS) = \
        ("init", "update", "build", "deploy", "genconf")

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

    elif a0.startswith("genc"):
        cmd = CMD_GEN_CONF_RPMS
    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)

    if options.config:
        params = C.init(options.config)

        p.set_defaults(**params)

        # re-parse to overwrite configurations with given options.
        (options, args) = p.parse_args()

    config = B.Bunch(options.__dict__.copy())

    if args[1:]:
        srpm = args[1]
        repos_g = create_repos_from_dists_option_g(config, R.is_noarch(srpm))
        do_command(cmd, repos_g, srpm)
    else:
        repos_g = create_repos_from_dists_option_g(config, True)
        do_command(cmd, repos_g)

    sys.exit()


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4 ts=4 et:
