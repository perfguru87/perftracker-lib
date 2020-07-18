%define _ver %(grep "__version__ = " ../perftrackerlib/__init__.py | cut -d'"' -f 2)

%define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")

Name:		python-perftrackerlib
Version:	%{_ver}
Release:	0%{?dist}
Summary:	The perftracker client libraries.

Group:		Development/Libraries
License:	MIT
Source:		sources

BuildRequires:	python
Requires:	python

%description
The pertrackerlib is a set of libraries for performance testing and perftracker
https://github.com/perfguru87/perftracker

%prep
ln -fsn ../../../ sources

%build
cd sources/
%{__python} ./setup.py build

%install
cd sources/
%{__python} ./setup.py install -O1 --root=$RPM_BUILD_ROOT

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
%{python_sitelib}/perftrackerlib/
%exclude %{python_sitelib}/perftrackerlib-*.egg-info/
%exclude %{python_sitelib}/test/

%changelog
* Thu Jul 26 2018 <perfguru87@gmail.com>
- initial version
