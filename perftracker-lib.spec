%define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")
%define _ver 0.0.41

Name:		perftracker-lib
Version:	%{_ver}
Release:	0
Summary:	The perftracker libraries set

BuildArch:	noarch
Group:		Development/Libraries
License:	MIT

BuildRequires:	python
Requires:	python git gcc python-devel python-setuptools python-dateutil
Requires:       xorg-x11-server-Xvfb chromedriver google-chrome-stable libjpeg-devel zlib-devel

%description
The perftracker-lib is a set of performance and reporting python libraries (the
perftracker client, the UI crawler library and other helpers)

%install
mkdir $RPM_BUILD_ROOT/bin
touch $RPM_BUILD_ROOT/bin/pt-suite-uploader.py
touch $RPM_BUILD_ROOT/bin/pt-artifact-ctl.py

%post
echo -e "\n====== Installing the perftracker-lib v%{_ver} from sources =======\n"
echo "PRE easy_install git+https://github.com/perfguru87/perftracker-lib.git@v%{_ver}"
easy_install git+https://github.com/perfguru87/perftracker-lib.git@v%{_ver} || exit -1
echo -e "\n====== The perftracker-lib installation done ======================\n"

%postun
echo -e "\n====== Uninstalling the perftracker-lib v%{_ver} =======\n"
echo "rm -rf %{python_sitelib}/perftrackerlib-%{_ver}*.egg"
rm -rf "%{python_sitelib}/"perftrackerlib-%{_ver}*.egg
echo -e "\n====== The perftracker-lib uninstallation done =========\n"

%files

%ghost
/bin/pt-suite-uploader.py
/bin/pt-artifact-ctl.py

%changelog
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
