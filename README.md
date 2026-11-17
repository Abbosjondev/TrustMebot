# DocGuard

A Python library and Telegram bot that embeds a **digital watermark** into photos. Every time an image is handed to someone, a unique ID is hidden inside it. If the image later leaks, choose **Tekshirish**
(check) reveals **who it was given to and when**. The watermark can be read after Telegram's JPEG compression, cropping,
screenshots and downscaling.

> The watermark is **probabilistic**, not an absolute guarantee: heavy blur, very small crops, or re-drawing / re-photographing
> the image can weaken it. The bot reports this through a `confidence` score.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m docguard.bot
```

Tests: `python -m unittest discover -s tests -t .` (or `pytest`).

## Bot usage

1. Send an image (as a regular photo or as a file, both work). If you add a caption, it is used as the label right away.
2. Otherwise the bot asks who/what the image is for, e.g. `Broker gave to Aziz, 16.11.2026`.
3. The bot returns the protected image **as a file**. Forward that file.
4. If an image leaks, send it to the bot and choose **Tekshirish**: the bot reads the watermark and shows the label.

The bot is controlled with reply-keyboard and inline buttons. During protection, it asks whether to add a visible text overlay.
Bot messages are in Uzbek (see `docguard/bot/texts.py`).

## Architecture

```
docguard/
├── config.py            .env -> Settings (immutable)
├── errors.py            single exception hierarchy
├── service.py           ProtectionService: ties core + storage together
├── core/                pure algorithm, independent of Telegram and the database
│   ├── params.py        WatermarkParams: all algorithm parameters
│   ├── reed_solomon.py  GF(256) Reed–Solomon (error + erasure decoding), dependency-free
│   ├── codec.py         ID -> CRC16 -> RS -> bits; soft-decision decoding
│   ├── layout.py        key-derived pilot/data slots and dither (SHA-256 based)
│   ├── dct.py           8x8 DCT bases and block coefficients (numpy)
│   ├── embedder.py      QIM embedding, processed in strips
│   ├── extractor.py     synchronisation + decoding
│   ├── imaging.py       safe loading, size limiting, metadata-free JPEG output
│   ├── metadata.py      detects EXIF/GPS/ICC/XMP (report of what was removed)
│   └── visible.py       optional visible diagonal text overlay
├── storage/repository.py  SQLite: watermark ID -> label, per-user settings
└── bot/                 aiogram 3: handlers, FSM and runner (thread pool + queue)
```

Dependencies point one way: `bot -> service -> (core, storage)`. `core` knows nothing about Telegram, SQLite or the
filesystem, so it can be tested alone and reused in other projects.

## Algorithm

**Layer 1: payload.** The image carries a **48-bit random ID**, not text; the text lives in the database (`ID -> label, date`).
ID + CRC16 -> Reed–Solomon (14 parity bytes) -> 176 bits.

**Layer 2: embedding (QIM in the DCT domain).** The image is split into 8x8 blocks on the Y (luma) channel. Two low-mid
frequency coefficients per block (`(1,2)`, `(2,1)`) are moved onto a quantisation lattice (`step=32`) according to the bit.
These coefficients survive both JPEG quantisation and mild downscaling. The change is added equally to R, G and B, so there
is no colour-conversion loss. Typical PSNR is about 43 dB.

**Layer 3: tiling (crop and screenshot resistance).** The image is divided into 128x128 px tiles and **every tile carries the
full payload** (25% of slots are pilots for synchronisation, the rest are repeated data bits). The decoder folds all tiles on
top of each other and averages out the noise: the larger the image, the more reliable the read.

**Layer 4: synchronisation.** In a cropped image the 8x8 grid and tile boundary are shifted. The decoder tries all 64 pixel
offsets and correlates each against the pilot pattern, finding the correct offset and the tile shift (all 16x16 block
shifts are evaluated at once).

**Layer 5: decoding.** Per-bit confidence (LLR) -> least reliable bytes are marked as erasures -> several Reed–Solomon
attempts -> CRC16 check. The false-positive probability is below ~1e-13.

**Scale.** Output images are resized to a long side of `MAX_SIDE=1280` px (Telegram's "photo" limit). If that image is later
sent as a regular photo, Telegram will not resize it, only re-compress it. If a downscaled copy is not found at its native
size, the decoder resizes it back to the canonical size and tries again.

## Memory

* The pixel limit is checked **before** decoding (`MAX_INPUT_PIXELS`), protecting against decompression bombs.
* For JPEG, `draft()` decodes large scans at reduced size (48 MP JPEG: ~85 MB RAM, ~0.5 s).
* Embedding and extraction work on **strips of block rows**: temporary memory depends on the strip size, not the image size.
* Bot: `MAX_WORKERS` jobs run in parallel, the rest wait in a queue (`JobRunner`).

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | required (bot) | token from @BotFather |
| `SECRET_KEY` | required | watermark key, at least 16 characters |
| `DB_PATH` | `data/docguard.sqlite3` | SQLite file |
| `TIMEZONE` | `Asia/Tashkent` | time zone for displayed dates |
| `MAX_SIDE` | `1280` | long side of output image (px) |
| `WM_STEP` | `32` | watermark strength: higher = more robust but more noticeable |
| `JPEG_QUALITY` | `93` | output JPEG quality |
| `MAX_INPUT_PIXELS` | `120000000` | RAM protection limit |
| `MAX_FILE_MB` | `20` | Telegram Bot API download limit |
| `MAX_WORKERS` | `2` | images processed concurrently |
| `VISIBLE_WATERMARK_DEFAULT` | `false` | default for the visible text overlay |

## Limitations and security

* **`SECRET_KEY` is the watermark's key.** If it is lost or changed, existing watermarks can no longer be read; if it leaks,
  someone else could read them. Back it up, and back up the database too.
* The bot does **not store images**, but it does process them in server memory.
* Users can only read **their own** watermarks (other users' labels are never shown).
* The watermark does **not survive** strong blur (sigma > ~1.5 px), very small crops (< ~256 px), rotation, perspective
  changes, or photographing a screen. Raising `WM_STEP` improves robustness at the cost of visibility.
* On load, the pixel range is compressed by ~6% so that pure white/black scans can still carry the watermark.
* If you need dependable evidence (e.g. in court), seek legal advice: this is a technical indicator, not legal proof.