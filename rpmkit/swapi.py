#
# Like utils/spacewalk-api, call Spacewalk/RHN RPC API from command line.
#
# Copyright (C) 2010 Satoru SATOH <satoru.satoh at gmail.com>
# Copyright (C) 2011 - 2013 Satoru SATOH <ssato at redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
#
# [Features]
#
# * Can call every Spacewalk/RHN RPC APIs with or without arguments from
#   command line.
#
# * If API needs arguments, you can pass them in comma separated strings or
#   JSON data.
#
# * API call results are output in JSON by default to enable post-processing of
#   that data by this script itself or another program.
#
# * Result outputs are easily customizable in python string format expression
#   as needed.
#
# * Utilize config file to save authentication parameters to cut out the need
#   of typing these parameters every time.
#
# * API call results are cached by default and it will drastically reduce the
#   time to get same resutls next time.
#
# * Can call an API with multiple different arguments sets at once.
#
from itertools import takewhile, izip, groupby
from operator import itemgetter

import BeautifulSoup
import ConfigParser as configparser
import cPickle as pickle
import commands
import datetime
import getpass
import glob
import logging
import optparse
import os
import os.path
import pprint
import random
import re
import shlex
import subprocess
import sys
import time
import urllib2
import xmlrpclib

try:
    from hashlib import md5  # python 2.5+
except ImportError:
    from md5 import md5

try:
    import json
except ImportError:
    import simplejson as json

try:
    all
except NameError:
    def all(xs):
        for x in xs:
            if not x:
                return False

        return True

try:
    from collections import OrderedDict as dict
except ImportError:
    pass

try:
    import tablib
    TABLIB_FOUND = True
except ImportError:
    TABLIB_FOUND = False

try:
    from rpmkit.memoize import memoize
except ImportError:
    def memoize(fn):
        """memoization decorator.
        """
        cache = {}

        def wrapped(*args, **kwargs):
            key = repr(args) + repr(kwargs)
            if key not in cache:
                cache[key] = fn(*args, **kwargs)

            return cache[key]

        return wrapped


"""
Examples:

$ ./swapi.py --args=10821 packages.listDependencies
[
  {
    "dependency": "/usr/bin/perl",
    "dependency_modifier": " ",
    "dependency_type": "requires"
  },

    ... (snip) ...

  {
    "dependency": "cvsmapfs",
    "dependency_modifier": "= 1.3-7",
    "dependency_type": "provides"
  }
]
$ ./swapi.py --list-args="10821,10822,10823" packages.getDetails
[
  {
    "package_size": "15653",
    "package_arch_label": "noarch",
    "package_cookie": "porkchop.redhat.com 964488467",
    "package_md5sum": "44971f49f5a521464c70038bd9641a8b",
    "package_summary": "Extension for CVS to handle links\n",
    "package_name": "cvsmapfs",
    "package_epoch": "",
    "package_checksums": {
      "md5": "44971f49f5a521464c70038bd9641a8b"
    },

    ... (snip) ...

  {
    "package_size": "3110234",
    "package_arch_label": "i386",
    "package_cookie": "porkchop.redhat.com 964465421",
    "package_md5sum": "1919a8e06ee5c0916685cd04dff20776",
    "package_summary": "SNNS documents\n",
    "package_name": "SNNS-doc",
    "package_epoch": "",
    "package_checksums": {
      "md5": "1919a8e06ee5c0916685cd04dff20776"
    },
    "package_payload_size": "5475688",
    "package_version": "4.2",
    "package_license": "Free Software",
    "package_vendor": "Red Hat, Inc.",
    "package_release": "7",
    "package_last_modified_date": "2006-08-22 21:56:01.0",
    "package_description": "This package includes the documents in ...\n",
    "package_id": 10823,
    "providing_channels": [
      "redhat-powertools-i386-7.0",
      "redhat-powertools-i386-7.1"
    ],
    "package_build_host": "porky.devel.redhat.com",
    "package_build_date": "2000-07-24 19:07:23.0",
    "package_file": "SNNS-doc-4.2-7.i386.rpm"
  }
]
$ ./swapi.py -vv --args=10821 \
> -F "%(dependency)s:%(dependency_type)s" packages.listDependencies
DEBUG:root: config_file = /home/ssato/.swapi/config
DEBUG:root: profile = 'None'
DEBUG:root: Call: api=packages.listDependencies, args=(10821,)
DEBUG:root: Loading cache: method=packages.listDependencies, args=(10821,)
DEBUG:root: Found query result cache
/usr/bin/perl:requires
cvs:requires
perl:requires
rpmlib(CompressedFileNames):requires
rpmlib(PayloadFilesHavePrefix):requires
cvsmapfs:provides
$
$ ./swapi.py -A '["rhel-i386-server-5","2010-04-01 08:00:00"]' \
> --format "%(package_name)s" channel.software.listAllPackages
kdebase
kdebase-devel
kexec-tools
krb5-devel
krb5-libs
krb5-server
krb5-workstation
lvm2
nss_db
sudo
wireshark
wireshark-gnome
$
$ ./swapi.py -A 10170***** -I 0 system.getDetails
[{"building": "", "profile_name": "rhel-5-3-guest-1.net-1.local", ...}]
$ ./swapi.py -A '[10*****,{"city": "tokyo", "rack": "ep7"}]' system.setDetails
[
  1
]
$ ./swapi.py -A 10170***** -I 0 system.getDetails
[{"building": "", ..."OS: redhat-release\nRelease: 5Server\n"...}]
$ ./swapi.py -A 10170***** -I 0 --no-cache system.getDetails
[{"building": "", ..."OS: redhat-release\nRelease: 5Server\n"...}]
$

"""


PROTO = 'https'
TIMEOUT = 900

CONFIG_DIR = os.path.join(os.environ.get('HOME', '.'), '.swapi')
CONFIG = os.path.join(CONFIG_DIR, 'config')
CONFIG_FILES = glob.glob("/etc/swapi.d/*.conf") + [CONFIG]

SYSTEM_CACHE_DIR = "/var/cache/swapi"
CACHE_DIR = os.path.join(CONFIG_DIR, 'cache')
CACHE_EXPIRING_DATES = 1  # [days]


## Cache expiration dates for each APIs:
API_CACHE_EXPIRATIONS = {
    # api method: expiration dates (0: no cache [default], 1.. days
    # or -1: permanent)
    "activationkey.getDetails": 1,
    "activationkey.listActivatedSystems": 1,
    "activationkey.listActivationKeys": 1,
    "activationkey.listConfigChannels": 1,
    "api.getApiCallList": 100,
    "api.getApiNamespaceCallList": 100,
    "api.getApiNamespaces": 100,
    "api.getVersion": 100,
    "api.systemVersion": 100,
    "channel.listAllChannels": 100,
    "channel.listMyChannels": 100,
    "channel.listPopularChannels": 100,
    "channel.listRedHatChannels": 100,
    "channel.listRetiredChannels": 100,
    "channel.listSharedChannels": 100,
    "channel.listSoftwareChannels": 100,
    "channel.access.getOrgSharing": 100,
    "channel.org.list": 1,
    "channel.software.getChannelLastBuildById": 1,
    "channel.software.getDetails": 1,
    "channel.software.listAllPackages": 1,
    "channel.software.listAllPackagesByDate": 1,
    "channel.software.listArches": 1,
    "channel.software.listChildren": 1,
    "channel.software.listErrata": 1,
    "channel.software.listErrataByType": 1,
    "channel.software.listLatestPackages": 1,
    "channel.software.listSystemChannels": 1,
    "configchannel.channelExists": 1,
    "configchannel.getDetails": 1,
    "configchannel.listFiles": 1,
    "configchannel.listGlobals": 1,
    "configchannel.listSubscribedSystems": 1,
    "configchannel.lookupChannelInfo": 1,
    "configchannel.lookupFileInfo": 1,
    "distchannel.listDefaultMaps": 100,
    "errata.applicableToChannels": 1,
    "errata.bugzillaFixes": 100,
    "errata.findByCve": 10,
    "errata.getDetails": 10,  # FIXME: How frequent errata updates?
    "errata.listAffectedSystems": 1,
    "errata.listByDate": 1,
    "errata.listCves": 100,
    "errata.listKeywords": 10,
    "errata.listPackages": 100,
    "errata.listUnpublishedErrata": 10,
    "kickstart.findKickstartForIp": 1,
    "kickstart.listAllIpRanges": 100,
    "kickstart.listKickstartableChannels": 10,
    "kickstart.listKickstartableTrees": 10,
    "kickstart.listKickstarts": 10,
    "kickstart.filepreservation.getDetails": 10,
    "kickstart.filepreservation.listAllFilePreservations": 10,
    "kickstart.keys.getDetails": 10,
    "kickstart.keys.listAllKeys": 10,
    "kickstart.profile.keys.getActivationKeys": 1,
    "kickstart.profile.software.getSoftwareList": 1,
    "kickstart.profile.system.checkConfigManagement": 1,
    "kickstart.profile.system.checkRemoteCommands": 1,
    "kickstart.profile.system.getLocale": 1,
    "kickstart.profile.system.getPartitioningScheme": 1,
    "kickstart.profile.system.getRegistrationType": 1,
    "kickstart.profile.system.getSELinux": 1,
    "kickstart.profile.system.listFilePreservations": 1,
    "kickstart.profile.system.listKeys": 1,
    "kickstart.snippet.listAll": 100,
    "kickstart.snippet.listCustom": 100,
    "kickstart.snippet.listDefault": 100,
    "kickstart.tree.getDetails": 100,
    "kickstart.tree.list": 100,
    "kickstart.tree.listInstallTypes": 100,
    "org.getDetails": 100,
    "org.listOrgs": 100,
    "org.listSoftwareEntitlements": 100,
    "org.listSoftwareEntitlementsForOrg": 100,
    "org.listSystemEntitlements": 100,
    "org.listSystemEntitlementsForOrg": 100,
    "org.listUsers": 100,
    "org.trusts.getDetails": 100,
    "org.trusts.listChannelsConsumed": 1,
    "org.trusts.listChannelsProvided": 100,
    "org.trusts.listOrgs": 100,
    "org.trusts.listSystemsAffected": 1,
    "org.trusts.listTrusts": 100,
    "packages.findByNvrea": -1,
    "packages.getDetails": 1,
    "packages.getPackage": -1,
    "packages.getPackageUrl": -1,
    "packages.listChangelog": -1,
    "packages.listDependencies": -1,
    "packages.listFiles": -1,
    "packages.listProvidingChannels": -1,
    "packages.listProvidingErrata": -1,
    "packages.provider.list": 100,
    "packages.provider.listKeys": 100,
    "packages.search.advanced": 1,
    "packages.search.advancedWithActKey": 1,
    "packages.search.advancedWithChannel": 1,
    "packages.name": 1,
    "packages.nameAndDescription": 1,
    "packages.nameAndSummary": 1,
    "preferences.locale.listLocales": -1,
    "preferences.locale.listTimeZones": -1,
    "proxy.isProxy": -1,
    "proxy.listAvailableProxyChannels": -1,
    "satellite.getCertificateExpirationDate": 1,
    "satellite.listEntitlements": 1,
    "satellite.listProxies": 1,
    "schedule.listAllActions": 1,
    "schedule.listArchivedActions": 1,
    "schedule.listCompletedActions": 1,
    "schedule.listCompletedSystems": 1,
    "schedule.listFailedActions": 1,
    "schedule.listFailedSystems": 1,
    "schedule.listInProgressActions": 1,
    "schedule.listInProgressSystems": 1,
    "schedule.rescheduleActions": 1,
    "system.comparePackageProfile": 1,
    "system.comparePackages": 1,
    "system.downloadSystemId": 100,
    "system.getConnectionPath": 100,
    "system.getCpu": -1,
    "system.getCustomValues": 100,
    "system.getDetails": 100,
    "system.getDevices": 100,
    "system.getDmi": -1,
    "system.getEntitlements": 100,
    "system.getEventHistory": 1,
    "system.getId": -1,
    "system.getMemory": 100,
    "system.getName": -1,
    "system.getNetwork": -1,
    "system.getNetworkDevices": -1,
    "system.getRegistrationDate": -1,
    "system.getRelevantErrata": 1,
    "system.getRelevantErrataByType": 1,
    "system.getRunningKernel": 1,
    "system.getScriptResults": 1,
    "system.getSubscribedBaseChannel": 100,
    "system.getUnscheduledErrata": 100,
    "system.getVariables": 100,
    "system.isNvreInstalled": 100,
    "system.listActivationKeys": -1,
    "system.listActiveSystems": 1,
    "system.listAdministrators": -1,
    "system.listBaseChannels": -1,
    "system.listChildChannels": 100,
    "system.listDuplicatesByHostname": 1,
    "system.listDuplicatesByIp": 1,
    "system.listDuplicatesByMac": 1,
    "system.listEligibleFlexGuests": 1,
    "system.listFlexGuests": 1,
    "system.listGroups": 1,
    "system.listInactiveSystems": 1,
    "system.listLatestAvailablePackage": 1,
    "system.listLatestInstallablePackages": 1,
    "system.listLatestUpgradablePackages": 1,
    "system.listNewerInstalledPackages": 1,
    "system.listNotes": 1,
    "system.listOlderInstalledPackages": 1,
    "system.listOutOfDateSystems": 1,
    "system.listPackageProfiles": 1,
    "system.listPackages": 1,
    "system.listPackagesFromChannel": 1,
    "system.listSubscribableBaseChannels": 100,
    "system.listSubscribableChildChannels": 100,
    "system.listSubscribedChildChannels": 100,
    "system.listSystemEvents": 1,
    "system.listSystems": 1,
    "system.listSystemsWithPackage": 1,
    "system.listUngroupedSystems": 1,
    "system.listUserSystems": 1,
    "system.listVirtualGuests": 1,
    "system.listVirtualHosts": 1,
    "system.searchByName": 1,
    "system.whoRegistered": 1,
    "system.config.listChannels": 1,
    "system.config.listFiles": 1,
    "system.config.lookupFileInfo": 1,
    "system.custominfo.listAllKeys": 1,
    "system.provisioning.snapshot.listSnapshotConfigFiles": 1,
    "system.provisioning.snapshot.listSnapshotPackages": 1,
    "system.provisioning.snapshot.listSnapshots": 1,
    "system.search.deviceDescription": 1,
    "system.search.deviceDriver": 1,
    "system.search.deviceId": 1,
    "system.search.deviceVendorId": 1,
    "system.search.hostname": 1,
    "system.search.ip": 1,
    "system.search.nameAndDescription": 1,
    "systemgroup.getDetails": 100,
    "systemgroup.listActiveSystemsInGroup": 1,
    "systemgroup.listAdministrators": 100,
    "systemgroup.listAllGroups": 1,
    "systemgroup.listGroupsWithNoAssociatedAdmins": 1,
    "systemgroup.listInactiveSystemsInGroup": 1,
    "systemgroup.listSystems": 1,
    "user.getDetails": 100,
    "user.getLoggedInTime": 1,
    "user.listAssignableRoles": 100,
    "user.listAssignedSystemGroups": 100,
    "user.listDefaultSystemGroups": 100,
    "user.listRoles": 100,
    "user.listUsers": 100,
    # Virtual (extended) RPC APIs:
    #"swapi.errata.getCvss": 100,  # TODO: Implement this.
    "swapi.cve.getCvss": 100,
    "swapi.cve.getAll": 1,
    "swapi.errata.getAll": 1,
    "swapi.bugzilla.getDetails": 1,
}

VIRTUAL_APIS = dict()

# @see http://www.first.org/cvss/cvss-guide.html
# AV:L/AC:N/Au:N/C:N/I:N/A:C
# AC:N/Au:N/C:N/I:N/A:C
CVSSS_METRICS_MAP = dict(
    AV=dict(
        label="Access Vector",
        metrics=dict(  # Larger values cause higher risk.
            L=1,  # Local
            A=2,  # Adjacent Network, e.g. LAN
            N=3   # Network
        ),
    ),
    AC=dict(
        label="Access Complexity",
        metrics=dict(
            H=1,  # High
            M=2,  # Medium
            L=3,  # Low
        ),
    ),
    Au=dict(
        label="Authentication",
        metrics=dict(
            M=1,  # Multiple
            S=2,  # Single
            N=3,  # None
        ),
    ),
    C=dict(
        label="Confidentiality Impact",
        metrics=dict(
            N=1,  # None
            P=2,  # Partial
            C=3,  # Complete
        ),
    ),
    I=dict(
        label="Integrity Impact",
        metrics=dict(
            N=1,  # None
            P=2,  # Partial
            C=3,  # Complete
        ),
    ),
    A=dict(
        label="Availability Impact",
        metrics=dict(
            N=1,  # None
            P=2,  # Partial
            C=3,  # Complete
        ),
    ),
)


def str_to_id(s):
    """
    >>> str_to_id("aaa")
    '47bce5c74f589f4867dbd57e9ca9f808'
    """
    return md5(s).hexdigest()


def object_to_id(obj):
    """Object -> id.

    NOTE: Object must be able to convert to str (i.e. implements __str__).

    >>> object_to_id("test")
    '098f6bcd4621d373cade4e832627b4f6'
    >>> object_to_id({'a': "test"})
    'c5b846ec3b2f1a5b7c44c91678a61f47'
    >>> object_to_id(['a', 'b', 'c'])
    'eea457285a61f212e4bbaaf890263ab4'
    """
    return str_to_id(str(obj))


def dict_equals(d0, d1, allow_more=False):
    """
    :param d0: a dict
    :param d1: a dict
    :param allow_more: Whether to allow d0 or d1 has more items than other.

    >>> dict_equals(dict(), dict())
    True
    >>> dict_equals(dict(a=0, b=1), dict(a=0, b=1))
    True
    >>> dict_equals(dict(a=0, b=1), dict(b=1, a=0))
    True
    >>> dict_equals(dict(a=0, b=1), dict())
    False
    >>> dict_equals(dict(a=0, b=1), dict(b=1, a=0, c=2))
    False
    """
    if not allow_more and len(d0.keys()) != len(d1.keys()):
        return False

    return all(k in d1 and d0[k] == d1.get(k, None) for k in d0.keys())


def all_eq(xs):
    """Whether all items in xs (list or generator) equals each other.

    >>> all_eq([])
    False
    >>> all_eq(["a", "a", "a"])
    True
    >>> all_eq(c for c in "")
    False
    >>> all_eq(c for c in "aaba")
    False
    >>> all_eq(c for c in "aaaa")
    True
    >>> all_eq([c for c in "aaaa"])
    True
    """
    if not isinstance(xs, list):
        xs = list(xs)  # xs may be a generator...

    return all(x == xs[0] for x in xs[1:]) if xs else False


def longest_common_prefix(*args):
    """Variant of LCS = Longest Common Sub-sequence.

    For LCS, see http://en.wikipedia.org/wiki/Longest_common_substring_problem

    >>> longest_common_prefix("abc", "ab", "abcd")
    'ab'
    >>> longest_common_prefix("abc", "bc")
    ''
    """
    return ''.join(x[0] for x in takewhile(all_eq, izip(*args)))


def shorten_dict_keynames(d, prefix=None):
    """
    It seems that API key names are shortened a bit at a time. The keys having
    prefix (e.g. 'channel_') will be deprecated but still remains in the old
    code (i.e. RHN hosted).

    This function is to hide and keep backward compatibility about it.

    :param d: A dict instance.

    >>> dr0 = dict(channel_label="foo-channel", channel_name="Foo Channel")
    >>> dr1 = dict(CHANNEL_LABEL="foo-channel", CHANNEL_NAME="Foo Channel")
    >>> dr2 = dict(channel_label="foo-channel", CHANNEL_NAME="Foo Channel")
    >>> d_ref = dict(label="foo-channel", name="Foo Channel")

    >>> d1 = shorten_dict_keynames(dr0, "channel_")
    >>> d2 = shorten_dict_keynames(dr0)
    >>> d3 = shorten_dict_keynames(dr1, "channel_")
    >>> d4 = shorten_dict_keynames(dr1)
    >>> d5 = shorten_dict_keynames(dr2, "channel_")
    >>> d6 = shorten_dict_keynames(dr2)

    >>> assert dict_equals(d_ref, d1)
    >>> assert dict_equals(d_ref, d2)
    >>> assert dict_equals(d_ref, d3)
    >>> assert dict_equals(d_ref, d4)
    >>> assert dict_equals(d_ref, d5)
    >>> assert dict_equals(d_ref, d6)
    """
    if not isinstance(d, dict):  # `dic` may be a str.
        return d

    if prefix is None:
        prefix = longest_common_prefix(*(k.lower() for k in d.keys()))

    return dict((k.lower().replace(prefix, ''), v) for k, v in d.iteritems())


def urlread(url, data=None, headers={}):
    """
    Open given url and returns its contents or None.
    """
    req = urllib2.Request(url=url, data=data, headers=headers)

    try:
        return urllib2.urlopen(req).read()
    except:
        return None


def cve2url(cve):
    """
    >>> url = "https://access.redhat.com/security/cve/CVE-2010-1585?lang=en"
    >>> assert url == cve2url("CVE-2010-1585")
    """
    return "https://access.redhat.com/security/cve/%s?lang=en" % cve


def cvss_metrics(cvss, metrics_map=CVSSS_METRICS_MAP):
    """
    TODO: Some of CVEs in Red Hat CVE database look having wrong CVSS
    metrics data.

    >>> ms0 = cvss_metrics("AV:N/AC:H/Au:N/C:N/I:P/A:N")
    >>> ms_ref = [
    ...     ("Access Vector", 3), ("Access Complexity", 1),
    ...     ("Authentication", 3), ("Confidentiality Impact", 1),
    ...     ("Integrity Impact", 2), ("Availability Impact", 1),
    ... ]
    >>> assert ms0 == ms_ref, str(ms0)

    >>> ms1 = cvss_metrics("AV:N/AC:H/AU:N/C:N/I:P/A:N")  # CVE-2012-3406
    >>> assert ms1 == ms_ref, str(ms1)

    >>> ms2 = cvss_metrics("AV:N/AC:H/Au/N/C:N/I:P/A:N")  # CVE-2012-5077
    >>> assert ms2 == ms_ref, str(ms2)

    >>> ms3 = cvss_metrics("AV:N/AC:N/Au/N/C:P/I:N/A:N")  # CVE-2012-3375
    >>> assert ms3 != ms_ref, str(ms3)
    """
    metrics = []

    if "/AU:" in cvss:
        cvss = cvss.replace("/AU:", "/Au:")

    if "/Au/" in cvss:
        cvss = cvss.replace("/Au/", "/Au:")

    for lms in cvss.split("/"):
        (key, m) = lms.split(":")
        metric = metrics_map.get(key, False)

        if not metric:
            logging.error("Unknown CVSS metric abbrev: " + key)
            return metrics

        label = metric["label"]
        val = metric["metrics"].get(m, False)

        if not val:
            logging.error(
                "Uknown value for CVSS metric '%s': %s" % (metric, m)
            )
            return metrics

        metrics.append((label, val))

    return metrics


def get_cvss_for_cve(cve):
    """
    Get CVSS data for given cve from the Red Hat www site.

    :param cve: CVE name, e.g. "CVE-2010-1585" :: str
    :return:  {"metrics": base_metric :: str, "score": base_score :: str}

    See the HTML source of CVE www page for its format, e.g.
    https://www.redhat.com/security/data/cve/CVE-2010-1585.html.
    """
    def has_cvss_link(tag):
        return tag.get("href", "").startswith("http://nvd.nist.gov/cvss.cfm")

    def is_base_score(tag):
        return tag.string == "Base Score:"

    url_fmt = "http://nvd.nist.gov/cvss.cfm?version=2&name=%s&vector=(%s)"

    try:
        data = urlread(cve2url(cve))
        soup = BeautifulSoup.BeautifulSoup(data)

        cvss_base_metrics = soup.findAll(has_cvss_link)[0].string
        cvss_base_score = soup.findAll(is_base_score)[0].parent.td.string

        # may fail to parse `cvss_base_metrics`
        cvss_base_metrics_vec = cvss_metrics(cvss_base_metrics)

        return dict(cve=cve,
                    metrics=cvss_base_metrics,
                    metrics_v=cvss_base_metrics_vec,
                    score=cvss_base_score,
                    url=url_fmt % (cve, cvss_base_metrics))

    except Exception, e:
        logging.warn(" Could not get CVSS data: err=" + str(e))

    return None


def get_all_cve_g(raw=False):
    """
    Get CVE and CVSS data from Red Hat www site:
      https://www.redhat.com/security/data/metrics/cve_dates.txt

    :param raw: Get raw txt data if True [False]

    It yields {"cve", "metrics" (cvss2 base metric), "score" (cvss2 score),
    "url" (cve url), }.

    cve_dates.txt format:

    CVE-2000-0909 public=20000922
    CVE-2000-0913 public=20000929,impact=important
    ...
    CVE-2008-1926 source=redhat,reported=20080419,public=20080421,impact=low
    ...
    CVE-2009-0778 ...,impact=important,cvss2=7.1/AV:N/AC:M/Au:N/C:N/I:N/A:C
    CVE-2009-1302 ...,cvss2=6.8/AV:N/AC:M/Au:N/C:P/I:P/A:P
    CVE-2009-1303 ...,cvss2=6.8/AV:N/AC:M/Au:N/C:P/I:P/A:P,impact...
    """
    cve_reg = r"^(?P<cve>CVE-\d+-\d+) .*"
    cve_cvsss_reg = cve_reg + \
        r"cvss2=(?P<score>[^/]+)/(?P<metrics>AV:[^,]+A:(?:N|P|C)).*"
    cvss_marker = "cvss2="
    url = "https://www.redhat.com/security/data/metrics/cve_dates.txt"

    try:
        data = urlread(url)
        if raw:
            for line in data.splitlines():
                yield line
        else:
            for line in data.splitlines():
                if not line or line.startswith("#"):
                    continue

                if cvss_marker in line:
                    m = re.match(cve_cvsss_reg, line)
                else:
                    m = re.match(cve_reg, line)

                if m:
                    d = m.groupdict()
                    d["url"] = d["cve_url"] = cve2url(d["cve"])
                else:
                    logging.warn("Not look a valid CVE line: " + line)
                    d = None

                yield d

    except Exception, e:
        logging.warn(" Could not get CVE and CVSS data: err=" + str(e))
        yield  # None


def get_all_cve(raw=False):
    return [r for r in get_all_cve_g(raw) if r is not None]


def get_all_errata_g(raw=False):
    """
    Get errata vs. CVEs data from Red Hat www site:
      https://www.redhat.com/security/data/metrics/rhsamapcpe.txt

    :param raw: Get raw txt data if True [False]

    It returns {errata_advisory: ["cve"]}

    rhsamapcpe.txt format:

    RHSA-2012:1023 CVE-2011-4605 cpe:/a:redhat:jboss_enterprise_web_platfor...
    RHSA-2012:1022 CVE-2011-4605 cpe:/a:redhat:jboss_enterprise_application...
    RHSA-2012:1019 CVE-2012-0551,CVE-2012-1711,...,CVE-2012-1726 cpe:/a:re:...
    RHSA-2012:1014 CVE-2012-1167 cpe:/a:redhat:jboss_enterprise_web_platfor...
    """
    advisory_prefix = "RH"
    cve_prefix = "CVE-"
    url = "https://www.redhat.com/security/data/metrics/rhsamapcpe.txt"

    try:
        data = urlread(url)
        if raw:
            for line in data.splitlines():
                yield line
        else:
            for line in data.splitlines():
                if not line.startswith(advisory_prefix):
                    continue

                try:
                    (adv, cves, cpe) = line.split()
                    assert cves.startswith(cve_prefix)

                    yield {"advisory": adv, "cves": cves.split(","), }

                except (IndexError, AssertionError):
                    logging.warn("Invalid line: " + line)
                    continue

    except Exception, e:
        logging.warn(" Could not get Errata vs. CVEs data: err=" + str(e))


def get_all_errata(raw=False):
    return [r for r in get_all_errata_g(raw)]


_BZ_KEYS = ["bug_id", "summary", "priority", "severity"]


def get_bugzilla_info(bzid, *keys):
    """
    Get bugzilla info of given ID.

    :param bzid: Bugzilla ID
    :param keys: Bugzilla fields to get info
    """
    default = dict()
    if not keys:
        keys = _BZ_KEYS

    try:
        ofs = "\n".join('%s %%{%s}' % (k, k) for k in keys)

        # wait a little to avoid DoS attack to the server if called
        # multiple times.
        time.sleep(random.random() * 5)

        uri = os.environ.get("BUGZILLA_URI", '')
        bzcmd = "bugzilla --bugzilla=" + uri if uri else "bugzilla"

        c = bzcmd + " query --bug_id=%s --outputformat='%s'" % (bzid, ofs)
        logging.info(" bz: " + c[:c.rfind('\n')] + "...")
        o = subprocess.check_output(c, shell=True)

        if not o:
            return default

        return dict(zip(keys, [l.split(' ', 1)[-1] for l in o.splitlines()]))

    except subprocess.CalledProcessError:
        return default


VIRTUAL_APIS["swapi.cve.getCvss"] = get_cvss_for_cve
VIRTUAL_APIS["swapi.cve.getAll"] = get_all_cve
VIRTUAL_APIS["swapi.errata.getAll"] = get_all_errata
VIRTUAL_APIS["swapi.bugzilla.getDetails"] = get_bugzilla_info


def run(cmd_str):
    return commands.getstatusoutput(cmd_str)


def id_(x):
    return x


class Cache(object):
    """Pickle module based data caching backend.
    """

    def __init__(self, domain, topdir=CACHE_DIR,
                 expirations=API_CACHE_EXPIRATIONS):
        """Initialize domain-local caching parameters.

        :param domain: a str represents target domain
        :param topdir: topdir to save cache files
        :param expirations: Cache expiration dates map
        """
        self.domain = domain
        self.topdir = os.path.join(topdir, domain)
        self.expirations = expirations

    def dir(self, obj):
        """Resolve the dir in which cache file of the object is saved.
        """
        oid = object_to_id(obj)

        oid0 = oid[0]
        oid1 = oid[1]
        oid_rest = oid[2:]

        return os.path.join(self.topdir, oid0, oid1, oid_rest)

    def path(self, obj):
        """Resolve path to cache file of the object.
        """
        return os.path.join(self.dir(obj), "cache.pkl")

    def load(self, obj):
        try:
            return pickle.load(open(self.path(obj), "rb"))
        except:
            return None

    def save(self, obj, data, protocol=pickle.HIGHEST_PROTOCOL):
        """
        :param obj:  object of which obj_id is used as caching key
        :param data: data to saved in cache
        """
        cache_dir = self.dir(obj)

        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir, mode=0700)

        cache_path = self.path(obj)

        try:
            # TODO: How to detect errors during/after pickle.dump.
            pickle.dump(data, open(cache_path, "wb"), protocol)
            logging.debug(" Saved in " + cache_path)
            return True
        except:
            return False

    def needs_update(self, obj, obj2key=id_):
        """
        :param obj: Cache key object
        :param obj2key: Any callables convert obj to key for expirations map.
        """
        key = obj2key(obj)
        expires = self.expirations.get(key, 0)  # Default: no cache
        logging.debug(" Expiration dates for %s: %d" % (key, expires))

        if expires == 0:  # it means never cache.
            return True

        if expires < 0:  # it meens cache never expire.
            return False

        if not os.path.exists(self.path(obj)):
            logging.info(" Cache file not found for " + str(obj))
            return True

        try:
            mtime = os.stat(self.path(obj)).st_mtime
        except OSError:  # It indicates that the cache file cannot be updated.
            return True  # FIXME: How to handle the above case?

        cur_time = datetime.datetime.now()
        cache_mtime = datetime.datetime.fromtimestamp(mtime)

        # Cache looks created in the future. Update it later to fix its mtime.
        if cur_time < cache_mtime:
            return True

        return (cur_time - cache_mtime) >= datetime.timedelta(expires)


class ReadOnlyCache(Cache):

    def save(self, *args, **kwargs):
        logging.debug(" Not save as read-only cache: " + self.topdir)
        return True

    def needs_update(self, *args, **kwargs):
        logging.debug(" No updates needed as read-only cache: " + self.topdir)
        return False


class RpcApi(object):
    """Spacewalk / RHN XML-RPC API server object.
    """

    def __init__(self, conn_params, enable_cache=True, cachedir=CACHE_DIR,
                 debug=False, readonly=False, cacheonly=False, force=False,
                 vapis=VIRTUAL_APIS):
        """
        :param conn_params: Connection parameters: server, userid, password,
            timeout, protocol.
        :param enable_cache: Whether to enable query result cache or not.
        :param cachedir: Cache saving directory
        :param debug: Debug mode
        :param readonly: Use read only cache
        :param cacheonly: Get results only from cache (w/o any access to RHNS)
        :param force: Force update caches even if these cached data are new and
            not need updates
        :param vapis: Virtual APIs :: dict
        """
        self.url = "%(protocol)s://%(server)s/rpc/api" % conn_params
        self.userid = conn_params.get("userid")
        self.passwd = conn_params.get("password")
        self.timeout = conn_params.get("timeout")

        self.sid = None
        self.debug = debug
        self.readonly = readonly
        self.cacheonly = cacheonly
        self.force = force
        self.vapis = vapis

        if enable_cache:
            cachecls = ReadOnlyCache if self.readonly else Cache
            cdomain = str_to_id("%s:%s" % (self.url, self.userid))

            self.caches = [
                ReadOnlyCache(cdomain, SYSTEM_CACHE_DIR),
                cachecls(cdomain, cachedir),
            ]
        else:
            self.caches = []

    def __del__(self):
        self.logout()

    def login(self):
        try:
            self.server = xmlrpclib.ServerProxy(self.url, verbose=self.debug,
                                                use_datetime=True)
        except:
            logging.error("Failed to connect: url=" + self.url)
            raise

        try:
            self.sid = self.server.auth.login(self.userid, self.passwd,
                                              self.timeout)
        except:
            logging.error("Failed to auth: "
                          "url=%s, userid=%s" % (self.url, self.userid))
            raise

    def logout(self):
        if self.sid is None:
            return

        self.server.auth.logout(self.sid)
        self.sid = None

    def get_result_from_caches(self, key):
        obj2key = lambda obj: obj[0]  # obj = (method, args)

        if self.force:
            return None

        for cache in self.caches:
            logging.debug(" Try the cache: " + cache.topdir)
            if not self.cacheonly and cache.needs_update(key, obj2key):
                logging.debug("Cached result is old and not "
                              "used: " + str(key))
            else:
                logging.debug("Loading cache: " + str(key))
                ret = cache.load(key)

                if ret is not None:
                    logging.info("Found cached result for " + str(key))
                    return ret

            logging.debug("No cached results found: " + cache.topdir)

        return None

    def ma_to_key(self, method_name, args):
        return (method_name, args)

    def call_virtual_api(self, method_name, *args):
        ret = self.vapis[method_name](*args)

        for cache in self.caches:
            key = self.ma_to_key(method_name, args)
            cache.save(key, ret)

        return ret

    def call(self, method_name, *args):
        logging.debug(" Call: api=%s, args=%s" % (method_name, str(args)))
        key = self.ma_to_key(method_name, args)

        if self.caches:
            ret = self.get_result_from_caches(key)

            if ret is None:
                if self.cacheonly:
                    logging.warn(" Cache-only mode but got no results!")
                    return None
            else:
                return ret

        # wait a little to avoid DoS attack to the server if called
        # multiple times.
        time.sleep(random.random() * 5)

        if method_name in self.vapis:
            return self.call_virtual_api(method_name, *args)

        try:
            logging.debug(" Try accessing the server to get results")
            if self.sid is None:
                self.login()

            method = getattr(self.server, method_name)

            # Special cases which do not need session_id parameter:
            # api.{getVersion, systemVersion} and auth.login.
            if re.match(r"^(api.|proxy.|auth.login)", method_name):
                ret = method(*args)
            else:
                ret = method(self.sid, *args)

            for cache in self.caches:
                cache.save(key, ret)

            return ret

        except xmlrpclib.Fault, m:
            raise RuntimeError("rpc: method '%s', args '%s'\nError message: "
                               "%s" % (method_name, str(args), m))

    def multicall(self, method_name, argsets):
        """Quick hack to implement XML-RPC's multicall like function.

        Please note that it returns a generator not a list.

        @see xmlrpclib.MultiCall
        """
        for arg in argsets:
            yield self.call(method_name, arg)


def __parse(arg):
    """
    >>> __parse("1234567")
    1234567
    >>> __parse("abcXYZ012")
    'abcXYZ012'
    >>> d = dict(channelLabel="foo-i386-5")
    >>> d = __parse('{"channelLabel": "foo-i386-5"}')
    >>> assert d["channelLabel"] == "foo-i386-5"
    """
    try:
        if re.match(r"[1-9]\d*", arg):
            return int(arg)
        elif re.match(r"{.*}", arg):
            return json.loads(arg)  # retry with json module
        else:
            return str(arg)

    except ValueError:
        return str(arg)


def parse_api_args(args, arg_sep=','):
    """
    Simple JSON-like expression parser.

    @args     options.args :: string
    @return   rpc arg objects, [arg] :: [string]

    >>> parse_api_args('')
    []
    >>> parse_api_args("1234567")
    [1234567]
    >>> parse_api_args("abcXYZ012")
    ['abcXYZ012']

    >>> cl = '{"channelLabel": "foo-i386-5"}'
    >>> assert parse_api_args(cl)[0]["channelLabel"] == "foo-i386-5"

    >>> args = '1234567,abcXYZ012,{"channelLabel": "foo-i386-5"}'
    >>> (i, s, d) = parse_api_args(args)
    >>> assert i == 1234567
    >>> assert s == "abcXYZ012"
    >>> assert d["channelLabel"] == "foo-i386-5"

    >>> args = '[1234567,"abcXYZ012",{"channelLabel": "foo-i386-5"}]'
    >>> (i, s, d) = parse_api_args(args)
    >>> assert i == 1234567
    >>> assert s == "abcXYZ012"
    >>> assert d["channelLabel"] == "foo-i386-5"
    """
    if not args:
        return []

    try:
        x = json.loads(args)
        ret = x if isinstance(x, list) else [x]

    except ValueError:
        ret = [__parse(a) for a in parse_list_str(args, arg_sep)]

    return ret


class JSONEncoder(json.JSONEncoder):
    """@see http://goo.gl/vEwdE
    """

    # pylint: disable=E0202
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            return json.JSONEncoder.default(self, obj)
    # pylint: enable=E0202


def results_to_json_str(results, indent=2):
    """
    >>> assert results_to_json_str("abc") == '"abc"'

    #>>> results_to_json_str([123, 'abc', {'x':'yz'}], 0)
    #'[123, "abc", {"x": "yz"}]'

    >>> results_to_json_str([123, "abc", {'x': "yz"}])
    '[\\n  123, \\n  "abc", \\n  {\\n    "x": "yz"\\n  }\\n]'
    """
    return json.dumps(
        results, ensure_ascii=False, indent=indent, cls=JSONEncoder
    )


def parse_list_str(list_s, sep=","):
    """
    simple parser for a list of items separated with "," (comma) and so on.

    >>> assert parse_list_str("") == []
    >>> assert parse_list_str("a,b") == ["a", "b"]
    >>> assert parse_list_str("a,b,") == ["a", "b"]
    """
    return [p for p in list_s.split(sep) if p]


def sorted_by(ds, key):
    """
    >>> (a, b, c) = (dict(a=1, b=2), dict(a=0, b=3), dict(a=3, b=0))
    >>> ds = [a, b, c]
    >>> assert sorted_by(ds, "a") == [b, a, c]
    """
    return sorted(ds, key=itemgetter(key))


def group_by(ds, key):
    """
    >>> (a, b, c) = (dict(a=1, b=2), dict(a=0, b=3), dict(a=1, b=0))
    >>> ds = [a, b, c]
    >>> ref = dict([(1, [a, c]), (0, [b])])
    >>> assert dict_equals(group_by(ds, "a"), ref)
    """
    kf = itemgetter(key)
    return dict((k, list(g)) for k, g in groupby(sorted_by(ds, key), kf))


def select_by(ds, key, values):
    """
    >>> (a, b, c) = (dict(a=1, b=2), dict(a=0, b=3), dict(a=3, b=0))
    >>> ds = [a, b, c]
    >>> assert select_by(ds, "a", (0, 1)) == [a, b]
    """
    return [r for r in ds if r.get(key, False) in values]


def deselect_by(ds, key, values):
    """
    >>> (a, b, c) = (dict(a=1, b=2), dict(a=0, b=3), dict(a=3, b=0))
    >>> ds = [a, b, c]
    >>> assert deselect_by(ds, "a", (0, 1)) == [c]
    """
    return [r for r in ds if r.get(key, False) not in values]


CONN_DEFAULTS = dict(
    server='', userid='', password='', timeout=TIMEOUT, protocol=PROTO,
)


def configure_with_configfile(config_file, profile="", defaults=CONN_DEFAULTS):
    """
    @config_file  Configuration file path, ex. "~/.swapi/config".
    """
    server = defaults["server"]
    userid = defaults["userid"]
    password = defaults["password"]
    timeout = defaults["timeout"]
    protocol = defaults["protocol"]

    # expand "~/"
    if config_file:
        if '~' in config_file:
            config_file = os.path.expanduser(config_file)

        config_files = CONFIG_FILES + [config_file]
    else:
        config_files = CONFIG_FILES

    cp = configparser.SafeConfigParser()
    logging.debug(" Loading config files: %s" % ",".join(config_files))

    if profile:
        logging.debug(" Config profile: " + profile)

    for cfg in config_files:
        if not os.path.exists(cfg):
            logging.debug("Not found. Skipping: " + cfg)
            continue

        cp.read(cfg)
        if profile and cp.has_section(profile):
            try:
                opts = dict(cp.items(profile))
            except configparser.NoSectionError:
                continue
        else:
            opts = cp.defaults()

        server = opts.get("server", server)
        userid = opts.get("userid", userid)
        password = opts.get("password", password)
        timeout = int(opts.get("timeout", timeout))
        protocol = opts.get("protocol", protocol)

    return dict(server=server, userid=userid, password=password,
                timeout=timeout, protocol=protocol)


def set_options(key, config, opts, ask_fun, param):
    cv = config.get(key, False)
    if cv:
        v = getattr(opts, key, False)
        return v if v else cv  # Prefer value from options.
    else:
        return ask_fun(param)


def configure_with_options(config, options):
    """
    @config   config parameters dict: {'server':, 'userid':, ...}
    @options  optparse.Options
    """
    server = set_options("server", config, options,
                         raw_input, "Enter server name > ")
    userid = set_options("userid", config, options,
                         raw_input, "Enter user ID > ")
    password = set_options("password", config, options,
                           getpass.getpass, "Enter your password > ")
    timeout = set_options("timeout", config, options, id_, TIMEOUT)
    protocol = set_options("protocol", config, options, id_, PROTO)

    return dict(server=server, userid=userid, password=password,
                timeout=timeout, protocol=protocol)


def configure(options):
    conf = configure_with_configfile(options.config, options.profile)
    conf = configure_with_options(conf, options)

    return conf


HELP_PRE = """%%prog [OPTION ...] RPC_API_STRING

Examples:
  %%prog --args=10821 packages.listDependencies
  %%prog --list-args="10821,10822,10823" packages.getDetails
  %%prog -vv --args=10821 packages.listDependencies
  %%prog -P MySpacewalkProfile --args=rhel-x86_64-server-vt-5 \\
    channel.software.getDetails
  %%prog -C /tmp/s.cfg -A rhel-x86_64-server-vt-5,guest \\
    channel.software.isUserSubscribable
  %%prog -A "rhel-i386-server-5","2010-04-01 08:00:00" \\
    channel.software.listAllPackages
  %%prog -A '["rhel-i386-server-5","2010-04-01 08:00:00"]' \\
    channel.software.listAllPackages
  %%prog --format "%%(label)s" channel.listSoftwareChannels
  %%prog -A 100010021 --no-cache -F "%%(hostname)s %%(description)s" \\
    system.getDetails
  %%prog -A '[1017068053,{"city": "tokyo", "rack": "rack-A-1"}]' \\
    system.setDetails


Config file example (%s):
--------------------------------------------------------------

[DEFAULT]
server = rhn.redhat.com
userid = xyz********
password =   # it will ask you if password is not set.
timeout = 900
protocol = https

[MySpacewalkProfile]
server = my-spacewalk.example.com
userid = rpcusr
password = secretpasswd

--------------------------------------------------------------
""" % CONFIG


def option_parser(prog="swapi", tablib_found=TABLIB_FOUND):
    defaults = dict(config=None, verbose=0, timeout=TIMEOUT, protocol=PROTO,
                    rpcdebug=False, no_cache=False, cachedir=CACHE_DIR,
                    readonly=False, cacheonly=False, force=False,
                    format=False, indent=2, sort="", group="", select="",
                    deselect="", short_keys=True,
                    profile=os.environ.get("SWAPI_PROFILE", ""),
                    list=False, output="stdout")

    if tablib_found:
        defaults["output_format"] = None
        defaults["headers"] = None

    p = optparse.OptionParser(HELP_PRE, prog=prog)
    p.set_defaults(**defaults)

    config_help = "Config file path [%s; loaded in this order]" % \
        ','.join(CONFIG_FILES)

    p.add_option('-C', '--config', help=config_help)
    p.add_option('-P', '--profile',
                 help='Select profile (section) in config file')
    p.add_option('-v', '--verbose', help='verbose mode', action="count")

    cog = optparse.OptionGroup(p, "Connect options")
    cog.add_option('-s', '--server', help='Spacewalk/RHN server hostname.')
    cog.add_option('-u', '--userid', help='Spacewalk/RHN login user id')
    cog.add_option('-p', '--password', help='Spacewalk/RHN Login password')
    cog.add_option('-t', '--timeout', help='Session timeout in sec [%default]')
    cog.add_option('',   '--protocol', help='Spacewalk/RHN server protocol.')
    p.add_option_group(cog)

    xog = optparse.OptionGroup(p, "XML-RPC options")
    xog.add_option('',   '--rpcdebug', action="store_true",
                   help="XML-RPC Debug mode")
    p.add_option_group(xog)

    caog = optparse.OptionGroup(p, "Cache options")
    caog.add_option('',   '--no-cache', action="store_true",
                    help='Do not use query result cache')
    caog.add_option('', '--cachedir', help="Caching directory [%default]")
    caog.add_option('', '--readonly', action="store_true",
                    help="Use read-only cache")
    caog.add_option('', '--cacheonly', action="store_true",
                    help="Get results only from cache w/o any access to RHNS")
    caog.add_option('', '--offline', action="store_true", dest="cacheonly",
                    help="Same as --cacheonly")
    caog.add_option('', '--force', action="store_true",
                    help="Force update caches regardless of caches "
                         "expiration dates")
    p.add_option_group(caog)

    oog = optparse.OptionGroup(p, "Output options")
    oog.add_option('-L', '--list', action="store_true", help="List APIs")
    oog.add_option('-F', '--format', help="Output format (non-json)")
    oog.add_option('-o', '--output', help="Output [stdout]")

    if tablib_found:
        formats = ("json", "xls", "yaml", "csv", "tsv", "xlsx", "ods")
        oog.add_option('-O', '--output-format', choices=formats,
                       help="Select output format from: " + ", ".join(formats))
        oog.add_option('-H', '--headers',
                       help="Comma separated output headers, e.g. 'aaa,bbb'")

    oog.add_option('-I', '--indent', type="int",
                   help="Indent for JSON output. 0 means no indent. "
                        "[%default]")
    oog.add_option('', '--sort', help="Sort out results by given key")
    oog.add_option('', '--group', help="Group results by given key")
    oog.add_option('', '--select',
                   help="Select results by given key and value pair in "
                        "format " + "key:value0,value1,...")
    oog.add_option('', '--deselect',
                   help="Deselect results by given key and value pair in "
                        "format " + "key:value0,value1,...")
    oog.add_option('', '--no-short-keys', action="store_false",
                   dest="short_keys",
                   help="Do not shorten keys in results by common longest "
                        "prefix " + "[not %default]")
    p.add_option_group(oog)

    aog = optparse.OptionGroup(p, "API argument options")
    aog.add_option('-A', '--args',
                   help="Api args other than session id in comma separated "
                        "strings " + "or JSON expression [empty]")
    aog.add_option('', '--list-args', help='Specify list of API arguments')
    p.add_option_group(aog)

    return p


def init_log(verbose):
    """Initialize logging module
    """
    level = logging.WARN  # default

    if verbose > 0:
        level = logging.INFO

        if verbose > 1:
            level = logging.DEBUG

    logging.basicConfig(level=level)


def init_rpcapi(options):
    params = configure(options)
    rapi = RpcApi(
        params, not options.no_cache, options.cachedir, options.rpcdebug,
        options.readonly, options.cacheonly, options.force,
    )
    return rapi


# wrapper functions to utilize this from other programs:
def _connect(*options):
    """
    :param options: List of option strings for swapi.main,
        e.g. ["--verbose", "--cacheonly"].

    """
    argv = ["dummy_av0"] + list(options) + ["dummy_args0"]
    (opts, _) = option_parser().parse_args(argv)

    return init_rpcapi(opts)


def _call(api, args=[], options=[]):
    """
    :param api: String represents RHN or swapi's virtual API,
        e.g. "packages.listProvidingErrata", "swapi.errata.getAll"
    :param options: List of options options for swapi. see also: _connect
    :param args: An argument or list of arguments passed to API call.
        (NOTE: rpmkit.swapi.parse_api_args can be used to parse
        string contains these arguments.)

    :return: [Reult]
    """
    args = args if isinstance(args, (list, tuple)) else [args]

    rapi = connect(*options)
    res = rapi.call(api, *args)

    if res is None:
        return []

    if not (isinstance(res, list) or getattr(res, "next", False)):
        res = [res]

    return [shorten_dict_keynames(r) for r in res]


connect = memoize(_connect)
call = memoize(_call)


def main(argv, tablib_found=TABLIB_FOUND):
    out = sys.stdout
    enable_cache = True

    parser = option_parser()
    (options, args) = parser.parse_args(argv)

    init_log(options.verbose)

    if options.list:
        options.format = "%s"
        return (sorted(API_CACHE_EXPIRATIONS.keys()), options)

    if options.no_cache and options.cacheonly:
        logging.error(
            " Conflicted options were given: --no-cache and --cacheonly"
        )
        return None

    # FIXME: Breaks DRY principle:
    if tablib_found:
        ofs = ("xls", "xlsx", "ods")
        if options.output_format in ofs and options.output == "stdout":
            logging.error(" Output format '%s' requires output but not "
                          "specified w/ --output "
                          "option" % options.output_format)
            return None

    if len(args) == 0:
        parser.print_usage()
        return None

    api = args[0]
    rapi = init_rpcapi(options)

    if options.force:
        logging.info(
            "Caches will be updated regardless of its expiration dates"
        )

    if options.list_args:
        list_args = parse_api_args(options.list_args)
        res = rapi.multicall(api, list_args)
    else:
        args = parse_api_args(options.args)
        res = rapi.call(api, *args)

    if res is None:
        return []

    if not (isinstance(res, list) or getattr(res, "next", False)):
        res = [res]

    if options.short_keys:
        res = [shorten_dict_keynames(r) for r in res]

    if options.sort:
        res = sorted_by(res, options.sort)

    if options.group:
        res = group_by(res, options.group)

    if options.select:
        kvs = parse_list_str(options.select, ":")

        if len(kvs) < 2:
            sys.stderr.write(
                "Invalid value given for --select: %s\n" % options.select
            )
            sys.exit(1)

        (key, values) = kvs
        values = parse_list_str(values, ",")
        res = select_by(res, key, values)

    if options.deselect:
        kvs = parse_list_str(options.deselect, ":")

        if len(kvs) < 2:
            sys.stderr.write(
                "Invalid value given for --deselect: %s\n" % options.deselect
            )
            sys.exit(1)

        (key, values) = kvs
        values = parse_list_str(values, ",")
        res = deselect_by(res, key, values)

    return (res, options)


def realmain(argv, tablib_found=TABLIB_FOUND):
    result = main(argv[1:])

    if not result:
        print "[]"  # empty results
        return 0

    (res, options) = result

    if options.format:
        if options.output == 'stdout':
            for r in res:
                print options.format % r
        else:
            with open(options.output, 'w') as f:
                for r in res:
                    print >> f, options.format % r
    else:
        if tablib_found and options.output_format:
            data = tablib.Dataset()

            if options.headers:
                data.headers = options.headers.split(",")
                for r in res:
                    data.append([r.get(h) for h in data.headers])
            else:
                for r in res:
                    data.append(r.values())

            ofs = ("xls", "xlsx", "ods")
            flg = "wb" if options.output_format in ofs else "w"

            with open(options.output, flg) as f:
                content = getattr(data, options.output_format)
                f.write(content)
        else:
            if options.output == 'stdout':
                print results_to_json_str(res, options.indent)
            else:
                with open(options.output, 'w') as f:
                    print >> f, results_to_json_str(res, options.indent)

    return 0


if __name__ == '__main__':
    sys.exit(realmain(sys.argv))

# vim:sw=4:ts=4:et:
