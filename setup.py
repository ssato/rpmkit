from distutils.core import setup, Command
from distutils.sysconfig import get_python_lib
from glob import glob

import os
import os.path
import sys

curdir = os.getcwd()
sys.path.append(curdir)

PACKAGE = "rpmkit"
VERSION = "0.2.14"
SNAPSHOT_BUILD_MODE = False
RHEL_5_BUILD = False

# For daily snapshot versioning mode:
if os.environ.get("_SNAPSHOT_BUILD", None) is not None:
    import datetime
    SNAPSHOT_BUILD_MODE = True
    VERSION = VERSION + datetime.datetime.now().strftime(".%Y%m%d")

if os.environ.get("_RHEL_5_BUILD", None) is not None:
    RHEL_5_BUILD = True


def list_files(tdir):
    return [f for f in glob(os.path.join(tdir, '*')) if os.path.isfile(f)]


data_files = [
    ("share/rpmkit/optimizer/pgroups.d/rhel-6-x86_64",
     list_files("data/optimizer/pgroups.d/rhel-6-x86_64/")),
    ("/var/lib/yum_makelistcache/root.d/",
     list_files("data/yum_makelistcache/root.d/")),
    ("/etc/yum_makelistcache.d/", list_files("etc/yum_makelistcache.d/")),
    ("/etc/cron.daily/", list_files("etc/cron.daily/")),
    ("/etc/sysconfig/", list_files("etc/sysconfig/")),
    ("/etc/httpd/conf.d/", list_files("etc/httpd/conf.d/")),
    ("/etc/httpd/passwd.d/", list_files("etc/httpd/passwd.d/")),
    ("/etc/rpmkit/optimizer.d/rhel-6-x86_64",
     list_files("etc/optimizer.d/rhel-6-x86_64/")),
    ("share/rpmkit/templates", list_files("data/templates/")),
    ("share/rpmkit/templates/css", list_files("data/templates/css")),
    ("share/rpmkit/templates/js", list_files("data/templates/js")),
#    (os.path.join(get_python_lib(), "rpmkit/locale/ja/LC_MESSAGES"),
#     ["rpmkit/locale/ja/LC_MESSAGES/rpmkit.mo"]),
]


def multi_replace(s, replaces):
    """
    >>> multi_replace("abc def", [("abc", "ABC"), ("def", "DEF")])
    'ABC DEF'
    """
    if replaces:
        for src, dst in replaces:
            s = s.replace(src, dst)

    return s


class SrpmCommand(Command):

    user_options = []

    build_stage = "s"
    cmd_fmt = """rpmbuild -b%(build_stage)s \
        --define \"_topdir %(rpmdir)s\" \
        --define \"_sourcedir %(rpmdir)s\" \
        --define \"_buildroot %(BUILDROOT)s\" \
        %(rpmspec)s """

    if RHEL_5_BUILD:
        cmd_fmt += ("--define '_source_filedigest_algorithm md5' "
                    "--define '_binary_filedigest_algorithm md5'")

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if not SNAPSHOT_BUILD_MODE:
            self.update_mo()
        self.run_command('sdist')
        self.build_rpm()

    def update_mo(self):
        os.system("./pkg/update-po.sh")

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

        if RHEL_5_BUILD:
            replaces = [("@VERSION@", VERSION),
                        ("yum-plugin-downloadonly", "yum-downloadonly"),
                        ("yum-plugin-security", "yum-security")]
        else:
            replaces = [("@VERSION@", VERSION), ]

        c = open(rpmspec + ".in").read()
        open(rpmspec, "w").write(multi_replace(c, replaces))

        cmd = self.cmd_fmt % params
        sys.stdout.write("[Info] run cmd: %s w/ %s\n" % (cmd, rpmspec))
        os.system(cmd)


class RpmCommand(SrpmCommand):

    build_stage = "b"


setup(name=PACKAGE,
      version=VERSION,
      description="RPM toolKit",
      author="Satoru SATOH",
      author_email="ssato@redhat.com",
      license="GPLv3+",
      url="https://github.com/ssato/rpmkit",
      packages=["rpmkit",
                "rpmkit.extras",
                "rpmkit.tests",
                "rpmkit.updateinfo",
                "rpmkit.updateinfo.tests"],
      scripts=glob("tools/*"),
      data_files=data_files,
      cmdclass={"srpm": SrpmCommand,
                "rpm":  RpmCommand})

# vim:sw=4:ts=4:et:
