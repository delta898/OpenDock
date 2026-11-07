#!/usr/bin/env python3
"""Run cloudflared using a short-lived token file derived from OpenDock config."""

import argparse
import os
import signal
import subprocess
import tempfile
from pathlib import Path


def read_token(config_path: Path) -> str:
    for raw_line in config_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "CLOUDFLARED_TUNNEL_TOKEN":
            continue
        token = value.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
            token = token[1:-1]
        if token:
            return token
    raise SystemExit(
        f"Missing CLOUDFLARED_TUNNEL_TOKEN in {config_path}; rerun bootstrap after configuring it."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--cloudflared", required=True)
    args = parser.parse_args()
    token = read_token(args.config)
    child = None
    with tempfile.TemporaryDirectory(prefix="opendock-cloudflared-") as runtime_dir:
        os.chmod(runtime_dir, 0o700)
        token_path = Path(runtime_dir) / "token"
        token_path.write_text(token)
        os.chmod(token_path, 0o600)
        child = subprocess.Popen([
            args.cloudflared, "tunnel", "--no-autoupdate", "run",
            "--token-file", str(token_path),
        ])

        def forward_signal(signum, _frame):
            if child and child.poll() is None:
                child.send_signal(signum)

        old_handlers = {
            signum: signal.signal(signum, forward_signal)
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
        }
        try:
            return child.wait()
        finally:
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
