# MakerWorld Posting Generator

A small desktop app that reads an STL or 3MF file, measures its geometry
(dimensions, volume, estimated weight), and drafts a MakerWorld-style
posting: title, description, tags, and a suggested category. You copy the
result into MakerWorld's own Upload form.

**Important limitation:** MakerWorld has no public API for creating drafts
or uploads, so nothing — this app included — can push a listing into your
MakerWorld drafts automatically. This tool only prepares the text.

## Get a ready-to-run Windows .exe (no Python needed)

This repo includes a GitHub Actions workflow that builds a Windows `.exe`
for you automatically, using PyInstaller, every time code is pushed.

### One-time setup

1. Go to [github.com](https://github.com) and sign in (or create a free account).
2. Click the **+** in the top right → **New repository**.
   - Name it anything, e.g. `makerworld-posting-generator`.
   - Set it to **Public** (so the download link works without signing in).
   - Click **Create repository**.
3. On the new repo's page, click **Add file → Upload files**.
4. Drag in both files from this folder — `makerworld_posting_generator.py`
   and the whole `.github` folder (drag the folder itself; GitHub preserves
   the path) — then click **Commit changes**.

### Build the .exe

Pushing to the repo automatically starts a build. To get a permanent
download link:

1. On your repo page, click **Releases** (right-hand sidebar) → **Create a
   new release**.
2. Under "Choose a tag," type a new tag like `v1.0.0` and select **Create
   new tag on publish**.
3. Give it a title (anything) and click **Publish release**.
4. Click the **Actions** tab and watch the "Build Windows EXE" run — it
   takes about a minute or two. A green checkmark means it succeeded.
5. Go back to **Releases** — your `v1.0.0` release now has
   `MakerWorldPostingGenerator.exe` attached. Anyone can download it
   straight from that page, no Python or GitHub account required.

### Updating later

Whenever you edit `makerworld_posting_generator.py`, upload the new
version (or push via git), then repeat the "Create a new release" step
with a new tag (e.g. `v1.0.1`) to get a fresh .exe attached.

## Running it without building an .exe

You can also just run the Python file directly if you have Python 3
installed (get it from [python.org](https://python.org), checking "Add
python.exe to PATH" during install):

```
python makerworld_posting_generator.py
```

No extra packages are required — it only uses Python's standard library.

## Using the app

1. Click **Choose STL / 3MF file...** and pick your model.
2. Set material and infill % (used for the weight estimate).
3. Click **Analyze File + Generate Posting**.
4. Edit the Title / Description / Tags as needed.
5. Copy each field (or **Save Everything to .txt**) and paste into
   MakerWorld's own upload form. The **Open MakerWorld Upload Page**
   button opens that page for you.

### Notes on the estimates

- Weight is a rough estimate from mesh volume, your chosen infill %, and
  an assumed shell thickness — always double-check against your slicer.
- "Supports needed" is not auto-detected; check your slicer's preview.
- For 3MF files, embedded metadata (title/designer) is picked up
  automatically when present.
