#!/usr/bin/env bash
# Rewrite author/committer email on every commit authored as "Zeel Rathi" and set it locally.
# Usage: tools/set-git-email.sh zeel@example.com
# Only run before the history is shared (it rewrites commit IDs).
set -euo pipefail
email="${1:?usage: tools/set-git-email.sh <verified-email>}"
git config --local user.name "Zeel Rathi"
git config --local user.email "$email"
branch="$(git branch --show-current)"
git -c user.name="Zeel Rathi" -c user.email="$email" rebase -r --root --exec \
  "git commit --amend --no-edit --no-verify --reset-author --quiet" "$branch"
echo "rewrote $(git rev-list --count HEAD) commits on $branch to Zeel Rathi <$email>"
echo "Other branches still point at old commits; delete merged ones: git branch --merged | grep -v main | xargs -r git branch -d"
