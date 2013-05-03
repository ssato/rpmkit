About
========

This is a collection of some rpm related toools distributed under
GPL3+/GPLv2+/MIT.

* buildsrpm: Build source rpm from given rpm spec file
* identrpm: Identify given rpm and print package metadata
* rpm2json: Dump rpm metadata in JSON format

  * rpms2csv: Dump metadata of given rpms in CSV format w/ rpm2json's help

* rpms2sqldb: Create SQLite database of given rpms metadata

  * list-requires-by-package-name.sh: List requirements for given rpm name[s],
    gotten from the sqlite database built by rpms2sqldb.

  * list-srpmnames-by-file.sh: List srpmnames List source rpm names for given
    files, gotten from the sqlite database built by rpms2sqldb.

* rk-repodata: Generate/query (rpm) repodata cache

  * minifyrpmlist: Minify given rpm list with using repodata cache

* swapi: Call RHN API to query RHN/Satellite from command line
* yum-surrogate: surrogate yum execution on hosts accessible to RHN/Satellite

buildsrpm
-----------

buildsrpm is a tiny tool to build src.rpm from the RPM spec.

buildsrpm looks into the given RPM spec and tries to find out the URL of
SOURCE0. Then it tries to download the SOURCE0 from the URL and build src.rpm.

Here is an example::

  ssato@localhost% buildsrpm -h
  Usage: buildsrpm [Options...] RPM_SPEC

  Options:
    -h, --help            show this help message and exit
    -D, --debug           Debug mode
    -w WORKDIR, --workdir=WORKDIR
                          Working dir to search source0
  ssato@localhost% grep ' http://' mscgen.spec
  URL:            http://www.mcternan.me.uk/mscgen
  Source0:        http://www.mcternan.me.uk/mscgen/software/%{name}-src-%{version}.tar.gz
  ssato@localhost% buildsrpm -D -w /tmp/mscgen mscgen.spec
  INFO:root:rpm spec is /home/ssato/repos/public/github.com/ssato/misc.git/rpmspecs/mscgen.spec
  INFO:root:Set workdir to /tmp/mscgen
  DEBUG:root:URL=http://www.mcternan.me.uk/mscgen/software/mscgen-src-0.20.tar.gz
  DEBUG:root:Creating working dir: /tmp/mscgen
  INFO:root:Creating src.rpm from /home/ssato/repos/public/github.com/ssato/misc.git/rpmspecs/mscgen.spec in /tmp/mscgen
  INFO:root:Run: rpmbuild --define "_srcrpmdir /tmp/mscgen" --define "_sourcedir /tmp/mscgen" --define "_buildroot /tmp/mscgen" -bs /home/ssato/repos/public/github.com/ssato/misc.git/rpmspecs/mscgen.spec [/tmp/mscgen]
  Wrote: /tmp/mscgen/mscgen-0.20-2.fc18.src.rpm
  ssato@localhost%

identrpm
-----------

identrpm can identify given RPMs and complement various package metadata with
the package information gotten by accessing the RHN or RHN Satellite.

Here is an example::

  $ identrpm --format "{name},{version},{release},{arch},{epoch}" autoconf-2.59-12.noarch
  autoconf,2.59,12,noarch,0

  $ identrpm --format "{name}: {summary}" autoconf-2.59-12
  autoconf: A GNU tool for automatically configuring source code.

.. note:: identrpm delegates swapi to query RHN to get necessary package
          metadata, so swapi must be configured when running identrpm.

rpm2json
---------

rpm2json just query the rpm database for given RPM file and output metada of
the RPM file in JSON format.

Here is an example::

  ssato@localhost% rpm2json
  Usage: rpm2json [OPTION ...] RPM_0 [RPM_1 ...]

  Examples:
    rpm2json Server/cups-1.3.7-11.el5.i386.rpm
    rpm2json -T name,sourcerpm,rpmversion Server/*openjdk*.rpm
    rpm2json --show-tags

  ssato@localhost% rpm2json -h
  Usage: rpm2json [OPTION ...] RPM_0 [RPM_1 ...]

  Examples:
    rpm2json Server/cups-1.3.7-11.el5.i386.rpm
    rpm2json -T name,sourcerpm,rpmversion Server/*openjdk*.rpm
    rpm2json --show-tags

  Options:
    -h, --help            show this help message and exit
    --show-tags           Show all possible rpm tags
    -o OUTPUT, --output=OUTPUT
                          output filename [stdout]
    -T TAGS, --tags=TAGS  Comma separated rpm tag list to get or "almost" to get
                          almost data dump (except for "headerimmutable").
                          [name,version,release,arch,epoch,sourcerpm]
    --blacklist=BLACKLIST
                          Comma separated tags list not to get data
                          [headerimmutable]
    -H, --human-readable  Output formatted results.
  ssato@localhost% rpm2json -H /tmp/mscgen/mscgen-0.20-2.fc18.src.rpm
  [
    {
      "name": "mscgen",
      "epoch": null,
      "version": "0.20",
      "release": "2.fc18",
      "sourcerpm": null,
      "arch": "x86_64"
    }
  ]
  ssato@localhost% rpm2json /tmp/mscgen/mscgen-0.20-2.fc18.src.rpm
  [{"name": "mscgen", "epoch": null, "version": "0.20", "release": "2.fc18", "sourcerpm": null, "arch": "x86_64"}]
  ssato@localhost% rpm2json -T name,sourcerpm /tmp/mscgen/mscgen-0.20-2.fc18.src.rpm
  [{"sourcerpm": null, "name": "mscgen"}]


yum-surrogate
----------------

yum-surrogate surrogates yum execution for other hosts have no access to any
yum repositories, on host can access to some yum repositories needed.

Here is an example::

  [root@rhel-6-client-1 ~]# scp rhel-6-client-2:/var/lib/rpm/{Packages,Basenames,Name,Providename,Requirename} \
  > rhel-6-client-2/rpmdb/
  Packages                                                                         100%   16MB   5.3MB/s   00:03
  Basenames                                                                        100% 1476KB   1.4MB/s   00:00
  Name                                                                             100%   12KB  12.0KB/s   00:00
  Providename                                                                      100% 1232KB   1.2MB/s   00:00
  Requirename                                                                      100%  116KB 116.0KB/s   00:00
  [root@rhel-6-client-1 ~]# yum-surrogate -L -v -f -p ./rhel-6-client-2/rpmdb/Packages \
  > -r rhel-6-client-2/ -- list-sec | grep RHSA
  DEBUG:root:Creating rpmdb dir: rhel-6-client-2/var/lib/rpm
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Packages -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Basenames -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Name -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Providename -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Requirename -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Run command: yum --installroot=/root/rhel-6-client-2 list-sec
  RHSA-2013:0550 Moderate/Sec.  bind-libs-32:9.8.2-0.17.rc1.el6.3.x86_64
  RHSA-2013:0689 Important/Sec. bind-libs-32:9.8.2-0.17.rc1.el6_4.4.x86_64
  RHSA-2013:0550 Moderate/Sec.  bind-utils-32:9.8.2-0.17.rc1.el6.3.x86_64
  RHSA-2013:0689 Important/Sec. bind-utils-32:9.8.2-0.17.rc1.el6_4.4.x86_64
  RHSA-2013:0771 Moderate/Sec.  curl-7.19.7-36.el6_4.x86_64
  RHSA-2013:0568 Important/Sec. dbus-glib-0.86-6.el6_4.x86_64
  RHSA-2013:0567 Important/Sec. kernel-2.6.32-358.0.1.el6.x86_64
  RHSA-2013:0630 Important/Sec. kernel-2.6.32-358.2.1.el6.x86_64
  RHSA-2013:0744 Important/Sec. kernel-2.6.32-358.6.1.el6.x86_64
  RHSA-2013:0567 Important/Sec. kernel-firmware-2.6.32-358.0.1.el6.noarch
  RHSA-2013:0630 Important/Sec. kernel-firmware-2.6.32-358.2.1.el6.noarch
  RHSA-2013:0744 Important/Sec. kernel-firmware-2.6.32-358.6.1.el6.noarch
  RHSA-2013:0656 Moderate/Sec.  krb5-libs-1.10.3-10.el6_4.1.x86_64
  RHSA-2013:0748 Moderate/Sec.  krb5-libs-1.10.3-10.el6_4.2.x86_64
  RHSA-2013:0771 Moderate/Sec.  libcurl-7.19.7-36.el6_4.x86_64
  RHSA-2013:0581 Moderate/Sec.  libxml2-2.7.6-12.el6_4.1.x86_64
  RHSA-2013:0581 Moderate/Sec.  libxml2-python-2.7.6-12.el6_4.1.x86_64
  RHSA-2013:0219 Moderate/Sec.  mysql-libs-5.1.67-1.el6_3.x86_64
  RHSA-2013:0772 Important/Sec. mysql-libs-5.1.69-1.el6_4.x86_64
  RHSA-2013:0587 Moderate/Sec.  openssl-1.0.0-27.el6_4.2.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-4:5.10.1-130.el6_4.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-Module-Pluggable-1:3.90-130.el6_4.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-Pod-Escapes-1:1.04-130.el6_4.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-Pod-Simple-1:3.13-130.el6_4.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-libs-4:5.10.1-130.el6_4.x86_64
  RHSA-2013:0685 Moderate/Sec.  perl-version-3:0.77-130.el6_4.x86_64
  [root@rhel-6-client-1 ~]# yum repolist
  Loaded plugins: downloadonly, rhnplugin, security
  This system is receiving updates from RHN Classic or RHN Satellite.
  repo id                     repo name                                                            status
  *epel                       Extra Packages for Enterprise Linux 6 - x86_64                        8,629
  rhel-nrt-ssato              Custom yum repository on ********.redhat.com by ssato                    58
  rhel-x86_64-server-6        Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)             10,485
  repolist: 19,172
  [root@rhel-6-client-1 ~]# ssh rhel-6-client-2 "yum repolist"
  root@rhel-6-client-2's password:
  Loaded plugins: product-id, security, subscription-manager
  This system is not registered to Red Hat Subscription Management. You can use subscription-manager to register.
  repolist: 0
  [root@rhel-6-client-1 ~]#


Build
========

Build w/ mock
---------------

It takes some time to make a rpm but should be better, I think.

1. python setup.py srpm
2. mock -r <target_build_dist> dist/SRPMS/packagemaker-*.src.rpm

Build w/o mock
----------------

It's easier than the above but only possible to make a rpm for build host.

1. python setup.py rpm

TODO
=======

* Write tests
* Fix PEP8 warnings and errors

NOTES
========

* filelist2rpm.py and xpack.py were removed as these are replaced with its
  successor, pmaker.py

* pmaker.py: I created other decicated git repo for it and renamed to
  packagemaker (pmaker). This script (legacy version now) will be kept for a
  while but will not be mantained any more.  Please look at the new repository
  of packagemaker (pmaker) at:

  https://github.com/ssato/packagemaker/

* myrepo: Exported to another project:

  https://github.com/ssato/python-myrepo/

* data/cve_dates.json:

  https://www.redhat.com/security/data/metrics/cve_dates.txt

Author
========

Satoru SATOH <ssato@redhat.com>

.. vim:sw=2:ts=2:et:
