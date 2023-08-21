%define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")
%define _ver 0.1.8

Name:		python36-perftracker-lib
Version:	%{_ver}
Release:	0
Summary:	The perftracker libraries set

BuildArch:	noarch
Group:		Development/Libraries
License:	MIT

BuildRequires:	python
Requires:	epel-release python36 python36-pip python36-devel python36-dateutil python36-paramiko gcc openssl-devel

%description
The perftracker-lib is a set of performance and reporting python libraries (the
perftracker client and some helpers)

%install
mkdir $RPM_BUILD_ROOT/bin
touch $RPM_BUILD_ROOT/bin/pt-suite-uploader.py
touch $RPM_BUILD_ROOT/bin/pt-artifact-ctl.py

%post
echo -e "\n====== Installing the perftracker-lib v%{_ver} from sources =======\n"
echo "pip3.6 install --upgrade perftrackerlib==%{_ver}"
pip3.6 install --upgrade perftrackerlib==%{_ver}
echo -e "\n====== The perftracker-lib installation done ======================\n"

%postun
echo -e "\n====== Uninstalling the perftracker-lib v%{_ver} =======\n"
echo "pip3.6 uninstall -y perftrackerlib"
pip3.6 uninstall -y perftrackerlib
echo -e "\n====== The perftracker-lib uninstallation done =========\n"

%files

%ghost
/bin/pt-suite-uploader.py
/bin/pt-artifact-ctl.py

%changelog
* Mon Jul 20 2020 <perfguru87@gmail.com>
- require python36 explicitly
* Sat Jul 18 2020 <perfguru87@gmail.com>
- removed all the UI crawler capabilities (moved to perftracker_cp_crawler)
* Tue Oct 2 2018 <perfguru87@gmail.com>
- added pt-artifact-ctl.py - a tool to manage artifacts
* Thu Aug 16 2018 <perfguru87@gmail.com>
- added libjpeg-devel, zlib-devel needed for Pillow installation
* Tue Aug 7 2018 <perfguru87@gmail.com>
- update to 0.0.20
* Tue Aug 7 2018 <perfguru87@gmail.com>
- update to 0.0.19
* Mon Jul 30 2018 <perfguru87@gmail.com>
- initial version
