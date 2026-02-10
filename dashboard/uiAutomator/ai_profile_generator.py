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

    def generate_username(self, mother_account, current_username=None, variations_count=5):
        """
        Generate username based on mother account

        Args:
            mother_account: Username of the mother account to base on
            current_username: Current username (optional, for context)
            variations_count: Number of variations to generate

        Returns:
            str: Generated username
        """
        if not self.api_key or not self.api_endpoint:
            # Fallback to algorithmic generation
            return self._generate_username_fallback(mother_account)

        prompt = self._create_username_prompt(mother_account, current_username, variations_count)

        try:
            response = self._call_ai_api(prompt)
            username = self._extract_username_from_response(response)

            # Validate Instagram username rules
            username = self._validate_username(username)

            return username

        except Exception as e:
            print(f"AI username generation failed: {e}")
            return self._generate_username_fallback(mother_account)

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

    def _create_username_prompt(self, mother_account, current_username, count):
        """Create prompt for username generation"""
        prompt = f"""Generate {count} Instagram username variations based on: {mother_account}

Requirements:
- Create usernames inspired by the theme/keywords provided
- Must be valid Instagram usernames (letters, numbers, periods, underscores only)
- Cannot start or end with a period
- Maximum 30 characters
- Should look natural and authentic like a real person's account
- NEVER use these words: private, real, official, backup, finsta, spam, alt, second, fake, main, priv, offical

Good patterns: name.style, firstname.lastname, name_xx, thename, namee, xname
Bad patterns: name_official, name.real, name_private, realname, officialname

"""
        if current_username:
            prompt += f"Current username is: {current_username}\n"

        prompt += "Provide just one username variation (the best one). Return ONLY the username, nothing else."

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
                {"role": "system", "content": "You are a creative Instagram username and bio generator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,
            "max_tokens": 100
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

    def _extract_username_from_response(self, response):
        """Extract username from AI response"""
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
        # Remove invalid characters
        valid_chars = 'abcdefghijklmnopqrstuvwxyz0123456789._'
        username = ''.join(c for c in username.lower() if c in valid_chars)

        # Remove leading/trailing periods
        username = username.strip('.')

        # Remove consecutive periods
        while '..' in username:
            username = username.replace('..', '.')

        # Limit length
        username = username[:30]

        # Ensure it's not empty
        if not username:
            username = f"user{random.randint(1000, 9999)}"

        return username

    def _generate_username_fallback(self, mother_account):
        """Fallback username generation without AI"""
        # Extract base name
        base = mother_account.split('.')[0].split('_')[0]

        # Generate variation - avoid words like official, real, private
        patterns = [
            f"{base}.ig",
            f"{base}_{random.randint(1, 999)}",
            f"{base}.{random.randint(1, 99)}",
            f"the.{base}",
            f"{base}x",
            f"{base}.x",
            f"its.{base}",
            f"{base}{random.randint(10, 99)}",
            f"x{base}x",
            f"{base}.life"
        ]

        return random.choice(patterns)

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
