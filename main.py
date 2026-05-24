#!/usr/bin/env python3
"""
Mixtape Organizer
-----------------
Scan a music folder and arrange tracks across both sides of a cassette tape.
Balances the two sides, then saves named .m3u8 playlists ready for playback
in VLC, foobar2000, or any M3U-compatible player.

Usage:
    python main.py
"""

import os
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

# Force UTF-8 output on Windows terminals that default to a narrow code page
# (e.g. GBK / cp936).  errors='replace' prevents crashes on very old consoles
# that cannot display certain glyphs — they'll show '?' instead of crashing.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("Error: mutagen is not installed.  Run:  pip install mutagen")
    sys.exit(1)


# ── Terminal colours ──────────────────────────────────────────────────────────
# ANSI escape codes — Windows 10+ enables Virtual Terminal Processing
# automatically in modern Python.  All codes are set to "" when stdout is
# not a TTY (pipe / file redirect) so no stray escape sequences appear.

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

if _supports_color():
    RST  = "\033[0m"
    BOLD = "\033[1m"
    DIM  = "\033[2m"
    RED  = "\033[91m"   # bright red   — errors, overflow
    GRN  = "\033[92m"   # bright green — success, stats
    YLW  = "\033[93m"   # bright yellow — Side B, warnings
    BLU  = "\033[94m"   # bright blue  — (reserved)
    MAG  = "\033[95m"   # bright magenta — header, tape title
    CYN  = "\033[96m"   # bright cyan  — Side A, prompts, info
else:
    RST = BOLD = DIM = RED = GRN = YLW = BLU = MAG = CYN = ""


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Track:
    name: str          # display name (file stem or relative sub-path)
    path: str          # absolute path on disk
    duration: float    # length in seconds
    album: str  = ""   # album tag     — used to suggest a default title
    year: str   = ""   # year/date tag — primary natural-order key
    track_num: int = 0 # track number  — secondary natural-order key
    artist: str = ""   # artist tag    — tiebreaker
    title: str  = ""   # title tag     — falls back to *name* for sorting


# ── Constants ─────────────────────────────────────────────────────────────────

# Standard cassette tape lengths (total minutes, both sides combined)
STANDARD_TAPE_MINUTES = [
    5, 10, 20, 30, 40, 46, 50, 54,
    60, 64, 70, 74, 80, 90, 100, 120, 150,
]

AUDIO_EXTENSIONS = {
    '.mp3', '.flac', '.wav', '.m4a',
    '.ogg', '.aac', '.opus', '.ape', '.wv',
}

DEFAULT_GAP_SECS       = 4   # seconds of silence assumed between tracks
DEFAULT_TOLERANCE_SECS = 60  # 1 minute of extra room per side by default
BAR_WIDTH              = 28  # character width of the progress bars


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt(seconds: float) -> str:
    """Format *seconds* as M:SS, or H:MM:SS for long durations."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def progress_bar(used: float, total: float, width: int = BAR_WIDTH) -> str:
    """
    Render a coloured text progress bar.

    Colour of the filled region:
      green  (≤ 80 %)  — plenty of room left
      yellow (80–100%) — getting close
      red    (> 100 %) — overflow, uses '!' instead of '█'
    """
    if total <= 0:
        return f"[{DIM}{'░' * width}{RST}]   0%"

    ratio  = used / total
    filled = min(int(width * ratio), width)
    empty  = width - filled

    if ratio > 1.0:
        fill_color, char = RED, '!'
    elif ratio > 0.80:
        fill_color, char = YLW, '█'
    else:
        fill_color, char = GRN, '█'

    bar      = f"{fill_color}{char * filled}{RST}{DIM}{'░' * empty}{RST}"
    pct_color = fill_color          # percentage uses the same colour as the bar
    return f"[{bar}] {pct_color}{ratio * 100:.0f}%{RST}"


# ── I/O helpers ───────────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    """Prompt the user; press Enter to accept the default."""
    hint = f" {DIM}[{YLW}{default}{DIM}]{RST}" if default else ""
    try:
        value = input(f"  {CYN}{prompt}{RST}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {YLW}Bye!{RST}")
        sys.exit(0)
    return value or default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Ask a yes/no question; press Enter to accept the default."""
    yn    = "Y/n" if default else "y/N"
    hint  = f"{DIM}({YLW}{yn}{DIM}){RST}"
    try:
        ans = input(f"  {CYN}{prompt}{RST} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {YLW}Bye!{RST}")
        sys.exit(0)
    if not ans:
        return default
    return ans in ('y', 'yes')


def sanitize(name: str) -> str:
    """Return a filesystem-safe version of *name* for use in filenames."""
    safe = "".join(c if (c.isalnum() or c in ' -_()') else '_' for c in name)
    return safe.strip().replace(' ', '_') or "mixtape"


# ── Core logic ────────────────────────────────────────────────────────────────

def _get_tag(audio, *keys: str) -> str:
    """Extract the first non-empty tag value matching any of *keys*.

    Handles four tag layouts transparently:
      VorbisComment (FLAC / OGG)  — lowercase string keys, list values
      ID3           (MP3)         — UPPERCASE keys, frame objects
      MP4 / iTunes  (M4A / AAC)   — '©xxx' keys, list values;
                                    track number is a list of (n, total) tuples
      ASF / WMA                   — 'WM/Xxx' keys, list values
    """
    if not audio or not audio.tags:
        return ""
    for key in keys:
        try:
            val = audio.tags[key]
            if not val:
                continue
            item = val[0] if isinstance(val, (list, tuple)) else val
            # MP4 track number comes as (track_index, total) tuple
            if isinstance(item, tuple):
                item = item[0]
            return str(item).strip()
        except (KeyError, TypeError, IndexError):
            pass
    return ""


def _parse_track_num(raw: str) -> int:
    """Parse '3', '03', '3/12', '3 of 12', etc. → integer track number."""
    if not raw:
        return 0
    try:
        return int(raw.split('/')[0].split()[0])
    except (ValueError, IndexError):
        return 0


def scan_folder(folder: str, recursive: bool = False) -> Tuple[List[Track], List[str]]:
    """
    Walk *folder* for audio files.

    Args:
        folder:    Path to the music directory.
        recursive: When True, descend into sub-directories as well.

    Returns:
        tracks   — list of Track objects sorted by relative path
        warnings — list of human-readable error strings for files that
                   could not be read
    """
    tracks: List[Track] = []
    warnings: List[str] = []

    root = Path(folder)
    pattern = "**/*" if recursive else "*"
    files = sorted(
        p for p in root.glob(pattern)
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )

    for p in files:
        rel = p.relative_to(root)  # e.g. "subfolder/song.mp3" or "song.mp3"
        # Include parent folder(s) in the display name when scanning recursively
        # so the user can tell tracks from different sub-directories apart.
        if recursive and rel.parent != Path("."):
            display_name = str(rel.with_suffix(""))   # "subfolder/song"
        else:
            display_name = p.stem                      # "song"
        try:
            audio = MutagenFile(str(p))
            if audio is None or not hasattr(audio, 'info'):
                warnings.append(f"Cannot read metadata — skipping: {rel}")
                continue
            tracks.append(Track(
                name=display_name,
                path=str(p),
                duration=audio.info.length,
                album=_get_tag(audio, "album",   "TALB",  "\xa9alb", "WM/AlbumTitle"),
                year =_get_tag(audio, "date",    "TDRC",  "\xa9day", "WM/Year")[:4],
                track_num=_parse_track_num(
                    _get_tag(audio, "tracknumber", "TRCK", "trkn", "WM/TrackNumber")
                ),
                artist=_get_tag(audio, "artist", "TPE1",  "\xa9ART", "Author"),
                title =_get_tag(audio, "title",  "TIT2",  "\xa9nam", "Title"),
            ))
        except Exception as exc:
            warnings.append(f"{rel}: {exc}")

    return tracks, warnings


def guess_title(tracks: List[Track]) -> str:
    """Return the most common album tag across *tracks*, or 'My Mixtape'.

    If a single album name appears more than once it is a strong signal
    that the user is dubbing one CD/album rather than making a mixtape.
    Single-track albums are ignored to avoid spurious matches.
    """
    albums = [t.album for t in tracks if t.album]
    if not albums:
        return "My Mixtape"
    most_common, count = Counter(albums).most_common(1)[0]
    # Require the album to appear on at least two tracks so a single
    # stray tag doesn't override the default.
    return most_common if count >= 2 else "My Mixtape"


def suggest_tape(total_secs: float) -> Optional[int]:
    """Return the smallest standard tape length (minutes) that fits *total_secs*."""
    for minutes in STANDARD_TAPE_MINUTES:
        if minutes * 60 >= total_secs:
            return minutes
    return None


def pack(
    tracks: List[Track],
    side_limit: float,
    gap: float,
) -> Tuple[List[Track], List[Track], List[Track], float, float]:
    """
    Greedy longest-first bin-packing into two sides (bins).

    Sorts tracks by duration descending and assigns each to whichever side
    is currently shorter, as long as it still fits within *side_limit*.
    Tracks that fit on neither side go into the overflow list.

    Args:
        tracks:     tracks to distribute
        side_limit: maximum seconds per side (including any tolerance)
        gap:        inter-track gap in seconds (counted toward used time)

    Returns:
        side_a, side_b, overflow, used_a, used_b
        where used_* counts track duration + one gap slot each.
    """
    a: List[Track] = []
    b: List[Track] = []
    overflow: List[Track] = []
    ua = ub = 0.0

    for t in sorted(tracks, key=lambda x: x.duration, reverse=True):
        slot = t.duration + gap
        # Prefer the shorter side; fall back to the longer side; else overflow
        order = [(a, True), (b, False)] if ua <= ub else [(b, False), (a, True)]
        placed = False
        for side, is_a in order:
            used = ua if is_a else ub
            if used + slot <= side_limit:
                side.append(t)
                if is_a:
                    ua += slot
                else:
                    ub += slot
                placed = True
                break
        if not placed:
            overflow.append(t)

    return a, b, overflow, ua, ub


def balance(
    a: List[Track],
    b: List[Track],
    ua: float,
    ub: float,
    side_limit: float,
) -> Tuple[List[Track], List[Track], float, float]:
    """
    Iteratively swap tracks between sides to minimise |ua - ub|.

    Only accepts swaps that keep both sides within *side_limit*.
    Gap time cancels out in swap calculations (each track carries the same
    gap regardless of which side it's on), so raw durations are compared.
    Runs until no improving swap is found or after 1 000 iterations.
    """
    for _ in range(1000):
        swapped = False
        for i, ta in enumerate(a):
            for j, tb in enumerate(b):
                new_ua = ua - ta.duration + tb.duration
                new_ub = ub - tb.duration + ta.duration
                if (
                    abs(new_ua - new_ub) < abs(ua - ub)
                    and new_ua <= side_limit
                    and new_ub <= side_limit
                ):
                    a[i], b[j] = tb, ta
                    ua, ub = new_ua, new_ub
                    swapped = True
                    break
            if swapped:
                break
        if not swapped:
            break
    return a, b, ua, ub


def write_m3u(tracks: List[Track], path: str) -> None:
    """Write *tracks* as a plain M3U8 playlist to *path*.

    Entries use paths relative to the playlist file's own directory so
    the playlist works in foobar2000, VLC, and portable players (e.g.
    Sony NW-ZX707) regardless of where the folder is mounted.
    The first line is a bare ``#`` comment so players recognise the file
    as an M3U without triggering extended-M3U parsing.
    """
    playlist_dir = os.path.dirname(os.path.abspath(path))
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write("#\n")
        for t in tracks:
            rel = os.path.relpath(t.path, playlist_dir)
            fh.write(f"{rel}\n")


# ── Natural-order sort ───────────────────────────────────────────────────────

def natural_sort_key(t: Track) -> tuple:
    """Sort key that mimics how a human would order tracks in a collection.

    Priority: year → track number → title (or filename stem) → artist.

    Tracks with no year tag sort before dated tracks so they don't get
    pushed to the end of an otherwise well-tagged album.
    Track number 0 (= unknown) sorts last within the same year so that
    numbered tracks always precede un-numbered bonus material.
    """
    year      = t.year or ""                 # "" < "1970" < "2025"
    track_num = t.track_num if t.track_num else 9999  # unknown → after numbered
    label     = (t.title or t.name).lower()  # case-insensitive title sort
    artist    = t.artist.lower()
    return (year, track_num, label, artist)


# ── Display ───────────────────────────────────────────────────────────────────

RULE = "  " + "─" * 58


def print_side(label: str, tracks: List[Track], used: float, tape_side: float) -> None:
    """Pretty-print one tape side with a coloured progress bar and track listing."""
    # Side A → cyan,  Side B → yellow
    side_color = CYN if "A" in label else YLW

    bar      = progress_bar(used, tape_side)
    over_str = (
        f"  {RED}(+{fmt(used - tape_side)} over){RST}"
        if used > tape_side else ""
    )

    print(f"{DIM}{RULE}{RST}")
    print(f"  {BOLD}{side_color}{label}{RST}  {bar}  "
          f"{side_color}{fmt(used)}{RST} / {DIM}{fmt(tape_side)}{RST}{over_str}")
    print(f"{DIM}{RULE}{RST}")

    name_col = 42  # characters reserved for the track name
    for i, t in enumerate(tracks, 1):
        # Truncate names that would overflow the column
        name = t.name if len(t.name) <= name_col else t.name[: name_col - 1] + "…"
        dur  = f"{DIM}[{fmt(t.duration)}]{RST}"
        print(f"  {DIM}{i:2}.{RST} {name:<{name_col}}  {dur}")

    print(f"{DIM}{RULE}{RST}")
    print(f"  {len(tracks)} track{'s' if len(tracks) != 1 else ''}  "
          f"{DIM}│{RST}  Total: {side_color}{BOLD}{fmt(used)}{RST}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(f"  {MAG}╔══════════════════════════════════════════════╗{RST}")
    print(f"  {MAG}║{RST}     🎵  {BOLD}{MAG}Mixtape Organizer{RST}  v4.0"
          f"              {MAG}║{RST}")
    print(f"  {MAG}║{RST}  Auto-fill both sides of a cassette tape"
          f"     {MAG}║{RST}")
    print(f"  {MAG}║{RST}  {DIM}by CrueChan{RST}"
          f"                                 {MAG}║{RST}")
    print(f"  {MAG}╚══════════════════════════════════════════════╝{RST}")
    print()

    # ── 1. Music folder ───────────────────────────────────────────────────────
    folder = ask("Music folder path").strip('"').strip("'")
    if not os.path.isdir(folder):
        print(f"\n  {RED}✗  Directory not found: {folder}{RST}")
        sys.exit(1)

    recursive = ask_yes_no("Include music in sub-directories?", default=False)

    print(f"\n  {DIM}Scanning…{RST}")
    tracks, warnings = scan_folder(folder, recursive=recursive)

    if warnings:
        print(f"\n  {YLW}Warnings ({len(warnings)}):{RST}")
        for w in warnings:
            print(f"    {YLW}!{RST} {w}")

    if not tracks:
        exts = ", ".join(sorted(AUDIO_EXTENSIONS))
        print(f"\n  {RED}✗  No audio files found.  "
              f"{DIM}(Supported formats: {exts}){RST}")
        sys.exit(1)

    total = sum(t.duration for t in tracks)
    print(f"\n  {GRN}{len(tracks)} tracks found{RST}  {DIM}│{RST}  "
          f"Total duration: {GRN}{fmt(total)}{RST} {DIM}({total / 60:.1f} min){RST}")

    # ── 2. Mixtape title ──────────────────────────────────────────────────────
    print()
    title = ask("Mixtape title (used in output filenames)", guess_title(tracks))
    safe  = sanitize(title)

    # ── 3. Tape length ────────────────────────────────────────────────────────
    suggested = suggest_tape(total)
    if suggested:
        print(f"\n  Suggested tape: {GRN}{suggested} min{RST}  "
              f"{DIM}(smallest standard size for all tracks){RST}")
    else:
        print(f"\n  {YLW}⚠  Total duration exceeds the longest "
              f"standard tape (150 min).{RST}")

    tape_min  = int(ask("Tape length (minutes)", str(suggested or 60)))
    tape_side = tape_min * 60 / 2   # seconds per side (no tolerance yet)

    # ── 4. Gap ────────────────────────────────────────────────────────────────
    gap = int(ask("Gap between tracks (seconds)", str(DEFAULT_GAP_SECS)))
    print(f"  {CYN}ℹ{RST}  {DIM}Gap is used only for side-length calculation,"
          f" not inserted into the playlist.")
    print(f"     To add real silence, edit the .m3u8 file and insert a blank"
          f" audio file entry between tracks.{RST}")

    # ── 5. Output folder ──────────────────────────────────────────────────────
    out_dir = ask("Save playlists to", folder).strip('"').strip("'")
    os.makedirs(out_dir, exist_ok=True)

    # ── 6. Pack with default tolerance ───────────────────────────────────────
    tolerance  = DEFAULT_TOLERANCE_SECS
    side_limit = tape_side + tolerance

    a, b, overflow, ua, ub = pack(tracks, side_limit, gap)

    # ── 7. Offer to extend tolerance for any overflowing tracks ───────────────
    while overflow:
        ov_total = sum(t.duration for t in overflow)
        print(
            f"\n  {YLW}⚠  {len(overflow)} track(s) don't fit within "
            f"{tape_min} min  "
            f"{DIM}(+{tolerance // 60:.0f} min tolerance per side){RST}{YLW}:{RST}"
        )
        for t in overflow:
            print(f"     {YLW}•{RST} {t.name}  {DIM}[{fmt(t.duration)}]{RST}")
        print(f"     {DIM}Combined: {fmt(ov_total)}{RST}")

        if not ask_yes_no(
            "\n  Allow a longer total duration to fit these tracks?",
            default=False,
        ):
            break

        extra_min  = float(ask("  Extra minutes to allow per side", "2"))
        tolerance += extra_min * 60
        side_limit = tape_side + tolerance
        a, b, overflow, ua, ub = pack(tracks, side_limit, gap)

        if not overflow:
            print(f"  {GRN}✓  All tracks now fit.{RST}")

    # ── 8. Balance the two sides ──────────────────────────────────────────────
    a, b, ua, ub = balance(a, b, ua, ub, side_limit)

    # ── 8b. Restore natural playback order within each side ───────────────────
    # pack() and balance() sort by duration internally; re-sort by
    # year → track number → title → artist for the final playlist.
    a.sort(key=natural_sort_key)
    b.sort(key=natural_sort_key)

    # ── 9. Display results ────────────────────────────────────────────────────
    print(f"\n\n  🎞  {BOLD}{MAG}{title}{RST}  {DIM}│  {tape_min}-minute tape{RST}")
    print_side("SIDE A", a, ua, tape_side)
    print()
    print_side("SIDE B", b, ub, tape_side)

    if overflow:
        print(f"\n  {YLW}Tracks not included ({len(overflow)}):{RST}")
        for t in overflow:
            print(f"    {YLW}•{RST} {t.name}  {DIM}[{fmt(t.duration)}]{RST}")

    # ── 10. Save playlists ────────────────────────────────────────────────────
    name_a = os.path.join(out_dir, f"{safe}_C-{tape_min}_Side_A.m3u8")
    name_b = os.path.join(out_dir, f"{safe}_C-{tape_min}_Side_B.m3u8")
    write_m3u(a, name_a)
    write_m3u(b, name_b)

    print(f"\n  {GRN}✓  Playlists saved to:{RST} {out_dir}")
    print(f"     {GRN}{os.path.basename(name_a)}{RST}")
    print(f"     {GRN}{os.path.basename(name_b)}{RST}")
    print()


if __name__ == "__main__":
    main()
