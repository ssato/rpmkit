from distutils.core import setup, Command
from distutils.sysconfig import get_python_lib
from glob import glob

import datetime
import os
import os.path
import sys

curdir = os.getcwd()
sys.path.append(curdir)

PACKAGE = "rpmkit"
VERSION = "0.2.10.16"

# For daily snapshot versioning mode:
if os.environ.get("_SNAPSHOT_BUILD", None) is not None:
    import datetime
    VERSION = VERSION + datetime.datetime.now().strftime(".%Y%m%d")


def list_files(tdir):
    return [f for f in glob(os.path.join(tdir, '*')) if os.path.isfile(f)]


data_files = [
    ("share/rpmkit/optimizer/pgroups.d/rhel-6-x86_64",
     list_files("data/optimizer/pgroups.d/rhel-6-x86_64/")),
    ("/etc/rpmkit/optimizer.d/rhel-6-x86_64",
     list_files("etc/optimizer.d/rhel-6-x86_64/")),
    ("share/rpmkit/templates", list_files("data/templates/")),
    ("share/rpmkit/templates/css", list_files("data/templates/css")),
    ("share/rpmkit/templates/js", list_files("data/templates/js")),
    (os.path.join(get_python_lib(), "rpmkit/locale/ja/LC_MESSAGES"),
     ["rpmkit/locale/ja/LC_MESSAGES/rpmkit.mo"]),
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
        self.update_mo()
        self.run_command('sdist')
        self.build_rpm()

    def update_mo(self):
        os.system("./aux/update-po.sh")

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
        "rpmkit.extras",
        "rpmkit.rhncachedb",
        "rpmkit.tests",
    ],
    scripts=glob("tools/*"),
    data_files=data_files,
    cmdclass={
        "srpm": SrpmCommand,
        "rpm":  RpmCommand,
    },
)

# vim:sw=4:ts=4:et:
