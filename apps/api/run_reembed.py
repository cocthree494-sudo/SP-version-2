"""Repository-root entry point for the standalone chunk re-embedding command."""

from app.workers.reembed import main

if __name__ == "__main__":
    raise SystemExit(main())
