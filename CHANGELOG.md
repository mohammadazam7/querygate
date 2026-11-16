# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-16

### Added
- `check`, which parses a query in the target dialect and refuses it unless it is one
  read-only statement on allowed tables, away from denied columns, with a row limit.
- `Policy` with table patterns matched part by part, denied columns and a row limit.
- Refusals with a stable rule name and a message meant to be shown to the model.
- The `querygate` command, with JSON output and exit statuses for use from other tools.
