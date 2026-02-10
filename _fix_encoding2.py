"""Fix mojibake emoji in template files.
The emoji were double-encoded: UTF-8 bytes -> cp1252 interpretation -> UTF-8 re-encoding.
We reverse this by finding the mangled sequences and replacing with correct emoji."""

import os

templates_dir = 'dashboard/templates'

def make_mojibake(emoji_char):
    """Given a proper emoji character, generate what its mojibake looks like as bytes."""
    utf8_bytes = emoji_char.encode('utf-8')
    # Each byte gets interpreted as cp1252, then that char gets re-encoded as UTF-8
    mojibake_bytes = b''
    for b in utf8_bytes:
        char = bytes([b]).decode('cp1252', errors='replace')
        mojibake_bytes += char.encode('utf-8')
    return mojibake_bytes

# All emoji we might have used
emojis = [
    '\U0001f464',  # bust in silhouette
    '\u2764\ufe0f',# red heart + variation selector
    '\u2764',      # red heart alone
    '\U0001f4ac',  # speech balloon
    '\U0001f4d6',  # open book
    '\U0001f4cb',  # clipboard
    '\U0001f48c',  # love letter
    '\U0001f4ca',  # bar chart
    '\U0001f527',  # wrench
    '\U0001f680',  # rocket
    '\U0001f525',  # fire
    '\U0001f4aa',  # flexed bicep
    '\U0001f4c8',  # chart increasing
    '\U0001f4c9',  # chart decreasing
    '\U0001f4cc',  # pushpin
    '\U0001f4dd',  # memo
    '\U0001f44d',  # thumbs up
    '\U0001f44e',  # thumbs down
    '\U0001f3af',  # bullseye
    '\U0001f522',  # input numbers
    '\U0001f50d',  # magnifying glass
    '\U0001f440',  # eyes
    '\u26a0',      # warning
    '\u2705',      # check mark
    '\u2714',      # heavy check mark
    '\u274c',      # cross mark
    '\u2139',      # information
    '\u2192',      # right arrow
    '\u2190',      # left arrow
    '\U0001f4e4',  # outbox tray
    '\U0001f4e5',  # inbox tray
    '\U0001f4e7',  # e-mail
    '\u25cf',      # black circle
    '\U0001f7e2',  # green circle
    '\U0001f534',  # red circle
    '\U0001f4f1',  # mobile phone
    '\U0001f4bb',  # laptop
    '\u23f0',      # alarm clock
    '\U0001f4a1',  # light bulb
    '\U0001f389',  # party popper
    '\U0001f6a8',  # police car light
    '\U0001f4e2',  # loudspeaker
]

# Build replacement map: mojibake bytes -> correct UTF-8 bytes
replacements = {}
for emoji in emojis:
    try:
        mojibake = make_mojibake(emoji)
        correct = emoji.encode('utf-8')
        if mojibake != correct:
            replacements[mojibake] = correct
    except:
        pass

print(f"Built {len(replacements)} mojibake -> correct mappings")

# Process each file
for filename in sorted(os.listdir(templates_dir)):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(templates_dir, filename)
    
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    original = raw
    fix_count = 0
    
    for bad, good in replacements.items():
        count = raw.count(bad)
        if count > 0:
            raw = raw.replace(bad, good)
            fix_count += count
    
    if fix_count > 0:
        print(f"FIXED: {filename} - {fix_count} emoji replacements")
        with open(filepath, 'wb') as f:
            f.write(raw)

# Also handle the special case of smart quotes that got double-encoded
# These show up in JS code as garbled arrow/quote characters
print("\nChecking for double-encoded smart quotes/dashes...")
smart_chars = {
    '\u2019': '\u2019',  # right single quote '
    '\u201c': '\u201c',  # left double quote
    '\u201d': '\u201d',  # right double quote
    '\u2013': '\u2013',  # en dash
    '\u2014': '\u2014',  # em dash
    '\u2018': '\u2018',  # left single quote
    '\u2026': '\u2026',  # ellipsis
    '\u00a0': '\u00a0',  # nbsp
}

for filename in sorted(os.listdir(templates_dir)):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(templates_dir, filename)
    
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    original = raw
    fix_count = 0
    
    for char in smart_chars:
        mojibake = make_mojibake(char)
        correct = char.encode('utf-8')
        if mojibake != correct:
            count = raw.count(mojibake)
            if count > 0:
                raw = raw.replace(mojibake, correct)
                fix_count += count
    
    if fix_count > 0:
        print(f"FIXED: {filename} - {fix_count} smart quote/dash replacements")
        with open(filepath, 'wb') as f:
            f.write(raw)

print("\nDone!")
