# 
# Makefile to build rpmkit srpm disctribution.
# 

REVISION ?= 1
VERSION	?= 0.1.$(shell date +%Y%m%d).$(REVISION)
PMVERSION ?= 0.2.$(shell date +%Y%m%d).$(REVISION)

DEBUG	?= 0

#py_SOURCES = rpm2json.py xpack.py myrepo.py rpms2sqldb.py
py_SOURCES = rpm2json.py myrepo.py rpms2sqldb.py list_errata_for_rpmlist.py
py_LIB_SOURCES = swapi.py
sh_SOURCES = list-srpmnames-by-file.sh list-requires-by-package-name.sh

REQUIRES = python-cheetah,rpm-python,mock,rpm-build,sqlite,autoconf,automake,packagemaker

FULLNAME = Satoru SATOH
EMAIL	= satoru.satoh@gmail.com


# Do not edit:
WORKDIR	= /tmp/rpmkit-$(VERSION)-build
bindir	= $(WORKDIR)/usr/bin
etcdir	= $(WORKDIR)/etc
etcdirs	= $(etcdir)/myrepo.d
pylibdir = $(WORKDIR)/$(shell python -c "import distutils.sysconfig; print distutils.sysconfig.get_python_lib()")

bin_PROGRAMS = $(bindir)/swapi
py_SCRIPTS = $(patsubst %.py,$(bindir)/%,$(py_SOURCES))
sh_SCRIPTS = $(patsubst %.sh,$(bindir)/%,$(sh_SOURCES))
py_LIBS = $(patsubst %.py,$(pylibdir)/%,$(py_LIB_SOURCES))

OBJS	= $(bin_PROGRAMS) $(py_SCRIPTS) $(sh_SCRIPTS) $(etcdirs) $(py_LIBS)

ifeq ($(DEBUG),1)
logopt	= --debug
else
logopt	= --verbose
endif


all: build


$(bindir):
	mkdir -p $@

$(bin_PROGRAMS): swapi
	@test -d $(bindir) || mkdir -p $(bindir)
	install -m 755 $< $@

$(bindir)/%: %.py
	@test -d $(bindir) || mkdir -p $(bindir)
	install -m 755 $< $@

$(bindir)/%: %.sh
	@test -d $(bindir) || mkdir -p $(bindir)
	install -m 755 $< $@

$(pylibdir)/%: %.py
	@test -d $(pylibdir) || mkdir -p $(pylibdir)
	install -m 644 $< $@

$(etcdir):
	@test -d $(etcdir) || mkdir -p $(etcdir)

$(etcdirs): $(etcdir)
	mkdir -p $@

$(WORKDIR)/files.list: $(OBJS)
	find $(WORKDIR) -type f > $@.tmp
	for d in $(etcdirs); do echo $$d >> $@.tmp; done
	mv $@.tmp $@


build: build-rpmkit

build-rpmkit: $(WORKDIR)/files.list
	pmaker -n rpmkit --license GPLv3+ \
		--group "System Environment/Base" --pversion $(VERSION) \
		--url https://github.com/ssato/rpmkit/ \
		--summary "RPM toolKit" \
		--relations "requires:$(REQUIRES)" \
		--packager "$(FULLNAME)" --email $(EMAIL) \
		--upto sbuild \
		-w $(WORKDIR) --destdir $(WORKDIR) \
		--ignore-owner $(logopt) \
		$(WORKDIR)/files.list

clean:
	-test "x$(WORKDIR)" != "x/" && rm -rf $(WORKDIR)


.PHONY: build clean
