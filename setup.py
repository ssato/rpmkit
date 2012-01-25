from distutils.core import setup, Command

import datetime
import glob
import os
import sys

curdir = os.getcwd()
sys.path.append(curdir)

PACKAGE = "rpmkit"
VERSION = "0.2.4"

# daily snapshots:
VERSION = VERSION + datetime.datetime.now().strftime(".%Y%m%d")


data_files = [
    ("share/rpmkit/templates/1/myrepo", glob.glob("templates/1/myrepo/*")),
]


class SrpmCommand(Command):

    user_options = []

    build_stage = "s"
    cmd_fmt = """rpmbuild -b%(build_stage)s \
        --define \"_topdir %(rpmdir)s\" \
        --define \"_sourcedir %(rpmdir)s\" \
        --define \"_buildroot %(BUILDROOT)s\" \
        %(rpmspec)s
    """

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.run_command('sdist')
        self.build_rpm()

    def build_rpm(self):
        params = dict()

        params["build_stage"] = self.build_stage
        rpmdir = params["rpmdir"] = os.path.join(
            os.path.abspath(os.curdir), "dist"
        )
        rpmspec = params["rpmspec"] = os.path.join(
            rpmdir, "../%s.spec" % PACKAGE
        )

        for subdir in ("SRPMS", "RPMS", "BUILD", "BUILDROOT"):
            sdir = params[subdir] = os.path.join(rpmdir, subdir)

            if not os.path.exists(sdir):
                os.makedirs(sdir, 0755)

        c = open(rpmspec + ".in").read()
        open(rpmspec, "w").write(c.replace("@VERSION@", VERSION))

        os.system(self.cmd_fmt % params)


class RpmCommand(SrpmCommand):

    build_stage = "b"


setup(name=PACKAGE,
    version=VERSION,
    description="RPM toolKit",
    author="Satoru SATOH",
    author_email="ssato@redhat.com",
    license="GPLv3+",
    url="https://github.com/ssato/rpmkit",
    packages=[
        "rpmkit",
        "rpmkit.myrepo",
    ],
    scripts=glob.glob("src/*"),
    data_files=data_files,
    cmdclass={
        "srpm": SrpmCommand,
        "rpm":  RpmCommand,
    },
)

# vim:sw=4 ts=4 et:
