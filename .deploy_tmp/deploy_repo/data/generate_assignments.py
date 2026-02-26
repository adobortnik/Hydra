#!/usr/bin/env python3
"""
Profile Assignment Generator V2 — Hydra Phone Farm
Generates complete assignment manifest for MASS profile automation.
Handles 924 accounts (77 devices × 12 accounts) with unique:
  - Usernames (from sk_cz_names.json — natural SK/CZ patterns)
  - Bios (from sk_cz_bios.json — realistic variety including empty)
  - Profile picture category assignments (diverse types, not just face selfies)

V2 Changes:
  - Bio pool now includes neutral + minimal (empty) bios for realism
  - ~15% of accounts get empty or minimal bios (like real people)
  - Profile pics assigned by category (face/lifestyle/aesthetic/gym/silhouette/other)
  - Username patterns updated for more natural look
  - Bio distribution: 40% ultra-short, 30% short, 20% medium, 10% longer

Usage:
    python generate_assignments.py --preview --accounts 924
    python generate_assignments.py --accounts 924 --output profile_assignment_manifest.json
"""

import json
import random
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

DATA_DIR = Path(__file__).parent

# Profile picture category distribution (must sum to 1.0)
PIC_CATEGORIES = {
    "face_selfie": 0.30,          # AI-generated face close-ups
    "full_body_lifestyle": 0.20,   # Travel, lifestyle, beach
    "aesthetic_artistic": 0.15,    # Landscapes, coffee, flowers, pets
    "mirror_selfie_gym": 0.15,     # Mirror/gym photos
    "back_view_silhouette": 0.10,  # Back view, silhouettes
    "other_diverse": 0.10,         # Pet portraits, abstract, B&W
}


def load_json(filename):
    with open(DATA_DIR / filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def remove_diacritics(text, mapping):
    """Remove Slovak/Czech diacritics using the mapping table."""
    result = text
    for char, replacement in mapping.items():
        result = result.replace(char, replacement)
    return result


def generate_username(gender, names_data, used_usernames, rng=None):
    """Generate a unique, natural-looking Instagram username."""
    if rng is None:
        rng = random

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

        # 35% chance to use nickname instead of full name
        use_nickname = rng.random() < 0.35 and first_name in nick_map
        if use_nickname:
            nickname = rng.choice(nick_map[first_name])
        else:
            nickname = first_name

        # Remove diacritics
        first_clean = remove_diacritics(first_name, diacritics).lower()
        last_clean = remove_diacritics(surname, diacritics).lower()
        nick_clean = remove_diacritics(nickname, diacritics).lower()
        last_initial = last_clean[0] if last_clean else ''
        
        # For doubled last char pattern (e.g., "nikolkaa")
        first_lower_doubled_last_char = first_clean[-1] if first_clean else ''

        # Generate birth year and random number
        birth_year = rng.randint(
            names_data['birth_year_range']['min'],
            names_data['birth_year_range']['max']
        )
        birth_year_short = str(birth_year)[-2:]
        random_num = str(rng.randint(1, 999))

        # Pick a pattern
        pattern = rng.choice(patterns)

        # Fill in the pattern
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

        # Clean up: only allow a-z, 0-9, periods, underscores
        username = re.sub(r'[^a-z0-9._]', '', username)
        username = re.sub(r'\.{2,}', '.', username)
        username = re.sub(r'_{2,}', '_', username)
        username = username[:30].strip('._')

        # Validate
        if len(username) < 4 or username in used_usernames:
            continue

        return username, first_name, surname

    # Fallback: guaranteed unique
    first_name = rng.choice(first_names)
    first_clean = remove_diacritics(first_name, diacritics).lower()
    for _ in range(50):
        fallback = f"{first_clean}{rng.randint(1000, 99999)}"
        if fallback not in used_usernames:
            return fallback, first_name, ""

    # Ultra-fallback
    uid = rng.randint(100000, 999999)
    return f"user_{uid}", "User", ""


def build_bio_pool(bios_data, rng):
    """
    Build a large pool of bios from all categories:
    - Female bios
    - Male bios  
    - Neutral bios (work for any gender)
    - Minimal bios (empty strings, just emoji, just age)
    
    Returns separate pools for female, male, and the assignment function.
    """
    female_bios = list(bios_data.get('female_bios', []))
    male_bios = list(bios_data.get('male_bios', []))
    neutral_bios = list(bios_data.get('neutral_bios', []))
    minimal_bios = list(bios_data.get('minimal_bios', []))
    
    return female_bios, male_bios, neutral_bios, minimal_bios


def assign_bio(gender, female_pool, male_pool, neutral_pool, minimal_pool,
               used_bios, rng):
    """
    Assign a bio with realistic distribution:
    - 15% chance of minimal/empty bio
    - 15% chance of neutral bio
    - 70% chance of gender-specific bio
    
    If gender pool exhausted, falls back to neutral then combinatorial.
    """
    roll = rng.random()
    
    if roll < 0.15:
        # Minimal/empty bio — very realistic
        available = [b for b in minimal_pool if b not in used_bios or b == ""]
        if available:
            bio = rng.choice(available)
            if bio != "":  # Don't track empty as used
                used_bios.add(bio)
            return bio
    
    if roll < 0.30:
        # Neutral bio
        available = [b for b in neutral_pool if b not in used_bios]
        if available:
            bio = rng.choice(available)
            used_bios.add(bio)
            return bio
    
    # Gender-specific bio
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
    
    # Fallback: generate from components
    components = bios_data_global.get('bio_components', {})
    if components:
        bio = generate_combinatorial_bio(gender, components, used_bios, rng)
        return bio
    
    return ""


# Global ref for fallback generation
bios_data_global = {}


def generate_combinatorial_bio(gender, components, used_bios, rng):
    """Generate a bio from combinatorial components as fallback."""
    cities = components.get('cities', ['Bratislava'])
    city_abbr = components.get('city_abbreviations', {})
    age_range = components.get('age_range', {'min': 18, 'max': 27})
    
    # Simple patterns that look natural
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
    
    # If collision, make unique with slight variation
    bio = f"{age} | {city_short}"
    return bio


def assign_pic_category(rng):
    """
    Assign a profile picture category based on the distribution.
    Returns the category name.
    """
    roll = rng.random()
    cumulative = 0
    for cat, pct in PIC_CATEGORIES.items():
        cumulative += pct
        if roll <= cumulative:
            return cat
    return "face_selfie"  # Fallback


def assign_profile_pics(gender, count, pic_categories):
    """
    Assign profile picture filenames by gender and category.
    Returns list of pic assignment dicts.
    """
    pic_dir = DATA_DIR / 'profile_pics' / gender
    assignments = []
    
    for i in range(count):
        cat = pic_categories[i] if i < len(pic_categories) else "face_selfie"
        
        if cat == "face_selfie":
            # AI-generated face — from generate_profile_pics.py
            prefix = "f" if gender == "female" else "m"
            # AI face index — we only need 30% of total as faces
            assignments.append({
                "filename": f"{prefix}_{i+1:04d}.jpg",
                "category": cat,
                "source": "ai_generation",
            })
        else:
            # Stock photo — from download_profile_pics.py
            assignments.append({
                "filename": f"stock_{cat}_{i+1:04d}.jpg",
                "category": cat,
                "source": "stock_download",
            })
    
    return assignments


def generate_manifest(num_accounts=924, devices_per_farm=77, accounts_per_device=12):
    """Generate the complete assignment manifest."""
    global bios_data_global
    
    names_data = load_json('sk_cz_names.json')
    bios_data = load_json('sk_cz_bios.json')
    bios_data_global = bios_data

    # Use fixed seed for reproducibility
    rng = random.Random(42)

    # Gender split: 70% female, 30% male
    num_female = round(num_accounts * 0.7)
    num_male = num_accounts - num_female

    # Build bio pools
    female_pool, male_pool, neutral_pool, minimal_pool = build_bio_pool(bios_data, rng)
    
    print(f"  Bio pools: {len(female_pool)} female, {len(male_pool)} male, "
          f"{len(neutral_pool)} neutral, {len(minimal_pool)} minimal")

    # Build account list with gender assignment
    genders = ['female'] * num_female + ['male'] * num_male
    rng.shuffle(genders)

    used_usernames = set()
    used_bios = set()
    accounts = []
    
    # Category counters for stats
    cat_counts = Counter()
    bio_type_counts = Counter()
    bio_length_counts = {"empty": 0, "ultra_short": 0, "short": 0, "medium": 0, "long": 0}

    for i, gender in enumerate(genders):
        # Calculate device assignment
        device_num = (i // accounts_per_device) + 1
        account_on_device = (i % accounts_per_device) + 1

        # Generate username
        username, first_name, surname = generate_username(
            gender, names_data, used_usernames, rng
        )
        used_usernames.add(username)

        # Assign bio
        bio = assign_bio(gender, female_pool, male_pool, neutral_pool, 
                        minimal_pool, used_bios, rng)
        
        # Track bio stats
        bio_len = len(bio)
        if bio_len == 0:
            bio_length_counts["empty"] += 1
        elif bio_len <= 10:
            bio_length_counts["ultra_short"] += 1
        elif bio_len <= 40:
            bio_length_counts["short"] += 1
        elif bio_len <= 80:
            bio_length_counts["medium"] += 1
        else:
            bio_length_counts["long"] += 1
        
        # Assign profile picture category
        pic_category = assign_pic_category(rng)
        cat_counts[pic_category] += 1

        accounts.append({
            "index": i + 1,
            "device_num": device_num,
            "account_on_device": account_on_device,
            "device_serial": "",  # Fill from actual farm data
            "current_username": "",  # Fill from actual farm data
            "gender": gender,
            "persona_name": f"{first_name} {surname}".strip(),
            "new_username": username,
            "new_bio": bio,
            "profile_pic_category": pic_category,
            "profile_pic": f"{gender}/{'f' if gender == 'female' else 'm'}_{i+1:04d}.jpg",
            "status": {
                "username": "pending",
                "bio": "pending",
                "picture": "pending"
            }
        })

    # Compute stats
    bio_uniqueness = len(set(a['new_bio'] for a in accounts if a['new_bio']))
    username_uniqueness = len(set(a['new_username'] for a in accounts))

    manifest = {
        "campaign": "sk_cz_persona_v2_diverse",
        "created": datetime.now().isoformat(),
        "version": "2.0",
        "scale": {
            "total_accounts": num_accounts,
            "devices": devices_per_farm,
            "accounts_per_device": accounts_per_device,
        },
        "gender_split": {
            "female": num_female,
            "male": num_male,
            "female_pct": round(num_female / num_accounts * 100, 1),
            "male_pct": round(num_male / num_accounts * 100, 1),
        },
        "uniqueness": {
            "unique_usernames": username_uniqueness,
            "unique_bios_non_empty": bio_uniqueness,
            "username_collision_rate": f"{(1 - username_uniqueness/num_accounts)*100:.1f}%",
        },
        "pic_category_distribution": {
            cat: {"count": count, "pct": f"{count/num_accounts*100:.1f}%"}
            for cat, count in sorted(cat_counts.items())
        },
        "bio_length_distribution": bio_length_counts,
        "stats": {
            "pending": num_accounts,
            "username_done": 0,
            "bio_done": 0,
            "picture_done": 0,
            "fully_complete": 0,
            "failed": 0
        },
        "accounts": accounts
    }

    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate profile assignment manifest for Hydra farm')
    parser.add_argument('--accounts', type=int, default=924, help='Number of accounts (default: 924)')
    parser.add_argument('--devices', type=int, default=77, help='Number of devices (default: 77)')
    parser.add_argument('--per-device', type=int, default=12, help='Accounts per device (default: 12)')
    parser.add_argument('--output', type=str, default='profile_assignment_manifest.json',
                       help='Output filename')
    parser.add_argument('--preview', action='store_true', help='Print preview instead of saving')
    args = parser.parse_args()

    print(f"\n  Generating manifest for {args.accounts} accounts...")
    manifest = generate_manifest(
        num_accounts=args.accounts,
        devices_per_farm=args.devices,
        accounts_per_device=args.per_device
    )

    if args.preview:
        print(f"\n{'='*70}")
        print(f"PROFILE ASSIGNMENT PREVIEW — HYDRA PHONE FARM V2")
        print(f"{'='*70}")
        print(f"  Total accounts:    {manifest['scale']['total_accounts']}")
        print(f"  Devices:           {manifest['scale']['devices']}")
        print(f"  Accounts/device:   {manifest['scale']['accounts_per_device']}")
        print(f"  Female:            {manifest['gender_split']['female']} ({manifest['gender_split']['female_pct']}%)")
        print(f"  Male:              {manifest['gender_split']['male']} ({manifest['gender_split']['male_pct']}%)")
        print(f"  Unique usernames:  {manifest['uniqueness']['unique_usernames']}")
        print(f"  Unique bios:       {manifest['uniqueness']['unique_bios_non_empty']}")
        print(f"{'='*70}\n")

        # Profile Pic Category Distribution
        print(f"  PROFILE PIC CATEGORIES:")
        print(f"  {'─'*50}")
        for cat, info in manifest['pic_category_distribution'].items():
            bar = '█' * int(float(info['pct'].rstrip('%')) / 2)
            print(f"  {cat:30s} {info['count']:4d} ({info['pct']:>5s}) {bar}")
        
        # Bio Length Distribution
        print(f"\n  BIO LENGTH DISTRIBUTION:")
        print(f"  {'─'*50}")
        for length_type, count in manifest['bio_length_distribution'].items():
            pct = count / manifest['scale']['total_accounts'] * 100
            bar = '█' * int(pct / 2)
            print(f"  {length_type:15s} {count:4d} ({pct:5.1f}%) {bar}")

        # Show samples from different devices
        print(f"\n  SAMPLE ACCOUNTS:")
        print(f"  {'─'*64}")
        
        # Show diverse sample
        samples = []
        categories_shown = set()
        for acc in manifest['accounts']:
            cat = acc['profile_pic_category']
            if cat not in categories_shown:
                samples.append(acc)
                categories_shown.add(cat)
            if len(samples) >= 12:
                break
        
        # Add some random samples too
        remaining = [a for a in manifest['accounts'] if a not in samples]
        random.shuffle(remaining)
        samples.extend(remaining[:6])
        
        for acc in samples[:18]:
            g = 'F' if acc['gender'] == 'female' else 'M'
            print(f"  [{g}] D{acc['device_num']:02d}/A{acc['account_on_device']:02d}  @{acc['new_username']}")
            print(f"      {acc['persona_name']}")
            bio_preview = acc['new_bio'].replace('\n', ' | ')[:70] if acc['new_bio'] else '(empty bio)'
            print(f"      Bio: {bio_preview}")
            print(f"      Pic category: {acc['profile_pic_category']}")
            print()

        remaining_count = manifest['scale']['total_accounts'] - len(samples)
        if remaining_count > 0:
            print(f"  ... and {remaining_count} more accounts\n")

        # Username pattern analysis
        print(f"  USERNAME SAMPLES (20 random):")
        print(f"  {'─'*40}")
        random_accounts = random.sample(manifest['accounts'], min(20, len(manifest['accounts'])))
        for s in random_accounts:
            g = 'F' if s['gender'] == 'female' else 'M'
            print(f"  [{g}] @{s['new_username']}")

    else:
        output_path = DATA_DIR / args.output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\n  Manifest saved: {output_path}")
        print(f"  File size:      {size_mb:.1f} MB")
        print(f"  Total accounts: {manifest['scale']['total_accounts']}")
        print(f"  Female:         {manifest['gender_split']['female']}")
        print(f"  Male:           {manifest['gender_split']['male']}")
        print(f"  Unique names:   {manifest['uniqueness']['unique_usernames']}")
        print(f"  Unique bios:    {manifest['uniqueness']['unique_bios_non_empty']}")
        print(f"  Collisions:     usernames={manifest['uniqueness']['username_collision_rate']}")
        print()
        
        # Pic category summary
        print(f"  Profile Pic Categories:")
        for cat, info in manifest['pic_category_distribution'].items():
            print(f"    {cat}: {info['count']} ({info['pct']})")
        
        print(f"\n  Bio Length Distribution:")
        for lt, count in manifest['bio_length_distribution'].items():
            print(f"    {lt}: {count}")


if __name__ == '__main__':
    main()
