#!/usr/bin/env python3
"""
Add mentors to an existing stage based on the latest Google Sheet worksheet.

Usage:
    python add_mentors_to_existing_stage.py <stage_number>

This script does NOT create channels or add track leads again.
It only:
    - Resolves the main stage channel and each track channel (creates if missing)
    - Reads mentors from the latest "Mentors YYYY-MM-DD" worksheet
    - Invites mentors to the main stage channel and each selected track channel

Incremental mode (default):
    - The first time you run, the script bootstraps by recording the current
        latest Timestamp in the sheet and exits without processing old rows.
    - Subsequent runs only process rows with Timestamp greater than the last
        recorded value, so it "continues from the latest" automatically.

Notes:
    - If the environment variable GOOGLE_CREDENTIALS_FILE is set, it will override
        the hardcoded path inside create_stage_channels.py for this run.
    - Requires: slack_sdk, gspread, oauth2client, python-dotenv
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root, not current working directory
load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

try:
    from mentor_hub.scripts import create_stage_channels as csc
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import create_stage_channels as csc

# If user provided a GOOGLE_CREDENTIALS_FILE in env, override the module's value
_env_creds = os.getenv("GOOGLE_CREDENTIALS_FILE")
if _env_creds:
    try:
        # Override module-level variable used by setup_google_sheets()
        print(f"🔧 Using GOOGLE_CREDENTIALS_FILE from env: {_env_creds}")
        csc.GOOGLE_CREDENTIALS_FILE = _env_creds
    except Exception as e:
        print(f"⚠️ Could not override GOOGLE_CREDENTIALS_FILE: {e}")


def build_stage_channels_map(stage_number: int):
    """Resolve channel IDs for main stage and each track.
    Returns a dict like {"main": id, "backend": id, ...}.
    """
    stage_name = f"stage-{stage_number}"
    channels = {}

    # Main stage channel
    channels["main"] = csc.get_or_create_channel(stage_name)

    # Per-track channels
    for track in csc.TRACKS.keys():
        ch_name = f"{stage_name}-{track}"
        channels[track] = csc.get_or_create_channel(ch_name)

    return channels


def _get_state_file(stage_number: int) -> str:
    """Get stage-specific state file to track baseline per stage."""
    return f"mentor_sheet_state_stage_{stage_number}.json"


def _load_state(stage_number: int) -> Dict[str, Any]:
    """Load stage-specific state."""
    state_file = _get_state_file(stage_number)
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_state(state: Dict[str, Any], stage_number: int) -> None:
    """Save stage-specific state."""
    state_file = _get_state_file(stage_number)
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Could not save state: {e}")


def _parse_ts(ts_str: str) -> Optional[datetime]:
    s = (ts_str or "").strip()
    if not s:
        return None
    # Normalize trivial variants
    if s.endswith("Z"):
        s = s[:-1]
    if s.endswith(" UTC"):
        s = s[:-4]
    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _get_recent_records(worksheet) -> Dict[str, Any]:
    """Return dict with keys: title, records(list), max_ts(datetime)."""
    title = getattr(worksheet, "title", "")
    records = worksheet.get_all_records()
    max_ts: Optional[datetime] = None
    for r in records:
        ts = _parse_ts(str(r.get("Timestamp", "")))
        if ts and (max_ts is None or ts > max_ts):
            max_ts = ts
    return {"title": title, "records": records, "max_ts": max_ts}


def _rows_with_timestamp(records: List[Dict[str, Any]], ts: Optional[datetime]) -> List[Dict[str, Any]]:
    if ts is None:
        return []
    want = ts.strftime("%Y-%m-%d %H:%M:%S")
    out: List[Dict[str, Any]] = []
    for r in records:
        if str(r.get("Timestamp", "")).strip() == want:
            out.append(r)
    return out


def _find_timestamp_row_numbers(worksheet, ts: Optional[datetime]) -> List[int]:
    """Return 1-based sheet row numbers that match the timestamp (exact string match)."""
    if ts is None:
        return []
    try:
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        values = worksheet.get_all_values()
        if not values:
            return []
        header = values[0]
        try:
            ts_idx = header.index("Timestamp")
        except ValueError:
            return []
        matches: List[int] = []
        for i in range(1, len(values)):
            row = values[i]
            if ts_idx < len(row) and row[ts_idx].strip() == ts_str:
                # Sheet rows are 1-based; +1 for header offset
                matches.append(i + 1)
        return matches
    except Exception:
        return []


def _build_row_lookup(worksheet) -> Dict[tuple, int]:
    """Build a map from (Timestamp, Slack ID) and (Timestamp, Display Name) to 1-based row numbers."""
    lookup: Dict[tuple, int] = {}
    try:
        values = worksheet.get_all_values()
        if not values:
            return lookup
        header = values[0]
        col_idx = {name: i for i, name in enumerate(header)}
        for i in range(1, len(values)):
            row = values[i]
            ts = row[col_idx.get("Timestamp", -1)].strip() if col_idx.get("Timestamp") is not None and col_idx.get("Timestamp") < len(row) else ""
            sid = row[col_idx.get("Slack ID", -1)].strip() if col_idx.get("Slack ID") is not None and col_idx.get("Slack ID") < len(row) else ""
            name = row[col_idx.get("Display Name", -1)].strip() if col_idx.get("Display Name") is not None and col_idx.get("Display Name") < len(row) else ""
            sheet_row_no = i + 1
            if ts:
                if sid:
                    lookup[(ts, sid)] = sheet_row_no
                if name:
                    lookup[(ts, name)] = sheet_row_no
    except Exception:
        pass
    return lookup


def _print_baseline_preview(ws_title: str, worksheet, records: List[Dict[str, Any]], ts: Optional[datetime], note: str = "") -> None:
    if ts is None:
        print(f"ℹ️ No baseline timestamp available for '{ws_title}'.")
        return
    print(f"📌 Baseline for '{ws_title}': {ts.strftime('%Y-%m-%d %H:%M:%S')} {note}")
    rows = _rows_with_timestamp(records, ts)
    row_nums = _find_timestamp_row_numbers(worksheet, ts)
    if not rows:
        print("   (No rows match this timestamp in the sheet.)")
        return
    max_show = 5
    for i, r in enumerate(rows[:max_show], start=1):
        name = str(r.get("Display Name", "")).strip()
        sid = str(r.get("Slack ID", "")).strip()
        tracks = str(r.get("Selected Tracks", "")).strip()
        suffix = f" | tracks: {tracks}" if tracks else ""
        row_no = row_nums[i - 1] if i - 1 < len(row_nums) else None
        prefix = f"Row {row_no}: " if row_no else ""
        print(f"   {i}. {prefix}{name or '(no name)'} {f'[{sid}]' if sid else ''}{suffix}")
    if len(rows) > max_show:
        print(f"   … and {len(rows) - max_show} more at the same timestamp.")


def _sort_records_by_ts(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def keyfn(r: Dict[str, Any]):
        ts = _parse_ts(str(r.get("Timestamp", "")))
        return ts or datetime.min
    return sorted(records, key=keyfn, reverse=True)


def process_incremental(
    stage: int,
    *,
    dry_run: bool = False,
    process_all: bool = False,
    since_minutes: Optional[int] = None,
    reset_baseline: bool = False,
    show_baseline: bool = False,
    show_newest: bool = False,
    list_new: bool = False,
    baseline_mode: str = "timestamp",  # "timestamp" | "row"
):
    # Build channel map (will create if any are missing)
    channels = build_stage_channels_map(stage)

    # Prepare user cache for name lookups when Slack ID is missing
    try:
        all_users = csc.fetch_all_users(max_retries=3, use_cache_file=True)
    except Exception:
        all_users = []

    # Access the latest worksheet directly
    spreadsheet, worksheet = csc.setup_google_sheets()
    if not worksheet:
        print("❌ Could not access latest mentor worksheet")
        return

    info = _get_recent_records(worksheet)
    ws_title = info["title"]
    records: List[Dict[str, Any]] = info["records"]
    max_ts: Optional[datetime] = info["max_ts"]

    state = _load_state(stage)

    # Optional: show baseline for this worksheet and exit
    if show_baseline:
        stored_ts = _parse_ts(state.get(ws_title)) if isinstance(state.get(ws_title), str) else None
        if baseline_mode == "row":
            state_row_key = f"{ws_title}__row"
            baseline_row = state.get(state_row_key)
            try:
                baseline_row = int(baseline_row) if baseline_row is not None else None
            except Exception:
                baseline_row = None
            # Determine last data row
            values = worksheet.get_all_values()
            last_row = len(values) if values else None
            if baseline_row is None and last_row is not None:
                print(f"📌 Row-baseline for '{ws_title}': not set yet (would bootstrap to last data row = {last_row})")
            else:
                print(f"📌 Row-baseline for '{ws_title}': {baseline_row if baseline_row is not None else 'N/A'}")
            # Show the row content if baseline exists
            if baseline_row and values and baseline_row <= len(values):
                header = values[0]
                row_vals = values[baseline_row - 1]
                row_map = {header[i]: row_vals[i] if i < len(row_vals) else "" for i in range(len(header))}
                name = (row_map.get("Display Name") or "").strip()
                sid = (row_map.get("Slack ID") or "").strip()
                ts = (row_map.get("Timestamp") or "").strip()
                print(f"   Row {baseline_row}: {ts} | {name or '(no name)'} {f'[{sid}]' if sid else ''}")
                newer_count = (len(values) - baseline_row) if len(values) >= baseline_row else 0
                print(f"   Rows after baseline: {newer_count}")
            return
        if stored_ts is None and info["max_ts"] is not None:
            _print_baseline_preview(ws_title, worksheet, records, info["max_ts"], note="(no saved baseline yet; would bootstrap to this)")
        else:
            _print_baseline_preview(ws_title, worksheet, records, stored_ts)
        # Also show how many rows are newer than the stored baseline, if available
        base = stored_ts
        if base is not None:
            newer = [r for r in records if (_parse_ts(str(r.get("Timestamp", ""))) or datetime.min) > base]
            newest = max((_parse_ts(str(r.get("Timestamp", ""))) for r in records if _parse_ts(str(r.get("Timestamp", ""))) is not None), default=None)
            print(f"   New rows since baseline: {len(newer)}" + (f" | newest timestamp: {newest.strftime('%Y-%m-%d %H:%M:%S')}" if newest else ""))
        return

    if show_newest:
        print(f"🧭 Newest rows in '{ws_title}' (by Timestamp):")
        sorted_rows = _sort_records_by_ts(records)
        lookup = _build_row_lookup(worksheet)
        max_show = 10
        count = 0
        for r in sorted_rows:
            ts = _parse_ts(str(r.get("Timestamp", "")))
            if not ts:
                continue
            name = str(r.get("Display Name", "")).strip()
            sid = str(r.get("Slack ID", "")).strip()
            key = (ts.strftime("%Y-%m-%d %H:%M:%S"), sid) if sid else (ts.strftime("%Y-%m-%d %H:%M:%S"), name)
            row_no = lookup.get(key)
            prefix = f"Row {row_no}: " if row_no else ""
            print(f"   • {ts.strftime('%Y-%m-%d %H:%M:%S')} | {prefix}{name or '(no name)'} {f'[{sid}]' if sid else ''}")
            count += 1
            if count >= max_show:
                break
        return

    # Optional: reset baseline for this worksheet and exit
    if reset_baseline:
        if ws_title in state:
            del state[ws_title]
            _save_state(state, stage)
            print(f"♻️ Reset baseline for '{ws_title}' in stage-{stage}. Next run will bootstrap again unless you use --process-all or --since-minutes.")
        else:
            print(f"ℹ️ No baseline stored for '{ws_title}' to reset.")
        # Also clear row-baseline if present
        state_row_key = f"{ws_title}__row"
        if state_row_key in state:
            del state[state_row_key]
            _save_state(state, stage)
            print(f"♻️ Reset row-baseline for '{ws_title}' in stage-{stage}.")
        return

    # Determine effective baseline according to flags/state
    last_ts: Optional[datetime] = None
    baseline_row: Optional[int] = None
    if baseline_mode == "row":
        # Row-based baseline
        values = worksheet.get_all_values()
        last_data_row = len(values) if values else None
        state_row_key = f"{ws_title}__row"
        if process_all:
            baseline_row = 1  # process all data rows (>= row 2)
            print("⚙️ Override: processing ALL rows by row index (ignoring saved row-baseline).")
        else:
            if since_minutes is not None:
                print("ℹ️ since-minutes is ignored in --baseline-mode row.")
            try:
                baseline_row = int(state.get(state_row_key)) if state.get(state_row_key) is not None else None
            except Exception:
                baseline_row = None
            if baseline_row is None:
                if last_data_row is not None:
                    state[state_row_key] = last_data_row
                    _save_state(state, stage)
                    print(f"🧭 Bootstrap (row-mode): recorded baseline row {last_data_row} for '{ws_title}' in stage-{stage}.")
                    print("   No mentors processed on the first run. Run again after new submissions.")
                else:
                    print("⚠️ Could not determine last data row; nothing to bootstrap.")
                return
    else:
        # Timestamp-based baseline (default)
        if process_all:
            last_ts = datetime.min
            print("⚙️ Override: processing ALL existing rows (ignoring saved baseline).")
        elif since_minutes is not None and since_minutes >= 0:
            last_ts = datetime.now() - timedelta(minutes=since_minutes)
            print(f"⚙️ Override: processing rows newer than {last_ts.strftime('%Y-%m-%d %H:%M:%S')} (since-minutes={since_minutes}).")
        else:
            last_ts_str = state.get(ws_title)
            last_ts = _parse_ts(last_ts_str) if isinstance(last_ts_str, str) else None

            if last_ts is None:
                # Bootstrap: record current max and exit to avoid processing the entire history
                if max_ts is not None:
                    state[ws_title] = max_ts.strftime("%Y-%m-%d %H:%M:%S")
                    _save_state(state, stage)
                    print(f"🧭 Bootstrap (stage-{stage}): recorded baseline {state[ws_title]} for '{ws_title}'.")
                    _print_baseline_preview(ws_title, worksheet, records, max_ts)
                    print("   No mentors processed on the first run. Run again after new submissions.")
                else:
                    print("⚠️ No timestamps found in worksheet; nothing to bootstrap.")
                return

    if baseline_mode == "row":
        # Filter rows by row index
        lookup = _build_row_lookup(worksheet)
        # Build (row_no, record) pairs
        row_recs: List[tuple] = []
        for r in records:
            ts = _parse_ts(str(r.get("Timestamp", "")))
            name = str(r.get("Display Name", "")).strip()
            sid = str(r.get("Slack ID", "")).strip()
            key = (ts.strftime("%Y-%m-%d %H:%M:%S"), sid) if ts and sid else (ts.strftime("%Y-%m-%d %H:%M:%S"), name) if ts else None
            row_no = lookup.get(key) if key else None
            if row_no:
                row_recs.append((row_no, r))
        # Only rows strictly after baseline_row
        recent_pairs = [(rn, r) for rn, r in row_recs if rn > (baseline_row or 0)]
        if list_new:
            print(f"📝 Rows after baseline row {baseline_row}: {len(recent_pairs)}")
            for rn, r in sorted(recent_pairs, key=lambda x: x[0]):
                ts = str(r.get("Timestamp", "")).strip()
                name = str(r.get("Display Name", "")).strip()
                sid = str(r.get("Slack ID", "")).strip()
                print(f"   • Row {rn}: {ts} | {name or '(no name)'} {f'[{sid}]' if sid else ''}")
            return
        if not recent_pairs:
            print(f"✅ No new mentor submissions after row {baseline_row} in '{ws_title}'.")
            # Show the current baseline row content
            values = worksheet.get_all_values()
            if values and baseline_row and baseline_row <= len(values):
                header = values[0]
                row_vals = values[baseline_row - 1]
                row_map = {header[i]: row_vals[i] if i < len(row_vals) else "" for i in range(len(header))}
                name = (row_map.get("Display Name") or "").strip()
                sid = (row_map.get("Slack ID") or "").strip()
                ts = (row_map.get("Timestamp") or "").strip()
                print(f"📌 Baseline row {baseline_row}: {ts} | {name or '(no name)'} {f'[{sid}]' if sid else ''}")
            return

        # Continue with processing using recent_pairs
        recent_rows = [r for _, r in sorted(recent_pairs, key=lambda x: x[0])]  # preserve sheet order
    else:
        # Timestamp mode
        # Filter only rows with Timestamp > last_ts
        recent_rows: List[Dict[str, Any]] = []
        recent_max: Optional[datetime] = last_ts
        for r in records:
            ts = _parse_ts(str(r.get("Timestamp", "")))
            if ts and ts > last_ts:
                recent_rows.append(r)
                if recent_max is None or ts > recent_max:
                    recent_max = ts

        if list_new:
            print(f"📝 Rows newer than baseline ({last_ts.strftime('%Y-%m-%d %H:%M:%S')}): {len(recent_rows)}")
            lookup = _build_row_lookup(worksheet)
            for r in _sort_records_by_ts(recent_rows):
                ts = _parse_ts(str(r.get("Timestamp", "")))
                name = str(r.get("Display Name", "")).strip()
                sid = str(r.get("Slack ID", "")).strip()
                key = (ts.strftime("%Y-%m-%d %H:%M:%S"), sid) if ts and sid else (ts.strftime("%Y-%m-%d %H:%M:%S"), name) if ts else None
                row_no = lookup.get(key) if key else None
                prefix = f"Row {row_no}: " if row_no else ""
                print(f"   • {ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '?'} | {prefix}{name or '(no name)'} {f'[{sid}]' if sid else ''}")
            return

        if not recent_rows:
            print(f"✅ No new mentor submissions since {last_ts.strftime('%Y-%m-%d %H:%M:%S')} in '{ws_title}'.")
            _print_baseline_preview(ws_title, worksheet, records, last_ts)
            return

    print(f"🚀 Processing {len(recent_rows)} new mentor submissions since {last_ts.strftime('%Y-%m-%d %H:%M:%S')}...")

    # Build lists to add
    stage_name = f"stage-{stage}"
    main_channel_id = channels.get("main")
    to_add_main: List[str] = []
    per_track: Dict[str, List[str]] = {}

    for r in recent_rows:
        slack_id = str(r.get("Slack ID", "")).strip()
        display_name = str(r.get("Display Name", "")).strip()
        selected_tracks_str = str(r.get("Selected Tracks", "")).strip()
        if not selected_tracks_str:
            continue
        tracks = [t.strip() for t in selected_tracks_str.split(",") if t.strip()]

        user_id: Optional[str] = None
        if slack_id:
            user_id = slack_id
        elif display_name:
            user_id = csc.get_user_id_by_username(display_name, all_users)

        if not user_id:
            print(f"   ⚠️ Could not resolve user for row: {display_name} | {slack_id}")
            continue

        to_add_main.append(user_id)
        for t in tracks:
            ch_id = channels.get(t)
            if ch_id:
                per_track.setdefault(t, []).append(user_id)

    # Deduplicate
    to_add_main = list(dict.fromkeys(to_add_main))
    for k in list(per_track.keys()):
        per_track[k] = list(dict.fromkeys(per_track[k]))

    if dry_run:
        print("\n🔎 DRY RUN: Planned actions (no Slack changes will be made)")
        if to_add_main:
            print(f"   • stage-{stage}: would invite {len(to_add_main)} users: {to_add_main}")
        for t, user_ids in per_track.items():
            if user_ids:
                print(f"   • stage-{stage}-{t}: would invite {len(user_ids)} users: {user_ids}")
    else:
        # Add to main channel
        if main_channel_id and to_add_main:
            added_main = csc.add_users_to_channel(main_channel_id, to_add_main, stage_name)
            # Exclude admin accounts from mentions
            added_main = [uid for uid in added_main if uid not in {"U09C0AAHT0Q", "U09LDCKAFJ6"}]
            csc._notify_new_members(main_channel_id, added_main, stage_name)

        # Add per-track and batch-mention once per track
        for t, user_ids in per_track.items():
            ch_id = channels.get(t)
            if not ch_id or not user_ids:
                continue
            added_ids = csc.add_users_to_channel(ch_id, user_ids, f"{stage_name}-{t}")
            csc._notify_new_members(ch_id, added_ids, f"{stage_name}-{t}")

    # Update state with new max
    if baseline_mode == "row":
        # Update row-baseline to the highest row processed
        lookup = _build_row_lookup(worksheet)
        max_row = None
        for r in recent_rows:
            ts = _parse_ts(str(r.get("Timestamp", "")))
            name = str(r.get("Display Name", "")).strip()
            sid = str(r.get("Slack ID", "")).strip()
            key = (ts.strftime("%Y-%m-%d %H:%M:%S"), sid) if ts and sid else (ts.strftime("%Y-%m-%d %H:%M:%S"), name) if ts else None
            row_no = lookup.get(key) if key else None
            if row_no is not None and (max_row is None or row_no > max_row):
                max_row = row_no
        if not dry_run and max_row is not None:
            state_row_key = f"{ws_title}__row"
            state[state_row_key] = max_row
            _save_state(state, stage)
            print(f"💾 Updated row-baseline to row {max_row} for '{ws_title}' in stage-{stage}.")
    else:
        if not dry_run and recent_max and (last_ts is None or recent_max > last_ts):
            state[ws_title] = recent_max.strftime("%Y-%m-%d %H:%M:%S")
            _save_state(state, stage)
            print(f"💾 Updated last processed timestamp to {state[ws_title]} for '{ws_title}' in stage-{stage}.")
            _print_baseline_preview(ws_title, worksheet, records, recent_max)


def main():
    parser = argparse.ArgumentParser(description="Incrementally add mentors to an existing stage from the latest worksheet.")
    parser.add_argument("stage", type=int, help="Stage number, e.g., 3 for stage-3")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without calling Slack")
    parser.add_argument("--process-all", action="store_true", help="Process all rows regardless of saved baseline")
    parser.add_argument("--since-minutes", type=int, default=None, help="Process rows newer than now minus these minutes (overrides baseline)")
    parser.add_argument("--reset-baseline", action="store_true", help="Clear saved baseline for the latest worksheet and exit")
    parser.add_argument("--show-baseline", action="store_true", help="Show the current baseline and the matching row(s) from the latest worksheet, then exit")
    parser.add_argument("--show-newest", action="store_true", help="Show the newest rows by Timestamp (top 10) with row numbers, then exit")
    parser.add_argument("--list-new", action="store_true", help="List rows newer than the baseline (what would be processed), then exit")
    parser.add_argument("--baseline-mode", choices=["timestamp", "row"], default="timestamp", help="Use 'timestamp' (default) or 'row' for incremental baseline tracking")

    args = parser.parse_args()

    print(f"🚀 Incremental add: stage-{args.stage} (latest worksheet only)")
    process_incremental(
        args.stage,
        dry_run=args.dry_run,
        process_all=args.process_all,
        since_minutes=args.since_minutes,
        reset_baseline=args.reset_baseline,
        show_baseline=args.show_baseline,
        show_newest=args.show_newest,
        list_new=args.list_new,
        baseline_mode=args.baseline_mode,
    )
    print("\n✅ Done (incremental)")


if __name__ == "__main__":
    main()
