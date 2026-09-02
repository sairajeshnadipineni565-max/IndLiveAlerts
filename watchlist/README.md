# Daily watchlist

Upload one JSON file here each morning before market open (9:15 AM IST),
named for **today's date in IST**: `YYYY-MM-DD.json`.

The scanners look up `watchlist/<today's IST date>.json` on every poll
(every 60s during market hours), so if you fix a typo mid-session and
re-upload, it takes effect on the next poll -- no restart needed.

## Format

```json
{
  "NSE:RELIANCE-EQ": {
    "resistance": 2950,
    "support": 2870,
    "pivot_level": null,
    "setup": "VCP breakout",
    "description": "3-week tight base, watching for volume breakout above 2950"
  },
  "NSE:HDFCBANK-EQ": {"resistance": null, "support": null, "pivot_level": null}
}
```

- **Symbol keys must be in Fyers' format**: `NSE:<SYMBOL>-EQ` (e.g.
  `NSE:RELIANCE-EQ`, `NSE:TCS-EQ`) -- not the plain ticker. This is what
  Fyers' historical-data API expects; the scanners pass the key straight
  through without translating it.
- `resistance` / `support` / `pivot_level` are all optional -- use `null`
  (not the string `"null"`) for any you don't have yet.
- A symbol with all three set to `null` is still watched: it just won't
  trigger the breakout / undercut-rally / 30-min-pivot / pivot-cross
  setups, which need a level. The RVOL+9EMA and extreme-volume alerts have
  no level requirement and still fire for it.
- `setup` and `description` are optional (leave them out, or set to `""`,
  if you don't want them). Whatever you put here is appended to every
  Telegram alert for that symbol that day:
  ```
  • Setup: VCP breakout
  • Note: 3-week tight base
  ```

Sample file: `2026-08-31.json` in this folder -- copy its structure for
each new day.
