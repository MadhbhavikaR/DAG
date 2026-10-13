# Releases

A GitHub Release is created automatically when a tag matching the utility branch name followed by an underscore and a semantic version is pushed.

For this utility, the tag format is:

```text
DAG-Jetson-Nano-4GB-Fan_Control_<MAJOR>.<MINOR>.<PATCH>
```

For example, `DAG-Jetson-Nano-4GB-Fan_Control_1.2.3`. Pre-release and build metadata suffixes are also accepted by the workflow when they follow Semantic Versioning syntax, such as `1.2.3-rc.1` or `1.2.3+build.4`.

Create the tag on the commit you intend to release, then push it:

```bash
git switch DAG-Jetson-Nano-4GB-Fan_Control
git pull --ff-only
git tag -a DAG-Jetson-Nano-4GB-Fan_Control_1.0.0 -m "Release 1.0.0"
git push origin DAG-Jetson-Nano-4GB-Fan_Control_1.0.0
```

The tag points to a specific commit; Git tags do not automatically follow a branch. Create the tag only after the desired code and checks are ready. The workflow validates the version, then creates a GitHub Release with generated release notes. It does not build or upload a platform-specific binary.
