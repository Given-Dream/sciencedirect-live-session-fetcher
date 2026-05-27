#!/usr/bin/env bash
set -euo pipefail

input_csv=""
out_dir=""
python_exe="python3"
script_path=""
debug_port="9222"
page_wait_seconds="8"
inter_item_sleep_seconds="8"
limit="0"

usage() {
  cat <<'USAGE'
Usage: run_devtools_sciencedirect_fetch_macos.sh --input-csv CSV --out-dir DIR [options]

Options:
  --input-csv PATH              CSV with number, doi, note columns.
  --out-dir DIR                 Output directory.
  --python-exe PATH             Python executable. Default: python3.
  --script-path PATH            Fetcher script path.
  --debug-port PORT             Chrome DevTools port. Default: 9222.
  --page-wait-seconds SECONDS   Wait after opening each page. Default: 8.
  --inter-item-sleep-seconds N  Pause between rows. Default: 8.
  --limit N                     Only process the first N rows.
  -h, --help                    Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-csv)
      input_csv="${2:?Missing value for --input-csv}"
      shift 2
      ;;
    --out-dir)
      out_dir="${2:?Missing value for --out-dir}"
      shift 2
      ;;
    --python-exe)
      python_exe="${2:?Missing value for --python-exe}"
      shift 2
      ;;
    --script-path)
      script_path="${2:?Missing value for --script-path}"
      shift 2
      ;;
    --debug-port)
      debug_port="${2:?Missing value for --debug-port}"
      shift 2
      ;;
    --page-wait-seconds)
      page_wait_seconds="${2:?Missing value for --page-wait-seconds}"
      shift 2
      ;;
    --inter-item-sleep-seconds)
      inter_item_sleep_seconds="${2:?Missing value for --inter-item-sleep-seconds}"
      shift 2
      ;;
    --limit)
      limit="${2:?Missing value for --limit}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$input_csv" || -z "$out_dir" ]]; then
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$script_path" ]]; then
  script_path="$script_dir/devtools_sciencedirect_serial_fetch.py"
fi

if [[ ! -f "$input_csv" ]]; then
  echo "Input CSV not found: $input_csv" >&2
  exit 1
fi

if [[ ! -f "$script_path" ]]; then
  echo "Script not found: $script_path" >&2
  exit 1
fi

repo_root="$(cd "$script_dir/.." && pwd)"
if [[ -d "$repo_root/.codex_deps" ]]; then
  export PYTHONPATH="$repo_root/.codex_deps${PYTHONPATH:+:$PYTHONPATH}"
fi

mkdir -p "$out_dir"

args=(
  "$script_path"
  "--input-csv" "$input_csv"
  "--out-dir" "$out_dir"
  "--debug-port" "$debug_port"
  "--page-wait-seconds" "$page_wait_seconds"
  "--inter-item-sleep-seconds" "$inter_item_sleep_seconds"
)

if [[ "$limit" -gt 0 ]]; then
  args+=("--limit" "$limit")
fi

"$python_exe" "${args[@]}"

echo "Done. Output directory: $out_dir"
