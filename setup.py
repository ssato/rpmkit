from distutils.core import setup, Command

import datetime
import glob
import os
import sys

try:
    import nose
except ImportError:
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        raise ImportError("python-nose is must for testing.")


curdir = os.getcwd()


sys.path.append(curdir)

PACKAGE = "rpmkit"
VERSION = "0.1." + datetime.datetime.now().strftime("%Y%m%d")


class SrpmCommand(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.run_command('sdist')
        self.build_rpm()

    def build_rpm(self):
        params = dict()

        topdir = params["topdir"] = os.path.abspath(os.curdir)
        rpmdir = params["rpmdir"] = os.path.join(topdir, "dist")
        rpmspec = params["rpmspec"] = os.path.join(topdir, "%s.spec" % PACKAGE)

        for subdir in ("RPMS", "BUILD", "BUILDROOT"):
            sdir = params[subdir] = os.path.join(rpmdir, subdir)

            if not os.path.exists(sdir):
                os.makedirs(sdir, 0755)

        open(rpmspec, "w").write(open(rpmspec + ".in").read().replace("@VERSION@", VERSION))

        cmd = """rpmbuild -bs \
            --define \"_topdir %(rpmdir)s\" --define \"_rpmdir %(rpmdir)s\" \
            --define \"_sourcedir %(topdir)s/dist\" --define \"_buildroot %(BUILDROOT)s\" \
            %(rpmspec)s
            """ % params

        os.system(cmd)



class RpmCommand(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.run_command('sdist')
        self.build_rpm()

    def build_rpm(self):
        params = dict()

        topdir = params["topdir"] = os.path.abspath(os.curdir)
        rpmdir = params["rpmdir"] = os.path.join(topdir, "dist")
        rpmspec = params["rpmspec"] = os.path.join(topdir, "%s.spec" % PACKAGE)

        for subdir in ("RPMS", "BUILD", "BUILDROOT"):
            sdir = params[subdir] = os.path.join(rpmdir, subdir)

            if not os.path.exists(sdir):
                os.makedirs(sdir, 0755)

        open(rpmspec, "w").write(open(rpmspec + ".in").read().replace("@VERSION@", VERSION))

        cmd = """rpmbuild -bb \
            --define \"_topdir %(rpmdir)s\" --define \"_srcrpmdir %(rpmdir)s\" \
            --define \"_sourcedir %(topdir)s/dist\" --define \"_buildroot %(BUILDROOT)s\" \
            %(rpmspec)s
            """ % params

        os.system(cmd)



setup(name=PACKAGE,
    version=VERSION,
    description="RPM toolKit",
    author="Satoru SATOH",
    author_email="ssato@redhat.com",
    license="GPLv3+",
    url="https://github.com/ssato/rpmkit",
    packages=[
        "rpmkit",
    ],
    scripts=[
        "src/list-requires-by-package-name.sh",
        "src/list-srpmnames-by-file.sh",
        "src/list_errata_for_rpmlist",
        "src/myrepo",
        ## Comment it out if you don't use external 'packagemaker':
        # "src/pmaker",
        "src/rpm2json",
        "src/rpms2sqldb",
        "src/swapi",
    ],
    cmdclass={
        "srpm": SrpmCommand,
        "rpm":  RpmCommand,
    },
)

# vim: set sw=4 ts=4 et:
