#! /bin/bash
set -e
set -x

python ../list_errata_for_rpmlist.py -vv \
  --channel rhel-i386-server-5,redhat-rhn-satellite-5.3-server-i386-5,rhn-tools-rhel-i386-server-5 \
  -F "%(name)s %(version)s %(release)s %(epoch)s" \
  ../tests/rhel-5-satellite-1.rpms 2>&1 | tee /tmp/list_updates.log
