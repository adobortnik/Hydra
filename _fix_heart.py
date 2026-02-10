"""Fix remaining mojibake by using latin1 instead of cp1252 for the reverse mapping."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')

templates_dir = 'dashboard/templates'

def make_mojibake_latin1(emoji_str):
    """Generate mojibake bytes using latin1 (which maps all 256 bytes)."""
    utf8_bytes = emoji_str.encode('utf-8')
    mojibake_bytes = b''
    for b in utf8_bytes:
        char = bytes([b]).decode('latin1')  # latin1 maps all 0-255
        mojibake_bytes += char.encode('utf-8')
    return mojibake_bytes

# Emoji to fix
emojis = [
    '\u2764\ufe0f',  # ❤️ red heart with variation selector
    '\u2764',         # ❤ red heart alone
    '\u2709\ufe0f',  # ✉️ envelope with variation selector
    '\u2709',         # ✉ envelope alone
    '\u2714\ufe0f',  # ✔️
    '\u2714',         # ✔
    '\u26a0\ufe0f',  # ⚠️
    '\u26a0',         # ⚠
    '\u2705',         # ✅
    '\u274c',         # ❌
    '\u2139\ufe0f',  # ℹ️
    '\u2b50',         # ⭐
]

# Build replacements
replacements = {}
for emoji in emojis:
    mojibake = make_mojibake_latin1(emoji)
    correct = emoji.encode('utf-8')
    if mojibake != correct:
        replacements[mojibake] = (correct, emoji)

print(f"Built {len(replacements)} latin1-based replacements")
for bad, (good, char) in replacements.items():
    print(f"  {bad.hex()} -> {good.hex()} ({char})")

# Also add 4-byte emoji that might have been missed
four_byte_emojis = [
    '\U0001f464', '\U0001f4ac', '\U0001f4d6', '\U0001f4cb',
    '\U0001f48c', '\U0001f4ca', '\U0001f527', '\U0001f680',
    '\U0001f525', '\U0001f4aa', '\U0001f4c8', '\U0001f4dd',
    '\U0001f44d', '\U0001f3af', '\U0001f50d', '\U0001f440',
    '\U0001f4e4', '\U0001f4e5', '\U0001f4e7', '\U0001f534',
    '\U0001f4f1', '\U0001f4bb', '\U0001f4a1', '\U0001f389',
    '\U0001f6a8', '\U0001f4e2',
]
for emoji in four_byte_emojis:
    mojibake = make_mojibake_latin1(emoji)
    correct = emoji.encode('utf-8')
    if mojibake != correct:
        replacements[mojibake] = (correct, emoji)

# Process files
for filename in sorted(os.listdir(templates_dir)):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(templates_dir, filename)
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    original = raw
    fix_count = 0
    
    for bad, (good, char) in replacements.items():
        count = raw.count(bad)
        if count > 0:
            raw = raw.replace(bad, good)
            fix_count += count
    
    if fix_count > 0:
        print(f"FIXED: {filename} - {fix_count} replacements")
        with open(filepath, 'wb') as f:
            f.write(raw)

print("Done!")
