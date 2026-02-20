#!/usr/bin/env python3
"""
Persona Generator — Unique Personas Mode for Profile Automation V2
Generates unique SK/CZ personas (username, bio, pic category) for selected accounts.
Uses data from data/sk_cz_names.json and data/sk_cz_bios.json.
"""

import json
import random
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

DATA_DIR = Path(__file__).parent.parent / "data"

# Profile picture category distribution (must sum to 1.0)
PIC_CATEGORIES = {
    "face_selfie": 0.30,
    "full_body_lifestyle": 0.20,
    "aesthetic_artistic": 0.15,
    "mirror_selfie_gym": 0.15,
    "back_view_silhouette": 0.10,
    "other_diverse": 0.10,
}


def _load_json(filename):
    with open(DATA_DIR / filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def _remove_diacritics(text, mapping):
    """Remove Slovak/Czech diacritics using the mapping table."""
    result = text
    for char, replacement in mapping.items():
        result = result.replace(char, replacement)
    return result


def _generate_username(gender, names_data, used_usernames, rng):
    """Generate a unique, natural-looking Instagram username."""
    diacritics = names_data['diacritics_removal']
    patterns = names_data['username_patterns']
    nicknames = names_data.get('nicknames', {})

    if gender == 'female':
        first_names = names_data['female_first_names']
        surnames = names_data['female_surnames']
        nick_map = nicknames.get('female', {})
    else:
        first_names = names_data['male_first_names']
        surnames = names_data['male_surnames']
        nick_map = nicknames.get('male', {})

    max_attempts = 200
    for attempt in range(max_attempts):
        first_name = rng.choice(first_names)
        surname = rng.choice(surnames)

        # 35% chance to use nickname
        use_nickname = rng.random() < 0.35 and first_name in nick_map
        if use_nickname:
            nickname = rng.choice(nick_map[first_name])
        else:
            nickname = first_name

        # Remove diacritics
        first_clean = _remove_diacritics(first_name, diacritics).lower()
        last_clean = _remove_diacritics(surname, diacritics).lower()
        nick_clean = _remove_diacritics(nickname, diacritics).lower()
        last_initial = last_clean[0] if last_clean else ''
        first_lower_doubled_last_char = first_clean[-1] if first_clean else ''

        # Generate birth year and random number
        birth_year = rng.randint(
            names_data['birth_year_range']['min'],
            names_data['birth_year_range']['max']
        )
        birth_year_short = str(birth_year)[-2:]
        random_num = str(rng.randint(1, 999))

        pattern = rng.choice(patterns)

        try:
            username = pattern.format(
                first_lower=first_clean,
                last_lower=last_clean,
                nickname_lower=nick_clean,
                first_initial=first_clean[0],
                last_initial=last_initial,
                first_lower_doubled_last_char=first_lower_doubled_last_char,
                birth_year=str(birth_year),
                birth_year_short=birth_year_short,
                random_num=random_num,
                num=random_num
            )
        except (KeyError, IndexError):
            continue

        # Clean: only a-z, 0-9, dots, underscores
        username = re.sub(r'[^a-z0-9._]', '', username)
        username = re.sub(r'\.{2,}', '.', username)
        username = re.sub(r'_{2,}', '_', username)
        username = username[:30].strip('._')

        if len(username) < 4 or username in used_usernames:
            continue

        return username, first_name, surname

    # Fallback
    first_name = rng.choice(first_names if gender == 'female' else names_data['male_first_names'])
    first_clean = _remove_diacritics(first_name, diacritics).lower()
    for _ in range(50):
        fallback = f"{first_clean}{rng.randint(1000, 99999)}"
        if fallback not in used_usernames:
            return fallback, first_name, ""

    uid = rng.randint(100000, 999999)
    return f"user_{uid}", "User", ""


def _assign_bio(gender, female_pool, male_pool, neutral_pool, minimal_pool,
                used_bios, rng, bio_components=None):
    """Assign a bio with realistic distribution."""
    roll = rng.random()

    if roll < 0.15:
        available = [b for b in minimal_pool if b not in used_bios or b == ""]
        if available:
            bio = rng.choice(available)
            if bio != "":
                used_bios.add(bio)
            return bio

    if roll < 0.30:
        available = [b for b in neutral_pool if b not in used_bios]
        if available:
            bio = rng.choice(available)
            used_bios.add(bio)
            return bio

    pool = female_pool if gender == 'female' else male_pool
    available = [b for b in pool if b not in used_bios]

    if available:
        bio = rng.choice(available)
        used_bios.add(bio)
        return bio

    # Fallback: neutral
    available = [b for b in neutral_pool if b not in used_bios]
    if available:
        bio = rng.choice(available)
        used_bios.add(bio)
        return bio

    # Fallback: combinatorial
    if bio_components:
        return _generate_combinatorial_bio(bio_components, used_bios, rng)

    return ""


def _generate_combinatorial_bio(components, used_bios, rng):
    """Generate a bio from combinatorial components as fallback."""
    cities = components.get('cities', ['Bratislava'])
    city_abbr = components.get('city_abbreviations', {})
    age_range = components.get('age_range', {'min': 18, 'max': 27})

    patterns = [
        "{age} | {city_short}",
        "📍{city}",
        "{age} | 📍{city_short}",
        "📍{city_short} 🇸🇰",
        "{age}",
        "{city_short} 📍",
        "📍{city} | {age}",
        "{age} | {city_short} | 🇸🇰",
    ]

    city = rng.choice(cities)
    age = str(rng.randint(age_range['min'], age_range['max']))
    city_short = city_abbr.get(city, city)

    pattern = rng.choice(patterns)
    bio = pattern.format(city=city, city_short=city_short, age=age)

    if bio not in used_bios:
        used_bios.add(bio)
        return bio

    return f"{age} | {city_short}"


def _assign_pic_category(rng):
    """Assign a profile picture category based on distribution."""
    roll = rng.random()
    cumulative = 0
    for cat, pct in PIC_CATEGORIES.items():
        cumulative += pct
        if roll <= cumulative:
            return cat
    return "face_selfie"


def generate_personas(account_ids, gender_split=0.7, age_range=None, seed=None):
    """
    Generate unique persona assignments for a list of account IDs.

    Args:
        account_ids: List of account ID integers
        gender_split: Fraction female (0.0 to 1.0), default 0.7
        age_range: [min_age, max_age], default [18, 28]
        seed: Random seed for reproducibility (None = random)

    Returns:
        List of persona dicts with: account_id, gender, new_username,
        persona_name, new_bio, pic_category
    """
    if age_range is None:
        age_range = [18, 28]

    names_data = _load_json('sk_cz_names.json')
    bios_data = _load_json('sk_cz_bios.json')

    rng = random.Random(seed)

    num_accounts = len(account_ids)
    num_female = round(num_accounts * gender_split)
    num_male = num_accounts - num_female

    # Build gender list and shuffle
    genders = ['female'] * num_female + ['male'] * num_male
    rng.shuffle(genders)

    # Bio pools
    female_pool = list(bios_data.get('female_bios', []))
    male_pool = list(bios_data.get('male_bios', []))
    neutral_pool = list(bios_data.get('neutral_bios', []))
    minimal_pool = list(bios_data.get('minimal_bios', []))
    bio_components = bios_data.get('bio_components', {})

    # Override age range in names data for username generation
    if age_range:
        current_year = datetime.now().year
        names_data['birth_year_range'] = {
            'min': current_year - age_range[1],
            'max': current_year - age_range[0]
        }

    used_usernames = set()
    used_bios = set()
    assignments = []

    for i, account_id in enumerate(account_ids):
        gender = genders[i] if i < len(genders) else 'female'

        # Generate username
        username, first_name, surname = _generate_username(
            gender, names_data, used_usernames, rng
        )
        used_usernames.add(username)

        # Assign bio
        bio = _assign_bio(
            gender, female_pool, male_pool, neutral_pool,
            minimal_pool, used_bios, rng, bio_components
        )

        # Assign pic category
        pic_category = _assign_pic_category(rng)

        assignments.append({
            'account_id': account_id,
            'gender': gender,
            'new_username': username,
            'persona_name': f"{first_name} {surname}".strip(),
            'new_bio': bio,
            'pic_category': pic_category,
        })

    return assignments


def regenerate_single(gender, existing_usernames=None, seed=None):
    """
    Regenerate a single persona assignment.
    Used when user clicks "regenerate" on a single row.

    Args:
        gender: 'female' or 'male'
        existing_usernames: Set of usernames to avoid duplicates
        seed: Random seed

    Returns:
        Dict with new_username, persona_name, new_bio, pic_category
    """
    if existing_usernames is None:
        existing_usernames = set()

    names_data = _load_json('sk_cz_names.json')
    bios_data = _load_json('sk_cz_bios.json')

    rng = random.Random(seed)

    female_pool = list(bios_data.get('female_bios', []))
    male_pool = list(bios_data.get('male_bios', []))
    neutral_pool = list(bios_data.get('neutral_bios', []))
    minimal_pool = list(bios_data.get('minimal_bios', []))
    bio_components = bios_data.get('bio_components', {})

    username, first_name, surname = _generate_username(
        gender, names_data, existing_usernames, rng
    )

    used_bios = set()
    bio = _assign_bio(
        gender, female_pool, male_pool, neutral_pool,
        minimal_pool, used_bios, rng, bio_components
    )

    pic_category = _assign_pic_category(rng)

    return {
        'gender': gender,
        'new_username': username,
        'persona_name': f"{first_name} {surname}".strip(),
        'new_bio': bio,
        'pic_category': pic_category,
    }


def get_pic_category_stats(assignments):
    """Get picture category distribution from assignments."""
    counts = Counter(a['pic_category'] for a in assignments)
    total = len(assignments) or 1
    return {
        cat: {
            'count': counts.get(cat, 0),
            'pct': round(counts.get(cat, 0) / total * 100, 1)
        }
        for cat in PIC_CATEGORIES
    }


def get_gender_stats(assignments):
    """Get gender distribution from assignments."""
    counts = Counter(a['gender'] for a in assignments)
    total = len(assignments) or 1
    return {
        'female': counts.get('female', 0),
        'male': counts.get('male', 0),
        'female_pct': round(counts.get('female', 0) / total * 100, 1),
        'male_pct': round(counts.get('male', 0) / total * 100, 1),
    }
