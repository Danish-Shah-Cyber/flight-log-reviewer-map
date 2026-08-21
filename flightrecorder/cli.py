from __future__ import annotations

import argparse
import os

from .analysis import analyze
from .csv_io import read_samples, write_samples
from .report import write_html_report
from .insights import generate_insights
from .simulator import generate_flight
from .tlog import read_tlog
from .tlog_fixture import generate_tlog
from .binlog import read_bin


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission Planner flight-data analyzer")
    commands = parser.add_subparsers(dest="command", required=True)

    simulate = commands.add_parser("simulate", help="generate a synthetic flight CSV")
    simulate.add_argument("output")
    simulate.add_argument("--duration", type=int, default=240)

    import_tlog = commands.add_parser("import-tlog", help="convert a Mission Planner .tlog")
    import_tlog.add_argument("input")
    import_tlog.add_argument("output")

    generate = commands.add_parser("generate-tlog", help="generate a test Mission Planner .tlog")
    generate.add_argument("output")
    generate.add_argument("--duration", type=int, default=120)

    import_bin = commands.add_parser("import-bin", help="convert an ArduPilot DataFlash .BIN")
    import_bin.add_argument("input")
    import_bin.add_argument("output")

    dashboard = commands.add_parser("dashboard", help="start the local upload dashboard")
    dashboard.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    dashboard.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    dashboard.add_argument("--no-browser", action="store_true")

    analyze_command = commands.add_parser("analyze", help="analyze CSV and generate HTML")
    analyze_command.add_argument("input")
    analyze_command.add_argument("output")

    args = parser.parse_args()
    if args.command == "simulate":
        samples = generate_flight(args.duration)
        write_samples(args.output, samples)
        print(f"Wrote {len(samples)} samples to {args.output}")
    elif args.command == "import-tlog":
        samples = read_tlog(args.input)
        write_samples(args.output, samples)
        print(f"Imported {len(samples)} telemetry snapshots to {args.output}")
    elif args.command == "generate-tlog":
        count = generate_tlog(args.output, args.duration)
        print(f"Wrote {count} MAVLink packets to {args.output}")
    elif args.command == "import-bin":
        samples = read_bin(args.input)
        write_samples(args.output, samples)
        print(f"Imported {len(samples)} DataFlash snapshots to {args.output}")
    elif args.command == "dashboard":
        from .dashboard import run_dashboard
        run_dashboard(args.host, args.port, not args.no_browser)
    elif args.command == "analyze":
        samples = read_samples(args.input)
        summary = analyze(samples)
        insights = generate_insights(samples)
        write_html_report(args.output, samples, summary, insights)
        print(f"Created report at {args.output} with {len(summary.events)} detected events")
