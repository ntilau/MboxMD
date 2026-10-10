# Mbox to Markdown Converter

This project contains a Python script that converts Google Takeout Mbox email exports to Markdown format, automatically extracting attachments and removing duplicate files based on MD5 hash comparison.

## Overview

The script processes an Mbox file containing emails and generates:
- A structured Markdown file (`mailbox.md`) with all emails
- An attachments directory with all unique attachments (duplicates removed)

## Main Output

After running the conversion script, the primary result can be found at:
```
mbox_markdown_output/mailbox.md
```

This file contains all emails in Markdown format, with each email formatted as:
- Email metadata (From, To, Subject, Date)
- Email body (plain text or converted from HTML)
- List of attachments (with links to the actual files)

## Attachments

All extracted attachments are saved in:
```
mbox_markdown_output/attachments/
```

The script automatically:
- Detects and removes duplicate attachments based on identical MD5 hash content
- Updates all references in `mailbox.md` to point to the kept files
- Sanitizes filenames to be filesystem-safe
- Handles naming conflicts by adding numerical suffixes

## Usage

### Prerequisites
- Python 3.x
- Google Takeout Mbox export file

### Steps
1. Place your Mbox file in this repository directory (or update the path in the script)
2. Ensure the script is configured to point to your Mbox file:
   ```python
   mbox_path = '/path/to/your/mailbox.mbox'
   output_dir = '/path/to/output/directory'
   ```
3. Run the conversion script:
   ```bash
   python3 mbox_to_markdown.py
   ```
4. Find your results in the `mbox_markdown_output/` directory:
   - **Main output**: `mbox_markdown_output/mailbox.md`
   - **Attachments**: `mbox_markdown_output/attachments/`

## Features

- ✅ Converts Mbox to well-formatted Markdown
- ✅ Extracts and saves all attachments
- ✅ Removes duplicate attachments (MD5-based)
- ✅ Updates attachment references in the Markdown file
- ✅ Handles both plain text and HTML email bodies
- ✅ Sanitizes attachment filenames for filesystem safety
- ✅ Preserves email metadata (From, To, Subject, Date)

## Output Structure

After running the script:
```
mbox_markdown_output/
├── mailbox.md          # Main output - all emails in Markdown format
└── attachments/
    ├── attachment1.pdf
    ├── attachment2.jpg
    └── ...             # All unique attachments (duplicates removed)
```

## Notes

- The original Mbox file is not modified
- Duplicate attachments are identified by identical content (MD5 hash)
- When duplicates are found, only the first encountered file is kept
- All references in `mailbox.md` point to the kept attachment files
- Large files (Mbox input and output directory) are intentionally not tracked by Git
- To regenerate output after cloning: place your Mbox file in the directory and run the script

## Example

After processing, an email with attachments will appear in `mailbox.md` as:

```markdown
## Message 42

**From:** sender@example.com
**To:** recipient@example.com
**Subject:** Meeting Notes
**Date:** 2023-05-15 14:30:00 UTC

---

Here are the meeting notes from our team discussion.


**Attachments:**
- [meeting_notes.pdf](./attachments/meeting_notes.pdf)
- [presentation_slides.pptx](./attachments/presentation_slides.pptx)
```

## Customization

To modify the conversion behavior, edit `mbox_to_markdown.py`:
- Adjust body extraction in `get_plain_text_part()` or `get_html_part()`
- Change attachment handling logic
- Modify Markdown formatting in the output generation section
- Update deduplication logic (currently keeps first-encountered file as original)

---

*Generated emails are presented in chronological order as they appear in the Mbox file.*