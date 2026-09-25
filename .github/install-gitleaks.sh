#!/bin/bash
set -euo pipefail

VERSION=8.30.1
SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb

into="${1:?usage: install-gitleaks.sh <directory to install into>}"

if [ -x "$into/gitleaks" ] \
  && "$into/gitleaks" version 2>/dev/null | grep -qxF "$VERSION"; then
  exit 0
fi

room="$(mktemp -d)"
trap 'rm -rf "$room"' EXIT

curl -sSfL -o "$room/gitleaks.tar.gz" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_linux_x64.tar.gz"
printf '%s  %s\n' "$SHA256" "$room/gitleaks.tar.gz" | sha256sum -c -
tar -xzf "$room/gitleaks.tar.gz" -C "$room" gitleaks

mkdir -p "$into"
mv "$room/gitleaks" "$into/gitleaks"
