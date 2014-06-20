#!/bin/bash
#
# Migrate RPM Database files and fix 'version_mismatch' problem.
#
# Copyright (C) 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato redhat.com>
# License: MIT
#
# Requirements: mock and initialized root for each migration from/to
# distributions.
#
set -e

USAGE="Usage: $0 [Options...] /path/to/your/rpmdb/root"

FROM_DIST=
TO_DIST=rhel-5-x86_64
OUTDIR=$(mktemp -d -u)
CLEANUP=0
REBUILD=0

RPMDB_DUMP="/usr/lib/rpm/rpmdb_dump"
RPMDB_LOAD="/usr/lib/rpm/rpmdb_load"

function show_help () {
    cat <<EOH
${USAGE}
Options:
    -F FROM_DIST  Specify the 'FROM' distribution RPM DB was generated.
                  Disribution must be available in mock, that is, 
                  /etc/mock/<dist>.cfg must exist, its root dir must be
                  initialized
                  ([/var/lib/mock/<dist>]/root/usr/lib/rpm/rpmdb_load
                  and [/var/lib/mock/<dist>/root]/usr/lib/rpm/rpmdb_dump
                  should exist). Current running dist will be used if not set.

    -T TO_DIST    Specify the 'TO' distribution in which RPM DB to be used.
                  If you want to set to the current running dist, specify
                  special keyword "CUR". [$TO_DIST]

    -O OUTDIR     Specify the output dir [$OUTDIR]
EOH
}

function detect_dbtype () {
    local dbpath=$1
    # echo "$(file ${dbpath} | sed -r 's@^(.+/[A-Z][^:]+):.*\(([^,]+),.*@test "x${dbpath}" = "x\1" \&\& dbtype=$(echo \2 | tr A-z a-z) || :@g')"
    test -f ${dbpath} && \
        file ${dbpath} | sed -r 's/.* DB \(([^,]+).*/\1/' | tr A-Z a-z || \
        echo "unknown"
}

function err_root_not_exist () {
    local sys_root=$1
    local dist=$2

    cat << EOM
[Error] Root dir '${sys_root:?}' does not exist for the dist '${dist:?}'.
        Try 'mock -r ${dist} init' to initialize dist.
EOM
}

function err_bin_not_exist () {
    local bin=$1
    local dist=$2

    cat << EOM
[Error] Program ${dump_bin} does not eixst.
        Try 'mock -r ${dist} init' to initialize dist.
EOM
}

function ld_library_path_for_root () {
    local root=$1
    local ldpath=""
    for d in $(ls -d ${root}/usr/lib*); do
        test "x${d##*/}" = "xlibexec" && continue || :
        test "x$ldpath" = "x" && ldpath="$d" || ldpath="$ldpath:$d"
    done
    echo "$ldpath"
}

while getopts "F:T:O:Crh" opt
do
  case $opt in
    F) FROM_DIST="$OPTARG" ;;
    T) TO_DIST="$OPTARG" ;;
    O) OUTDIR="$OPTARG" ;;
    C) CLEANUP=1 ;;
    r) REBUILD=1 ;;
    h) show_help; exit 0 ;;
    \?) show_help; exit 1 ;;
  esac
done
shift $(($OPTIND - 1))

FROM_RPMDB_ROOT=$1

if test "x$FROM_RPMDB_ROOT" = "x"; then
    show_help
    exit 1
fi

# 1. Dump text
#
# ex. LD_LIBRARY_PATH=/var/lib/mock/rhel-6-x86_64/root/usr/lib64 \
#       /var/lib/mock/rhel-6-x86_64/root/usr/lib/rpm/rpmdb_dump \
#       -f Packages.txt Packages

if test "x$FROM_DIST" = "x"; then
    FROM_SYS_ROOT=/
else
    FROM_SYS_ROOT=/var/lib/mock/${FROM_DIST}/root/
    RPMDB_DUMP=${FROM_SYS_ROOT}/usr/lib/rpm/rpmdb_dump
    FROM_SET_LIBPATH=$(ld_library_path_for_root ${FROM_SYS_ROOT})

    if test ! -d ${FROM_SYS_ROOT}; then
        err_root_not_exist ${FROM_SYS_ROOT} ${FROM_DIST}
        exit 1
    fi
    if test ! -x ${RPMDB_DUMP}; then
        err_bin_not_exist ${RPMDB_DUMP} ${FROM_DIST}
        exit 1
    fi
fi

if test "x$TO_DIST" = "xCUR"; then
    TO_SYS_ROOT=/
else
    TO_SYS_ROOT=/var/lib/mock/${TO_DIST}/root/
    RPMDB_LOAD=${TO_SYS_ROOT}/usr/lib/rpm/rpmdb_load
    TO_SET_LIBPATH=$(ld_library_path_for_root ${TO_SYS_ROOT})

    if test ! -d ${TO_SYS_ROOT}; then
        err_root_not_exist ${TO_SYS_ROOT} ${TO_DIST}
        exit 1
    fi
    if test ! -x ${RPMDB_LOAD}; then
        err_bin_not_exist ${RPMDB_LOAD} ${TO_DIST}
        exit 1
    fi
fi

if test -d ${OUTDIR}; then
    echo "[Info] Use existing ${OUTDIR} ..."
else
    echo "[Info] Creating ${OUTDIR} ..."
    mkdir -p ${OUTDIR}
fi

for dbpath in ${FROM_RPMDB_ROOT}/var/lib/rpm/[A-Z]*; do
    dbname=${dbpath##*/}
    dumpfile=${OUTDIR}/${dbname}.txt
    outfile=${OUTDIR}/${dbname}

    from_dbtype=$(detect_dbtype ${FROM_SYS_ROOT}/var/lib/rpm/${dbname})
    to_dbpath=${TO_SYS_ROOT}/var/lib/rpm/${dbname}

    if test -f ${to_dbpath}; then
        to_dbtype=$(detect_dbtype ${to_dbpath})
    else
        cat << EOM
[Warn] RPM DB ${dbname} should not exist in ${TO_DIST}.
       Skip to convert ${dbname}.
EOM
        if test "x${CLEANUP}" = "x1"; then
            echo "[Warn] cleanup this db: ${dbpath}"
            rm -f ${dbpath}
        fi
        continue
    fi

   # TODO: How to convert between Btree and hash (-t just looks implying the input format) ?
    # LD_LIBRARY_PATH=${TO_SET_LIBPATH} ${RPMDB_LOAD} -t ${from_dbtype} -f ${dumpfile} ${outfile}

    LD_LIBRARY_PATH=${FROM_SET_LIBPATH} ${RPMDB_DUMP} -f ${dumpfile} ${dbpath} && \
    LD_LIBRARY_PATH=${TO_SET_LIBPATH} ${RPMDB_LOAD} -f ${dumpfile} ${outfile}

    if test "${from_dbtype:?}" != "${to_dbtype:?}"; then
        infile=${outfile}.${from_dbtype}
        python=${TO_SYS_ROOT}/usr/bin/python

        test "${from_dbtype}" = "hash" && indb_open="bsddb.hashopen" || indb_open="bsddb.btopen"
        test "${to_dbtype}" = "hash" && outdb_open="bsddb.hashopen" || outdb_open="bsddb.btopen"

        conv="import bsddb, operator; indb = ${indb_open}('${infile}', flag='r'); outdb = ${outdb_open}('${outfile}'); [operator.setitem(outdb, k, v) for k, v in indb.iteritems()]"

        echo -ne "[Info] Try to convert from ${from_dbtype} to ${to_dbtype} ..."
        mv ${outfile} ${infile} && LD_LIBRARY_PATH=${TO_SET_LIBPATH} ${python} -c "${conv}"
        echo " Done"
    fi

done

# Rebuild.
if test "x${REBUILD}" = "x1"; then
    echo -ne "[Info] Try to rebuild db in ${OUTDIR} ..."
    LD_LIBRARY_PATH=${TO_SET_LIBPATH} ${TO_SYS_ROOT}/usr/bin/rpmdb --rebuilddb --dbpath ${OUTDIR}
    echo " Done"
fi

# vim:sw=4:ts=4:et:
