#!/usr/bin/env python3
"""
AI Profile Generator
Generates usernames and bios using AI API based on mother account
"""

import requests
import json
import random
from pathlib import Path

class AIProfileGenerator:
    """
    Generate profile content using AI
    Supports multiple AI providers (OpenAI, Anthropic, custom endpoints)
    """

    def __init__(self, api_endpoint=None, api_key=None, provider="openai"):
        """
        Initialize AI generator

        Args:
            api_endpoint: Custom API endpoint (optional)
            api_key: API key for the service
            provider: "openai", "anthropic", or "custom"
        """
        self.api_key = api_key
        self.provider = provider

        # Default endpoints
        if api_endpoint:
            self.api_endpoint = api_endpoint
        elif provider == "openai":
            self.api_endpoint = "https://api.openai.com/v1/chat/completions"
        elif provider == "anthropic":
            self.api_endpoint = "https://api.anthropic.com/v1/messages"
        else:
            self.api_endpoint = None

    def generate_username(self, mother_account, current_username=None, variations_count=5, name_shortcuts=None):
        """
        Generate username based on mother account

        Args:
            mother_account: Username of the mother account to base on
            current_username: Current username (optional, for context)
            variations_count: Number of variations to generate
            name_shortcuts: Optional list of name variations to use as base

        Returns:
            str: Generated username
        """
        if not self.api_key or not self.api_endpoint:
            # Fallback to algorithmic generation
            return self._generate_username_fallback(mother_account)

        prompt = self._create_username_prompt(mother_account, current_username, variations_count, name_shortcuts)

        try:
            response = self._call_ai_api(prompt)
            username = self._extract_username_from_response(response)

            # Validate Instagram username rules
            username = self._validate_username(username)

            # Safety check: if validation stripped it to something too short/just numbers, use fallback
            if len(username) < 4 or username.isdigit():
                print(f"AI returned invalid username after validation: '{username}', using fallback")
                return self._generate_username_fallback(mother_account)

            return username

        except Exception as e:
            print(f"AI username generation failed: {e}")
            return self._generate_username_fallback(mother_account)

    def generate_usernames_batch(self, mother_account, count=5, name_shortcuts=None):
        """
        Generate multiple usernames in a single AI call.

        Args:
            mother_account: Username of the mother account to base on
            count: Number of usernames to generate
            name_shortcuts: Optional list of name variations to use as base

        Returns:
            list: List of generated usernames
        """
        if not self.api_key or not self.api_endpoint:
            # Fallback to algorithmic generation
            return [self._generate_username_fallback(mother_account, index=i) for i in range(count)]

        prompt = self._create_username_prompt(mother_account, None, count, name_shortcuts)

        try:
            response = self._call_ai_api(prompt)
            usernames = self._extract_usernames_batch_from_response(response)

            # Validate each username
            validated = []
            for u in usernames:
                v = self._validate_username(u)
                if len(v) >= 4 and not v.isdigit():
                    validated.append(v)

            # If we got enough valid ones, return them
            if len(validated) >= count:
                return validated[:count]

            # Fill remaining with fallbacks
            for i in range(count - len(validated)):
                validated.append(self._generate_username_fallback(mother_account, index=len(validated) + i))

            return validated[:count]

        except Exception as e:
            print(f"AI batch username generation failed: {e}")
            return [self._generate_username_fallback(mother_account, index=i) for i in range(count)]

    def generate_bio(self, mother_account, mother_bio=None, account_number=None):
        """
        Generate bio based on mother account's bio

        Args:
            mother_account: Username of mother account
            mother_bio: Bio of mother account to base variation on
            account_number: Number/index of this account (for variations)

        Returns:
            str: Generated bio
        """
        if not self.api_key or not self.api_endpoint:
            # Fallback to template variation
            return self._generate_bio_fallback(mother_bio)

        prompt = self._create_bio_prompt(mother_account, mother_bio, account_number)

        try:
            response = self._call_ai_api(prompt)
            bio = self._extract_bio_from_response(response)

            # Validate bio length (Instagram limit: 150 characters)
            if len(bio) > 150:
                bio = bio[:147] + "..."

            return bio

        except Exception as e:
            print(f"AI bio generation failed: {e}")
            return self._generate_bio_fallback(mother_bio)

    def _create_username_prompt(self, mother_account, current_username, count, name_shortcuts=None):
        """Create prompt for username generation"""
        prompt = f"""Generate exactly {count} unique Instagram username variations inspired by: {mother_account}

"""
        if name_shortcuts:
            prompt += f"""Use these name variations as base elements: {', '.join(name_shortcuts)}
Mix these names with creative suffixes, prefixes, dots, and underscores to create natural-looking handles.

"""

        prompt += f"""Requirements:
- Must be valid Instagram usernames (lowercase letters, numbers, periods, underscores only)
- Cannot start or end with a period
- Between 6 and 20 characters preferred
- Should look like a REAL person's Instagram handle - creative, trendy, authentic
- Mix dots and underscores naturally (e.g. name.vibe, name_era, x.name)
- NEVER use these words: private, real, official, backup, finsta, spam, alt, second, fake, main, priv, offical, fan, backup, secret

Great examples of natural-looking usernames:
- chantie.vibes, xchantall, chantie_mood, chan.life
- its.chantie, hey.chan, chantall.era, chan_szn
- justchan_, oh.chantie, chantie.gram, chanverse

Bad examples (DO NOT generate these):
- chantall_official, real.chantall, chantall_private
- user123, chantall1, generic_name_42

Return ONLY a JSON array of {count} usernames, nothing else. Example format:
["name.vibes", "xname", "its.namee", "name_mood", "nameszn"]"""

        if current_username:
            prompt += f"\n\nNote: current username is {current_username}, avoid returning the same one."

        return prompt

    def _create_bio_prompt(self, mother_account, mother_bio, account_number):
        """Create prompt for bio generation"""
        prompt = f"""Generate an Instagram bio variation based on this mother account:
Account: {mother_account}
"""
        if mother_bio:
            prompt += f"Mother Bio: {mother_bio}\n"

        prompt += f"""
Requirements:
- Similar theme and style to the mother account
- Maximum 150 characters
- Can include emojis
- Should feel authentic and natural
- Slight variation that makes it seem like a related but unique account
"""
        if account_number:
            prompt += f"- This is variation #{account_number}\n"

        prompt += "\nProvide just the bio text, no explanations."

        return prompt

    def _call_ai_api(self, prompt):
        """Call the AI API"""
        if self.provider == "openai":
            return self._call_openai(prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt)
        else:
            return self._call_custom_api(prompt)

    def _call_openai(self, prompt):
        """Call OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a creative Instagram username generator. You create trendy, authentic-looking usernames that real people would use. Always respond with valid JSON when asked for arrays."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "max_tokens": 300
        }

        response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        return response.json()

    def _call_anthropic(self, prompt):
        """Call Anthropic Claude API"""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        data = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        return response.json()

    def _call_custom_api(self, prompt):
        """Call custom API endpoint"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "prompt": prompt
        }

        response = requests.post(self.api_endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        return response.json()

    def _extract_usernames_batch_from_response(self, response):
        """Extract multiple usernames from AI JSON array response"""
        if self.provider == "openai":
            text = response['choices'][0]['message']['content'].strip()
        elif self.provider == "anthropic":
            text = response['content'][0]['text'].strip()
        else:
            text = response.get('text', response.get('response', '')).strip()

        # Try to parse as JSON array
        try:
            # Find JSON array in the response
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                usernames = json.loads(text[start:end])
                if isinstance(usernames, list):
                    return [str(u).strip().lower() for u in usernames if u]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: split by newlines or commas
        usernames = []
        for line in text.replace(',', '\n').split('\n'):
            line = line.strip().strip('"\'`[]- ').strip()
            if line and len(line) >= 3:
                # Remove numbering like "1. " or "1) "
                import re
                line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if line:
                    usernames.append(line.lower())

        return usernames

    def _extract_username_from_response(self, response):
        """Extract a single username from AI response"""
        # Try batch extraction first (prompt now asks for JSON array)
        batch = self._extract_usernames_batch_from_response(response)
        if batch:
            return batch[0]

        # Legacy single extraction
        if self.provider == "openai":
            text = response['choices'][0]['message']['content'].strip()
        elif self.provider == "anthropic":
            text = response['content'][0]['text'].strip()
        else:
            text = response.get('text', response.get('response', '')).strip()

        # Clean up the response - take first line or first word
        username = text.split('\n')[0].strip()

        # Remove any quotes or extra characters
        username = username.strip('"\'` \n')

        # Remove any explanation text
        if ':' in username:
            username = username.split(':')[-1].strip()

        # Take only the username part if there's explanation
        username = username.split()[0] if ' ' in username else username

        return username

    def _extract_bio_from_response(self, response):
        """Extract bio from AI response"""
        if self.provider == "openai":
            bio = response['choices'][0]['message']['content'].strip()
        elif self.provider == "anthropic":
            bio = response['content'][0]['text'].strip()
        else:
            bio = response.get('text', response.get('response', '')).strip()

        # Clean up the bio
        bio = bio.strip('"\'` \n')

        # Remove "Bio:" prefix if present
        if bio.lower().startswith('bio:'):
            bio = bio[4:].strip()

        return bio

    def _validate_username(self, username):
        """Validate and clean username according to Instagram rules"""
        if not username:
            return self._generate_username_fallback('user')

        # Remove @ prefix if present
        username = username.lstrip('@')

        # Remove invalid characters
        valid_chars = 'abcdefghijklmnopqrstuvwxyz0123456789._'
        username = ''.join(c for c in username.lower() if c in valid_chars)

        # Remove leading/trailing periods and underscores
        username = username.strip('._')

        # Remove consecutive periods
        while '..' in username:
            username = username.replace('..', '.')

        # Remove consecutive underscores
        while '__' in username:
            username = username.replace('__', '_')

        # Limit length
        username = username[:30]

        # Ensure it's not empty or too short or just numbers
        if not username or len(username) < 3 or username.isdigit():
            return self._generate_username_fallback('user')

        return username

    def _generate_username_fallback(self, mother_account, index=None):
        """
        Fallback username generation without AI.
        Generates creative, Instagram-style usernames.

        Args:
            mother_account: Base account name to derive from
            index: Optional index for deterministic variety across batch calls
        """
        if not mother_account or mother_account.strip() == '':
            mother_account = 'user'

        # Extract base name - get the name part
        base = mother_account.split('.')[0].split('_')[0].strip().lower()
        if not base or len(base) < 2:
            base = 'nova'

        # Creative suffixes (trendy Instagram style)
        suffixes = [
            'vibes', 'mood', 'era', 'szn', 'way', 'ish', 'gram', 'feed',
            'daily', 'core', 'zone', 'verse', 'tales', 'world', 'life',
            'glow', 'aura', 'flow', 'wave', 'lane', 'crew', 'club',
            'diaries', 'hq', 'hub', 'land', 'luxe', 'edit', 'flex'
        ]

        # Creative prefixes
        prefixes = [
            'its', 'the', 'hey', 'im', 'just', 'so', 'oh', 'ya',
            'not', 'hi', 'ur', 'bb', 'lil', 'miss', 'sir', 'x'
        ]

        # Separators
        seps = ['.', '_', '']

        # Build a large pool of patterns
        all_patterns = []

        for suf in suffixes:
            sep = random.choice(seps)
            all_patterns.append(f"{base}{sep}{suf}")

        for pre in prefixes:
            sep = random.choice(seps)
            all_patterns.append(f"{pre}{sep}{base}")

        # Double-name combos
        for suf in suffixes[:15]:
            all_patterns.append(f"{base}.{suf}")
            all_patterns.append(f"{base}_{suf}")

        for pre in prefixes[:10]:
            all_patterns.append(f"{pre}.{base}")
            all_patterns.append(f"{pre}_{base}")

        # With short numbers (2 digits only, not single digits)
        num = random.randint(10, 99)
        all_patterns.extend([
            f"{base}.x{num}",
            f"x{base}{num}",
            f"{base}{num}x",
            f"{base}.{num}",
        ])

        # Extra creative combos
        all_patterns.extend([
            f"x{base}x",
            f"{base}xo",
            f"{base}ee",
            f"{base}y",
            f"{base}.bb",
            f"bb.{base}",
            f"{base}.xo",
        ])

        if index is not None:
            # Deterministic selection based on index to avoid duplicates in batch
            pattern_idx = index % len(all_patterns)
            # Shuffle with a seed derived from index to spread patterns
            rng = random.Random(index * 7 + 42)
            rng.shuffle(all_patterns)
            return all_patterns[pattern_idx]
        else:
            return random.choice(all_patterns)

    def _generate_bio_fallback(self, mother_bio):
        """Fallback bio generation without AI"""
        if not mother_bio:
            templates = [
                "✨ Living my best life",
                "📸 Content creator",
                "🌟 Life & Style",
                "💫 Just being me",
                "🎨 Creative soul"
            ]
            return random.choice(templates)

        # Simple variation: keep emojis, slightly modify text
        return mother_bio  # Could add more sophisticated fallback logic


class CampaignAIGenerator:
    """
    High-level AI generator for campaigns
    Integrates with tag-based automation
    """

    def __init__(self, api_key=None, provider="openai"):
        self.generator = AIProfileGenerator(api_key=api_key, provider=provider)

    def generate_campaign_profiles(self, mother_account, mother_bio, account_count):
        """
        Generate complete profiles for a campaign

        Args:
            mother_account: Mother account username
            mother_bio: Mother account bio
            account_count: Number of profiles to generate

        Returns:
            list: List of dicts with 'username' and 'bio'
        """
        profiles = []

        for i in range(account_count):
            profile = {
                'username': self.generator.generate_username(
                    mother_account,
                    account_number=i+1
                ),
                'bio': self.generator.generate_bio(
                    mother_account,
                    mother_bio,
                    account_number=i+1
                )
            }
            profiles.append(profile)

        return profiles

    def fetch_mother_account_info(self, mother_username):
        """
        Fetch mother account bio from Instagram
        (Placeholder - would need Instagram API or scraping)
        """
        # This would integrate with Instagram API or scraping
        # For now, return None and require manual input
        return {
            'username': mother_username,
            'bio': None  # Would fetch from Instagram
        }


def example_usage():
    """Example usage of AI profile generator"""

    print("="*70)
    print("AI PROFILE GENERATOR - EXAMPLE")
    print("="*70)

    # Example without API key (uses fallback)
    print("\n--- Fallback Generation (No API Key) ---")
    generator = AIProfileGenerator()

    username1 = generator.generate_username("chantall.main")
    bio1 = generator.generate_bio("chantall.main", "✨ Fashion & Lifestyle | 📍 Paris | DM for collabs")

    print(f"Generated username: {username1}")
    print(f"Generated bio: {bio1}")

    # Example with API key (would use real AI)
    print("\n--- AI Generation (With API Key) ---")
    # Uncomment and add your API key to test
    # generator_ai = AIProfileGenerator(api_key="your-api-key-here", provider="openai")
    # username2 = generator_ai.generate_username("chantall.main")
    # bio2 = generator_ai.generate_bio("chantall.main", "✨ Fashion & Lifestyle | 📍 Paris | DM for collabs")
    # print(f"AI generated username: {username2}")
    # print(f"AI generated bio: {bio2}")

    # Example campaign generation
    print("\n--- Campaign Profile Generation ---")
    campaign_gen = CampaignAIGenerator()

    profiles = campaign_gen.generate_campaign_profiles(
        mother_account="chantall.main",
        mother_bio="✨ Fashion & Lifestyle | 📍 Paris | DM for collabs",
        account_count=5
    )

    print(f"Generated {len(profiles)} profiles:")
    for i, profile in enumerate(profiles, 1):
        print(f"{i}. Username: {profile['username']}")
        print(f"   Bio: {profile['bio']}")
        print()


if __name__ == "__main__":
    example_usage()
