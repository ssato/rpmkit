#! /usr/bin/python
#
# sqlminus.py - Query Oracle database.
#
#
# Copyright (C) 2009 - 2012 Red Hat, Inc.
# Copyright (C) 2008, 2009 Satoru SATOH <ssato@redhat.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# NOTE: This is just a script example to show how to access Oracle database in
# python. It is not a product supported by Red Hat and not intended for
# production use.
#
# SEE ALSO: http://cx-oracle.sourceforge.net/html/
#
"""
Examples:

## List label of channels given package belongs to.
##
$ ./sqlminus.py sql "SELECT DISTINCT A.LABEL FROM RHNCHANNEL A, \
> RHNCHANNELPACKAGE B, RHNPACKAGE C, RHNPACKAGENAME D WHERE D.NAME = \
> 'NetworkManager' AND A.ID = B.CHANNEL_ID AND B.PACKAGE_ID = C.ID AND \
> C.NAME_ID = D.ID"
('rhel-i386-as-4',)
('rhel-x86_64-as-4',)
('rhel-x86_64-server-5',)
('rhel-i386-server-5',)

## List name of packages own given file.
##
## (NOTE: SQL string is interpreted as a python format string. '%' is the
## special character in python format strings so that '%' must be escaped.)
##
$ ./sqlminus.py sql "SELECT DISTINCT D.NAME,B.NAME FROM RHNPACKAGEFILE \
> A, RHNPACKAGECAPABILITY B, RHNPACKAGE C, RHNPACKAGENAME D WHERE \
> B.NAME LIKE '%%libgcrypt.so.11' AND A.CAPABILITY_ID = B.ID AND \
> A.PACKAGE_ID = C.ID AND C.NAME_ID = D.ID"
('libgcrypt', '/lib/libgcrypt.so.11')
('libgcrypt', '/lib64/libgcrypt.so.11')
('libgcrypt', '/usr/lib/libgcrypt.so.11')
('libgcrypt', '/usr/lib64/libgcrypt.so.11')
"""

import logging
import optparse
import os
import pprint
import subprocess
import sys

try:
    import cx_Oracle
except ImportError:
    logging.error("Unable to load cx_Oracle module. Aborting...")
    sys.exit(0)  # Make not an error.

__version__ = '0.1.1'

DSN = 'rhnsat/rhnsat@rhnsat'


def connect(dsn):
    return cx_Oracle.connect(dsn)


def disconnect(conn):
    conn.close()


def try_to_explain_with_sqlplus(conn, sql):
    dsn = "%s/%s@%s" % (conn.username, conn.password, conn.tnsentry)
    cmdseq = """sqlplus %s << EOF | sed -nre '/^SQL>/,/^SQL>/p'
EXPLAIN PLAN FOR %s
SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY())
EXIT
EOF
""" % (dsn, sql)

    p = subprocess.Popen(cmdseq, shell=True)
    sys.exit(os.waitpid(p.pid, 0)[1])


def try_to_describe_with_sqlplus(conn, table):
    dsn = "%s/%s@%s" % (conn.username, conn.password, conn.tnsentry)
    cmdseq = """sqlplus %s << EOF | sed -nre '/^SQL>/,/^SQL>/p'
describe %s
EXIT
EOF
""" % (dsn, table)

    p = subprocess.Popen(cmdseq, shell=True)
    sys.exit(os.waitpid(p.pid, 0)[1])


def execute(conn, sql, noresult=False, **params):
    sql = sql % params

    cur = conn.cursor()
    cur.execute(sql)
    if noresult:
        cur.close()
        return
    else:
        res = [r for r in cur.fetchall()]
        cur.close()
        return res


## queries:
def analyze_table(conn, table):
    sql = 'ANALYZE TABLE %(table)s COMPUTE STATISTICS'
    return execute(conn, sql, True, table=table)


def take_all_stats(conn):
    sql = "SELECT a.table_name, b.bytes, a.avg_row_len " + \
          "FROM user_tables a JOIN user_segments b ON " + \
          "b.segment_name = a.table_name"
    return execute(conn, sql)


def all_tables(conn):
    sql = 'SELECT table_name FROM user_tables'
    return [r[0] for r in execute(conn, sql)]


def describe(conn, table):
    """sqlplus command 'desc[ribe]' alternative.

    @return array of dict,
    """
    def make_desc_dict(desc):
        return {'name': desc[0], 'type': desc[1].__name__,
                'display_size': desc[2], 'internal_size': desc[3],
                'precision': desc[4], 'scale': desc[5],
                'null_ok': desc[6] == 1, }

    cur = conn.cursor()
    try:
        cur.execute('select * from %s where 1 = 0' % table)  # dummy query.
        res = [make_desc_dict(d) for d in cur.description]
    except:
        try_to_describe_with_sqlplus(conn, table)
        res = [{'name': 'unknown', 'type': 'unknown', 'display_size': -1,
                'internal_size': -1, 'precision': -1, 'scale': -1,
                'null_ok': False}, ]
    return res


def calc_rowsize(conn, table):
    record_header = 3

    def col_size(data_size):
        return (1 if data_size < 250 else 3) + data_size

    descs = describe(conn, table)

    return record_header + sum([col_size(d.get('internal_size')) for d
                                in descs])


## main:
COMMANDS = ['an[alyze]', 'st[ats]', 'desc[rive]', 'rows[ize]',
            'li[st]', 'sq[l]']

USAGE = "%prog [OPTION ...] COMMAND (" + ", ".join(COMMANDS) + ')'


def opts_parser():
    p = optparse.OptionParser(USAGE)
    p.add_option('-d', '--dsn', dest='dsn', help='Specify datasource.',
                 default=DSN)
    p.add_option('-t', '--tables', dest='tables',
                 help='Comma separated table list or "all" (all tables).')
    p.add_option('-v', '--verbose', dest='verbose', action='store_true',
                 help='Verbose mode.', default=False)
    return p


def println(s, err=True):
    if err:
        sys.stderr.write(s + '\n')
    else:
        sys.stdout.write(s + '\n')


def parse_and_exec(options, args):
    cmd = args[0]
    conn = connect(options.dsn)

    tables = []
    if options.tables:
        if options.tables == 'all':
            tables = all_tables(conn)
        else:
            tables = options.tables.split(',')

    if cmd.startswith('st'):
        res = take_all_stats(conn)
        print >> sys.stdout, "# table: bytes avg_row_len"
        for r in res:
            print >> sys.stdout, "%s: %d %d" % (r[0], r[1], r[2])

    elif cmd.startswith('li'):
        for r in all_tables(conn):
            print >> sys.stdout, r

    elif cmd.startswith('sq'):
        if len(args) < 2:
            println("Usage: %s sq[l] SQL_EXPRESSION", True)
            println("\nSQL_EXPRESSION: e.g. 'SELECT * FROM aTable'", True)
            sys.exit(1)

        sql = args[1]
        if options.verbose:
            print >> sys.stdout, "# sql = '%s'" % sql
            pprint.pprint(execute(conn, sql))
        else:
            for r in execute(conn, sql):
                print >> sys.stdout, r

    else:
        if not tables:
            m = "No tables given. Please specify table[s] with " + \
                "--tables option."
            println(m)
            sys.exit(1)

        if cmd.startswith('an'):
            for t in tables:
                analyze_table(conn, t)

        elif cmd.startswith('desc'):
            for t in tables:
                println(" ")
                println("# table: " + t)
                println("# name, size(display), size(internal), precision, "
                        "nullable?")

                sql = ' '.join(["%(name)s", "%(display_size)d",
                                "%(internal_size)d", "%(precision)s",
                                "%(null_ok)s"])

                for r in describe(conn, t):
                    print >> sys.stdout, sql % r

        elif cmd.startswith('rows'):
            for t in tables:
                print >> sys.stdout, "%s: %d" % (t, calc_rowsize(conn, t))

        else:
            print >> sys.stderr, "No such commnd: '%s'." % cmd

    disconnect(conn)


def main():
    parser = opts_parser()
    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.print_help()
        sys.exit(0)

    parse_and_exec(options, args)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
