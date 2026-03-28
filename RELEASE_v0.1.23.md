## PO Builder `v0.1.23`

Release date: 2026-03-28

This is a parser compatibility hotfix for slash-bearing X4 line codes.

### Highlights

- Fixed parsing for line codes such as `B/B-` and `C/W-`.
- The fix applies across generic CSV parsing and X4-style combined-code parsing.
- Rebuilt the packaged executable with the parser fix.

### Hotfix details

- Updated line-code validation so slash-bearing three-character fragments are treated as valid X4 line codes.
- Updated line-code column detection so rows containing values like `B/B-` and `C/W-` are recognized instead of being skipped.
- Updated combined detailed-sales token splitting so values like `B/B-00055062` are split into:
  - line code `B/B-`
  - item code `00055062`
- Added parser regression coverage for:
  - generic pack-size parsing with slash line codes
  - generic part-sales parsing with slash line codes
  - X4 detailed-sales parsing with slash line-code fragments
  - X4 received-parts parsing with slash line codes

### Validation

- `C:\Users\Cornelio\Desktop\POCreator\.venv\Scripts\python.exe -m unittest discover -s tests -q`
- `C:\Users\Cornelio\Desktop\POCreator\.venv\Scripts\python.exe -m PyInstaller -y PO_Builder.spec`
- Confirmed `dist\POBuilder.exe` was rebuilt successfully.
