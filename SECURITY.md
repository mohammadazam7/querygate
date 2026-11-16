# Security policy

## Reporting a bypass

A query that querygate allows and that writes, reads a table or column outside the
policy, reaches a file or another server, or escapes the row limit is a security bug.
Please report it privately through GitHub's
[security advisories](https://github.com/mohammadazam7/querygate/security/advisories/new)
with the query, the policy and the dialect. Expect an acknowledgement within a few days.
Every confirmed bypass is fixed with a test containing the reported query.

## What querygate does not protect against

querygate checks the text of a query. It does not replace a read-only database role,
network controls, statement timeouts or scan limits; the README lists these limits. Use
it together with them.
