About
========

This is a collection of some rpm related toools distributed under
GPL3+/GPLv2+/MIT.

* buildsrpm: Build source rpm from given rpm spec file
* identrpm: Identify given rpm and print info

* rpms2sqldb: Create SQLite database of given rpms metadata

  * list-requires-by-package-name.sh: List requirements for given rpm name[s],
    gotten from the sqlite database built by rpms2sqldb.

  * list-srpmnames-by-file.sh: List srpmnames List source rpm names for given
    files, gotten from the sqlite database built by rpms2sqldb.

* rpm2json: Dump rpm metadata in JSON format
* rpms2csv: Dump metadata of given rpms in CSV format
* rk-repodata: Generate/query (rpm) repodata cache
* minifyrpmlist: Minify given rpm list with using repodata cache

* swapi: Query RHN/Satellite
* yum-surrogate: ...FIXME...

Some examples
---------------

Here is an example session running yum-surrogate::

  [root@rhel-6-client-1 ~]# scp rhel-6-client-2:/var/lib/rpm/{Packages,Basenames,Name,Providename,Requirename} rhel-6-client-2/rpmdb/
  root@rhel-6-client-2's password:
  Packages                                                                                                                              100%   16MB   5.3MB/s   00:03
  root@rhel-6-client-2's password:
  Basenames                                                                                                                             100% 1476KB   1.4MB/s   00:00
  root@rhel-6-client-2's password:
  Name                                                                                                                                  100%   12KB  12.0KB/s   00:00
  root@rhel-6-client-2's password:
  Providename                                                                                                                           100% 1232KB   1.2MB/s   00:00
  root@rhel-6-client-2's password:
  Requirename                                                                                                                           100%  116KB 116.0KB/s   00:00
  [root@rhel-6-client-1 ~]# yum-surrogate -L -v -f -p ./rhel-6-client-2/rpmdb/Packages -r rhel-6-client-2/ -- list-sec | grep RHSA
  DEBUG:root:Creating rpmdb dir: rhel-6-client-2/var/lib/rpm
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Packages -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Basenames -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Name -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Providename -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:Create a symlink: ./rhel-6-client-2/rpmdb/Requirename -> rhel-6-client-2/var/lib/rpm/
  DEBUG:root:cmd: yum --installroot=/root/rhel-6-client-2 list-sec
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
  repo id                     repo name                                                                   status
  *epel                       Extra Packages for Enterprise Linux 6 - x86_64                               8,629
  rhel-nrt-ssato              Custom yum repository on file.nrt.redhat.com by ssato                           58
  rhel-x86_64-server-6        Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)                    10,485
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
