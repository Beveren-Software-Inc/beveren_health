#!/usr/bin/env bash
#
# Semgrep check for beveren_health.
#
# Runs the Frappe Semgrep rules (https://github.com/frappe/semgrep-rules) and
# fails only on findings that are NEW compared to a baseline commit, so the
# findings that already exist in the app do not block contributors.
#
# Used by:
#   * the `semgrep` hook in .pre-commit-config.yaml -> runs on every commit
#     (baseline defaults to HEAD, i.e. exactly what is being committed)
#   * the `pre-commit` job in .github/workflows/ci.yml -> runs on every push
#     and pull request (baseline is the previous commit / PR base commit)
#
# Environment variables:
#   SEMGREP_RULES_REPO       rules repository cloned when the cache is empty
#   SEMGREP_RULES_DIR        cache directory for the cloned rules
#   SEMGREP_BASELINE_COMMIT  commit to diff against (default: HEAD)
#
# Any extra arguments are forwarded to `semgrep ci`, e.g.
#   scripts/run_semgrep.sh --config r/python.lang.correctness
set -euo pipefail

RULES_REPO="${SEMGREP_RULES_REPO:-https://github.com/frappe/semgrep-rules.git}"
RULES_DIR="${SEMGREP_RULES_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/frappe-semgrep-rules}"
BASELINE="${SEMGREP_BASELINE_COMMIT:-HEAD}"

if [ ! -d "$RULES_DIR/rules" ]; then
	printf 'Cloning Frappe Semgrep rules into %s\n' "$RULES_DIR"
	rm -rf "$RULES_DIR"
	git clone --depth 1 "$RULES_REPO" "$RULES_DIR"
fi

args=(ci --config "$RULES_DIR/rules" --dry-run)

if resolved="$(git rev-parse --verify --quiet "${BASELINE}^{commit}")"; then
	args+=(--baseline-commit "$resolved")
else
	printf 'Semgrep baseline "%s" not found - scanning the whole tree.\n' "$BASELINE"
fi

exec semgrep "${args[@]}" "$@"
