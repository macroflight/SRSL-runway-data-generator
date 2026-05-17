#!/usr/bin/env python3
"""Generate runway data for airports from a Little NavMap SQLite database.

Usage examples:
  python3 add_airports.py --generate-only-icao EGLL --output-stdout
  python3 add_airports.py --generate-all --output-file new_runways.data
  python3 add_airports.py --generate-longer-than 3000 --output-file big_airports.data --verbose
"""

import argparse
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB = SCRIPT_DIR / "little_navmap_navigraph.sqlite"
DEFAULT_OVERRIDE_DB = SCRIPT_DIR / "Runways.data.ORIG"

FEET_PER_METER = 3.28084


def decimal_to_dms(value):
    abs_val = abs(value)
    degrees = int(abs_val)
    minutes_f = (abs_val - degrees) * 60
    minutes = int(minutes_f)
    seconds_f = (minutes_f - minutes) * 60
    seconds = int(seconds_f)
    hundredths = round((seconds_f - seconds) * 100)
    if hundredths >= 100:
        hundredths -= 100
        seconds += 1
    if seconds >= 60:
        seconds -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return degrees, minutes, seconds, hundredths


def format_lat(lat):
    hem = 'N' if lat >= 0 else 'S'
    d, m, s, h = decimal_to_dms(lat)
    return f"{hem}{d:02d}{m:02d}{s:02d}{h:02d}"


def format_lon(lon):
    hem = 'E' if lon >= 0 else 'W'
    d, m, s, h = decimal_to_dms(lon)
    return f"{hem}{d:03d}{m:02d}{s:02d}{h:02d}"


def format_runway_id(name):
    name = name.strip()
    suffix = name[2] if len(name) >= 3 else ' '
    if suffix not in ('L', 'C', 'R'):
        suffix = ' '
    return name[:2] + suffix


def format_threshold(feet):
    val = max(0, min(9999, int(round(feet))))
    return f"{val:04d}"


def make_record(icao, p_name, p_lon, p_lat, p_dt, s_name, s_lon, s_lat, s_dt):
    record = (
        f"{icao}"
        f"{format_runway_id(p_name)}"
        f"{format_lat(p_lat)}"
        f"{format_lon(p_lon)}"
        f"{format_threshold(p_dt)}"
        f"{format_runway_id(s_name)}"
        f"{format_lat(s_lat)}"
        f"{format_lon(s_lon)}"
        f"{format_threshold(s_dt)}"
    )
    assert len(record) == 56, f"Record length {len(record)} != 56: {record!r}"
    return record


def vprint(verbose, msg):
    if verbose:
        print(f"[verbose] {msg}", file=sys.stderr)


def load_existing_airports(path, verbose):
    airports = set()
    p = Path(path)
    if not p.exists():
        vprint(verbose, f"Override database {str(path)!r} not found; no airports will be excluded")
        return airports
    vprint(verbose, f"Reading existing airports from {str(path)!r}")
    with open(p, 'r', encoding='ascii', errors='replace') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if line.startswith('//') or len(line) < 4:
                continue
            airports.add(line[:4])
    vprint(verbose, f"Found {len(airports)} airports to exclude")
    return airports


ICAO_GLOB = '[A-Z][A-Z][A-Z][A-Z]'


def get_airport_icaos_all(db, verbose):
    vprint(verbose, "Querying all airports with runways and 4-letter ICAO codes from database")
    cur = db.cursor()
    cur.execute("""
        SELECT DISTINCT a.ident
        FROM airport a
        JOIN runway r ON r.airport_id = a.airport_id
        WHERE a.ident GLOB ?
        ORDER BY a.ident
    """, (ICAO_GLOB,))
    return [row[0] for row in cur.fetchall()]


def get_airport_icaos_longer_than(db, min_meters, verbose):
    min_feet = min_meters * FEET_PER_METER
    vprint(verbose, f"Querying airports with at least one runway >= {min_meters}m ({min_feet:.0f}ft)")
    cur = db.cursor()
    cur.execute("""
        SELECT DISTINCT a.ident
        FROM airport a
        JOIN runway r ON r.airport_id = a.airport_id
        WHERE r.length >= ? AND a.ident GLOB ?
        ORDER BY a.ident
    """, (min_feet, ICAO_GLOB))
    return [row[0] for row in cur.fetchall()]


def get_runways(db, icao):
    cur = db.cursor()
    cur.execute("""
        SELECT p.name, p.lonx, p.laty, p.offset_threshold,
               s.name, s.lonx, s.laty, s.offset_threshold
        FROM airport a
        JOIN runway r ON r.airport_id = a.airport_id
        JOIN runway_end p ON p.runway_end_id = r.primary_end_id
        JOIN runway_end s ON s.runway_end_id = r.secondary_end_id
        WHERE a.ident = ?
        ORDER BY p.name
    """, (icao,))
    return cur.fetchall()


def generate_records(icaos, db, existing, verbose):
    records = []
    skipped = 0
    not_found = []
    for icao in icaos:
        if not (len(icao) == 4 and icao.isalpha() and icao.isupper()):
            print(f"Warning: {icao!r} is not a 4-letter uppercase ICAO code, skipping", file=sys.stderr)
            continue
        if icao in existing:
            skipped += 1
            vprint(verbose, f"{icao}: skipping (already in override database)")
            continue
        runways = get_runways(db, icao)
        if not runways:
            not_found.append(icao)
            vprint(verbose, f"{icao}: no runways found in database")
            continue
        for row in runways:
            p_name, p_lon, p_lat, p_dt, s_name, s_lon, s_lat, s_dt = row
            records.append(make_record(
                icao, p_name, p_lon, p_lat, p_dt,
                s_name, s_lon, s_lat, s_dt
            ))
        vprint(verbose, f"{icao}: {len(runways)} runway(s) generated")
    if skipped:
        vprint(verbose, f"Skipped {skipped} airport(s) already in override database")
    if not_found:
        print(f"Warning: no runways found for: {', '.join(not_found)}", file=sys.stderr)
    return records


def write_output(records, args, verbose):
    if args.output_stdout:
        vprint(verbose, f"Writing {len(records)} records to stdout")
        for record in records:
            print(record)
        return

    out_path = Path(args.output_file)
    if out_path.exists() and not args.force:
        print(f"Error: {str(out_path)!r} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)
    action = "Overwriting" if out_path.exists() else "Writing"
    vprint(verbose, f"{action} {len(records)} records to {str(out_path)!r}")
    with open(out_path, 'wb') as f:
        for record in records:
            f.write((record + '\r\n').encode('ascii'))
    vprint(verbose, "Done")


def main():
    parser = argparse.ArgumentParser(
        description="Generate runway data for airports from a Little NavMap SQLite database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        '--database', default=str(DEFAULT_DB), metavar='FILE',
        help='Little NavMap SQLite database'
    )
    parser.add_argument(
        '--override-database', default=str(DEFAULT_OVERRIDE_DB), metavar='FILE',
        help='Runway data file whose airports are excluded from output'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Explain what the script is doing'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Overwrite output file if it already exists'
    )

    gen_group = parser.add_mutually_exclusive_group(required=True)
    gen_group.add_argument(
        '--generate-all', action='store_true',
        help='Generate data for all airports in the database'
    )
    gen_group.add_argument(
        '--generate-longer-than', type=float, metavar='METERS',
        help='Generate data for airports with at least one runway longer than METERS'
    )
    gen_group.add_argument(
        '--generate-only-icao', metavar='ICAO',
        help='Generate data for a single airport'
    )

    out_group = parser.add_mutually_exclusive_group(required=True)
    out_group.add_argument(
        '--output-file', metavar='FILE',
        help='Write output to FILE'
    )
    out_group.add_argument(
        '--output-stdout', action='store_true',
        help='Print output to terminal'
    )

    args = parser.parse_args()
    verbose = args.verbose

    vprint(verbose, f"Connecting to database {args.database!r}")
    db = sqlite3.connect(args.database)

    existing = load_existing_airports(args.override_database, verbose)

    if args.generate_all:
        icaos = get_airport_icaos_all(db, verbose)
        vprint(verbose, f"{len(icaos)} airports with runways found in database")
    elif args.generate_longer_than is not None:
        icaos = get_airport_icaos_longer_than(db, args.generate_longer_than, verbose)
        vprint(verbose, f"{len(icaos)} airports found with at least one runway > {args.generate_longer_than}m")
    else:
        icaos = [args.generate_only_icao.upper()]

    records = generate_records(icaos, db, existing, verbose)
    db.close()

    vprint(verbose, f"Total records generated: {len(records)}")
    write_output(records, args, verbose)


if __name__ == '__main__':
    main()
