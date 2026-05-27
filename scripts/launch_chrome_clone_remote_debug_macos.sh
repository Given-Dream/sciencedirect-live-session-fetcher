#!/usr/bin/env bash
set -euo pipefail

chrome_binary="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
clone_user_data_dir=""
profile_directory="Default"
remote_debugging_port="9222"
url="https://www.sciencedirect.com/"
direct_connection="false"
disable_extensions="false"
one_shot_profile="false"

usage() {
  cat <<'USAGE'
Usage: launch_chrome_clone_remote_debug_macos.sh [options]

Options:
  --chrome-binary PATH          Chrome binary path.
  --clone-user-data-dir DIR     Dedicated Chrome user-data directory.
  --profile-directory NAME      Chrome profile directory name. Default: Default.
  --remote-debugging-port PORT  DevTools remote debugging port. Default: 9222.
  --url URL                     Initial URL. Default: https://www.sciencedirect.com/
  --direct-connection           Disable proxy for this Chrome process only.
  --disable-extensions          Disable extensions in this Chrome process.
  --one-shot-profile            Create a timestamped temporary profile under runtime/.
  -h, --help                    Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chrome-binary)
      chrome_binary="${2:?Missing value for --chrome-binary}"
      shift 2
      ;;
    --clone-user-data-dir)
      clone_user_data_dir="${2:?Missing value for --clone-user-data-dir}"
      shift 2
      ;;
    --profile-directory)
      profile_directory="${2:?Missing value for --profile-directory}"
      shift 2
      ;;
    --remote-debugging-port)
      remote_debugging_port="${2:?Missing value for --remote-debugging-port}"
      shift 2
      ;;
    --url)
      url="${2:?Missing value for --url}"
      shift 2
      ;;
    --direct-connection)
      direct_connection="true"
      shift
      ;;
    --disable-extensions)
      disable_extensions="true"
      shift
      ;;
    --one-shot-profile)
      one_shot_profile="true"
      shift
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

if [[ ! -x "$chrome_binary" ]]; then
  echo "Chrome binary not found or not executable: $chrome_binary" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [[ -z "$clone_user_data_dir" ]]; then
  if [[ "$one_shot_profile" == "true" ]]; then
    stamp="$(date +"%Y%m%d_%H%M%S")"
    clone_user_data_dir="$repo_root/runtime/chrome_profile_once_$stamp/User Data"
  else
    clone_user_data_dir="$repo_root/runtime/chrome_profile_clone/User Data"
  fi
fi

mkdir -p "$clone_user_data_dir"

args=(
  "--remote-debugging-port=$remote_debugging_port"
  "--user-data-dir=$clone_user_data_dir"
  "--profile-directory=$profile_directory"
  "--new-window"
)

if [[ "$direct_connection" == "true" ]]; then
  args+=(
    "--no-proxy-server"
    "--proxy-bypass-list=*"
  )
fi

if [[ "$disable_extensions" == "true" ]]; then
  args+=("--disable-extensions")
fi

args+=("$url")

"$chrome_binary" "${args[@]}" >/dev/null 2>&1 &

echo "Opened Chrome window with remote debugging on port $remote_debugging_port."
echo "User data dir: $clone_user_data_dir"
if [[ "$direct_connection" == "true" ]]; then
  echo "Proxy mode: direct connection for this Chrome process only (--no-proxy-server)."
fi
if [[ "$disable_extensions" == "true" ]]; then
  echo "Extensions: disabled."
fi
if [[ "$one_shot_profile" == "true" ]]; then
  echo "Profile mode: one-shot profile. Close this Chrome window to end the session."
fi
