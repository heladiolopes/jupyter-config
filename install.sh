#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target="$HOME/.local/bin/jlab"
if [[ -e "$target" || -L "$target" ]]; then
    if [[ $(readlink -f -- "$target") != "$repo/bin/jlab" ]]; then
        echo "Refusing to overwrite $target" >&2
        exit 1
    fi
fi
uv sync --project "$repo" --locked
mkdir -p -- "$HOME/.local/bin"
ln -sfn -- "$repo/bin/jlab" "$target"
echo "Installed $target"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo 'Add to your shell configuration: export PATH="$HOME/.local/bin:$PATH"' ;;
esac
