# 
# Makefile to build rpmkit srpm disctribution.
# 

REVISION ?= 1
VERSION	?= 0.1.$(shell date +%Y%m%d).$(REVISION)

DEBUG	?= 0

py_SOURCES = rpm2json.py xpack.py myrepo.py rpms2sqldb.py
sh_SOURCES = list-srpmnames-by-file.sh list-requires-by-package-name.sh

REQUIRES = python-cheetah,rpm-python,mock,rpm-build,sqlite,autoconf,automake

FULLNAME = Satoru SATOH
EMAIL	= ssato@redhat.com


# Do not edit:
WORKDIR	= /tmp/rpmkit-$(VERSION)-build
bindir	= $(WORKDIR)/usr/bin

py_SCRIPTS = $(patsubst %.py,$(bindir)/%,$(py_SOURCES))
sh_SCRIPTS = $(patsubst %.sh,$(bindir)/%,$(sh_SOURCES))

ifeq ($(DEBUG),1)
logopt	= --debug
else
logopt	= --verbose
endif


all: build


$(bindir):
	mkdir -p $@

$(bindir)/%: %.py
	@test -d $(bindir) || mkdir -p $(bindir)
	install -m 755 $< $@

$(bindir)/%: %.sh
	@test -d $(bindir) || mkdir -p $(bindir)
	install -m 755 $< $@

build: $(py_SCRIPTS) $(sh_SCRIPTS)
	find $(bindir) -type f | python xpack.py -n rpmkit --license GPLv3+ \
		--group "System Environment/Base" --pversion $(VERSION) \
		--url https://github.com/ssato/rpmkit/ \
		--summary "RPM toolKit" --requires $(REQUIRES) \
		--packager "$(FULLNAME)" --mail $(EMAIL) \
		-w $(WORKDIR) --destdir $(WORKDIR) \
		--ignore-owner $(logopt) -

clean:
	-test "x$(WORKDIR)" != "x/" && rm -rf $(WORKDIR)


.PHONY: build clean
