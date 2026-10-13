#!/bin/sh
set -eu
if ! { [ -f /etc/prettyversion.txt ] || [ -d /mnt/us ] || pgrep lipc-daemon >/dev/null 2>&1; }; then
  echo "This installer is intended for a Kindle device." >&2
  printf "Continue anyway? [y/N]: "
  read -r answer
  case "$answer" in y|Y) ;; *) exit 1 ;; esac
fi
OWNER_REPO="MadhbhavikaR/DAG"
BRANCH="Kindle-Fetch"
API_URL="https://api.github.com/repos/${OWNER_REPO}/commits/${BRANCH}"
ZIP_URL="https://github.com/${OWNER_REPO}/archive/refs/heads/${BRANCH}.zip"
ZIP_FILE=/mnt/us/kindlefetch-repo.zip
EXTRACTED_DIR="/mnt/us/DAG-${BRANCH}"
INSTALL_DIR=/mnt/us/extensions/kindlefetch
CONFIG_FILE="$INSTALL_DIR/bin/kindlefetch_config"
TEMP_CONFIG=/mnt/us/kindlefetch_config
ZLIB_COOKIES_FILE="$INSTALL_DIR/bin/zlib_cookies.txt"
TEMP_ZLIB_COOKIES_FILE=/mnt/us/zlib_cookies.txt
VERSION_FILE="$INSTALL_DIR/bin/.version"
get_version() {
  api_response=$(curl -fsSL -H 'Accept: application/vnd.github+json' "$API_URL") || { echo unknown; return; }
  printf '%s' "$api_response" | grep -m1 '"sha"' | sed -E 's/.*"sha"[[:space:]]*:[[:space:]]*"([0-9a-f]+)".*/\1/' | cut -c1-7
}
mkdir -p /mnt/us/extensions
[ ! -f "$CONFIG_FILE" ] || cp -f "$CONFIG_FILE" "$TEMP_CONFIG"
[ ! -f "$ZLIB_COOKIES_FILE" ] || cp -f "$ZLIB_COOKIES_FILE" "$TEMP_ZLIB_COOKIES_FILE"
echo 'Downloading KindleFetch...'
curl -fsSL -o "$ZIP_FILE" "$ZIP_URL"
rm -rf "$EXTRACTED_DIR"
unzip -q -o "$ZIP_FILE" -d /mnt/us
rm -f "$ZIP_FILE"
SOURCE_DIR="$EXTRACTED_DIR/kindlefetch"
[ -d "$SOURCE_DIR" ] || { echo "Missing extension directory: $SOURCE_DIR" >&2; exit 1; }
echo 'Installing KindleFetch...'
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -R "$SOURCE_DIR"/. "$INSTALL_DIR"/
mkdir -p "$INSTALL_DIR/bin"
get_version > "$VERSION_FILE"
[ ! -f "$TEMP_CONFIG" ] || mv -f "$TEMP_CONFIG" "$CONFIG_FILE"
[ ! -f "$TEMP_ZLIB_COOKIES_FILE" ] || mv -f "$TEMP_ZLIB_COOKIES_FILE" "$ZLIB_COOKIES_FILE"
rm -rf "$EXTRACTED_DIR"
echo "KindleFetch installed. Version: $(cat "$VERSION_FILE")"
