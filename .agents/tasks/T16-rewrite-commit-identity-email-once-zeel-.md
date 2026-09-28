---
id: T16
title: Rewrite commit identity email once Zeel's address is known
status: done
priority: P0
owner: 
depends_on: []
paths: []
---

## Goal
Run `tools/set-git-email.sh <email>` on the integration clone; force-push only if nothing was shared yet.

## Acceptance
- [x] git log shows the verified email
- [x] `make check` passes
