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
# Requirements: packagemaker
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
import os
import re
import subprocess
import sys
import tempfile
import unittest

import pmaker


VMM = "qemu:///system"
LIBVIRT_DOMAIN_XML_SAVEDIR = "/var/lib/pmaker/libvirt.domain"



def xml_context(xmlfile):
    return libxml2.parseFile(xmlfile).xpathNewContext()


def xpath_eval(xpath, xmlfile=False, ctx=None):
    """Parse given XML and evaluate given XPath expression, then returns
    result[s].
    """
    assert xmlfile or ctx, "No sufficient arguements"

    if ctx is None:
        ctx = xml_context(xmlfile)

    return [r.content for r in ctx.xpathEval(xpath)]



class LibvirtObject(object):

    name_xpath = "//name"
    xmlpath_fmt = "/etc/libvirt/%s/%s.xml"

    def __init__(self, name=False, xmlpath=False, vmm=VMM):
        assert name or xmlpath, "Not enough arguments"

        self.vmm = vmm
        self.type = self.type_by_vmm(vmm)

        if name:
            self.name = name
            self.xmlpath = self.xmlpath_by_name(name)
        else:
            self.xmlpath = xmlpath
            self.name = self.name_by_xmlpath(self.name_xpath, xmlpath)

        self.setup()

    def setup(self):
        pass

    def name_by_xmlpath(self, xpath_exp, xmlpath):
        return xpath_eval(xpath_exp, xmlpath)[0]

    def xmlpath_by_name(self, name):
        return self.xmlpath_fmt % (self.type, name)

    def type_by_vmm(self, vmm):
        return vmm.split(":")[0]  # e.g. 'qemu'

    def connect(self):
        return libvirt.openReadOnly(self.vmm)



class LibvirtNetwork(LibvirtObject):

    name_xpath = "/network/name"
    xmlpath_fmt = "/etc/libvirt/%s/networks/%s.xml"



class LibvirtDomain(LibvirtObject):

    name_xpath = "/domain/name"
    xmlpath_fmt = "/etc/libvirt/%s/networks/%s.xml"

    xmlsavedir = LIBVIRT_DOMAIN_XML_SAVEDIR

    def setup(self):
        """Parse domain xml and store various guest profile data.

        TODO: storage pool support
        """
        ctx = xml_context(self.xmlpath)

        self.arch = xpath_eval("/domain/os/type/@arch", ctx=ctx)[0]
        self.networks = pmaker.unique(xpath_eval('/domain/devices/interface[@type="network"]/source/@network', ctx=ctx))

        images = xpath_eval('/domain/devices/disk[@type="file"]/source/@file', ctx=ctx)

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



TEST_DOMAIN_XML_0 = """\
<domain type='kvm'>
  <name>rhel-5-5-vm-1</name>
  <os>
    <type arch='i686' machine='pc-0.13'>hvm</type>
    <boot dev='hd'/>
  </os>
  <!-- ... snip ... -->
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='/var/lib/libvirt/images/rhel-5-5-guest-1/disk-0.qcow2'/>
      <target dev='vda' bus='virtio'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>
    </disk>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='/var/lib/libvirt/images/rhel-5-5-guest-1/disk-1.qcow2'/>
      <target dev='vdb' bus='virtio'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>
    </disk>
    <interface type='network'>
      <mac address='54:52:00:01:01:55'/>
      <source network='net-1'/>
      <model type='virtio'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x0'/>
    </interface>
    <interface type='network'>
      <mac address='54:52:00:03:01:55'/>
      <source network='net-2'/>
      <model type='virtio'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x0'/>
    </interface>
    <!-- ... snip ... -->
  </devices>
</domain>
"""

TEST_NETWORK_XML_0 = """\
<network>
  <name>net-0</name>
  <forward mode='nat'/>
  <bridge name='virbr1' stp='on' delay='0' />
  <domain name='net-1.local'/>
  <ip address='192.168.151.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.151.200' end='192.168.151.254' />
      <host mac='54:52:00:01:00:10' name='service-0' ip='192.168.151.10' />
      <host mac='54:52:00:01:00:11' name='service-1' ip='192.168.151.11' />
    </dhcp>
  </ip>
</network>
"""



class TestXpathEval(unittest.TestCase):

    _multiprocess_shared_ = True

    def setUp(self):
        global TEST_DOMAIN_XML_0

        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="pplx-")

        xmlpath = os.path.join(self.workdir, "test-0.xml")
        open(xmlpath, "w").write(TEST_DOMAIN_XML_0)

        self.xmlpath = xmlpath

        self.xpath_archs = "/domain/os/type/@arch"
        self.xpath_networks = "/domain/devices/interface[@type='network']/source/@network"
        self.xpath_images = "/domain/devices/disk[@type='file']/source/@file"

    def tearDown(self):
        pmaker.rm_rf(self.workdir)

    def test_xpath_eval_xmlfile_archs(self):
        self.assertEquals(xpath_eval(self.xpath_archs, self.xmlpath)[0], "i686")

    def test_xpath_eval_xmlfile_networks(self):
        networks = xpath_eval(self.xpath_networks, self.xmlpath)

        self.assertEquals(networks[0], "net-1")
        self.assertEquals(networks[1], "net-2")

    def test_xpath_eval_xmlfile_images(self):
        images = xpath_eval(self.xpath_images, self.xmlpath)

        self.assertEquals(images[0], "/var/lib/libvirt/images/rhel-5-5-guest-1/disk-0.qcow2")
        self.assertEquals(images[1], "/var/lib/libvirt/images/rhel-5-5-guest-1/disk-1.qcow2")

    def test_xpath_eval_ctx(self):
        ctx = xml_context(self.xmlpath)

        self.assertEquals(xpath_eval(self.xpath_archs, ctx=ctx)[0], "i686")

        networks = xpath_eval(self.xpath_networks, ctx=ctx)

        self.assertEquals(networks[0], "net-1")
        self.assertEquals(networks[1], "net-2")

        images = xpath_eval(self.xpath_images, ctx=ctx)

        self.assertEquals(images[0], "/var/lib/libvirt/images/rhel-5-5-guest-1/disk-0.qcow2")
        self.assertEquals(images[1], "/var/lib/libvirt/images/rhel-5-5-guest-1/disk-1.qcow2")



class TestLibvirtNetwork(unittest.TestCase):

    _multiprocess_shared_ = True

    def setUp(self):
        global TEST_NETWORK_XML_0

        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="pplx-")

        xmlpath = os.path.join(self.workdir, "net-0.xml")
        open(xmlpath, "w").write(TEST_NETWORK_XML_0)

        self.xmlpath = xmlpath

    def tearDown(self):
        pmaker.rm_rf(self.workdir)

    def test_instance_by_xmlpath(self):
        lnet = LibvirtNetwork(xmlpath=self.xmlpath)

        self.assertEquals(lnet.name, "net-0")

    def test_instance_by_name(self):
        lnet = LibvirtNetwork("net-0")

        self.assertEquals(lnet.xmlpath, LibvirtNetwork.xmlpath_fmt % (lnet.type, lnet.name))



class TestLibvirtDomain(unittest.TestCase):

    _multiprocess_shared_ = True

    def setUp(self):
        global TEST_DOMAIN_XML_0

        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="pplx-")

        xmlpath = os.path.join(self.workdir, "rhel-5-5-vm-1.xml")
        open(xmlpath, "w").write(
            TEST_DOMAIN_XML_0.replace("/var/lib/libvirt/images/rhel-5-5-guest-1", self.workdir)
        )

        bimg0 = os.path.join(self.workdir, "disk-0-base.img")
        bimg1 = os.path.join(self.workdir, "disk-1-base.img")
        img0 = os.path.join(self.workdir, "disk-0.qcow2")
        img1 = os.path.join(self.workdir, "disk-1.qcow2")

        pmaker.shell2("qemu-img create -f qcow2 %s 1G" % bimg0, self.workdir, log=False)
        pmaker.shell2("qemu-img create -f qcow2 %s 1G" % bimg1, self.workdir, log=False)

        pmaker.shell2("qemu-img create -f qcow2 -b %s %s" % (bimg0, img0), self.workdir, log=False)
        pmaker.shell2("qemu-img create -f qcow2 -b %s %s" % (bimg1, img1), self.workdir, log=False)

        self.xmlpath = xmlpath
        self.base_images = [bimg0, bimg1]
        self.delta_images = [img0, img1]

        self.xmlpath = xmlpath

    def tearDown(self):
        pmaker.rm_rf(self.workdir)

    def test_instance_by_xmlpath(self):
        domain = LibvirtDomain(xmlpath=self.xmlpath)

        self.assertEquals(domain.name, "rhel-5-5-vm-1")
        self.assertEquals(domain.arch, "i686")
        self.assertListEqual(domain.networks, ["net-1", "net-2"])

        self.assertListEqual(domain.base_images, self.base_images)
        self.assertListEqual(domain.delta_images, self.delta_images)



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

%define domainxml_savedir  $domain.xmlsavedir
%define domainxml_path     ${domain.xmlsavedir}/${domain.name}.xml

Name:           $name
Version:        $version
Release:        1%{?dist}
Summary:        libvirt domain $domain.name
Group:          $group
License:        $license
URL:            $url
Source0:        %{name}-%{version}.tar.${compressor.ext}
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
#for $rel in $relations
$rel.type:\t$rel.targets
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
    /usr/bin/virsh define %{domainxml_path}
elif [ \$1 = 2 ]; then  # update
    if `/usr/bin/virsh list | grep -q ${domain.name} 2>/dev/null`; then
        echo "${domain.name} is running. Run the following later when it's stopped to update its profile:"
        echo "   /usr/bin/virsh undefine ${domain.name}"
        echo "   /usr/bin/virsh define %{domainxml_path}"
    else
        /usr/bin/virsh undefine $domain.name
        /usr/bin/virsh define %{domainxml_path}
    fi
fi


%files
%defattr(-,root,root,-)
%doc README
#for $fi in $fileinfos
#if $fi.path in $domain.delta_images
$fi.rpm_attr()$fi.target
#end if
#end for


%files    base
%defattr(-,root,root,-)
%doc README
#for $fi in $fileinfos
#if $fi.path in $domain.base_images
$fi.rpm_attr()$fi.target
#end if
#end for
%{domainxml_path}


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

domainxml_path=${domain.xmlsavedir}/${domain.name}.xml

case "\$1" in
    configure)
        if `/usr/bin/virsh list --all | grep -q ${domain.name} 2>/dev/null`; then
            if `/usr/bin/virsh list | grep -q ${domain.name} 2>/dev/null`; then
                echo "${domain.name} is running. Run the following later when it's stopped:"
                echo "   /usr/bin/virsh define \$domainxml_path"
            else
                /usr/bin/virsh undefine ${domain.name}
                /usr/bin/virsh define \$domainxml_path
            fi
        else
            /usr/bin/virsh define \$domainxml_path
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
class LibvirtDomainXMLModifier(pmaker.FileInfoModifier):

    def __init__(self, domain):
        self.domain = domain

    def update(self, fileinfo, *args, **kwargs):
        if fileinfo.path.endswith(".xml"):  # it should be domain xml
            if getattr(fileinfo, "target", False):
                fileinfo.target = fileinfo.target.replace(os.path.dirname(fileinfo.path), self.domain.xmlsavedir)
            else:
                fileinfo.target = os.path.join(self.domain.xmlsavedir, "%s.xml" % self.domain.name)

        return fileinfo



class LibvirtDomainCollector(pmaker.FilelistCollector):

    _type = "libvirt.domain"

    def __init__(self, domname, pkgname, options):
        super(LibvirtDomainCollector, self).__init__(domname, pkgname, options)

        self.domain = LibvirtDomain(domname)
        self.modifiers.append(LibvirtDomainXMLModifier(self.domain))

    def list_targets(self, domname):
        """Gather files of which the domain $domname owns.
        
        @domname  str  Domain's name [dummy arg]
        """
        filelist = [self.domain.xmlpath] + self.domain.base_images + self.domain.delta_images

        return pmaker.unique(filelist)



class RpmLibvirtDomainPackageMaker(pmaker.RpmPackageMaker):

    global LIBVIRT_DOMAIN_TEMPLATES

    _templates = LIBVIRT_DOMAIN_TEMPLATES
    _type = "libvirt.domain"
    _collector = LibvirtDomainCollector

    def __init__(self, package, domname, options, *args, **kwargs):
        """
        $filelist (FILELIST) parameter is interpreted as a domain name.
        """
        super(LibvirtDomainCollector, self).__init__(package, domname, options)

        self.domain = LibvirtDomain(self.filelist)  # filelist == domain name
        self.package["domain"] = self.domain




class DebLibvirtDomainPackageMaker(pmaker.DebPackageMaker):

    global LIBVIRT_DOMAIN_TEMPLATES

    _templates = LIBVIRT_DOMAIN_TEMPLATES
    _type = "libvirt.domain"
    _collector = LibvirtDomainCollector

    def __init__(self, package, domname, options, *args, **kwargs):
        super(LibvirtDomainCollector, self).__init__(package, domname, options)

        self.domain = LibvirtDomain(self.filelist)
        self.package["domain"] = LibvirtDomain(domname)



if __name__ == '__main__':
    sys.path.append(os.curdir)

    def test(verbose=True):
        doctest.testmod(verbose=verbose, raise_on_error=True)

        (major, minor) = sys.version_info[:2]
        if major == 2 and minor < 5:
            unittest.main(argv=sys.argv[:1])
        else:
            unittest.main(argv=sys.argv[:1], verbosity=(verbose and 2 or 0))

    test()


# vim:sw=4:ts=4:et:
