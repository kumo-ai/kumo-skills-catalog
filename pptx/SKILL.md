---
name: pptx
metadata:
  version: "1.0.0"
description: Create, edit, or read .pptx PowerPoint files using PptxGenJS. Use when the user asks for a presentation, slide deck, or mentions a .pptx file. Includes the full authoring workflow with visual QA.
allowed-tools: Bash Read Write Edit Glob Grep Agent
---

# PPTX Skill

Create polished PowerPoint presentations from scratch using PptxGenJS. Includes a full QA loop with visual verification.

---

## One-Time Setup (check first, install only if missing)

```bash
# Check if pptxgenjs is available
NODE_PATH=$(npm root -g) node -e "require('pptxgenjs')" 2>/dev/null \
  && echo "OK" || npm install -g pptxgenjs

# Check if libreoffice is available (needed for PDF conversion / visual QA)
which libreoffice || sudo apt-get install -y libreoffice

# Check if pdftoppm is available (needed for slide-to-image rendering)
which pdftoppm || sudo apt-get install -y poppler-utils
```

---

## Recommended Permissions

Add these to `~/.claude/settings.json` (or `.claude/settings.json` for project scope) to
avoid approval prompts for every command this skill runs:

```json
{
  "permissions": {
    "allow": [
      "Bash(NODE_PATH=* node *.cjs)",
      "Bash(npm root -g)",
      "Bash(npm install -g pptxgenjs)",
      "Bash(libreoffice --headless --convert-to pdf *)",
      "Bash(pdftoppm *)",
      "Bash(cp *.js *.cjs)"
    ]
  }
}
```

These are scoped to the exact commands used in the workflow — no broad wildcards.

---

## Workflow

### 1. Write the generation script

Write a `.cjs` file (not `.js`) — the working directory may have `"type": "module"` in its
`package.json`, which breaks `require()`. Using `.cjs` forces CommonJS mode regardless.

```javascript
// my-deck.cjs
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";

// ... build slides ...

pres.writeFile({ fileName: "output.pptx" })
  .then(() => console.log("✅ output.pptx written"))
  .catch((e) => { console.error(e); process.exit(1); });
```

### 2. Run the script

`pptxgenjs` is installed globally, so use `NODE_PATH` to resolve it:

```bash
NODE_PATH=$(npm root -g) node my-deck.cjs
```

### 3. Visual QA

Convert to images and inspect with a subagent:

```bash
# PDF conversion (use libreoffice directly — soffice may not be in PATH)
libreoffice --headless --convert-to pdf output.pptx --outdir .

# Render to JPEG (150 dpi is fast; use 200 for final review)
pdftoppm -jpeg -r 150 output.pdf slide_qa

# Re-render a specific slide after a fix
pdftoppm -jpeg -r 150 -f 3 -l 3 output.pdf slide_fix
```

Inspect with a subagent (fresh eyes catch what you miss):

```
Visually inspect these slides. Assume there are issues — find them.

Look for:
- Overlapping elements or text cut off at edges
- Double bullets (unicode • AND bullet:true combined)
- Low-contrast text on matching backgrounds
- Elements overflowing the slide boundary (16x9 = 10" × 5.625")
- Cramped gaps (< 0.3") or uneven spacing

Read images: /path/to/slide_qa-01.jpg, slide_qa-02.jpg, ...
Report ALL issues, including minor ones.
```

Fix issues, re-render affected slides, and verify again. **Do not declare done until
at least one fix-and-verify cycle has been completed.**

---

## PptxGenJS Reference

### Setup

```javascript
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";  // 10" × 5.625"
pres.title = "My Presentation";
```

### Text

```javascript
slide.addText("Hello", {
  x: 0.5, y: 0.5, w: 9, h: 1,
  fontSize: 36, bold: true, color: "1E293B",
  align: "left", valign: "middle",
  margin: 0,  // set to 0 when aligning with shapes
});

// Rich text / multi-line
slide.addText([
  { text: "Bold part", options: { bold: true, breakLine: true } },
  { text: "Normal part" },
], { x: 0.5, y: 1.5, w: 9, h: 1, fontSize: 14, color: "334155" });

// Letter spacing
slide.addText("LABEL", { charSpacing: 6, fontSize: 9 });
```

### Bullets

```javascript
// ✅ CORRECT — no unicode • in the text string
slide.addText([
  { text: "First item", options: { bullet: true, breakLine: true } },
  { text: "Second item", options: { bullet: true } },
], { x: 0.5, y: 1, w: 8, h: 2, fontSize: 14 });

// ❌ WRONG — creates double bullets
slide.addText("• First item", { bullet: true });
```

### Shapes

```javascript
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.5, y: 0.5, w: 4, h: 1,
  fill: { color: "0891B2" },
  line: { color: "0891B2" },
  shadow: { type: "outer", blur: 8, offset: 3, angle: 135,
            color: "000000", opacity: 0.12 },
});

// IMPORTANT: never reuse a shadow object — PptxGenJS mutates it in-place
const makeShadow = () => ({ type: "outer", blur: 8, offset: 3,
                            angle: 135, color: "000000", opacity: 0.12 });
slide.addShape(pres.shapes.RECTANGLE, { shadow: makeShadow(), ... });
slide.addShape(pres.shapes.RECTANGLE, { shadow: makeShadow(), ... });

// Line
slide.addShape(pres.shapes.LINE, {
  x: 0.5, y: 2, w: 9, h: 0,
  line: { color: "E2E8F0", width: 1 },
});
```

### Backgrounds & images

```javascript
slide.background = { color: "021428" };

slide.addImage({ path: "logo.png", x: 1, y: 1, w: 3, h: 2 });
```

### Tables

```javascript
slide.addTable([
  [{ text: "Header", options: { fill: { color: "1C3557" }, color: "FFFFFF",
     bold: true, fontSize: 9, margin: [3,5,3,5] } }, ...],
  [{ text: "Row 1", options: { fill: { color: "F1F5F9" }, fontSize: 8.5,
     margin: [3,5,3,5] } }, ...],
], {
  x: 0.25, y: 1, w: 9.5, rowH: 0.34,
  border: { pt: 0.5, color: "E2E8F0" },
  colW: [2, 2, 3, 2.5],
});
```

### Charts

```javascript
slide.addChart(pres.charts.BAR, [{
  name: "Series", labels: ["Q1","Q2","Q3"], values: [10,20,15],
}], {
  x: 0.5, y: 1, w: 9, h: 4, barDir: "col",
  chartColors: ["0891B2"], chartArea: { fill: { color: "FFFFFF" } },
  catAxisLabelColor: "64748B", valAxisLabelColor: "64748B",
  valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" },
  showValue: true, showLegend: false,
});
```

---

## Common Pitfalls

| # | Wrong | Right |
|---|-------|-------|
| 1 | `color: "#FF0000"` | `color: "FF0000"` (no `#`) |
| 2 | `shadow: { color: "00000020" }` | `shadow: { color: "000000", opacity: 0.12 }` |
| 3 | `"• Item"` + `bullet: true` | `"Item"` + `bullet: true` |
| 4 | Reusing a shadow object | `makeShadow()` factory function |
| 5 | `.js` file in ES-module repo | `.cjs` extension to force CommonJS |
| 6 | `node script.cjs` (pptxgenjs not found) | `NODE_PATH=$(npm root -g) node script.cjs` |
| 7 | `soffice` not in PATH | `libreoffice --headless --convert-to pdf ...` |
| 8 | Elements at y > 5.625" | Stay within slide bounds (10" × 5.625") |

---

## Design Principles

- **Pick a palette for the topic** — don't default to generic blue
- **Dark/light sandwich** — dark title + conclusion, light content slides
- **One visual motif** — repeat one shape style / accent treatment throughout
- **Never accent lines under titles** — hallmark of AI-generated slides
- **Every slide needs a visual element** — shape, icon, chart, or image
- **Left-align body text** — center only titles and large callout numbers
- **Shadow every floating card** — `{ type:"outer", blur:8, offset:3, opacity:0.12 }`
- **0.5" minimum margins** from slide edges; 0.3–0.5" between blocks

---

## Suggested Color Palettes

| Theme | Primary | Accent | Background |
|-------|---------|--------|------------|
| Midnight Executive | `1E2761` | `FFFFFF` | `CADCFC` |
| Ocean Gradient | `065A82` | `21295C` | `1C7293` |
| Charcoal Minimal | `36454F` | `212121` | `F2F2F2` |
| Teal Trust | `028090` | `02C39A` | `00A896` |
| Cherry Bold | `990011` | `2F3C7E` | `FCF6F5` |
