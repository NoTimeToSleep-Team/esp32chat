%global debug_package %{nil}

Name:           local-chat-release
Version:        1
Release:        1
Summary:        Local Chat package repository configuration
License:        MIT
URL:            https://github.com/NoTimeToSleep-Team/esp32chat
BuildArch:      noarch

Requires:       /bin/sh
Requires:       rpm

%description
Installs the dnf repository definition and the signing key for Local Chat
packages.

After installing this package:

    sudo dnf install local-chat

%prep

%build

%install
mkdir -p %{buildroot}/etc/yum.repos.d %{buildroot}/etc/pki/rpm-gpg
install -m 0644 %{_sourcedir}/local-chat.repo %{buildroot}/etc/yum.repos.d/local-chat.repo
install -m 0644 %{_sourcedir}/local-chat.gpg %{buildroot}/etc/pki/rpm-gpg/local-chat.gpg

%post
rpm --import /etc/pki/rpm-gpg/local-chat.gpg >/dev/null 2>&1 || true
echo "Local Chat repository added — install the server with: sudo dnf install local-chat"

%files
%config(noreplace) /etc/yum.repos.d/local-chat.repo
/etc/pki/rpm-gpg/local-chat.gpg

%changelog
* Tue Nov 10 2026 Local Chat Team <280044855+NoTimeToSleep-Team@users.noreply.github.com> - 1-1
- Repository definition for Local Chat packages.
