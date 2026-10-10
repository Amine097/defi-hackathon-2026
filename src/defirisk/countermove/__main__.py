import sys

if len(sys.argv) > 1 and sys.argv[1] == "dry-run":  # read-only mainnet dry run: python -m defirisk.countermove dry-run ...
    from .dryrun import main as dry_run

    raise SystemExit(dry_run(sys.argv[2:]))

from .watcher import main  # noqa: E402

raise SystemExit(main())
