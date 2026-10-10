#!/usr/bin/env python3
"""
Convert an mbox file to markdown format with attachments extracted.
"""

import mailbox
import email
import os
import mimetypes
import hashlib
from email.header import decode_header
from email.utils import parsedate_to_datetime
import re

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
                    return payload.decode(charset, errors='replace')
                except Exception:
                    continue
    else:
        if message.get_content_type() == 'text/plain':
            try:
                payload = message.get_payload(decode=True)
                charset = message.get_content_charset() or 'utf-8'
                return payload.decode(charset, errors='replace')
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

def safe_filename(filename):
    """Make a filename safe for filesystem."""
    # Remove or replace unsafe characters
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename

def main():
    mbox_path = '/Users/ntilau/Downloads/Takeout/Mail/All_mail_Including_Spam_and_Trash.mbox'
    output_dir = '/Users/ntilau/Downloads/Takeout/Mail/mbox_markdown_output'
    attachments_dir = os.path.join(output_dir, 'attachments')

    # Create directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)

    # Output markdown file
    md_file = os.path.join(output_dir, 'mailbox.md')

    # Open mbox
    mbox = mailbox.mbox(mbox_path)

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write('# Mailbox Export\n\n')
        f.write(f'Total messages: {len(mbox)}\n\n')
        f.write('---\n\n')

        for i, message in enumerate(mbox):
            # Decode headers
            subject = decode_mime_words(message.get('Subject'))
            from_addr = decode_mime_words(message.get('From'))
            to_addr = decode_mime_words(message.get('To'))
            date_str = decode_mime_words(message.get('Date'))

            # Try to parse date for better formatting
            try:
                date_obj = parsedate_to_datetime(date_str)
                formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S %Z')
            except Exception:
                formatted_date = date_str

            # Get body
            body = get_plain_text_part(message)
            html_body = get_html_part(message)

            # If no plain text, try to convert HTML to plain text (basic)
            if body is None and html_body is not None:
                # Very basic HTML to text conversion: remove tags, replace <br> with newline
                body = re.sub(r'<br\s*/?>', '\n', html_body, flags=re.IGNORECASE)
                body = re.sub(r'</?p[^>]*>', '\n\n', body, flags=re.IGNORECASE)
                body = re.sub(r'<[^>]+>', '', body)
                body = body.strip()
                if not body:
                    body = "[HTML content not converted to plain text]"
            elif body is None:
                body = "[No plain text content found]"

            # Get attachments
            attachments = []
            if message.is_multipart():
                for part in message.walk():
                    content_disposition = str(part.get('Content-Disposition'))
                    if 'attachment' in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            filename = decode_mime_words(filename)
                            safe_name = safe_filename(filename)
                            # Avoid duplicate filenames
                            base, ext = os.path.splitext(safe_name)
                            counter = 1
                            while os.path.exists(os.path.join(attachments_dir, safe_name)):
                                safe_name = f"{base}_{counter}{ext}"
                                counter += 1

                            # Save attachment
                            payload = part.get_payload(decode=True)
                            if payload:
                                filepath = os.path.join(attachments_dir, safe_name)
                                with open(filepath, 'wb') as att_file:
                                    att_file.write(payload)
                                attachments.append(safe_name)

            # Write message to markdown
            f.write(f'## Message {i+1}\n\n')
            f.write(f'**From:** {from_addr}\n\n')
            f.write(f'**To:** {to_addr}\n\n')
            f.write(f'**Subject:** {subject}\n\n')
            f.write(f'**Date:** {formatted_date}\n\n')
            f.write('---\n\n')
            f.write(body)
            f.write('\n\n')

            if attachments:
                f.write('**Attachments:**\n')
                for att in attachments:
                    f.write(f'- [{att}](./attachments/{att})\n')
                f.write('\n')

            f.write('---\n\n')

    mbox.close()

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
            # Get relative paths from attachments_dir for the markdown links
            duplicate_rel = os.path.relpath(duplicate_path, attachments_dir)
            original_rel = os.path.relpath(original_path, attachments_dir)

            # Replace markdown links: [duplicate](./attachments/duplicate) -> [duplicate](./attachments/original)
            duplicate_link = f'./attachments/{duplicate_rel}'
            original_link = f'./attachments/{original_rel}'

            # Replace in the content
            content = content.replace(f']({duplicate_link})', f']({original_link})')

        # Write the updated content back
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # Actually remove the duplicate files
        for duplicate_path in duplicate_map.keys():
            try:
                os.remove(duplicate_path)
                print(f'Removed duplicate: {duplicate_path}')
            except Exception as e:
                print(f'Error removing {duplicate_path}: {e}')

        print('Duplicate removal complete.')
    else:
        print('No duplicate attachments found.')

    print(f'Conversion complete. Output written to: {md_file}')
    print(f'Attachments saved to: {attachments_dir}')

if __name__ == '__main__':
    main()