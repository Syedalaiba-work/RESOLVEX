"""Turns coverage.py's JSON report into the per-area line coverage of spec 9.3 (COVERAGE.json format)."""
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


def main(path: str) -> None:
    files = json.load(open(path))["files"]
    result = {}
    for area, names in AREAS.items():
        covered = total = 0
        for file_path, data in files.items():
            if file_path.replace("\\", "/").rsplit("/", 1)[-1] in names:
                covered += data["summary"]["covered_lines"]
                total += data["summary"]["num_statements"]
        result[area] = round(100.0 * covered / total, 1) if total else 0.0
    print(json.dumps(result))


if __name__ == "__main__":
    main(sys.argv[1])
