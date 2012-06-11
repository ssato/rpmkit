#
# build srpm in current dir or specified working dir from given rpm spec.
#
# Author: Satoru SATOH <ssato redhat.com>
# License: MIT
#
# Requirements: rpm-python, rpm-build
#
import rpmkit.shell as SH

import logging
import optparse
import os.path
import re
import rpm
import sys
import urllib2


def get_source0_url_from_rpmspec(rpmspec):
    """
    Parse given rpm spec and return (source0's url, source0).

    It may throw ValuError("can't parse specfile"), etc.
    """
    spec = rpm.spec(rpmspec)

    src0 = spec.sources[0][0]
    assert src0, "SOURCE0 should not be empty!"

    # First, try SOURCE0:
    if re.match(r"(ftp|http|https)://", src0):
        logging.debug("URL=" + src0)
        return (src0, os.path.basename(src0))

    base_url = spec.sourceHeader["URL"]
    assert base_url, "URL should not be empty!"

    logging.debug("Base URL=" + base_url + ", src0=" + src0)
    return (os.path.join(base_url, src0), src0)


def download(url, out, data=None, headers={}):
    """
    Download file from given URL and save as $out.
    """
    req = urllib2.Request(url=url, data=data, headers=headers)
    f = urllib2.urlopen(req)

    with open(out, "w") as o:
        o.write(f.read())


def download_src0(rpmspec, url, out):
    try:
        download(url, out)

    except urllib2.HTTPError, e:
        logging.warn("Could not download source0's url.")
        url = raw_input("Input the URL of source0 > ")

        download(url, out)


def do_buildsrpm(rpmspec, workdir):
    cmd = " ".join([
        "rpmbuild",
        "--define \"_srcrpmdir %(workdir)s\"",
        "--define \"_sourcedir %(workdir)s\"",
        "--define \"_buildroot %(workdir)s\"",
        "-bs %(spec)s",
    ]) % { "workdir": workdir, "spec": rpmspec, }

    logging.info("Creating src.rpm from %s in %s" % (rpmspec, workdir))
    SH.run(cmd, workdir=workdir, stop_on_error=True)


def main(argv=sys.argv):
    defaults = {
        "debug": False,
        "workdir": None,
    }

    p = optparse.OptionParser("%prog [Options...] RPM_SPEC")
    p.set_defaults(**defaults)

    p.add_option("-D", "--debug", action="store_true", help="Debug mode")
    p.add_option("-w", "--wordir", help="Working dir to search source0")
    
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_usage()
        sys.exit(-1)

    if options.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    rpmspec = args[0]

    if not options.workdir:
        options.workdir = os.path.dirname(rpmspec)
        logging.info("Set workdir to " + options.workdir)

    (url, src0) = get_source0_url_from_rpmspec(rpmspec)
    out = os.path.join(options.workdir, src0)

    if not os.path.exists(out):
        download_src0(rpmspec, url, out)

    do_buildsrpm(rpmspec, options.workdir)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
