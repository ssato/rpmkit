#! /bin/bash
set -e
#set -x

sqlite="/usr/bin/sqlite3"
usage="Usage: $0 sqldb filename or $0 sqldb file_basename"

if test ! -x $sqlite; then
    echo $usage
    exit 1
fi

sqldb=$1
filename=$2
if test -z "$filename"; then
    echo $usage
    exit 1
fi

filename0="${filename:0:1}"
if test "x$filename0" = "x/"; then
    sql="SELECT p.srpmname FROM packages as p, files as f WHERE p.pid = f.pid AND f.path = \"$filename\""
else
    sql="SELECT p.srpmname FROM packages as p, files as f WHERE p.pid = f.pid AND f.basename = \"$filename\""
fi

$sqlite $sqldb "$sql" | sort | uniq

# vim: set sw=4 ts=4 et:
