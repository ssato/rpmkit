#
# test code for swapi.py
#
# Copyright (C) 2011 Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
import os.path
import shlex
import sys
import unittest


moddir = os.path.dirname(__file__)
sys.path.append(moddir)
import swapi as S


def __helper(args):
    common_opts = ["--no-cache"]
    (res, _opts) = S.main(common_opts + shlex.split(args))
    assert res, "args=" + args


# TODO: More test cases
def test_api_wo_arg_and_sid():
    __helper("api.getVersion")


def test_api_wo_arg():
    __helper("channel.listSoftwareChannels")


def test_api_w_arg():
    __helper("--args=rhel-i386-server-5 channel.software.getDetails")


def test_api_w_arg_and_format_option():
    __helper(
        "-A rhel-i386-server-5 --format '%%(channel_description)s' " + \
            "channel.software.getDetails"
    )


def test_api_w_arg_multicall():
    __helper(
        "--list-args='rhel-i386-server-5,rhel-x86_64-server-5' " + \
            "channel.software.getDetails"
    )


def test_api_w_args():
    __helper(
        "-A 'rhel-i386-server-5,2010-04-01 08:00:00' " + \
            "channel.software.listAllPackages"
    )


def test_api_w_args_as_list():
    __helper(
        "-A '[\"rhel-i386-server-5\",\"2010-04-01 08:00:00\"]' " + \
            "channel.software.listAllPackages"
    )


# vim:sw=4 ts=4 et:
