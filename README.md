# HSV Color Detector

A desktop tool for working out HSV thresholds that isolate a colored target in video (for example, a paint-marked animal), and for checking how well those thresholds hold up across the whole recording.

You click on the target to sample its color, drag threshold lines on three HSV scatter plots until only the target survives, then use the mask view, per-frame stats, seeker markers and frame search to find the frames where detection fails. The finished thresholds are saved as a small JSON file.

## Install

You need Python 3.10 or newer and Git. The commands below are for Windows PowerShell; macOS and Linux differences are noted at the end of this section.

```powershell
git clone https://github.com/soulsynapse/antscihub_color_detector_v2.git
cd antscihub_color_detector_v2
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This puts every dependency (NumPy, OpenCV, PyQt6) inside the `.venv` folder in the project, so nothing is installed system-wide and deleting `.venv` undoes the install. `.venv` is already git-ignored.

Check that it worked:

```powershell
.\.venv\Scripts\python.exe -c "import sys, numpy, cv2, PyQt6; print(sys.executable)"
```

It should print a path ending in `.venv\Scripts\python.exe` with no errors.

If you use VS Code, open the folder (`code .`), press `Ctrl+Shift+P`, choose **Python: Select Interpreter**, and pick `.venv\Scripts\python.exe`. After that, new VS Code terminals use the environment automatically and plain `python` works.

**macOS / Linux:** use `python3 -m venv .venv`, and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` everywhere.

## Run

```powershell
.\.venv\Scripts\python.exe main.py
```

Then **File → Open Video** (`.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`).

## Update

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Typical workflow

1. Open a video and scrub to a frame where the target is clearly visible.
2. Click the target a few times, on different frames and under different lighting. Each click samples an 11×11 pixel patch.
3. On the **Color Isolation** tab, drag the dashed lines on the three scatter plots so the box encloses the target's cluster of points.
4. Hold `Shift` (or press **Show Mask**) to see what the thresholds keep.
5. Raise **Min area** to drop specks, and raise **Merge dist** if one target is being split into several detections.
6. Turn on the seeker markers to see where in the video detection fails, and step through those frames to refine.
7. **Save Settings**.

## Features

### Video panel (left)

**Color picking.** Clicking the video adds every pixel in the 11×11 patch around the click (up to 121 samples) to the picked colors. The bar under the video shows the clicked pixel's position and its RGB, HSV and YCrCb values.

**Native-resolution view.** The video is drawn at 1:1 pixel scale, not shrunk to fit, so the pixel you click is the pixel you sample. When the frame is larger than the panel, a small overview appears in the top-left corner with a highlighted rectangle showing the visible region; click or drag in the overview to pan.

**Scrubber.** Drag to seek. The current time is on the left and the total duration on the right.

**Frame back / frame advance.** The `<<` and `>>` buttons move exactly one frame backward or forward. The frame counter beside them shows the current and last frame index (frames are counted from 0).

**Play / Pause.** The **Play** button or `Space` plays at the video's own frame rate.

**Mask.** **Show Mask** toggles the detection view: pixels inside the HSV thresholds keep their full color, everything else is dimmed to 20% brightness, and each detection that survives Min area and Merge dist is outlined in green. The view updates live as you change thresholds. Holding `Shift` shows the mask temporarily and returns to the original on release. With no thresholds set, the mask view is identical to the original.

**Seeker markers.** Two toggle buttons under the scrubber draw tick marks on the scrubber itself:

| Button | Tick color | Marks frames with |
| --- | --- | --- |
| **0 detections** | red | no detection (the target was lost) |
| **2+ detections** | amber | two or more detections (likely false positives, or a split target) |

Turning either on scans every frame of the video in the background, so it can take a while on long recordings; the label on the right shows progress and then the number of frames in each category. Markers are recomputed automatically whenever the thresholds, Min area or Merge dist change, so they always describe the current settings.

### Color Isolation tab (right)

**HSV scatter plots.** Three plots (H vs S, H vs V, S vs V) show every picked color as a dot drawn in its own color. Each plot has four dashed lines, the low and high threshold on each axis; drag them to move the thresholds. The three plots share one set of thresholds, so moving H on one plot moves it on the other. The counter in each plot's corner is in-bounds / total picked colors. Values use OpenCV's scale: H is 0–179, S and V are 0–255.

A channel left at its full range is not used as a constraint.

**Wrapped hue (reds).** Hue is circular, and red sits at both ends of the scale (near 0 and near 179). To select it, drag one H line past the other: the range inverts, so the two outer strips are selected and the middle is excluded, and the plot title shows `[H WRAPS]`. Drag the line back across to return to a normal range. S and V do not wrap; their lines stop at each other. In a settings file a wrapped range is stored with the low value above the high one, for example `"H": [170, 12]`.

**Shift.** Holding `Shift` hides the out-of-bounds dots on the plots and shows the mask on the video at the same time.

**Min area (px).** The smallest detection to keep. Each connected blob of in-threshold pixels is one candidate, and a blob is kept only if its area is strictly greater than this value, so the default of 1 already discards single-pixel noise. The spinbox goes to 50,000; the slider covers 1–5,000.

**Merge dist (px).** Combines nearby detections into one. Two detections are merged when the centers of their bounding boxes are closer than this distance, and merging chains: if A is close to B and B is close to C, all three become one detection even when A and C are far apart. Min area is applied again after merging. 0 disables merging. The spinbox goes to 1,000; the slider covers 0–500.

**Detection stats.** The box at the bottom of Refinement Tools describes the current frame and updates as you scrub or change settings:

- the frame index and the number of detections
- the number of pixels inside the thresholds and the share of the frame they cover
- the merge distance, when merging is on
- the areas of the eight largest detections, in px²

It stays blank until at least one threshold has been moved.

**Find frames by detection count.** Jumps to a frame with 0, exactly 1, exactly 2, or 5+ detections, or to the frame with the most detections. **Find next** repeats the last search from the current frame. The search checks about 200 evenly spaced frames, not every frame, so it is fast but can miss short events; use the seeker markers when you need every frame checked.

**Bottom bar.**

| Button | What it does |
| --- | --- |
| **Save Settings** | Writes thresholds, Min area, Merge dist and the picked colors to a JSON file. |
| **Load Settings** | Restores all of those from a JSON file. This replaces the current thresholds and picked colors. |
| **Clear Excluded** | Removes the picked colors that fall outside the current thresholds. |
| **Clear All** | Removes every picked color. Thresholds are not changed. |

### Full Video Analysis tab (right)

**Run Full Analysis** processes the video with the current thresholds, Min area and Merge dist, so its counts agree with the stats, markers and frame search on the Color Isolation tab. The **Analyze** buttons choose whether to process every frame or only every 2nd, 10th or 100th, which is much faster on long recordings; percentages and averages are then taken over the frames that were analyzed. It reports:

- a summary: frames analyzed, frames with a detection, total detections, mean and median detection size, mean circularity
- a detection timeline (green where at least one detection was present)
- detections per frame
- a detection size histogram and a circularity histogram, each with draggable bounds that report how many detections fall inside
- a heatmap of where in the frame the thresholds matched over the whole video

**Cancel** stops a run in progress.

### Keyboard

| Key | Action |
| --- | --- |
| `Space` | Play / pause |
| `Shift` (hold) | Show the mask and hide out-of-bounds colors |

## Settings file

```json
{
  "version": 1,
  "bounds": { "H": [67, 102], "S": [154, 255], "V": [83, 166] },
  "min_area": 1,
  "merge_distance": 0,
  "colors": [ { "BGR": [10, 200, 30], "H": 63, "S": 242, "V": 200 } ]
}
```

`bounds` holds the low and high threshold for each channel, on OpenCV's scale. `colors` is the list of picked samples and is only needed to redraw the scatter plots; another program that just wants to reproduce the detection needs `bounds`, `min_area` and `merge_distance`.

## Known limitations

- **Areas of merged detections are approximate.** A merged detection is the combined outline points of its parts, not a filled shape, so the area shown for it is not the sum of the parts.

## Project layout

```
main.py             entry point
core/               color store, mask building, contour filtering, video access
gui/                windows, tabs and widgets
requirements.txt    dependencies
color_settings.json example settings file
```
