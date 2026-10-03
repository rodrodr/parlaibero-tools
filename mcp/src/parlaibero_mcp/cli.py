"""Command line: run the MCP server (default) or manage the local data from a terminal."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .catalog import COUNTRIES


def _bar(name: str, done: int, total: int | None) -> None:
    if total:
        sys.stderr.write(f"\r  {name}: {done / 2**20:7.0f} / {total / 2**20:.0f} MB ({done / total:5.1%})")
    else:
        sys.stderr.write(f"\r  {name}: {done / 2**20:7.0f} MB")
    if total and done >= total:
        sys.stderr.write("\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="parlaibero-mcp",
        description="ParlaIbero MCP server. Without a command it serves MCP over stdio.")
    ap.add_argument("--version", action="version", version=f"parlaibero-mcp {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="serve MCP over stdio (default)")
    d = sub.add_parser("download", help="download countries from Harvard Dataverse and load them")
    d.add_argument("countries", nargs="+", help="ISO2 codes, or 'all'")
    d.add_argument("--force", action="store_true", help="re-download even if current")
    i = sub.add_parser("import", help="load CSV files downloaded by hand")
    i.add_argument("folder")
    sub.add_parser("status", help="show what is loaded locally")
    r = sub.add_parser("remove", help="remove a country from the local database")
    r.add_argument("countries", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd in (None, "serve"):
        from .server import main as serve
        serve()
        return 0

    from . import store  # imported late so `serve` starts fast

    if args.cmd == "download":
        isos = list(COUNTRIES) if [c.lower() for c in args.countries] == ["all"] else args.countries
        for c in isos:
            print(f"▸ {c}", file=sys.stderr)
            r = store.download_country(c, args.force, _bar)
            print(f"  ✓ {r['country']} v{r['version']}: {r['rows']:,} rows, {r['sessions']:,} sessions, "
                  f"{r['date_min']} → {r['date_max']}", file=sys.stderr)
    elif args.cmd == "import":
        for r in store.import_folder(args.folder):
            print(f"  ✓ {r['country']}: {r['rows']:,} rows", file=sys.stderr)
    elif args.cmd == "status":
        loaded = store.loaded()
        print(f"data: {store.HOME}")
        if not loaded:
            print("nothing loaded yet — try: parlaibero-mcp download SV")
        for iso, d in loaded.items():
            print(f"  {iso}  v{d['version'] or '?':<4} {d['n_rows']:>10,} rows  {d['n_sessions']:>6,} sessions  "
                  f"{d['date_min']} → {d['date_max']}  ({d['source']})")
    elif args.cmd == "remove":
        for c in args.countries:
            store.remove_country(c)
            print(f"  removed {c.upper()} from the database (downloaded files kept in {store.DATA})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
