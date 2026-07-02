# Demo video build

The README demo is assembled from **real headless VMD renders** — no mock frames.

## Pipeline

```
build_frames.py   ->  video/frames/*.png        (real VMD/Tachyon renders)
      |                 - 60 frames: sII crystal rotating, waters colored by cage
      |                 - 48 frames: an isolated 5^12 dodecahedron rotating
      v
remotion/         ->  out/demo.mp4              (composites frames + branded overlays)
      |
ffmpeg + gifsicle ->  ../docs/media/demo.gif    (compressed, README-embeddable)
```

## Rebuild

```bash
# 1. render the VMD frames (needs VMD; uses the tests/fixtures/hydrate_sII_222.gro sII example)
python video/build_frames.py            # or --quick for a fast preview

# 2. composite with Remotion
cd video/remotion
npm install
cp ../frames/*.png public/frames/
npm run mp4                              # -> out/demo.mp4
npm run gif                              # -> out/demo.gif (large; compress below)

# 3. compress the GIF for the README
ffmpeg -i out/demo.mp4 -vf "fps=15,scale=480:-1:flags=lanczos,palettegen=max_colors=192" /tmp/pal.png
ffmpeg -i out/demo.mp4 -i /tmp/pal.png -lavfi "fps=15,scale=480:-1:flags=lanczos,paletteuse" /tmp/raw.gif
gifsicle -O3 --lossy=80 /tmp/raw.gif -o ../../docs/media/demo.gif
cp out/demo.mp4 ../../docs/media/demo.mp4
```

`video/frames/`, `video/remotion/node_modules/`, `video/remotion/public/frames/`, and
`video/remotion/out/` are gitignored (regenerable). The committed artifacts are the source
(`build_frames.py`, `remotion/src/`) and the final `docs/media/demo.{gif,mp4}`.
