#!/usr/bin/env python3
"""
Minimal CLI wrapper around StateManager for updating skill status from SKILL.md scripts.

CLI:
    python update_state.py --country <iso2> --skill <name> --session <id> \
        --status <pending|running|complete|flag|halt|skipped> \
        --confidence <float> [--output <path>] [--error <msg>]
"""
import sys
import json
import argparse
from pathlib import Path

LIB_ROOT = Path(__file__).resolve().parents[2]   # carpeta diaries-lib (contiene lib/) — para imports
PROJECT_ROOT = Path.cwd()                         # raíz del proyecto (datos); el skill corre desde aquí

sys.path.insert(0, str(LIB_ROOT))

from lib.state_manager import StateManager

_VALID_STATUSES = {"pending", "running", "complete", "flag", "halt", "skipped"}


def main():
    parser = argparse.ArgumentParser(description="Update ParlaIbero pipeline state")
    parser.add_argument("--country", required=True, help="ISO 2-letter country code")
    parser.add_argument("--skill", required=True, help="Skill/stage name")
    parser.add_argument("--session", required=True, help="Session ID")
    parser.add_argument(
        "--status",
        required=True,
        choices=sorted(_VALID_STATUSES),
        help="New status for the skill",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Confidence score (0.0–1.0)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output file path to record in state",
    )
    parser.add_argument(
        "--error",
        default=None,
        help="Optional error message to record in state",
    )
    args = parser.parse_args()

    try:
        sm = StateManager(PROJECT_ROOT, args.country)
        sm.load()

        kwargs = {}
        if args.confidence is not None:
            kwargs["confidence"] = args.confidence
        if args.output is not None:
            kwargs["output"] = args.output
        if args.error is not None:
            kwargs["error"] = args.error

        sm.mark_skill(
            session_id=args.session,
            skill=args.skill,
            status=args.status,
            **kwargs,
        )
        sm.save()

        print(json.dumps({
            "ok": True,
            "session": args.session,
            "skill": args.skill,
            "status": args.status,
        }, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "session": args.session,
            "skill": args.skill,
            "status": args.status,
            "error": str(exc),
        }, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
