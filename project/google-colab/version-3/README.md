# Version 3 — Batch processing, run from local (no human in the loop)

Process many videos × many source images in one go, driven entirely from your
machine. The local orchestrator uploads inputs to DagsHub, runs the batch on a
Colab GPU via the **Google Colab CLI**, then downloads the named results back.

```
LOCAL  orchestrate.py ──upload inputs──▶ DagsHub ──pull──▶ COLAB GPU (v3_batch_run.py)
        │  launch detached (colab exec _launch.py, returns in seconds)            │
        │  poll bucket for _SUCCESS/_FAILED marker  ◀────── write marker ─────────┘
        ▼
      download results ◀── DagsHub ◀── upload per-combo output (headless-run)
```

The batch runs **detached** on the VM; the orchestrator **polls DagsHub** for a
completion marker rather than holding a live connection for the whole job. A brief
network blip just retries the next poll instead of killing the run, and the session
is always reclaimed. While polling, it tails the remote log and prints the live
FaceFusion stage/percentage (analysing → extracting → processing → merging).

## One-time setup

1. **Colab CLI** — install and authenticate:
   ```bash
   uv tool install google-colab-cli      # or: pip install google-colab-cli
   colab status                          # triggers auth (oauth2 / adc) on first use
   ```
2. **Python deps for the orchestrator** (local):
   ```bash
   pip install boto3
   ```
3. **DagsHub token** — create a fresh token (DagsHub → User Settings → Tokens) and
   expose it to `orchestrate.py` as either:
   - an env var `DAGSHUB_USER_TOKEN`, or
   - a line `DAGSHUB_USER_TOKEN=...` in a `.env` file next to `orchestrate.py`.

   The token is gitignored and only ever lands on the ephemeral Colab VM inside
   `batch_config.json`. Never commit it (the original V1/V2 token was leaked and
   must stay rotated).

## Prepare a batch

Make an input folder like:

```
batch_in/
  sources/    ls 65.jpg   ls 33.jpg
  targets/    25-lnka-cc.0756-0838.mp4   20-lnka-cc.0644-0725.mp4
  override.ini
```

`override.ini` is a native `facefusion.ini` slice (see the sample in this folder).
It applies to the whole batch. Its `face_swapper_model` also sets the output
filename suffix letter: `a / b / c` for `hyperswap_1a/1b/1c_256`, `in` for
`inswapper_128` and `inswapper_128_fp16`.

## Run

```bash
# preview the output filenames only — no GPU, no upload
python orchestrate.py --inputs ./batch_in --dry-run

# full run: upload → Colab GPU batch → download results to ./batch_out
python orchestrate.py --inputs ./batch_in --out ./batch_out --gpu L4

# reclaim a stranded session (e.g. if the machine slept mid-run)
python orchestrate.py --stop
```

The session is always stopped at the end (even on error). If the local process is
killed outright before it can stop the session (e.g. the machine sleeps), the VM
lingers until Colab's idle timeout — run `python orchestrate.py --stop` to reclaim
it immediately.

### Windows note
The Colab CLI is officially Linux/macOS only (it imports the Unix-only `termios`).
A tiny stub in `_winshim/` makes it import on Windows — `orchestrate.py` puts it on
`PYTHONPATH` automatically when it calls `colab`. For manual `colab` use in a plain
terminal, copy `_winshim/termios.py` into the CLI's `site-packages`, or run inside
WSL. Output is forced to UTF-8 so the streamed `✓`/progress chars don't crash a
non-UTF-8 console.

## Output naming

Outputs compound the target name + source token + model letter:

| target | source | model | output |
|---|---|---|---|
| `25-lnka-cc.0756-0838.mp4` | `ls 65.jpg` | `hyperswap_1b_256` | `25-lnka-cc.0756-0838 ls65b.mp4` |
| `25-lnka-cc.0756-0838.mp4` | `ls 65.jpg` | `hyperswap_1c_256` | `25-lnka-cc.0756-0838 ls65c.mp4` |
| `25-lnka-cc.0756-0838.mp4` | `ls 65.jpg` | `inswapper_128` | `25-lnka-cc.0756-0838 ls65in.mp4` |

**Round 2** (swap a new face over an already-swapped video): put the round-1
outputs into `targets/` and a new image in `sources/`. The existing token is
detected and the new one is joined with a hyphen:

```
25-lnka-cc.0756-0838 ls65b.mp4  +  ls 33.jpg (1c)  ->  25-lnka-cc.0756-0838 ls65b-ls33c.mp4
```

## Troubleshooting

**A video comes out unswapped (or barely swapped).** Almost always the
`occlusion` entry in `face_mask_types`. The XSeg occluder keeps whatever is *in
front of* the face (hands, objects, fluid) unswapped — on clips where the face is
covered throughout, that suppresses nearly the entire swap, so the result looks
like the original. Fix: set `face_mask_types = box` in `override.ini`. Add
`occlusion` back only for clips where the face is mostly clear and you want
passing hands/objects to remain visible. (This is per-clip content, not a
first-run or upload issue — the swap and source load fine.)

## Files

| file | runs on | purpose |
|---|---|---|
| `orchestrate.py` | local | upload → launch detached → poll → download → stop |
| `v3_batch_run.py` | Colab VM | install, pull, loop combos, headless-run, upload, write marker |
| `_launch.py` | Colab VM | detaches `v3_batch_run.py` so `exec` returns immediately |
| `naming.py` | both | output filename compounding |
| `_winshim/termios.py` | local (Windows) | lets the Colab CLI import on native Windows |
| `override.ini` | — | sample per-batch settings |
| `tests/test_naming.py` | local | unit tests for the naming rules |

Run the tests with: `python -m pytest tests/test_naming.py`
