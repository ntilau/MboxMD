# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains a Python script that converts Google Takeout Mbox email exports to Markdown format, extracting attachments in the process. The script processes an Mbox file containing emails and generates a structured Markdown file with all messages and their attachments.

Key features include:
- Extraction of email metadata (From, To, Subject, Date)
- Processing of both plain text and HTML email bodies
- Saving attachments to a dedicated directory with safe filenames
- Automatic detection and removal of duplicate attachments based on MD5 hash
- Generation of a structured Markdown file with all messages and updated attachment references

## Common Commands

### Running the Conversion Script

To convert an Mbox file to Markdown and remove duplicate attachments:

```bash
python3 mbox_to_markdown.py
```

All three arguments are optional positional arguments:

```bash
python3 mbox_to_markdown.py [mbox_path] [output_dir] [limit]
```

`limit` converts only the first N messages, which is useful for spot-checking the
output format before committing to a full run over a multi-gigabyte mailbox.

The defaults (in `mbox_to_markdown.py`) are:

- Input: `/Users/ntilau/Downloads/Mail/All_mail_Including_Spam_and_Trash.mbox`
- Output directory: `/Users/ntilau/Downloads/Mail/mbox_markdown_output/`
- Markdown output: `/Users/ntilau/Downloads/Mail/mbox_markdown_output/mailbox.md`
- Attachments directory: `/Users/ntilau/Downloads/Mail/mbox_markdown_output/attachments/`

### One Run at a Time

The script takes an exclusive lock (`<output_dir>/.mbox_to_markdown.lock`) and
refuses to start if another conversion is already writing to the same output
directory. This matters: each run deletes the duplicate attachments *it* found,
so two concurrent runs remove files the other run's markdown still links to,
leaving `mailbox.md` full of dead attachment links. A lock left behind by a
killed run is reclaimed automatically once its pid is gone; the error message
says which file to delete if a lock ever needs removing by hand.

Every run ends by verifying that all attachment links in `mailbox.md` resolve —
look for `All attachment links resolve.` (a `WARNING:` line instead means the
markdown and the attachments directory disagree).

## Code Structure

### Main Components

1. **mbox_to_markdown.py** - The primary conversion script
   - Reads an Mbox file using Python's `mailbox` module
   - Extracts email metadata (From, To, Subject, Date)
   - Processes both plain text and HTML email bodies
   - Saves attachments to a dedicated directory with safe filenames
   - Detects and removes duplicate attachments based on MD5 hash
   - Updates attachment references in the output Markdown file
   - Generates a structured Markdown file with all messages

2. **Output Directory Structure** (not tracked by git, can be regenerated)
   - `mailbox.md` - Combined Markdown file containing all emails with updated attachment references
     - Opens with `# Mailbox Export`, `Total messages: N` and the date range
     - Then a `## Index` of one line per message: `- [Message N](#message-N) — YYYY-MM-DD — Sender — Subject`
     - Then one `## Message N` section per email, with `**From:**` / `**To:**` / `**Subject:**` /
       `**Date:**` fields, an optional `**Attachments:**` list, and the body fenced by `---`
   - `attachments/` - Directory containing all extracted attachments (duplicates removed)
     - Files are safely renamed to avoid filesystem conflicts
     - Duplicate filenames are handled with numerical suffixes during initial save
     - After deduplication, only one copy of each unique attachment remains
   - `.mbox_to_markdown.lock` - Present only while a conversion is running

### Key Functions

- `decode_mime_words(s)` - Decodes MIME-encoded header strings
- `clean_text(text)` - Normalises whitespace while preserving paragraph breaks
- `get_plain_text_part(message)` / `get_html_part(message)` - Extract body parts
- `strip_markup_noise(text)` - Removes leaked CSS, VML/Outlook markup and comments,
  including a line that begins with stylesheet syntax even when the lines around it
  are prose (mail clients wrap declarations mid-value, leaving lone fragments)
- `looks_like_leaked_markup(text, stripped)` - Decides whether a `text/plain` part is
  really markup and the HTML part should be used instead
- `strip_invisible_padding(text)` - Drops invisible padding characters, and lines that
  were nothing but padding. Characters that carry meaning survive where real text uses
  them: the ZWNJ in Persian words, the ZWJ in emoji sequences, LRM/RLM in bidi text.
  The decision is made per character from its neighbours, so the same character is
  dropped as filler next to a space, a digit or another mark (`servizio <ZWNJ> <ZWNJ>`,
  `3<ZWJ>1<ZWJ> dicembre`) and kept between two ordinary characters
- `html_to_text(html_content)` - Basic HTML-to-text conversion
- `sanitize_body(body)` - Escapes characters that would break Markdown structure
  (leading `#`, `|`, fences, setext-underline lines, stray `<`) while keeping autolinks
- `safe_filename(filename)` - Creates filesystem-safe filenames
- `attachment_link(filename)` - Percent-encodes an attachment name for a link destination
- `acquire_lock(output_dir)` - Refuses to start when another run owns the output directory
- `verify_attachment_links(md_file, output_dir)` - Reports links whose target file is missing
- `main()` - Orchestrates conversion, deduplication, reference updates and verification

### Body Selection

Gmail's generated `text/plain` parts frequently contain raw CSS stylesheets and even
raw Outlook/VML markup rather than readable text. `build_body()` strips markup noise
from the plain-text part first and only falls back to the HTML part when the plain
text is missing or still looks like leaked markup after cleaning.

## Development Workflow

### Typical Usage

1. Put the Mbox file somewhere on disk (the default path is the repository's mailbox)
2. Run the conversion: `python3 mbox_to_markdown.py [mbox_path] [output_dir] [limit]`
3. The script will:
   - Process all emails in the Mbox file
   - Extract attachments and save them to the attachments directory
   - Detect and remove duplicate attachments (based on MD5 hash)
   - Update all attachment references in mailbox.md to point to the kept files
   - Verify that every remaining attachment link resolves
   - Generate the final markdown output
4. Find the output in the `mbox_markdown_output/` directory
   - Read emails in `mailbox.md`
   - Access attachments in the `attachments/` subdirectory
5. Spot-check a run cheaply with a limit first, e.g. `python3 mbox_to_markdown.py All_mail_Including_Spam_and_Trash.mbox /tmp/md_check 500`

### Customization

To modify the conversion behavior:

- Adjust the body extraction logic in `get_plain_text_part()` or `get_html_part()`
- Modify the attachment handling in the main loop
- Change the Markdown formatting in the output generation section
- Enhance the HTML-to-text conversion if better formatting is needed
- Modify the deduplication logic (currently keeps first-encountered file as original)

## GitHub Repository

This repository is hosted on GitHub at: https://github.com/ntilau/MboxMD

Repository details:
- Private repository
- Topics: email, mbox, markdown, python, google-takeout
- Contains the conversion script, documentation, and .gitignore
- Large files (mbox input and output directory) are intentionally not tracked

## Notes

- The script handles basic HTML-to-text conversion for emails without plain text bodies
- Attachment filenames are sanitized to remove unsafe characters
- Attachment link destinations are percent-encoded, since Markdown link targets cannot
  contain spaces or most non-ASCII characters
- Duplicate attachment filenames are automatically resolved with numerical suffixes during initial save
- After processing, the script identifies and removes duplicate attachments based on identical MD5 hash content
- Frame the run with a single process: concurrent runs over one output directory corrupt each other
- The Mbox file itself is gitignored due to its large size (can be regenerated from Google Takeout)
- Output files (Markdown and attachments) are gitignored as they can be regenerated by running the script
- Only the script, documentation, and .gitignore are tracked in the repository
- To regenerate output after cloning: place your Mbox file in the directory and run `python3 mbox_to_markdown.py`