---
name: valpulse-tech-dashboard
description: "Build ValPulse tech-terminal design and sync email."
version: 0.1.0
author: Shreker, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [valpulse, dashboard, html-design, email-sync, tech-terminal]
    related_skills: [hermes-agent-skill-authoring]
---

# ValPulse Tech Dashboard

Rebuild `reports/index.html` and sync `src/push.py` email HTML to a shared tech-terminal design.

## When to Use

- Redesign ValPulse `reports/index.html` with modern/high-contrast terminal-style UI
- Sync email (`push.py`) with web design (same colors/fonts/spacing)
- Create comparison variants (glass/neon/tech) before finalizing
- Resolve `data/valuation.db` git conflicts with remote (`git checkout origin/main --`)

Don't use for: generic web design, non-ValPulse dashboards.

## Design System (Always-On)

User selected tech-terminal over glass/neon. Lock these rules:

- Background: `#060b14`; Card: `#0d1115`; Accent: `#00d4aa` (cyan)
- Text: `#e6f0fa` (primary), `#8899aa` (secondary)
- Font: `"JetBrains Mono", "Noto Sans CJK SC", sans-serif`
- Section headings (`h2`): `text-align:center; letter-spacing:4px; border-bottom:3px solid var(--accent); font-size:20px`
- Temperature value: `42px`, `font-weight:900`, cyan glow shadow
- Footer: `font-family:"JetBrains Mono"`, `font-size:12px`, `#8899aa`
- Notice: `background:rgba(0,255,204,.08); border:2px solid rgba(0,255,204,.3)`

## Procedure

### 1. Verify File State
Before changing anything, confirm whether `reports/index.html` is original or redesigned. Check line 10-12 of CSS (`--bg:#f5f6f8` = original; `--bg:#060b14` = redesigned).

### 2. Apply Design Changes
Use `patch` or targeted Python `replace` (more reliable than full rewrite for existing large files). Key replacements:
- CSS `:root` variables → tech theme colors
- `body` font → `"JetBrains Mono"...`
- `section h2` → centered + letter-spacing
- `.tempbar .t` → `42px` + cyan glow
- `.card .fund` → `15px` + bold white
- `table` → `12px` bright text
- `.toolbar .grp button.on` → accent background
- Responsive `@media`: `.cards{grid-template-columns:1fr}` for mobile

Always verify after write: `read_file(..., limit=10)` to confirm `--bg:#060b14`, not `#f5f6f8`.

### 3. Create Variants (Optional)
Copy `index.html` to `index_glass.html`, `index_neon.html`, `index_tech.html`. Modify CSS per variant:
- Glass: `rgba(255,255,255,.06)` cards, `backdrop-filter:blur(12px)`, gradient glow
- Neon: `#0f0518` bg, `Orbitron` font, gradient borders, neon shadows
Keep `index.html` as the selected working copy.

### 4. Sync Email (`push.py`)
The email HTML (`build_summary()` in `src/push.py`) must share the same design. Replace inline styles:
- Body: `font-family:"JetBrains Mono"...; color:#e6f0fa; background:#060b14`
- `<h3>` headings: centered, `font-size:20px`, `#00d4aa`, `letter-spacing:4px`
- Tables: `border-color:#1a2a3a; font-size:12px; background:#0d1115; color:#d0e0f0`
- Temperature values: `color:#00d4aa` (not `#1565c0`)
- Footer notes: `font-family:"JetBrains Mono"`, `#8899aa`

Never leave email with `font-family:sans-serif; color:#333; background:#fff` when web uses dark tech theme.

### 5. Verify Sync
After editing both files, confirm design alignment:
- `reports/index.html` line 29: `text-align:center`
- `src/push.py` line 142: `<h3>` contains `text-align:center`
- Both have `font-family` referencing `JetBrains Mono`

### 6. Local Test Server
Create/update `serve.py` with absolute `ROOT` (not relative `__file__`):
```python
ROOT = pathlib.Path(__file__).resolve().parent / "reports"
```
Run `python serve.py`, access `http://localhost:8080/index.html`. Confirm CSS renders.

### 7. Git Conflict (If Needed)
For `data/valuation.db` conflicts (remote GitHub Actions updated db, local has uncommitted code):
```bash
git checkout origin/main -- data/valuation.db
git add .
git commit -m "sync: update db from remote; preserve local code changes"
git push origin main
```
Never `git reset --hard` when local uncommitted code exists.

## Pitfalls

1. Writing to `reports/index.html` without reading first → working on original light theme (`--bg:#f5f6f8`). Verify line 10-12.
2. `serve.py` using relative `__file__` → resolves to working directory. Fix: `resolve().parent / "reports"`.
3. `push.py` diverging from web → inconsistent user experience. Always verify both files after redesign.
4. Not confirming style preference → user may prefer glass/neon over tech. Offer variants (`index_glass.html`, `index_neon.html`) before finalizing.
5. Changing font sizes without responsive rules → overflow on mobile. Add `@media (max-width:600px)` rules.
6. Accessing `/reports/index.html` instead of `/index.html` with server → 404. Confirm `serve.py` root and URL.

## Verification Checklist

- `reports/index.html` line 10: `--bg:#060b14` (or selected theme bg)
- `reports/index.html` line 29: `section h2` has `text-align:center; letter-spacing:4px`
- `reports/index.html` line 34: `.tempbar .t` has `font-size:42px`
- `reports/index.html` line 101: body has `font-family:"JetBrains Mono"`
- `reports/index_tech.html` preserved (tech variant)
- `src/push.py`: body style has `font-family:"JetBrains Mono"` + `background:#060b14`
- `src/push.py`: `<h3>` headings have `text-align:center`
- `serve.py`: `ROOT` uses absolute path
- `git status`: `reports/index.html` modified, no unexpected deletions

## References

- `references/design-system.md` — tech terminal color/font/spacing reference
- `reports/index_glass.html`, `reports/index_neon.html`, `reports/index_tech.html` — comparison variants
- `serve.py` — local test server script
- `src/push.py` — email HTML builder (must sync with web design)
