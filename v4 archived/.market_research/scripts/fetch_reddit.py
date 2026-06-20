#!/usr/bin/env python3
"""Fetch Reddit content from archive.org and extract post + comments."""
import subprocess
import re
import sys

def fetch_url(url, timeout=60):
    """Fetch URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '-L', '-A',
             'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
             '--max-time', str(timeout), url],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return ""

def extract_text_from_wayback(html):
    """Extract post text and top comments from a wayback machine Reddit page."""
    result = {
        'title': '',
        'post_body': '',
        'author': '',
        'score': '',
        'comments': []
    }

    # Title extraction
    title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if title_match:
        result['title'] = title_match.group(1)

    # Description (post body preview)
    desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
    if desc_match:
        result['post_body'] = desc_match.group(1)

    # Try to find shreddit-post attributes
    body_matches = re.findall(r'<shreddit-post[^>]+body="([^"]*)"', html)
    for m in body_matches:
        if m and len(m) > 50:
            result['post_body'] = m

    # Author
    author_match = re.search(r'<shreddit-post[^>]+author="([^"]+)"', html)
    if author_match:
        result['author'] = author_match.group(1)

    # Look for comment text in <p> tags
    fc_matches = re.findall(r'<faceplate-comment-body[^>]*>(.*?)</faceplate-comment-body>', html, re.DOTALL)
    for fc in fc_matches[:25]:
        text = re.sub(r'<[^>]+>', ' ', fc).strip()
        text = re.sub(r'\s+', ' ', text)
        if 30 < len(text) < 3000:
            result['comments'].append(text)

    # Older reddit format
    if not result['comments']:
        # <div class="comment"><div class="md"><p>...</p></div>
        comments = re.findall(r'<div class="md[^"]*">\s*<p>(.*?)</p>', html, re.DOTALL)
        for c in comments[:25]:
            text = re.sub(r'<[^>]+>', ' ', c).strip()
            text = re.sub(r'\s+', ' ', text)
            if 30 < len(text) < 3000:
                result['comments'].append(text)

    return result

if __name__ == "__main__":
    test_urls = [
        "https://www.reddit.com/r/askcarsales/comments/159rwgk/missed_call_from_dealership/",
        "https://www.reddit.com/r/askcarsales/comments/1fz4ge6/no_call_back_yet_from_dealership/",
    ]
    for url in test_urls:
        print(f"Fetching {url}...")
        path = url.replace('https://www.reddit.com', '')
        archive_url = f"https://web.archive.org/web/2024/{path}"
        html = fetch_url(archive_url)
        if html:
            data = extract_text_from_wayback(html)
            print(f"Title: {data['title'][:200]}")
            print(f"Author: {data['author']}")
            print(f"Post body: {data['post_body'][:500]}")
            print(f"Comments: {len(data['comments'])}")
            for i, c in enumerate(data['comments'][:5]):
                print(f"  [{i+1}] {c[:400]}")
            print("---")
        else:
            print("No HTML returned")
