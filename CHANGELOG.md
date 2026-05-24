# Changelog

All notable changes to **Mixtape Organizer** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.0] — current (`main.py`)

Complete rewrite.  The tool graduated from a single-function script into a
structured, interactive CLI application.

### Added
- **`Track` dataclass** — replaces the bare `Song` namedtuple; stores `path`,
  `duration`, `album`, `year`, `track_num`, `artist`, and `title`
- **Rich tag reading** — handles VorbisComment (FLAC/OGG), ID3 (MP3),
  MP4/iTunes (M4A/AAC), and ASF/WMA tags transparently via `_get_tag()`
- **Recursive folder scanning** — optional sub-directory traversal using
  `pathlib.Path.glob("**/*")`
- **Auto-suggested mixtape title** — `guess_title()` picks the most common
  album tag; falls back to `"My Mixtape"`
- **Named output files** — `{Title}_C-{minutes}_Side_{A/B}.m3u8`
- **Configurable output directory** — defaults to the music folder
- **Portable playlist paths** — entries use paths relative to the playlist
  file, so the folder works on any machine or player
- **Interactive overflow handling** — when tracks don't fit, the user can
  add extra tolerance per side and retry; loops until all tracks fit or the
  user skips the rest
- **Natural playback order** — after packing, tracks are re-sorted by
  year → track number → title → artist for the final playlist
- **ANSI colour output** with TTY detection (degrades gracefully to plain text
  in pipes and legacy `cmd.exe`)
- **Progress bars** — coloured fill indicators (green / yellow / red) for each
  side's used capacity
- **Five new audio formats** — `.ogg`, `.aac`, `.opus`, `.ape`, `.wv`
  (total: 9 formats)
- **Windows UTF-8 fix** — reconfigures `sys.stdout` to UTF-8 on startup to
  prevent `UnicodeEncodeError` on narrow code pages (GBK / cp936)
- **Graceful import error** — prints a helpful message and exits cleanly if
  `mutagen` is not installed

### Changed
- Entry point renamed: `tape_organizer.py` → `main.py`
- `organize_songs()` split into two focused functions: `pack()` (greedy
  longest-first bin-packing) and `balance()` (iterative swap, up to
  1 000 passes)
- Balance iteration limit raised from 100 → 1 000

### Removed
- `#EXTM3U` / `#EXTINF` extended headers removed from playlist output —
  entries are now bare relative paths for maximum player compatibility

---

## [1.2] — archived (`archive/tape_organizer_v1.2.py`)
*2024-08-03*

### Added
- `optimize_sides()` — dedicated balance function using pairwise swap
  (up to `max_iterations=100`); replaces the inline `while` loop from v1.1
- `organize_songs()` now returns `(side_a, side_b, length_a, length_b)` so
  the caller can pass live lengths directly to `optimize_sides()`

### Removed
- Inline balancing `while` loop removed from `organize_songs()`

---

## [1.1] — archived (`archive/tape_organizer_v1.1.py`)
*2024-08-03*

### Added
- `try/except` error handling around `mutagen.File()` calls — bad files are
  reported and skipped instead of crashing the program
- Post-packing balancing loop: iteratively moves tracks between sides to
  reduce the duration gap
- Input path quote-stripping in `main()` (handles drag-and-drop on Windows)
- Early exit when no valid music files are found

### Fixed
- Extension check changed to `filename.lower().endswith(...)` — files with
  uppercase extensions (`.MP3`, `.FLAC`) are now recognised
- Gap accounting corrected: was `len(side) * gap` (wrong), now `gap` added
  once per track

### Changed
- Tracks sorted by duration descending before packing (longest-first
  heuristic improves bin-packing quality)

---

## [1.0] — archived (`archive/tape_organizer_v1.0.py`)
*2024-07-29*

Initial version.

- Scans a folder for `.mp3`, `.flac`, `.wav`, `.m4a` files via `os.listdir()`
- Suggests the smallest standard tape length that fits all tracks
- Greedy two-sided packing: assigns each track to whichever side is currently
  shorter
- Exports Side A and Side B as `side_a.m3u8` / `side_b.m3u8` with `#EXTM3U`
  and `#EXTINF` headers
