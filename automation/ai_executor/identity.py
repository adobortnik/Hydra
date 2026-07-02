"""
Identity generator — per-account data for the Account Factory.

Account creation (Gmail signup, IG signup, profile) needs realistic, unique
values for each account: name, username, password, birthday. This module
produces them so a single RECORDED recipe can be REPLAYED across many accounts
with different data (the recipe stores `{first_name}` / `{username}` / ... and
the executor substitutes a fresh identity per run).

Pure-stdlib (no external deps). Username follows IG/Gmail rules.
"""

import random
import re

_FIRST_M = [
    'Jack', 'Liam', 'Noah', 'Ethan', 'Mason', 'Lucas', 'Leo', 'Adam', 'Max',
    'Marco', 'David', 'Filip', 'Samuel', 'Oliver', 'Daniel', 'Martin', 'Tomas',
    'Andrej', 'Patrik', 'Matej', 'Erik', 'Robert', 'Peter', 'Michal', 'Jakub',
]
_FIRST_F = [
    'Emma', 'Olivia', 'Mia', 'Sofia', 'Nina', 'Lena', 'Sara', 'Ema', 'Laura',
    'Nikol', 'Klara', 'Tereza', 'Viktoria', 'Natalia', 'Simona', 'Lucia',
    'Kristina', 'Barbora', 'Dominika', 'Petra', 'Veronika', 'Karolina',
]
_LAST = [
    'Harrer', 'Paluan', 'Novak', 'Kovac', 'Horvath', 'Varga', 'Toth', 'Nagy',
    'Balog', 'Marek', 'Hudak', 'Krause', 'Weber', 'Fischer', 'Meyer', 'Bauer',
    'Moretti', 'Russo', 'Ferrari', 'Costa', 'Romano', 'Bruno', 'Greco',
]

_THEMES = [
    'fit', 'travel', 'food', 'style', 'life', 'daily', 'vibes', 'world',
    'official', 'real', 'home', 'art', 'moto', 'gym', 'eats', 'shots',
]


def _slug(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _ig_username(base, suffix=None, max_len=30):
    """Make an IG/Gmail-valid handle: lowercase a-z0-9 . _, no leading/trailing
    or consecutive separators, <= max_len."""
    base = _slug(base) or 'user'
    if suffix:
        h = f'{base}_{_slug(suffix)}'
    else:
        h = base
    h = re.sub(r'[._]{2,}', '_', h).strip('._')
    return h[:max_len].strip('._')


_PW_WORDS = ['Happy', 'Sunny', 'Lucky', 'Coffee', 'Summer', 'Winter', 'Tiger',
             'Eagle', 'River', 'Ocean', 'Maple', 'Cosmic', 'Turbo', 'Magic',
             'Rocket', 'Falcon', 'Panda', 'Mango', 'Cherry', 'Silver', 'Golden',
             'Bright', 'Storm', 'Jungle', 'Smooth', 'Royal', 'Cyber', 'Neon']


def gmail_password(length=None):
    """Simple, HUMAN-LIKE password (a capitalized word + digits, e.g. Sunny4821).
    Meets Google's rules (8+ chars, upper+lower+digit), no symbols — a complex
    random password pasted instantly looks bot-ish and triggers phone challenges;
    a memorable one typed char-by-char passes more often."""
    word = random.choice(_PW_WORDS)
    return f'{word}{random.randint(100, 99999)}'


def generate_identity(naming_base=None, theme=None, index=None,
                      gender=None, username=None, min_age=19, max_age=38,
                      email_domain=None):
    """Return one account identity.

    naming_base  mother/brand stem for the handle (e.g. 'jackharrer')
    theme        suffix word (e.g. 'fit' -> jackharrer_fit). Random if omitted.
    index        optional integer to vary/deduplicate (appended if needed)
    username     explicit handle override (skips generation)
    gender       'm' | 'f' | None (random)
    email_domain catch-all domain (e.g. 'ourdomain.com'). When set the identity
                 is a SLAVE: its email is `<local>@<domain>` and the IG code is
                 read over IMAP — no Gmail created on device. When omitted the
                 email defaults to <local>@gmail.com (MOTHER / real-Gmail path).
    Returns a dict with first_name, last_name, full_name, username, password,
    birth_day, birth_month, birth_year, birth_month_name, gender, email_local,
    email, email_domain, account_type.
    """
    g = gender or random.choice(['m', 'f'])
    first = random.choice(_FIRST_M if g == 'm' else _FIRST_F)
    last = random.choice(_LAST)
    full = f'{first} {last}'

    if username:
        handle = _ig_username(username)
    elif naming_base:
        th = theme or random.choice(_THEMES)
        handle = _ig_username(naming_base, th)
        if index is not None:
            handle = _ig_username(f'{handle}{index}')
    else:
        th = theme or random.choice(_THEMES)
        handle = _ig_username(f'{first}{last}', th)
        if index is not None:
            handle = _ig_username(f'{handle}{index}')

    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December']
    ref_year = 2026  # plausible birth-year window reference
    age = random.randint(min_age, max_age)
    byear = ref_year - age
    # Jan-May only: Google's month dropdown shows ~5 options without scrolling,
    # and the executor can't reliably scroll that popup — so we always pick a
    # month that's directly tappable (the exact month is irrelevant for the acct).
    bmonth = random.randint(1, 5)
    bday = random.randint(2, 28)   # avoid always-"1" (looks bot-ish / repetitive)

    # Gmail address local-part: name-based, Gmail-VALID (letters + digits only,
    # NO underscore — Gmail rejects '_'; the IG `username` may keep underscores).
    email_local = _slug(first) + _slug(last) + str(random.randint(10, 9999))
    dom = (email_domain or '').strip().lstrip('@').lower() or None
    if dom:
        email = f'{email_local}@{dom}'      # catch-all slave address
        acct_type = 'slave'
    else:
        email = f'{email_local}@gmail.com'  # real-Gmail mother path
        acct_type = 'mother'
    return {
        'first_name': first,
        'last_name': last,
        'full_name': full,
        'username': handle,             # IG handle (naming scheme, may have '_')
        'password': gmail_password(),
        'birth_day': str(bday),
        'birth_month': str(bmonth),
        'birth_month_name': months[bmonth - 1],
        'birth_year': str(byear),
        'gender': g,
        'email_local': email_local,     # local part (name-based, no '_')
        'email': email,                 # full address (catch-all or gmail)
        'email_domain': dom,            # None => gmail/mother
        'account_type': acct_type,
    }


def generate_batch(naming_base, count, themes=None, start_index=1,
                   email_domain=None):
    """Generate `count` identities for a mother's slaves with a naming scheme:
    jackharrer_fit, jackharrer_travel, ... (unique handles). When email_domain
    is set, every slave gets a unique catch-all address (no Gmail per device)."""
    themes = list(themes or _THEMES)
    random.shuffle(themes)
    out, seen, seen_email = [], set(), set()
    i = start_index
    for n in range(count):
        theme = themes[n % len(themes)]
        ident = generate_identity(naming_base=naming_base, theme=theme,
                                  email_domain=email_domain)
        # ensure unique handle AND unique email local-part
        idx = i
        while ident['username'] in seen or ident['email'] in seen_email:
            ident = generate_identity(naming_base=naming_base, theme=theme,
                                      index=idx, email_domain=email_domain)
            idx += 1
        seen.add(ident['username'])
        seen_email.add(ident['email'])
        out.append(ident)
        i += 1
    return out
