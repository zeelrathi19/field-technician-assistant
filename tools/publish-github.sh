#!/usr/bin/env bash
# Create a PRIVATE GitHub repo and push main without ever writing the token to disk,
# a remote URL, git config, or shell history.
#
#   tools/publish-github.sh <owner> <repo> [--org] [--public] [--allow-placeholder-email]
#
# Token: taken from $GH_TOKEN if set, otherwise prompted silently. Needs a fine-grained
# token with "Administration: write" + "Contents: write" on the target (or classic `repo`).
set -euo pipefail
owner="${1:?usage: tools/publish-github.sh <owner> <repo> [--org] [--public]}"; repo="${2:?repo name}"; shift 2
org=0; private=true; allow_placeholder=0
for a in "$@"; do case "$a" in --org) org=1;; --public) private=false;; --allow-placeholder-email) allow_placeholder=1;; esac; done

cd "$(git rev-parse --show-toplevel)"
[ "$(git branch --show-current)" = "main" ] || { echo "checkout main first"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean"; exit 1; }
python3 tools/scan_secrets.py
if git log --format='%ae %ce' | grep -q placeholder.invalid && [ $allow_placeholder = 0 ]; then
  echo "Commits still use the placeholder email. Run tools/set-git-email.sh <email> first (a push makes rewriting costly)," >&2
  echo "or pass --allow-placeholder-email to publish anyway." >&2; exit 1
fi

TOKEN="${GH_TOKEN:-}"
if [ -z "$TOKEN" ]; then read -r -s -p "GitHub token (input hidden): " TOKEN; echo; fi
api() { curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }

login="$(api https://api.github.com/user | python3 -c 'import sys,json; print(json.load(sys.stdin).get("login",""))')"
[ -n "$login" ] || { echo "token rejected by GitHub"; exit 1; }
echo "authenticated as $login"

endpoint="https://api.github.com/user/repos"; [ $org = 1 ] && endpoint="https://api.github.com/orgs/$owner/repos"
body=$(printf '{"name":"%s","private":%s,"description":"Grounded, policy-enforced field technician assistant (FastAPI + React)","has_wiki":false,"auto_init":false}' "$repo" "$private")
code=$(api -o /tmp/.gh_create.json -w '%{http_code}' -X POST "$endpoint" -d "$body")
if [ "$code" = 201 ]; then echo "created $owner/$repo (private=$private)";
elif [ "$code" = 422 ]; then echo "repo exists; pushing to it";
else echo "create failed ($code): $(python3 -c 'import json;print(json.load(open("/tmp/.gh_create.json")).get("message"))')"; rm -f /tmp/.gh_create.json; exit 1; fi
rm -f /tmp/.gh_create.json

url="https://github.com/$owner/$repo.git"
git remote get-url origin >/dev/null 2>&1 && git remote set-url origin "$url" || git remote add origin "$url"

askpass="$(mktemp)"; trap 'rm -f "$askpass"' EXIT
printf '#!/bin/sh\ncase "$1" in *sername*) echo x-access-token;; *) echo "$GH_PUSH_TOKEN";; esac\n' > "$askpass"; chmod 700 "$askpass"
GH_PUSH_TOKEN="$TOKEN" GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 \
  git -c credential.helper= push -u origin main
echo "pushed main -> $url"
echo "Next: in GitHub settings add reviewers/collaborators; branch protection on main requires a paid plan for private repos."
