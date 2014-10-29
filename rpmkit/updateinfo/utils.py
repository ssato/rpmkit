#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
import codecs
import datetime
import logging
import os.path
import os
import re
import tempfile

try:
    import bsddb
except ImportError:
    bsddb = None

try:
    _MODE_RO = eval('0o444')
except SyntaxError:  # Older python (2.4.x in RHEL 5) doesn't like the above.
    _MODE_RO = eval('0444')

# cmp is missing in python >= 3.0.
try:
    cmp
except NameError:
    def cmp(a, b):
        return (a > b) - (a < b)

RPMDB_SUBDIR = "var/lib/rpm"


def noop(*args, **kwargs):
    pass


class JST(datetime.tzinfo):
    def utcoffset(self, *args):
        return datetime.timedelta(hours=9)

    def dst(self, *args):
        return datetime.timedelta(0)

    def tzname(self, *args):
        return "JST"


LOG_FORMAT = "%(asctime)s %(name)s: [%(levelname)s] %(message)s"


def logger_init(name=None, level=logging.WARN, fmt=LOG_FORMAT):
    if fmt is not None:
        logging.basicConfig(format=fmt)

    lgr = logging.getLogger(name)
    lgr.setLevel(level)

    return lgr


def local_timestamp(tz=JST()):
    return datetime.datetime.now(tz).strftime("%c %Z")


def fileopen(path, flag='r', encoding="utf-8"):
    return codecs.open(path, flag, encoding)


def _is_bsd_hashdb(dbpath):
    """
    TODO: Is this enough to check if given file ``dbpath`` is RPM DB file ?
    And also, maybe some db files should be opened w/ bsddb.btopen instead of
    bsddb.hashopen.

    >>> if os.path.exists("/etc/redhat-release"):
    ...     _is_bsd_hashdb("/var/lib/rpm/Packages")
    True
    """
    try:
        if bsddb is None:
            return True  # bsddb is not avialable in python3.

        bsddb.hashopen(dbpath, 'r')
    except:
        logging.warn("Not a Berkley DB?: %s" % dbpath)
        return False

    return True


def is_rhel_or_fedora(relfile="/etc/redhat-release"):
    return os.path.exists(relfile)


def mkdtemp(prefix="rpmkit-", dir="/tmp"):
    return tempfile.mkdtemp(dir=dir, prefix=prefix)


# It may depends on the versions of rpm:
_RPM_DB_FILENAMES = ["Packages", "Basenames", "Dirnames", "Installtid", "Name",
                     "Obsoletename", "Providename", "Requirename"]


def check_rpmdb_root(root, readonly=True, dbnames=_RPM_DB_FILENAMES):
    """
    :param root: The pivot root directry where target's RPM DB files exist.
    :param readonly: Ensure RPM DB files readonly.
    :return: True if necessary setup was done w/ success else False
    """
    assert root != "/",  "Do not run this for host system's RPM DB!"

    rpmdbdir = os.path.join(root, RPMDB_SUBDIR)

    if not os.path.exists(rpmdbdir):
        logging.error("RPM DB dir %s does not exist!" % rpmdbdir)
        return False

    pkgdb = os.path.join(rpmdbdir, "Packages")
    if not _is_bsd_hashdb(pkgdb):
        logging.error("%s does not look a RPM DB (Packages) file!" % pkgdb)
        return False

    for dbn in dbnames:
        dbpath = os.path.join(rpmdbdir, dbn)

        if not os.path.exists(dbpath):
            # NOTE: It's not an error at once.
            logging.info("RPM DB %s looks missing" % dbn)

        if readonly and os.access(dbpath, os.W_OK):
            logging.info("Drop write access perm from %s " % dbn)
            os.chmod(dbpath, _MODE_RO)

    return True


RHERRATA_RE = re.compile(r"^RH[SBE]A-\d{4}[:-]\d{4}(?:-\d+)?$")


def errata_url(advisory):
    """
    :param errata: Red Hat Errata Advisory name :: str

    >>> errata_url("RHSA-2011:1073")
    'http://rhn.redhat.com/errata/RHSA-2011-1073.html'
    >>> errata_url("RHSA-2007:0967-2")
    'http://rhn.redhat.com/errata/RHSA-2007-0967.html'
    """
    assert isinstance(advisory, str), "Not a string: %s" % str(advisory)
    assert RHERRATA_RE.match(advisory), "Not a errata advisory: %s" % advisory

    if advisory[-2] == "-":  # degenerate advisory names
        advisory = advisory[:-2]

    return "http://rhn.redhat.com/errata/%s.html" % advisory.replace(':', '-')


RHSA_SEV_MAP = dict(Critical=0, Important=1, Moderate=2, Low=3)


def rhsa_sev_to_int(sev, sevmap=RHSA_SEV_MAP):
    return sevmap.get(sev, 100)


def errata_type_to_int(adv):
    if adv.startswith("RHSA"):
        return 0
    elif adv.startswith("RHBA"):
        return 1
    else:
        return 2


def cmp_errata(lhs, rhs):
    """
    :param lhs: A dict represents errata info
    :param rhs: Likewise

    >>> lhs = dict(advisory="RHSA-2009:1238", severity="Important")
    >>> rhs = dict(advisory="RHSA-2009:1364", severity="Low")
    >>> cmp_errata(lhs, rhs)
    -1
    >>> rhs2 = dict(advisory="RHBA-2009:1403", )
    >>> cmp_errata(lhs, rhs2)
    -1
    """
    lhs_adv = lhs["advisory"]
    rhs_adv = rhs["advisory"]

    if lhs_adv[:4] == rhs_adv[:4]:
        lhs_sev = lhs.get("severity")
        if lhs_sev:
            rhs_sev = rhs.get("severity")
            return cmp(rhsa_sev_to_int(lhs_sev), rhsa_sev_to_int(rhs_sev))

        return cmp(lhs_adv, rhs_adv)
    else:
        return cmp(errata_type_to_int(lhs_adv), errata_type_to_int(rhs_adv))

# vim:sw=4:ts=4:et:
