#!/usr/bin/env python3
"""
Convert an mbox file to markdown format with attachments extracted.

Usage:
    python3 mbox_to_markdown.py [mbox_path] [output_dir] [limit]

Both arguments are optional; the defaults point at this repository's mailbox.
`limit` converts only the first N messages, which is handy for spot-checking
the output format before running the full mailbox.
"""

import atexit
import mailbox
import os
import sys
import re
import html
import hashlib
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
from urllib.parse import quote, unquote

DEFAULT_MBOX_PATH = '/Users/ntilau/Downloads/Mail/All_mail_Including_Spam_and_Trash.mbox'
DEFAULT_OUTPUT_DIR = '/Users/ntilau/Downloads/Mail/mbox_markdown_output'

# ---------------------------------------------------------------------------
# Header / body decoding
# ---------------------------------------------------------------------------

def decode_mime_words(s):
    """Decode MIME words in a header string."""
    if s is None:
        return ''
    decoded_parts = decode_header(s)
    decoded_string = ''
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            if encoding:
                try:
                    decoded_string += part.decode(encoding)
                except LookupError:
                    # Fallback for unknown encodings
                    decoded_string += part.decode('utf-8', errors='replace')
            else:
                decoded_string += part.decode('utf-8', errors='replace')
        else:
            decoded_string += part
    return decoded_string

def clean_text(text):
    """Apply common text cleaning: decode entities, normalize whitespace, keep paragraph breaks."""
    if not text:
        return ""

    # Decode HTML entities
    text = html.unescape(text)

    # Convert non-breaking spaces to regular spaces
    text = text.replace('\xa0', ' ')

    # Strip trailing whitespace from each line; blank lines are kept because they
    # separate paragraphs in the rendered markdown.
    text = '\n'.join(line.strip() for line in text.split('\n'))

    # Collapse runs of blank lines down to a single blank line
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def get_plain_text_part(message):
    """Extract plain text from an email message."""
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    text = payload.decode(charset, errors='replace')
                    # Apply text cleaning
                    return clean_text(text)
                except Exception:
                    continue
    else:
        if message.get_content_type() == 'text/plain':
            try:
                payload = message.get_payload(decode=True)
                charset = message.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='replace')
                # Apply text cleaning
                return clean_text(text)
            except Exception:
                pass
    return None

def get_html_part(message):
    """Extract HTML from an email message."""
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if content_type == 'text/html' and 'attachment' not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')
                except Exception:
                    continue
    else:
        if message.get_content_type() == 'text/html':
            try:
                payload = message.get_payload(decode=True)
                charset = message.get_content_charset() or 'utf-8'
                return payload.decode(charset, errors='replace')
            except Exception:
                pass
    return None

# ---------------------------------------------------------------------------
# Markup noise removal (Gmail's generated text/plain often leaks CSS/HTML)
# ---------------------------------------------------------------------------

# HTML tags we are willing to strip. The list is deliberately explicit: matching
# any "<word ...>" would also destroy the "<https://...>" autolinks that Gmail
# puts in plain-text bodies, which we want to keep as clickable links. The VML
# names (v:, o:, roundrect, ...) come from Outlook markup.
_TAG_NAMES = (
    r'html|head|body|meta|link|title|style|script|div|span|table|thead|tbody'
    r'|tfoot|tr|td|th|caption|colgroup|col|p|br|hr|img|a|font|b|i|u|s|strike|strong'
    r'|em|ul|ol|li|dl|dt|dd|h[1-6]|center|blockquote|pre|code|small|big|sub|sup'
    r'|o:|v:|w:|m:|st1:|xml|roundrect|shapetype|shape|imagedata|textbox|path'
    r'|stroke|fill|vmlframe|formula')
_HTML_TAG = re.compile(rf'</?(?:{_TAG_NAMES})\b[^>]*>', re.IGNORECASE)
# The same tags, but wrapped across lines by the sender's mail client.
_HTML_TAG_WRAPPED = re.compile(rf'</?(?:{_TAG_NAMES})\b\s[^<>]{{0,400}}?>', re.IGNORECASE)

_CSS_DECL_LINE = re.compile(r'^(?:[a-z-]+\s*:\s*[^;{}]*;\s*)+$', re.IGNORECASE)
# Properties whose name alone marks a line as stylesheet. Everyday-English names
# (top, left, width, height, ...) are left out on purpose, so a shipping email
# listing "Width: 180 cm;" is not mistaken for a stylesheet; those declarations
# are still caught by the value test below.
_CSS_WORDS = (
    r'background|border|clear|color|cursor|display|fill|filter|font|font-size'
    r'|font-style|font-weight|letter-spacing|list-style|margin|opacity|outline'
    r'|overflow|padding|stroke|text-align|text-indent|text-transform|transform'
    r'|transition|vertical-align|visibility|white-space|z-index')
_CSS_PROPERTY = re.compile(rf'^(?:-{{0,2}}[a-z]+(?:-[a-z]+)+|{_CSS_WORDS})\s*:', re.IGNORECASE)
_CSS_VALUE = re.compile(
    r'!important|\d(?:px|pt|pc|em|rem|ex|ch|vh|vw|%)\b|#[0-9a-f]{3,8}\b|url\(|rgba?\('
    r'|:\s*\d+(?:\.\d+)?\s*[;}]|sans-serif|serif|monospace|inherit|none|auto|block'
    r'|inline|hidden|collapse|middle|baseline|both|center|justify|nowrap|solid|dashed'
    r'transparent|pointer|underline|uppercase|lowercase|bold|normal|break-word'
    r'|border-box|content-box|ellipsis|bicubic', re.IGNORECASE)
_CSS_BRACES_ONLY = re.compile(r'^[{};,\s]+$')
_CSS_SELECTORISH = re.compile(r"^[\d\s]*[.#@]?[A-Za-z][\w\s.#:\[\]=\-'\">+()~*,]*$")
_CSS_DUMP = re.compile(r':\s*[^;{}]*;\s*\}')

def _css_score(line):
    """Score how much a line looks like CSS: 2 = certainly, 1 = probably, 0 = no.

    Gmail's generated text/plain parts carry whole stylesheets as bare text, and
    the lines are wrapped at random points, so a single-line shape test is not
    enough: a line may end mid-declaration or mid-selector. Declaration-only
    lines additionally have to carry a CSS-ish value, otherwise ordinary prose
    like "Deadline: Friday;" would score as stylesheet.
    """
    line = line.strip()
    if not line:
        return 0
    if '!important' in line:
        return 2
    # A stylesheet squashed onto one line
    if len(line) > 80 and line.count('{') >= 2 and line.count(';') >= 2 and _CSS_DUMP.search(line):
        return 2

    braces = line.count('{') + line.count('}')
    # CSS lines that get wrapped always break after a brace, a semicolon or a
    # comma; prose almost never does.
    css_shape = line.endswith(('{', '}', ';', ',')) or braces >= 2
    if not css_shape and ';' not in line:
        return 0

    if braces and _CSS_SELECTORISH.match(line.split('{', 1)[0].strip()):
        return 2
    if _CSS_DECL_LINE.match(line) and (_CSS_PROPERTY.match(line) or _CSS_VALUE.search(line)):
        return 2
    if _CSS_BRACES_ONLY.match(line):
        return 2
    if braces and ';' in line:
        return 2
    if line.endswith(',') and _CSS_SELECTORISH.match(line):
        return 1
    return 0

_CSS_PROPERTY_NAME = rf'(?:-{{0,2}}[a-z]+(?:-[a-z]+)+|{_CSS_WORDS})'

# A line that *starts* with CSS syntax came from a stylesheet, however little of
# it arrived and whatever surrounds it. Block-level scoring cannot see these:
# mail clients wrap declarations mid-value, so a fragment like
# "min-width:100%; ... font-family: Arial," sits alone among prose lines.
# Anchoring at the start of the line is what keeps prose safe -- a line that
# merely contains CSS-like text ("Deadline: Friday; Owner: Laurent;") or carries
# a heading before it ("BriterEYE: January 2024#yiv...") is never matched.
_CERTAIN_CSS_LINE = re.compile(
    r'^(?:'
    r'@font-face\s*\{?$'
    r'|(?:' + _CSS_PROPERTY_NAME + r'\s*:\s*[^;{}]+;\s*)*src:\s*(?:local|url)\('
    r'|(?:' + _CSS_PROPERTY_NAME + r'\s*:\s*[^;{}]+;\s*){2,}$'
    r'|\\?(?:[a-z][\w-]*)?[.#@][\w-]+[\w\s.#:\[\]>+~,()\-]*\{[^{}]*[a-z-]+\s*:'
    r'|(?:[\w\s,;.\'()%\-]*[\s;,])?(?:-webkit|-moz|-ms|-o)-[a-z-]+\s*:'
    r'|\\?(?:mso)-[a-z-]+\s*:'
    r'|[{}]$'
    r'|!important'
    r')',
    re.IGNORECASE,
)

def strip_markup_noise(text):
    """Remove leaked <style>/<script> content, CSS blocks and bare HTML tags.

    Emails without a real text/plain part get one generated by Gmail that keeps
    stylesheet text and stray tags. Left alone, those lines render as headings
    and HTML blocks and swamp the message.
    """
    if not text:
        return ""

    # Conditional comments ("<!--[if mso]> ... <![endif]-->") wrap chunks of
    # Outlook markup, and are removed whole along with their payload.
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<style\b[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script\b[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = _HTML_TAG_WRAPPED.sub('', text)

    def without_tags(line):
        """Strip known HTML tags; return None for a line that was only tags.

        Leftover comment markers are dropped too: senders' HTML often arrives
        with unclosed comments, which no doubt-removal regex can match whole.
        """
        stripped = _HTML_TAG.sub('', line)
        stripped = re.sub(r'<!--|-->|<![^>]*>', '', stripped)
        return stripped if stripped.strip() else None

    kept = []
    block = []
    scores = []

    def flush_block():
        # Drop the CSS-looking lines of a block that is mostly CSS. Lines that
        # score 0 are kept, so prose sitting inside a leaked block survives.
        if block:
            certain = sum(1 for score in scores if score == 2)
            scored = sum(1 for score in scores if score > 0)
            mostly_css = scored >= 2 and sum(scores) >= 4 and scored >= 0.5 * len(block)
            # A lone line is dropped only when it carries real CSS syntax, so a
            # sentence that merely mentions, say, "!important" is left alone.
            lone_css = len(block) == 1 and scores[0] == 2 and ('{' in block[0] or '}' in block[0])
            # Two unmistakable CSS lines are enough on their own: prose wrapped
            # mid-sentence can end in a comma, so score-1 lines are only dropped
            # from a block that really is mostly stylesheet.
            if certain >= 2 or mostly_css or lone_css:
                for line, score in zip(block, scores):
                    if score == 0 or (score == 1 and not mostly_css):
                        line = without_tags(line)
                        if line:
                            kept.append(line)
            else:
                for line in block:
                    line = without_tags(line)
                    if line:
                        kept.append(line)
            block.clear()
            scores.clear()

    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            flush_block()
            kept.append('')
            continue
        # Strip tags before judging the line: a leaked stylesheet often arrives
        # as "<style>@font-face{" with its opening tag still attached, and only
        # the tag-stripped text shows what the line really is.
        line = without_tags(line)
        if not line:
            continue
        # Padding marks often sit in front of a stylesheet fragment, as in
        # "<ZWNJ> <ZWNJ> @font-face{", so judge the line without any of them.
        if _CERTAIN_CSS_LINE.match(_INVISIBLE_ALL.sub('', line).lstrip()):
            # A stylesheet fragment, whatever the lines around it look like.
            continue
        block.append(line)
        scores.append(_css_score(line))

    flush_block()

    return re.sub(r'\n{3,}', '\n\n', '\n'.join(kept)).strip()

# Invisible characters are used as padding (for preheader text) and leave lines
# that render as nothing at all. They are split in two: characters that only ever
# pad, and characters that carry meaning where real text uses them.
_PADDING_CODE_POINTS = [
    0x00ad,  # soft hyphen
    0x034f,  # combining grapheme joiner
    0x200b,  # zero-width space
    0x202a, 0x202b, 0x202c, 0x202d, 0x202e,  # bidi embedding and override controls
    0x2060, 0x2061, 0x2062, 0x2063, 0x2064,  # word joiner and invisible operators
    0xfeff,  # zero-width no-break space / BOM
]

# Characters that are meaningful in some text: ZWNJ and ZWJ hold Persian and
# Arabic words and emoji sequences together, LRM/RLM steer bidirectional text.
_MEANINGFUL_CODE_POINTS = [
    0x200c, 0x200d,  # zero-width non-joiner / joiner
    0x200e, 0x200f,  # left-to-right / right-to-left mark
]

def _char_class(code_points):
    return re.compile('[%s]' % ''.join(chr(c) for c in code_points))

_INVISIBLE_PADDING = _char_class(_PADDING_CODE_POINTS)
_INVISIBLE_ALL = _char_class(_PADDING_CODE_POINTS + _MEANINGFUL_CODE_POINTS)
_MEANINGFUL_CHARS = ''.join(chr(c) for c in _MEANINGFUL_CODE_POINTS)
_FILLER_NEIGHBOUR = re.compile(r'[\s0-9]')

def _drop_filler_marks(line):
    """Remove joiner and bidi marks that are padding rather than text.

    The same character is padding in one place and text in another, so decide by
    context: keep a mark only where it sits between two ordinary characters, as
    in the Persian 'فایلها' or the emoji '🕵️♀️'. A mark at a line edge, beside
    a space or a digit, or alongside another mark is the repeated filler that
    senders use to pad out a preheader ('servizio ‹ZWNJ› ‹ZWNJ› ‹ZWNJ›',
    '3‹ZWJ›1‹ZWJ› dicembre').
    """
    kept = []
    for index, char in enumerate(line):
        if char not in _MEANINGFUL_CHARS:
            kept.append(char)
            continue
        before = line[index - 1] if index else ''
        after = line[index + 1] if index + 1 < len(line) else ''
        if any(neighbour == '' or neighbour in _MEANINGFUL_CHARS
               or _FILLER_NEIGHBOUR.match(neighbour)
               for neighbour in (before, after)):
            continue
        kept.append(char)
    return ''.join(kept)

def strip_invisible_padding(text):
    """Drop invisible padding, keeping meaningful joiners inside real text."""
    lines = []
    for line in (text or '').split('\n'):
        line = _INVISIBLE_PADDING.sub('', line)
        lines.append(_drop_filler_marks(line).strip())
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()

def looks_like_leaked_markup(text, stripped=None):
    """True when a text/plain body is mostly leaked stylesheet or HTML markup."""
    if not text:
        return False

    if stripped is None:
        stripped = strip_markup_noise(text)
    if len(text) >= 200 and len(stripped) < 0.5 * len(text):
        return True

    tag_count = len(_HTML_TAG.findall(text))
    return tag_count >= 8 and tag_count >= 0.05 * len(text.split())

def html_to_text(html_content):
    """Convert HTML content to plain text with proper formatting."""
    if not html_content:
        return ""

    # Remove script/style tags and their content
    html_content = re.sub(r'<script\b[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<style\b[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # Remove comments, including the "<!--[if mso]> ... <![endif]-->" blocks
    # that hold Outlook-only markup
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)

    # Convert anchor tags to markdown links
    # Find all <a href="url">text</a> and replace with [text](url)
    def replace_anchor(match):
        href = match.group(1)
        text = match.group(2).strip()
        # If text is empty, use the href as text
        if not text:
            text = href
        return f'[{text}]({href})'

    html_content = re.sub(r'<a\s+[^>]*?href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', replace_anchor, html_content, flags=re.DOTALL | re.IGNORECASE)

    # Replace <br> and <br/> with newlines
    html_content = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)

    # Replace paragraph tags with double newlines
    html_content = re.sub(r'</?p[^>]*>', '\n\n', html_content, flags=re.IGNORECASE)

    # Replace div tags with newlines (block-level elements)
    html_content = re.sub(r'</?div[^>]*>', '\n', html_content, flags=re.IGNORECASE)

    # Replace list items
    html_content = re.sub(r'</?li[^>]*>', '\n• ', html_content, flags=re.IGNORECASE)

    # Replace heading tags
    html_content = re.sub(r'</?h[1-6][^>]*>', '\n\n', html_content, flags=re.IGNORECASE)

    # Remove all remaining HTML tags, plus any comment markers left behind by a
    # comment the sender never closed
    html_content = re.sub(r'<[^>]+>', '', html_content)
    html_content = re.sub(r'<!--|-->', '', html_content)

    # Apply text cleaning (decodes entities, converts nbsp, normalizes whitespace)
    return clean_text(html_content)

# ---------------------------------------------------------------------------
# Markdown safety
# ---------------------------------------------------------------------------

_AUTOLINK = re.compile(r'^<[A-Za-z][A-Za-z0-9+.\-]*:[^<>\s]*>')
_SETEXT_OR_RULE = re.compile(r'^[-=*_][\-=*_\s]*$')
_FENCE = re.compile(r'^(?:`{3,}|~{3,})')

def sanitize_body(body):
    """Escape body characters that would otherwise reshape the document.

    Email text is arbitrary: a line starting with "##" becomes a heading and
    collides with the per-message headings, a "---" line under a line of text
    turns that text into a setext heading, and a "<div>" line opens an HTML
    block. Escaping the first character keeps the text readable while stopping
    it from hijacking the structure around it.
    """
    if not body:
        return ""

    safe_lines = []
    for line in body.split('\n'):
        if line.startswith('#'):
            line = '\\' + line
        elif _SETEXT_OR_RULE.match(line):
            line = '\\' + line
        elif line.startswith('|'):
            line = '\\' + line
        elif _FENCE.match(line):
            line = '\\' + line
        elif line.startswith('<') and not _AUTOLINK.match(line):
            line = '\\' + line
        safe_lines.append(line)

    return '\n'.join(safe_lines)

def safe_filename(filename):
    """Make a filename safe for filesystem."""
    # Remove or replace unsafe characters
    filename = re.sub(r'[^\w\-_\. ]', '_', filename).strip()
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename

def attachment_link(filename):
    """Build a markdown link target for an attachment.

    Attachment names keep spaces and accented characters, which are not valid in
    a bare markdown link destination, so percent-encode them.
    """
    return './attachments/' + quote(filename, safe='/-_.~')

def acquire_lock(output_dir):
    """Take an exclusive lock on the output directory.

    Two conversions writing the same directory corrupt each other: each removes
    the duplicate attachments it found, including files the other run's
    markdown still links to. Returns the lock path, or None if another run
    holds the lock.
    """
    lock_path = os.path.join(output_dir, '.mbox_to_markdown.lock')
    for attempt in (1, 2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if attempt == 2:
                return None
            # A run killed mid-way leaves its lock behind; reclaim it if the
            # process that wrote it is gone.
            try:
                with open(lock_path) as f:
                    pid = int(f.read().strip() or 0)
            except Exception:
                pid = 0
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except PermissionError:
                    alive = True
                except OSError:
                    alive = False
            if alive:
                return None
            print(f'Removing stale lock left by pid {pid}', file=sys.stderr)
            try:
                os.remove(lock_path)
            except OSError:
                return None
        else:
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            atexit.register(lambda: os.path.exists(lock_path) and os.remove(lock_path))
            return lock_path
    return None

def verify_attachment_links(md_file, output_dir):
    """Report markdown links that point at attachments which do not exist.

    Returns the list of missing link targets. Anything but an empty list means
    the attachments directory and the markdown disagree about what was kept.
    """
    with open(md_file, encoding='utf-8') as f:
        content = f.read()

    missing = []
    seen = set()
    for link in re.findall(r'\]\((\./attachments/[^)]*)\)', content):
        if link in seen:
            continue
        seen.add(link)
        path = os.path.join(output_dir, os.path.normpath(unquote(link)))
        if not os.path.exists(path):
            missing.append(link)
    return missing

def inline_text(text, limit=None):
    """Collapse a header value onto one line and escape markdown punctuation."""
    text = ' '.join((text or '').split())
    text = text.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
    if limit and len(text) > limit:
        text = text[:limit - 1].rstrip() + '…'
    return text

def sender_name(from_addr):
    """Prefer the display name, falling back to the address."""
    name, addr = parseaddr(from_addr)
    name = name.strip().strip('"')
    return name or addr or from_addr.strip()

# ---------------------------------------------------------------------------

def build_body(message):
    """Pick the best available body and clean it up."""
    plain = get_plain_text_part(message)
    html_body = get_html_part(message)

    cleaned = strip_markup_noise(plain) if plain else None

    if plain and looks_like_leaked_markup(plain, cleaned) and html_body:
        # The plain-text alternative is a stylesheet/HTML dump; the HTML part is
        # the better source when we have it.
        cleaned = strip_markup_noise(html_to_text(html_body))
    elif not cleaned and html_body:
        cleaned = strip_markup_noise(html_to_text(html_body))

    if not cleaned:
        return "[No readable content found]"
    return strip_invisible_padding(cleaned)

def main():
    mbox_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MBOX_PATH
    output_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    attachments_dir = os.path.join(output_dir, 'attachments')

    # Create directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)

    md_file = os.path.join(output_dir, 'mailbox.md')

    if acquire_lock(output_dir) is None:
        print(f'Error: another conversion is already writing to {output_dir}.\n'
              f'       Wait for it to finish, or delete '
              f'{os.path.join(output_dir, ".mbox_to_markdown.lock")} if no '
              f'conversion is running.', file=sys.stderr)
        sys.exit(1)

    mbox = mailbox.mbox(mbox_path)
    total = len(mbox)
    if limit:
        total = min(total, limit)

    # Attachment names already handed out this run. Tracking them in memory
    # (rather than testing for an existing file) keeps re-runs deterministic:
    # the same mailbox always produces the same file names.
    used_names = set()
    index_entries = []
    message_blocks = []
    dates_seen = []

    for i, message in enumerate(mbox):
        if limit and i >= limit:
            break

        if (i + 1) % 250 == 0:
            print(f'  converted {i + 1}/{total} messages', file=sys.stderr, flush=True)

        # Decode headers
        subject = decode_mime_words(message.get('Subject'))
        from_addr = decode_mime_words(message.get('From'))
        to_addr = decode_mime_words(message.get('To'))
        date_str = decode_mime_words(message.get('Date'))

        # Try to parse date for better formatting
        try:
            date_obj = parsedate_to_datetime(date_str)
            formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S %Z')
            index_date = date_obj.strftime('%Y-%m-%d')
            dates_seen.append(index_date)
        except Exception:
            formatted_date = date_str
            index_date = 'unknown'

        body = sanitize_body(build_body(message))

        # Get attachments
        attachments = []
        if message.is_multipart():
            for part in message.walk():
                content_disposition = str(part.get('Content-Disposition'))
                if 'attachment' in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = decode_mime_words(filename)
                        candidate = safe_filename(filename) or 'attachment'
                        base, ext = os.path.splitext(candidate)
                        counter = 1
                        while candidate.lower() in used_names:
                            candidate = f"{base}_{counter}{ext}"
                            counter += 1
                        used_names.add(candidate.lower())

                        # Save attachment
                        payload = part.get_payload(decode=True)
                        if payload:
                            with open(os.path.join(attachments_dir, candidate), 'wb') as att_file:
                                att_file.write(payload)
                            attachments.append(candidate)

        # Write message to markdown
        block = [f'## Message {i+1}\n\n']
        block.append(f'**From:** {inline_text(strip_invisible_padding(from_addr))}\n\n')
        block.append(f'**To:** {inline_text(strip_invisible_padding(to_addr))}\n\n')
        block.append(f'**Subject:** {inline_text(strip_invisible_padding(subject))}\n\n')
        block.append(f'**Date:** {inline_text(strip_invisible_padding(formatted_date))}\n\n')

        if attachments:
            block.append('**Attachments:**\n\n')
            for att in attachments:
                block.append(f'- [{inline_text(strip_invisible_padding(att))}]'
                             f'({attachment_link(att)})\n')
            block.append('\n')

        block.append('---\n\n')
        block.append(body + '\n\n')
        block.append('---\n\n')
        message_blocks.append(''.join(block))

        index_entries.append(
            f'- [Message {i+1}](#message-{i+1}) — {index_date} — '
            f'{inline_text(strip_invisible_padding(sender_name(from_addr)), 60)} — '
            f'{inline_text(strip_invisible_padding(subject), 120)}\n')

    mbox.close()

    # Write the header, the index and then every message
    print('Writing markdown...', file=sys.stderr, flush=True)
    date_range = f'{min(dates_seen)} → {max(dates_seen)}' if dates_seen else 'unknown'
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write('# Mailbox Export\n\n')
        f.write(f'Total messages: {len(message_blocks)}\n')
        f.write(f'Date range: {date_range}\n\n')
        f.write('## Index\n\n')
        f.writelines(index_entries)
        f.write('\n---\n\n')
        f.writelines(message_blocks)

    # Remove MD5 duplicate attachments and update references in mailbox.md
    print('Checking for duplicate attachments...')
    duplicate_map = {}
    seen_hashes = {}

    # Scan all attachment files for duplicates
    for root, dirs, files in os.walk(attachments_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                if file_hash in seen_hashes:
                    # This is a duplicate, map it to the original file
                    duplicate_map[filepath] = seen_hashes[file_hash]
                else:
                    # First time seeing this hash
                    seen_hashes[file_hash] = filepath
            except Exception as e:
                print(f'Error processing {filepath}: {e}')

    # Remove duplicate files and update mailbox.md references
    if duplicate_map:
        print(f'Found {len(duplicate_map)} duplicate attachment(s) to remove.')

        # Read the markdown file to update references
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace references to duplicate files with references to the kept files
        for duplicate_path, original_path in duplicate_map.items():
            duplicate_link = attachment_link(os.path.basename(duplicate_path))
            original_link = attachment_link(os.path.basename(original_path))

            # Replace markdown links: [duplicate](./attachments/duplicate) -> [duplicate](./attachments/original)
            content = content.replace(f']({duplicate_link})', f']({original_link})')

        # Write the updated content back
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # Actually remove the duplicate files
        for duplicate_path in duplicate_map.keys():
            try:
                os.remove(duplicate_path)
            except Exception as e:
                print(f'Error removing {duplicate_path}: {e}')

        print('Duplicate removal complete.')
    else:
        print('No duplicate attachments found.')

    missing = verify_attachment_links(md_file, output_dir)
    if missing:
        print(f'WARNING: {len(missing)} attachment link(s) point at missing '
              f'files, e.g. {missing[:3]}', file=sys.stderr)
    else:
        print('All attachment links resolve.')

    print(f'Conversion complete. Output written to: {md_file}')
    print(f'Attachments saved to: {attachments_dir}')

if __name__ == '__main__':
    main()
