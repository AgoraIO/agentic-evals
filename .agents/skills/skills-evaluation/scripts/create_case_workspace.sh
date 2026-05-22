#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <source_workspace> <case_workspace_root> <case_id> [--target <target_id>] [include_path ...]" >&2
  exit 1
fi

source_workspace=$1
case_workspace_root=$2
case_id=$3
shift 3
default_target_id="voice-ai-integration"
target_id="$default_target_id"
eval_repo_root=""
target_yaml=""

if [[ ! -d "$source_workspace" ]]; then
  echo "source workspace does not exist: $source_workspace" >&2
  exit 1
fi

mkdir -p "$case_workspace_root"

source_workspace=$(cd "$source_workspace" && pwd)
case_workspace_root=$(cd "$case_workspace_root" && pwd)

resolve_eval_repo_root() {
  local target="$1"
  if [[ -f "$source_workspace/targets/$target/target.yaml" ]]; then
    printf '%s\n' "$source_workspace"
    return 0
  fi
  if [[ -f "$source_workspace/agentic-evals/targets/$target/target.yaml" ]]; then
    printf '%s\n' "$source_workspace/agentic-evals"
    return 0
  fi
  return 1
}

eval_repo_root=""
safe_case_id=${case_id//\//-}
case_dir="$case_workspace_root/$safe_case_id"
mkdir -p "$case_dir"

attempt=1
while :; do
  attempt_name=$(printf 'attempt-%02d' "$attempt")
  workspace_root="$case_dir/$attempt_name"
  if [[ ! -e "$workspace_root" ]]; then
    break
  fi
  attempt=$((attempt + 1))
done

mkdir -p "$workspace_root"

if [[ $# -gt 0 && "$1" == "--target" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "missing target id after --target" >&2
    exit 1
  fi

  target_id=$2
  shift 2

fi

if ! eval_repo_root=$(resolve_eval_repo_root "$target_id"); then
  echo "target config does not exist: targets/$target_id/target.yaml (checked $source_workspace and $source_workspace/agentic-evals)" >&2
  exit 1
fi

target_yaml="$eval_repo_root/targets/$target_id/target.yaml"

resolve_existing_relpath_base() {
  local relpath
  relpath=$1

  if [[ -e "$source_workspace/$relpath" ]]; then
    printf '%s\n' "$source_workspace"
    return 0
  fi

  if [[ -e "$eval_repo_root/$relpath" ]]; then
    printf '%s\n' "$eval_repo_root"
    return 0
  fi

  return 1
}

discover_default_include_paths() {
  if [[ -f "$target_yaml" ]] && command -v ruby >/dev/null 2>&1; then
    ruby -r yaml -e '
      data = YAML.load_file(ARGV[0])
      paths = [data["entry_skill"], *(data["roots"] || [])].compact.uniq
      paths.each { |path| puts path }
    ' "$target_yaml"
    return 0
  fi

  if [[ -f "$source_workspace/.agents/skills/$target_id/SKILL.md" ]]; then
    printf '%s\n' ".agents/skills/$target_id"
    return 0
  fi

  return 1
}

collect_include_paths() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return 0
  fi

  discover_default_include_paths
}

validate_include_path() {
  local relpath
  relpath=$1

  if [[ -z "$relpath" ]]; then
    echo "include path must not be empty" >&2
    exit 1
  fi

  if [[ "$relpath" = /* ]]; then
    echo "include path must be relative: $relpath" >&2
    exit 1
  fi

  if [[ "$relpath" == ../* || "$relpath" == */../* || "$relpath" == *"/.." || "$relpath" == ".." ]]; then
    echo "include path must stay inside source workspace: $relpath" >&2
    exit 1
  fi

  if ! resolve_existing_relpath_base "$relpath" >/dev/null 2>&1; then
    return 1
  fi

  return 0
}

copy_include_path() {
  local relpath base
  relpath=$1
  base=$(resolve_existing_relpath_base "$relpath")

  tar -C "$base" -cf - "$relpath" | tar -C "$workspace_root" -xf -
}

include_paths=()
while IFS= read -r relpath; do
  [[ -n "$relpath" ]] || continue
  if ! validate_include_path "$relpath"; then
    echo "warning: skipping missing include path: $relpath" >&2
    continue
  fi
  include_paths+=("$relpath")
done < <(collect_include_paths "$@")

if [[ ${#include_paths[@]} -eq 0 ]]; then
  echo "no include paths resolved for case workspace" >&2
  exit 1
fi

for relpath in "${include_paths[@]}"; do
  copy_include_path "$relpath"
done

printf '%s\n' "$workspace_root"
