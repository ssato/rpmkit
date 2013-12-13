#
# List latest RPMs in the software channel specified with using RHN API.
#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato redhat.com>
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
import rpmkit.swapi as RS

import base64
import datetime
import logging
import optparse
import os
import os.path
import shlex
import sys


def swapicall(cmd):
    """
    swapi (SpaceWalk API library) main() wrapper.

    :param cmd: command args :: [str]
    """
    return RS.main(cmd)[0]


def list_latest_packages_in_the_channel_g(channel, details=True):
    """
    :param channel: Software channel label, e.g. rhel-x86_64-as-4.
    :param details: Get more detailed information of each RPM by the RHN API
        "packages.getDetails".
    :yield: A dict of RPM information
    """
    for r in swapicall(["-A", channel, "channel.software.listLatestPackages"]):
        if details:
            logging.info("Try to get more detailed info: pid=" + str(r["id"]))
            args = ["-A", str(r["id"]), "packages.getDetails"]
            logging.debug("swapi::args: " + str(args))
            yield swapicall(args)
        else:
            yield r


def get_filepath_of_rpm_on_satellite(rpminfo, topdir="/var/satellite"):
    """
    NOTE: Requires the info gotten by the RHN API "packages.getDetails".
    """
    assert "path" in rpminfo, \
        "'path' info is necessary to get RPM's filepath: " + str(rpminfo)
    return os.path.join(topdir, rpminfo["path"])


def download_rpm(rpminfo, outdir):
    """
    NOTE: Requires the info gotten by the RHN API "packages.getDetails".
    """
    assert "id" in rpminfo, \
        "'id' info is necessary to download RPM: " + str(rpminfo)
    assert "file" in rpminfo, \
        "'file' info is necessary to download RPM: " + str(rpminfo)

    b64s = swapicall(["-A", str(rpminfo["id"]), "packages.getPackage"])

    logging.info("Try to download the RPM: " + rpminfo["file"])
    with open(os.path.join(outdir, rpminfo["file"]), 'wb') as o:
        o.write(b64s)


def init_log(level):
    lvl = [logging.DEBUG, logging.INFO, logging.WARN][level]
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=lvl)


def option_parser():
    p = optparse.OptionParser("%prog [OPTION ...] SW_CHANNEL_LABEL")

    date = datetime.datetime.now().strftime("%Y%m%d")

    defaults = dict(outdir="download-rpms-" + date, download=False, verbose=1)
    p.set_defaults(**defaults)

    p.add_option("-o", "--outdir", help="Specify output dir [%default]")
    p.add_option("-d", "--download", action="store_true", help="Download RPMs")
    p.add_option("-v", "--verbose", action="store_const", const=0,
                 dest="verbose", help="Verbose mode")
    p.add_option("-q", "--quiet", action="store_const", const=2,
                 dest="verbose", help="Quiet mode")
    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        print >> sys.stderr, \
            "\nNo channel was specified!\n" + \
            "Try `swapi channel.listSoftwareChannels` to get sw channels"
        sys.exit(0)

    init_log(options.verbose)

    channel = args[0]

    if options.download:
        for rpm in list_latest_packages_in_the_channel_g(channel, True):
            download_rpm(rpm, options.outdir)
    else:
        for rpm in list_latest_packages_in_the_channel_g(channel, True):
            for r in rpm:
                print get_filepath_of_rpm_on_satellite(r)


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
