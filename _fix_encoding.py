"""Fix double-encoded UTF-8 in template files.
When UTF-8 bytes get misinterpreted as latin1/cp1252 and re-encoded to UTF-8,
you get mojibake. This reverses that by trying latin1->utf8 decode on suspicious chunks."""

import os, re

templates_dir = 'dashboard/templates'

def try_fix_double_encoded(raw_bytes):
    """
    Given raw UTF-8 bytes of a file, find chunks that are double-encoded
    and fix them. Double-encoded UTF-8 shows up as sequences like:
    C3 A2 C5 93 E2 80 9C  (which is latin1-reinterpreted UTF-8)
    """
    # Strategy: find runs of bytes > 0x7F that form valid latin1->utf8 sequences
    result = bytearray()
    i = 0
    fixed_count = 0
    
    while i < len(raw_bytes):
        # If we see a byte that could be start of double-encoded sequence
        if raw_bytes[i] >= 0xC0 and raw_bytes[i] <= 0xFF:
            # Try to grab a chunk of high bytes
            j = i
            while j < len(raw_bytes) and j < i + 20:
                # Collect what looks like a double-encoded multi-byte sequence
                if raw_bytes[j] >= 0x80 or (j > i and raw_bytes[j] < 0x80):
                    if raw_bytes[j] < 0x80:
                        break
                    j += 1
                else:
                    j += 1
            
            chunk = bytes(raw_bytes[i:j])
            
            # Try to decode: interpret as latin1 (identity mapping) then decode as utf8
            try:
                text_latin1 = chunk.decode('latin1')
                text_utf8 = text_latin1.encode('latin1')  # This is identity
                decoded = text_utf8.decode('utf-8')
                
                # Check if the decoded version looks like real characters (emoji, special chars)
                # and is shorter (fewer bytes) than the original
                re_encoded = decoded.encode('utf-8')
                if len(re_encoded) < len(chunk) and all(ord(c) > 127 for c in decoded if not c.isascii()):
                    result.extend(re_encoded)
                    fixed_count += 1
                    i = j
                    continue
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
            
            result.append(raw_bytes[i])
            i += 1
        else:
            result.append(raw_bytes[i])
            i += 1
    
    return bytes(result), fixed_count


for filename in os.listdir(templates_dir):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(templates_dir, filename)
    
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    # Check for non-ASCII bytes beyond BOM
    has_high_bytes = False
    start = 3 if raw[:3] == b'\xef\xbb\xbf' else 0
    for b in raw[start:]:
        if b > 127:
            has_high_bytes = True
            break
    
    if not has_high_bytes:
        continue
    
    # Try the simple full-file approach first: decode as utf8, encode as latin1, decode as utf8
    try:
        text = raw.decode('utf-8')
        # Try to find and fix mojibake patterns
        # Look for common mojibake signatures
        mojibake_patterns = [
            b'\xc3\xa2\xc5\x93',  # double-encoded
            b'\xc3\xa2\xe2\x80',  # double-encoded
            b'\xc3\xa2\xe2\x82',  # double-encoded  
            b'\xc3\x83',          # double-encoded A-tilde area
            b'\xc5\x93',          # double-encoded
            b'\xc5\xa1',          # double-encoded
            b'\xc2\xa0',          # NBSP (might be intentional, skip)
        ]
        
        has_mojibake = any(p in raw for p in mojibake_patterns[:6])
        
        if has_mojibake:
            fixed, count = try_fix_double_encoded(raw)
            if count > 0:
                print(f"FIXED: {filename} - {count} double-encoded sequences repaired")
                with open(filepath, 'wb') as f:
                    f.write(fixed)
            else:
                print(f"SUSPICIOUS but couldn't auto-fix: {filename}")
        
    except UnicodeDecodeError:
        print(f"BROKEN UTF-8: {filename}")

print("\nDone!")
