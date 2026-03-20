#!/bin/bash
set -xe

winget_repo=$1
setup_exe=$2
TAG_NAME=$(ci/tag-name.sh)
PACKAGE_IDENTIFIER="wakamex.wakterm"
PUBLISHER="wakamex"
MANIFEST_ROOT="manifests/w/wakamex/wakterm/$TAG_NAME"

cd "$winget_repo" || exit 1

# First sync repo with upstream
git remote add upstream https://github.com/microsoft/winget-pkgs.git || true
git fetch upstream master --quiet
git checkout -b "$TAG_NAME" upstream/master

exehash=$(sha256sum -b ../$setup_exe | cut -f1 -d' ' | tr a-f A-F)

release_date=$(git show -s "--format=%cd" "--date=format:%Y-%m-%d")

# Create the directory structure
mkdir -p "$MANIFEST_ROOT"

cat > "$MANIFEST_ROOT/$PACKAGE_IDENTIFIER.installer.yaml" <<-EOT
PackageIdentifier: $PACKAGE_IDENTIFIER
PackageVersion: $TAG_NAME
MinimumOSVersion: 10.0.17763.0
InstallerType: inno
UpgradeBehavior: install
ReleaseDate: $release_date
Installers:
- Architecture: x64
  InstallerUrl: https://github.com/wakamex/wakterm/releases/download/$TAG_NAME/$setup_exe
  InstallerSha256: $exehash
  ProductCode: '{BCF6F0DA-5B9A-408D-8562-F680AE6E1EAF}_is1'
ManifestType: installer
ManifestVersion: 1.1.0
EOT

cat > "$MANIFEST_ROOT/$PACKAGE_IDENTIFIER.locale.en-US.yaml" <<-EOT
PackageIdentifier: $PACKAGE_IDENTIFIER
PackageVersion: $TAG_NAME
PackageLocale: en-US
Publisher: $PUBLISHER
PublisherUrl: https://github.com/wakamex
PublisherSupportUrl: https://github.com/wakamex/wakterm/issues
Author: $PUBLISHER
PackageName: wakterm
PackageUrl: https://wakterm.org
License: MIT
LicenseUrl: https://github.com/wakamex/wakterm/blob/main/LICENSE.md
ShortDescription: A GPU-accelerated cross-platform terminal emulator and multiplexer implemented in Rust
ReleaseNotesUrl: https://wakterm.org/changelog.html#$TAG_NAME
ManifestType: defaultLocale
ManifestVersion: 1.1.0
EOT

cat > "$MANIFEST_ROOT/$PACKAGE_IDENTIFIER.yaml" <<-EOT
PackageIdentifier: $PACKAGE_IDENTIFIER
PackageVersion: $TAG_NAME
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.1.0
EOT

git add --all
git diff --cached
git commit -m "New version: $PACKAGE_IDENTIFIER version $TAG_NAME"
git push --set-upstream origin "$TAG_NAME" --quiet
