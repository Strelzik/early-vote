import argparse

from earlyvote import eavs, finals, fl, nc, pa, report, snapshot, uf


def main() -> None:
    parser = argparse.ArgumentParser(prog="earlyvote")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="save new copies of the UF and Florida daily files")
    sub.add_parser("backfill", help="add Internet Archive copies of UF files from 2024 and 2026")
    nc_cmd = sub.add_parser("nc", help="download NC absentee files and build tidy parquet")
    nc_cmd.add_argument("cycles", nargs="*", type=int, help="election years (default: all)")
    sub.add_parser("pa", help="count PA mail ballot files on data.pa.gov into tidy parquet")
    sub.add_parser("uf", help="parse UF snapshots into tidy parquet")
    sub.add_parser("fl", help="parse Florida snapshots into tidy parquet")
    sub.add_parser("eavs", help="download EAVS 2014-2024 and build the finals table")
    sub.add_parser("finals", help="rebuild past final early vote by party (McDonald, UF, MEDSL)")
    sub.add_parser("build", help="nc + pa + uf + fl + eavs + finals + report")
    sub.add_parser("report", help="write reports/earlyvote.html from the processed data")
    args = parser.parse_args()

    if args.command in ("snapshot", "backfill"):
        written = snapshot.run() if args.command == "snapshot" else snapshot.backfill()
        print(f"{len(written)} new snapshot files")
        for p in written:
            print(" ", p)
        return
    steps = {
        "nc": lambda: nc.run(getattr(args, "cycles", None)) + [nc.repeat_voters()],
        "pa": pa.run,
        "uf": uf.run,
        "fl": lambda: [fl.build()],
        "eavs": lambda: [eavs.run()],
        # Past cycles never change, so `build` only creates the table when it is missing.
        "finals": lambda: [finals.build() if args.command == "finals" or not finals.OUT.exists() else finals.OUT],
        "report": lambda: [report.build()],
    }
    for name in steps if args.command == "build" else [args.command]:
        for p in steps[name]():
            print(p)


if __name__ == "__main__":
    main()
