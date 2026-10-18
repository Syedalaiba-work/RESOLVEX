"""Turns coverage.py's JSON report into per-area line coverage.

Default: Part I spec 9.3 (COVERAGE.json). With --day2: Part II §7.2 (COVERAGE_DAY2.json).
"""
import json
import sys

AREAS = {
    "fixtures": ["fixtures.py"],
    "scoring": ["sports.py", "scoring.py"],
    "standings": ["standings.py"],
    "store": ["store.py", "pdf.py"],
    "roster": ["roster.py"],
    "rbac": ["rbac.py"],
}
AREAS_DAY2 = {
    "streaming": ["streaming.py"],
    "costream": ["costream.py"],
    "qr_guest": ["qr_guest.py", "web.py"],
    "moderation_dlq": ["moderation_dlq.py"],
    "observability": ["observability.py"],
}


def main(path: str, areas: dict) -> None:
    files = json.load(open(path))["files"]
    result = {}
    for area, names in areas.items():
        covered = total = 0
        for file_path, data in files.items():
            if file_path.replace("\\", "/").rsplit("/", 1)[-1] in names:
                covered += data["summary"]["covered_lines"]
                total += data["summary"]["num_statements"]
        result[area] = round(100.0 * covered / total, 1) if total else 0.0
    print(json.dumps(result))


if __name__ == "__main__":
    main(sys.argv[1], AREAS_DAY2 if "--day2" in sys.argv[2:] else AREAS)
