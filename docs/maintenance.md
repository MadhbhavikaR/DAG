# Maintenance and releases

## Local checks

```sh
sh -n install.sh
for f in kindlefetch/bin/*.sh kindlefetch/bin/downloads/*.sh; do
  bash -n "$f"
done
bash -n kindlefetch/run.sh
```

Some `.sh` modules rely on Bash-compatible constructs. Syntax checks are necessary but not sufficient; device-level testing is still required for complete validation.

## Tag and release format
Push a tag like `Kindle-Fetch_1.2.3`. The workflow validates the prefix and three-part semantic version, builds `Kindle-Fetch_1.2.3.zip` containing `kindlefetch/`, and publishes a GitHub Release with generated notes.

```sh
git tag Kindle-Fetch_1.0.0
git push origin Kindle-Fetch_1.0.0
```

Use patch increments for compatible fixes, minor increments for backward-compatible features, and major increments for breaking changes. Do not reuse published version tags.

## Installer and updater
The installer fetches the branch archive and attempts to preserve configuration and cookies. The in-app updater checks the latest commit on this branch and invokes the branch-local installer. Recheck URLs after renaming the repository or branch.

## Device validation
When possible, test installation, KUAL launch, first-run setup, pagination, downloads, settings persistence, and upgrade preservation on a test Kindle. Do not claim hardware testing unless it was performed.
