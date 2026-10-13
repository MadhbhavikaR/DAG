# KindleFetch

KindleFetch is a menu-driven shell utility for jailbroken Kindle devices. It helps you search for books from supported catalogues and download selected files directly to the Kindle, without needing a separate computer.

## What it does

- Search a catalogue and browse paginated results.
- Filter results by content, file format, language, source, and sort order.
- Download selected results from supported mirrors when available.
- Manage books and folders stored on the Kindle.
- Configure the download directory, result display, subfolders, network DNS, catalogue URLs, and optional account login.
- Check for updates from the release branch.

## Requirements

- A jailbroken Kindle with KUAL or KPM available.
- [kterm](https://github.com/bfabiszewski/kterm/releases), installed under the Kindle's `extensions` directory.
- Network access from the Kindle.
- KOReader is optional; use it if you want an additional reader for supported formats.

Kindle modification can carry a risk of data loss or device issues. Follow device-specific guidance and keep backups before changing your Kindle software.

## Install

### Automatic installation

1. Install kterm and launch it from KUAL.
2. In kterm, run:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/MadhbhavikaR/DAG/Kindle-Fetch/install.sh | sh
   ```

3. Follow the prompts. When installation completes, exit kterm and launch **KindleFetch** from KUAL.

### Manual installation

1. Download the `Kindle-Fetch_<version>.zip` asset from this branch's [Releases](https://github.com/MadhbhavikaR/DAG/releases).
2. Extract the `kindlefetch` directory into the Kindle's `extensions` directory.
3. Confirm that the `kindlefetch` directory contains `config.xml`, `menu.json`, `run.sh`, and `bin/`.
4. Launch KindleFetch from KUAL.

## First run

On the first launch, follow the setup prompts to choose a destination directory and optional account settings. The app saves its configuration under `extensions/kindlefetch/bin/`. Settings can be changed later from the Settings menu.

## Use

Open KindleFetch from KUAL. Choose **Search and download books** to search, browse results, and select an available source. **Filter search results** adjusts search criteria, **List my books** manages files stored on the device, and **Settings** controls preferences and update checks.

The program relies on third-party catalogues and mirrors that can change or become unavailable. Availability, account requirements, and supported formats depend on those services. Only download and keep content you are legally entitled to access in your jurisdiction.

## Updates and releases

Releases are created automatically when a tag matching `Kindle-Fetch_<semantic-version>` is pushed. Use semantic versions such as `Kindle-Fetch_1.0.0`, `Kindle-Fetch_1.1.0`, or `Kindle-Fetch_2.0.0`. The release includes a ZIP of the installable `kindlefetch/` extension.

## Documentation

Project and maintenance instructions are organized with the DOX framework in `AGENTS.md` and the scoped `AGENTS.md` files alongside the relevant directories. These documents are written for contributors and coding agents; this README is the human-oriented overview and usage guide.

---

Inspired by https://github.com/justrals/KindleFetch.
