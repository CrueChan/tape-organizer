# 🎞 Mixtape Organizer

Auto-arrange your music collection across both sides of a cassette tape and export named `.m3u8` playlists — perfect for recording your own mixtapes.

```
  ╔══════════════════════════════════════════════╗
  ║     🎵  Mixtape Organizer  v4.0              ║
  ║  Auto-fill both sides of a cassette tape     ║
  ║  by CrueChan                                 ║
  ╚══════════════════════════════════════════════╝

  Music folder path: /home/user/music/summer-vibes
  Scanning…
  22 tracks found  │  Total duration: 78:42 (78.7 min)

  Mixtape title (used in output filenames) [My Mixtape]: Summer Vibes
  Suggested tape: 90 min  (smallest standard size for all tracks)
  Tape length (minutes) [90]:
  Gap between tracks (seconds) [4]:
  Save playlists to [/home/user/music/summer-vibes]:

  🎞  Summer Vibes  │  90-minute tape
  ──────────────────────────────────────────────────────────
  SIDE A  [████████████████████░░░░░░░░] 87%  38:54 / 45:00
  ──────────────────────────────────────────────────────────
   1. Where Do I Begin                              [4:22]
   2. Fade Into You                                 [4:50]
   ...
  ──────────────────────────────────────────────────────────
  11 tracks  │  Total: 38:54

  ✓  Playlists saved to: /home/user/music/summer-vibes
     Summer_Vibes_C-90_Side_A.m3u8
     Summer_Vibes_C-90_Side_B.m3u8
```

## Features

- **Scans a folder** for audio files (MP3, FLAC, WAV, M4A, OGG, AAC, Opus, APE, WavPack)
- **Suggests the right tape size** — shows the smallest standard cassette that fits all your tracks
- **Balances both sides** using a greedy longest-first algorithm, then refines with iterative swapping
- **Named output files** — e.g. `Summer_Vibes_C-90_Side_A.m3u8`
- **Configurable output folder** — save playlists anywhere
- **Adjustable gap** — set the silence between tracks in seconds
- **Interactive overflow handling** — when tracks don't fit, you decide how much extra time to allow (can loop until everything fits or you choose to skip the rest)

## Requirements

- Python 3.11 or newer
- [mutagen](https://mutagen.readthedocs.io/)

> **Windows note:** coloured output and progress bars require **Windows Terminal** or **PowerShell 5.1+**.  The program works fine in the legacy `cmd.exe` prompt too — it simply falls back to plain text with no colour.

## Installation

### With [uv](https://docs.astral.sh/uv/) (recommended)

```sh
# Clone the repo, then:
uv run main.py
```

`uv` reads `pyproject.toml` and installs dependencies automatically.  On Windows, install uv with:

```powershell
winget install astral-sh.uv
```

### With pip

```sh
pip install mutagen
python main.py
```

On Windows you may need to use `py` instead of `python`:

```powershell
py -m pip install mutagen
py main.py
```

## Usage

```sh
python main.py
```

The program walks you through these steps interactively.

> **Windows tip:** when prompted for a folder path, you can drag-and-drop a folder from File Explorer into the terminal window — it pastes the full path automatically (with quotes, which the program strips for you).  Both backslash (`C:\Users\yourname\Music`) and forward-slash paths are accepted.

| Step | Prompt | Notes |
|------|--------|-------|
| 1 | Music folder path | Scanned non-recursively by default |
| 2 | Include music in sub-directories? | Default: No |
| 3 | Mixtape title | Sanitised and used in output filenames |
| 4 | Tape length (minutes) | Standard sizes suggested automatically |
| 5 | Gap between tracks (seconds) | Default: 4 s |
| 6 | Save playlists to | Defaults to the music folder |

If some tracks don't fit within the tape length (plus 1 minute default tolerance per side), you'll be asked whether to allow a longer total duration and how many extra minutes per side to add.  This loop repeats until everything fits or you choose to skip the remaining tracks.

## Output

Two `.m3u8` playlist files, one per side:

```
Summer_Vibes_C-90_Side_A.m3u8
Summer_Vibes_C-90_Side_B.m3u8
```

These can be opened in **VLC**, **foobar2000**, **Winamp**, **Clementine**, or any player that supports M3U playlists.  Each entry uses a path **relative to the playlist file**, so the playlist is portable — move the whole folder and it still works.

## Algorithm

1. **Scan** — read audio metadata (duration) via mutagen
2. **Pack** — sort tracks longest-first; greedily assign each to the shorter side as long as it fits within the limit
3. **Balance** — iteratively swap tracks between sides to minimise the duration difference, without exceeding the limit
4. **Export** — write M3U8 files with relative paths (portable across machines)

## Standard cassette tape lengths

| Minutes | Common name |
|---------|-------------|
| 46      | C-46        |
| 60      | C-60 (most common) |
| 74      | C-74        |
| 80      | C-80        |
| 90      | C-90        |
| 100     | C-100       |
| 120     | C-120       |

Full list supported: 5, 10, 20, 30, 40, 46, 50, 54, 60, 64, 70, 74, 80, 90, 100, 120, 150 minutes.

## Supported audio formats

`.mp3` · `.flac` · `.wav` · `.m4a` · `.ogg` · `.aac` · `.opus` · `.ape` · `.wv`

## License

MIT
