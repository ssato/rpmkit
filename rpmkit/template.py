"""
Subset of jinja2_cli.render from https://github.com/ssato/python-jinja2-cli
"""
from jinja2.exceptions import TemplateNotFound

import codecs
import jinja2
import locale
import os.path
import os
import sys


ENCODING = locale.getdefaultlocale()[1] or "UTF-8"

# pylint: disable=no-member
reload(sys)
sys.setdefaultencoding(ENCODING.lower())
# pylint: enable=no-member

sys.stdout = codecs.getwriter(ENCODING)(sys.stdout)
sys.stderr = codecs.getwriter(ENCODING)(sys.stderr)
open = codecs.open


def normpath(path):
    """Normalize given path in various different forms.

    >>> normpath("/tmp/../etc/hosts")
    '/etc/hosts'
    >>> normpath("~root/t")
    '/root/t'
    """
    if "~" in path:
        fs = [os.path.expanduser, os.path.normpath, os.path.abspath]
    else:
        fs = [os.path.normpath, os.path.abspath]

    return chaincalls(fs, path)


def chaincalls(callables, x):
    """
    :param callables: callable objects to apply to x in this order
    :param x: Object to apply callables
    """
    for c in callables:
        assert callable(c), "%s is not callable object!" % str(c)
        x = c(x)

    return x


def tmpl_env(paths):
    """
    :param paths: Template search paths
    """
    return jinja2.Environment(loader=jinja2.FileSystemLoader(paths))


def render_s(tmpl_s, ctx, paths=[os.curdir]):
    """
    Compile and render given template string `tmpl_s` with context `context`.

    :param tmpl_s: Template string
    :param ctx: Context dict needed to instantiate templates
    :param paths: Template search paths

    >>> s = render_s('a = {{ a }}, b = "{{ b }}"', {'a': 1, 'b': 'bbb'})
    >>> assert s == 'a = 1, b = "bbb"'
    """
    return tmpl_env(paths).from_string(tmpl_s).render(**ctx)


def render_impl(filepath, ctx, paths):
    """
    :param filepath: (Base) filepath of template file or '-' (stdin)
    :param ctx: Context dict needed to instantiate templates
    :param paths: Template search paths
    """
    env = tmpl_env(paths)
    return env.get_template(os.path.basename(filepath)).render(**ctx)


def render(filepath, ctx, paths, ask=False):
    """
    Compile and render template, and return the result.

    Similar to the above but template is given as a file path `filepath` or
    sys.stdin if `filepath` is '-'.

    :param filepath: (Base) filepath of template file or '-' (stdin)
    :param ctx: Context dict needed to instantiate templates
    :param paths: Template search paths
    :param ask: Ask user for missing template location if True
    """
    if filepath == '-':
        return render_s(sys.stdin.read(), ctx, paths)
    else:
        try:
            return render_impl(filepath, ctx, paths)
        except TemplateNotFound as mtmpl:
            if not ask:
                raise RuntimeError("Template Not found: " + str(mtmpl))

            usr_tmpl = raw_input(
                "\n*** Missing template '%s'. "
                "Please enter absolute or relative path starting from "
                "'.' to the template file: " % mtmpl
            )
            usr_tmpl = normpath(usr_tmpl.strip())
            usr_tmpldir = os.path.dirname(usr_tmpl)

            return render_impl(usr_tmpl, ctx, paths + [usr_tmpldir])

# vim:sw=4:ts=4:et:
