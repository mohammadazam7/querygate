# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Fixed
- `count(*)` was refused as a wildcard read whenever the policy denied a column. It
  counts rows and reveals no column, so it is now allowed; a real `*` and a denied
  column inside `count(*) filter (...)` are still refused.

## [0.1.1] - 2026-11-18

### Added
- `querygate --rules` lists every rule with a one-line description of what it refuses.
  Thanks to @P1LOTRX (#2).

### Security
- SQLite's `readfile`, `writefile`, `edit`, `fsdir` and `load_extension` were allowed
  inside a SELECT; `writefile` writes to the database host's disk. They are now refused.
- Oracle calls into the `UTL_`, `DBMS_` and `OWA_` packages (network, file, job and mail
  access) and the `HTTPURITYPE` family are now refused, including when written with the
  `SYS.` prefix.

## [0.1.0] - 2026-11-16

### Added
- `check`, which parses a query in the target dialect and refuses it unless it is one
  read-only statement on allowed tables, away from denied columns, with a row limit.
- `Policy` with table patterns matched part by part, denied columns and a row limit.
- Refusals with a stable rule name and a message meant to be shown to the model.
- The `querygate` command, with JSON output and exit statuses for use from other tools.
