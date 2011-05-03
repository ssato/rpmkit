#
# packagemaker plugin for libvirt objects:
# 
# Copyright (C) 2011 Satoru SATOH <satoru.satoh @ gmail.com>
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
#
# Requirements: xpack
#
#
# Installation: ...
#
# References:
# * http://libvirt.org/html/libvirt-libvirt.html
# * http://libvirt.org/formatdomain.html
# * http://libvirt.org/formatnetwork.html
#
#
# TODO:
# * plugin template and basic mechanism to overwrite parameters from main
# * VMs other than KVM guests such like LXC guests
#
#
# Internal:
#
# Make some pylint errors ignored:
# pylint: disable=E0611
# pylint: disable=E1101
# pylint: disable=E1103
# pylint: disable=W0613
#
# How to run pylint: pylint --rcfile pylintrc THIS_SCRIPT
#

import copy
import doctest
import libvirt
import libxml2
import logging
import re
import subprocess
import unittest
import pmaker



VMM = "qemu:///system"



def xml_context(xmlfile):
    return libxml2.parseFile(xmlfile).xpathNewContext()


def xpath_eval(xpath, xmlfile=False, ctx=False):
    """Parse given XML and evaluate given XPath expression, then returns
    result[s].
    """
    assert xmlfile or ctx, "No sufficient arguements"

    if not ctx:
        ctx = xml_context(xmlfile)

    return [r.content for r in ctx.xpathEval(xpath)]



class LibvirtObject(object):

    def __init__(self, name=False, xmlpath=False, vmm=VMM):
        assert name or xmlpath, "Not enough arguments"

        self.vmm = vmm
        self.type = self.type_by_vmm(vmm)

        if name:
            self.name = name
            self.xmlpath = self.xmlpath_by_name(name)
        else:
            self.xmlpath = xmlpath
            self.name = self.name_by_xml_path(xmlpath)

    def xpath_eval(self, xpath):
        return xpath_eval(xpath, self.xmlpath)

    def name_by_xmlpath(self, xmlpath):
        return self.xpath_eval("//name", xmlpath)[0]

    def xmlpath_by_name(self, name):
        return "/etc/libvirt/%s/%s.xml" % (self.type, name)

    def type_by_vmm(self, vmm):
        return vmm.split(":")[0]  # e.g. 'qemu'

    def connect(self):
        return libvirt.openReadOnly(self.vmm)



class LibvirtNetwork(LibvirtObject):

    def name_by_xmlpath(self, xmlpath):
        return self.xpath_eval('/network/name', xmlpath)[0]

    def xmlpath_by_name(self, name):
        return "/etc/libvirt/%s/networks/%s.xml" % (self.type, name)



class LibvirtDomain(LibvirtObject):

    def name_by_xmlpath(self, xmlpath):
        return self.xpath_eval('/domain/name', xmlpath)[0]

    def parse(self):
        """Parse domain xml and store various guest profile data.

        TODO: storage pool support
        """
        self.arch = self.xpath_eval('/domain/os/type/@arch')[0]
        self.networks = xpack.unique(self.xpath_eval('/domain/devices/interface[@type="network"]/source/@network'))

        images = self.xpath_eval('/domain/devices/disk[@type="file"]/source/@file')
        dbs = [(img, self.get_base_image_path(img)) for img in images]
        self.base_images = [db[1] for db in dbs if db[1]] + [db[0] for db in dbs if not db[1]]
        self.delta_images = [db[0] for db in dbs if db[1]]

    def status(self):
        conn = self.connect()

        if conn is None: # libvirtd is not running.
            return libvirt.VIR_DOMAIN_SHUTOFF

        dom = conn.lookupByName(self.name)
        if dom:
            return dom.info()[0]
        else:
            return libvirt.VIR_DOMAIN_NONE

    def is_running(self):
        return self.status() == libvirt.VIR_DOMAIN_RUNNING

    def is_shutoff(self):
        return self.status() == libvirt.VIR_DOMAIN_SHUTOFF

    def get_base_image_path(self, image_path):
        try:
            out = subprocess.check_output("qemu-img info %s" % image_path, shell=True)
            m = re.match(r"^backing file: (.+) \(actual path: (.+)\)$", out.split("\n")[-2])
            if m:
                (delta, base) = m.groups()
                return base
            else:
                return False
        except Exception, e:
            logging.warn("get_delta_image_path: " + str(e))
            pass



# plugin main:
__version__ = "0.1"
__author__  = "Satoru SATOH"
__email__   = "satoru.satoh@gmail.com"
__website__ = "https://github.com/ssato/rpmkit"


LIBVIRT_DOMAIN_TEMPLATES = copy.copy(pmaker.TEMPLATES)
LIBVIRT_DOMAIN_TEMPLATES.update(
{
    "package.spec": """\
# disable debuginfo
%define debug_package %{nil}

Name:           $name
Version:        $version
Release:        1%{?dist}
Summary:        libvirt domain $domain.name
Group:          $group
License:        $license
URL:            $url
Source0:        %{name}-%{version}.tar.${compressor.ext}
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
#for $req in $requires
Requires:       $req
#end for
PreReq:         /usr/bin/virsh
Requires:       /usr/bin/virsh
Requires:       libvirt
Requires:       %{name}-base


%description
Libvirt domain (virtual) hardware data and disk images for ${domain.name}
on $host packaged by $packager at $date.date.


%package        base
Summary:        Base disk images for libvirt domain $domain.name
Group:          $group
Provides:       %{name}-base


%description    base
Libvirt domain (virtual) hardware data and disk images for ${domain.name}
on $host packaged by $packager at $date.date.

This package provides the (virtual) hardware definition xml data and base disk
images required for %{name}.


%prep
%setup -q


%build
%configure
make


%install
rm -rf \$RPM_BUILD_ROOT
make install DESTDIR=\$RPM_BUILD_ROOT

# saved doamin xml:
install -d \$RPM_BUILD_ROOT$domain.xmlpath_savedir
install -m 600 \$RPM_BUILD_ROOT$domain.xmlpath \$RPM_BUILD_ROOT$domainxml_savedir


%clean
rm -rf \$RPM_BUILD_ROOT


%preun
if [ \$1 = 0 ]; then  # erase
    if `/usr/bin/virsh list | grep -q $domain.name 2>/dev/null`; then
        echo "${domain.name} is still running. Please shut it off and try again later."
        exit 1
    else
        /usr/bin/virsh undefine $domain.name
    fi
fi


%post
if [ \$1 = 1 ]; then    # install
    /usr/bin/virsh define %{domainxml_savedir}/${domain.name}
elif [ \$1 = 2 ]; then  # update
    if `/usr/bin/virsh list | grep -q ${domain.name} 2>/dev/null`; then
        echo "${domain.name} is running. Run the following later when it's stopped to update its profile:"
        echo "   /usr/bin/virsh undefine ${domain.name}"
        echo "   /usr/bin/virsh define $domain.xmlpath_saved"
    else
        /usr/bin/virsh undefine $domain.name
        /usr/bin/virsh define $domain.xmlpath_saved
    fi
fi


%files
%defattr(-,root,root,-)
%doc README
#for $fi in $fileinfos
#if $fi.target in $domain.delta_images
$fi.rpm_attr()$fi.target
#end if
#end for


%files    base
%defattr(-,root,root,-)
%doc README
#for $fi in $fileinfos
#if $fi.target not in $domain.delta_images
$fi.rpm_attr()$fi.target
#end if
#end for
$domain.xmlpath_saved


%changelog
* $date.timestamp ${packager} <${mail}> - ${version}-${release}
- Initial packaging.
""",

    "debian/postinst": """\
#!/bin/sh
#
# see: dh_installdeb(1)
#
# summary of how this script can be called:
#        * <postinst> `configure' <most-recently-configured-version>
#        * <old-postinst> `abort-upgrade' <new version>
#        * <conflictor's-postinst> `abort-remove' `in-favour' <package>
#          <new-version>
#        * <postinst> `abort-remove'
#        * <deconfigured's-postinst> `abort-deconfigure' `in-favour'
#          <failed-install-package> <version> `removing'
#          <conflicting-package> <version>
# for details, see http://www.debian.org/doc/debian-policy/ or
# the debian-policy package

set -e

case "\$1" in
    configure)
        if `/usr/bin/virsh list --all | grep -q ${domain.name} 2>/dev/null`; then
            if `/usr/bin/virsh list | grep -q ${domain.name} 2>/dev/null`; then
                echo "${domain.name} is running. Run the following later when it's stopped:"
                echo "   /usr/bin/virsh define $domain.xmlpath"
            else
                /usr/bin/virsh undefine ${domain.name}
                /usr/bin/virsh define $domain.xmlpath
            fi
        else
            /usr/bin/virsh define $domain.xmlpath
        fi
    ;;

    abort-upgrade|abort-remove|abort-deconfigure)
    ;;

    *)
        echo "postinst called with unknown argument \`\$1'" >&2
        exit 1
    ;;
esac

#DEBHELPER#

exit 0
""",
    "debian/postinst": """\
#!/bin/sh
#
# see: dh_installdeb(1)
set -e

case "\$1" in
    remove|upgrade|deconfigure)
        if `/usr/bin/virsh list | grep -q ${domain.name} 2>/dev/null`; then
            echo "${domain.name} is still running and cannot be uninstalled right now. Please stop it and try again later."
            exit 1
        else
            /usr/bin/virsh undefine ${domain.name}
        fi
        ;;
    failed-upgrade)
        ;;
    *)
        echo "prerm called with unknown argument \`\$1'" >&2
        exit 0
        ;;
esac

#DEBHELPER#

exit 0
""",
})



# PackageMaker Inherited classes:
class LibvirtDomainCollector(pmaker.FilelistCollector):

    _type = "libvirt.domain"

    def __init__(self, domname, pkgname, options):
        super(LibvirtDomainCollector, self).__init__(domname, pkgname, options)

    @classmethod
    def list_targets(cls, domname):
        """Gather files of which the domain $domname owns.
        
        @domname  str  Domain's name
        """
        self.domain = LibvirtDomain(domname)
        self.domain.parse()

        self.domain.xmlpath_savedir = "/var/lib/pmaker/libvirt.domain"
        self.domain.xmlpath_saved = os.path.join(self.domain.xmlpath_savedir, "%s.xml" % self.domain.name)

        #filelist = [self.domain.xmlpath]
        filelist = []
        filelist += self.domain.base_images
        filelist += self.domain.delta_images

        return unique(filelist)



class RpmLibvirtDomainPackageMaker(pmaker.RpmPackageMaker):

    global LIBVIRT_DOMAIN_TEMPLATES

    _templates = LIBVIRT_DOMAIN_TEMPLATES
    _type = "libvirt.domain"
    _collector = LibvirtDomainCollector



class DebLibvirtDomainPackageMaker(pmaker.DebPackageMaker):

    global LIBVIRT_DOMAIN_TEMPLATES

    _templates = LIBVIRT_DOMAIN_TEMPLATES
    _type = "libvirt.domain"
    _collector = LibvirtDomainCollector



# vim:sw=4:ts=4:et:
