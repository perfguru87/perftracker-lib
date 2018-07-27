PWD=$(shell pwd)

all: rpms

rpms: clean
	mkdir -p "$(PWD)/rpmbuild"
	mkdir -p "$(PWD)/rpmbuild/SOURCES/"
	mkdir -p "$(PWD)/rpmbuild/BUILD/"
	mkdir -p "$(PWD)/rpmbuild/RPMS/$(ARCH)"

	(cd $(PWD)/rpmbuild/SOURCES/; ln -s ../../../ sources)

	rpmbuild --define '_topdir '"$(PWD)/rpmbuild" -bb --clean python-perftrackerlib.spec

clean:
	rm -rf "$(PWD)/rpmbuild/"
