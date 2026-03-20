#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: ci/fork-rust-loc.sh [BASE_REF] [HEAD_REF]

Compare Rust LOC in HEAD_REF against BASE_REF and print a few useful variants.

Defaults:
  BASE_REF=upstream/main
  HEAD_REF=HEAD

Reported variants:
  1. all .rs files
  2. excluding tests/, test/, examples/, benches/, build.rs
  3. same as #2, plus excluding deps/
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if (( $# > 2 )); then
  usage >&2
  exit 1
fi

BASE_REF="${1:-upstream/main}"
HEAD_REF="${2:-HEAD}"

require_ref() {
  local ref="$1"
  if ! git rev-parse --verify -q "${ref}^{commit}" >/dev/null; then
    printf 'error: ref not found: %s\n' "$ref" >&2
    exit 1
  fi
}

require_ref "$BASE_REF"
require_ref "$HEAD_REF"

MERGE_BASE="$(git merge-base "$BASE_REF" "$HEAD_REF")"

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

git archive "$BASE_REF" | tar -x -C "$tmpdir"

count_total_lines() {
  local mode="$1"

  case "$mode" in
    all)
      find "$tmpdir" -name '*.rs' -print0
      ;;
    core)
      find "$tmpdir" \
        \( -path '*/tests/*' -o -path '*/test/*' -o -path '*/examples/*' -o -path '*/benches/*' -o -name 'build.rs' \) -prune \
        -o -name '*.rs' -print0
      ;;
    core_no_deps)
      find "$tmpdir" \
        -path "$tmpdir/deps" -prune \
        -o \( -path '*/tests/*' -o -path '*/test/*' -o -path '*/examples/*' -o -path '*/benches/*' -o -name 'build.rs' \) -prune \
        -o -name '*.rs' -print0
      ;;
    *)
      printf 'internal error: unknown mode %s\n' "$mode" >&2
      exit 1
      ;;
  esac | xargs -0 wc -l | awk 'END {print $1 + 0}'
}

diff_stats() {
  local mode="$1"
  local filter='1'

  case "$mode" in
    all)
      filter='1'
      ;;
    core)
      filter='$3 !~ /(^|\/)tests?\// && $3 !~ /(^|\/)examples\// && $3 !~ /(^|\/)benches\// && $3 !~ /(^|\/)build\.rs$/'
      ;;
    core_no_deps)
      filter='$3 !~ /(^|\/)deps\// && $3 !~ /(^|\/)tests?\// && $3 !~ /(^|\/)examples\// && $3 !~ /(^|\/)benches\// && $3 !~ /(^|\/)build\.rs$/'
      ;;
    *)
      printf 'internal error: unknown mode %s\n' "$mode" >&2
      exit 1
      ;;
  esac

  awk "
    BEGIN { add = 0; del = 0; files = 0 }
    ${filter} {
      add += \$1
      del += \$2
      files += 1
    }
    END {
      printf \"%d %d %d\\n\", files, add, del
    }
  " < <(git diff --numstat "${BASE_REF}...${HEAD_REF}" -- '*.rs')
}

print_row() {
  local label="$1"
  local mode="$2"
  local total current files add del net churn_pct net_pct pct_wez

  total="$(count_total_lines "$mode")"
  read -r files add del < <(diff_stats "$mode")
  net=$((add - del))
  current=$((total + net))
  churn_pct="$(awk -v a="$add" -v d="$del" -v t="$total" 'BEGIN { if (t == 0) print "0.00"; else printf "%.2f", ((a + d) / t) * 100 }')"
  net_pct="$(awk -v n="$net" -v t="$total" 'BEGIN { if (t == 0) print "0.00"; else printf "%.2f", (n / t) * 100 }')"
  pct_wez="$(awk -v b="$total" -v c="$current" 'BEGIN { if (c <= 0) print "0.00"; else printf "%.2f", (b / c) * 100 }')"

  printf '%-34s %8d %7d %7d %7d %8s %8s %8s %6d\n' \
    "$label" "$total" "$add" "$del" "$net" "$churn_pct" "$net_pct" "$pct_wez" "$files"
}

printf 'Base ref:   %s\n' "$BASE_REF"
printf 'Head ref:   %s\n' "$HEAD_REF"
printf 'Merge base: %s\n' "$MERGE_BASE"
printf '\n'
printf '%-34s %8s %7s %7s %7s %8s %8s %8s %6s\n' \
  'Variant' 'BaseLOC' 'Added' 'Deleted' 'Net' 'Churn%' 'Net%' 'PctWez' 'Files'
printf '%-34s %8s %7s %7s %7s %8s %8s %8s %6s\n' \
  '-------' '-------' '-----' '-------' '---' '------' '----' '------' '-----'

print_row 'all .rs' 'all'
print_row 'no tests/examples/benches/build' 'core'
print_row 'core only, no deps/' 'core_no_deps'

printf '\n'
printf 'Churn%% = (added + deleted) / base LOC * 100\n'
printf 'Net%%   = (added - deleted) / base LOC * 100\n'
printf 'PctWez = base LOC / (base LOC + net LOC) * 100\n'
