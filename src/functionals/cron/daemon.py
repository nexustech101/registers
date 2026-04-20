"""
CLI entrypoint for the background cron runtime daemon.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import sys

import functionals.cli as cli
from functionals.cron.runtime import run_daemon


@cli.register(name="daemon", description="Run the functionals cron runtime daemon")
@cli.option("--daemon")
@cli.argument("root", type=str, default=".", help="Project root path")
@cli.argument("workers", type=int, default=4, help="Worker concurrency")
@cli.argument("poll_interval", type=float, default=1.0, help="Polling interval in seconds")
@cli.argument("webhook_host", type=str, default="127.0.0.1", help="Webhook server host")
@cli.argument("webhook_port", type=int, default=8787, help="Webhook server port")
def daemon_command(
    root: str = ".",
    workers: int = 4,
    poll_interval: float = 1.0,
    webhook_host: str = "127.0.0.1",
    webhook_port: int = 8787,
) -> None:
    asyncio.run(
        run_daemon(
            root=root,
            workers=workers,
            poll_interval=poll_interval,
            webhook_host=webhook_host,
            webhook_port=webhook_port,
        )
    )


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        # Preserve argparse-era behavior: no args means run daemon with defaults.
        return ["daemon"]

    first = raw[0]
    # Preserve compatibility with option-only invocation used by fx daemon spawn:
    #   python -m functionals.cron.daemon --root ... --workers ...
    if first.startswith("-") and first not in {"--help", "-h"}:
        return ["daemon", *raw]
    return raw


def main(argv: Sequence[str] | None = None) -> int:
    normalized = _normalize_argv(argv)
    cli.run(
        normalized,
        print_result=False,
        shell_banner=False,
        shell_title="Functionals Cron Daemon",
        shell_description="Daemon runtime entrypoint for cron jobs.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
