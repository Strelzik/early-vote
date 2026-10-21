import argparse

from earlyvote import nc, snapshot


def main() -> None:
    parser = argparse.ArgumentParser(prog="earlyvote")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="save new copies of the UF and Florida daily files")
    nc_cmd = sub.add_parser("nc", help="download NC absentee files and build tidy parquet")
    nc_cmd.add_argument("cycles", nargs="*", type=int, help="election years (default: all)")
    args = parser.parse_args()

    if args.command == "snapshot":
        written = snapshot.run()
        print(f"{len(written)} new snapshot files")
        for p in written:
            print(" ", p)
    elif args.command == "nc":
        for p in nc.run(args.cycles):
            print(p)


if __name__ == "__main__":
    main()
