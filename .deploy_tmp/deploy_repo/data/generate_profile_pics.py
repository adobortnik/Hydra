#!/usr/bin/env python3
"""
Profile Picture Generator for Mass Profile Automation
Generates realistic AI face photos using fal.ai or Replicate APIs.

Usage:
    # Using fal.ai (recommended - cheapest)
    python generate_profile_pics.py --provider fal --api-key YOUR_KEY --female 650 --male 274

    # Using Replicate
    python generate_profile_pics.py --provider replicate --api-key YOUR_KEY --female 650 --male 274

    # Dry run (show what would be generated)
    python generate_profile_pics.py --dry-run --female 650 --male 274

    # Generate a small test batch first
    python generate_profile_pics.py --provider fal --api-key YOUR_KEY --female 5 --male 3

Environment variables (alternative to --api-key):
    FAL_KEY=your_fal_api_key
    REPLICATE_API_TOKEN=your_replicate_token
"""

import os
import sys
import json
import time
import random
import hashlib
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent
PICS_DIR = DATA_DIR / "profile_pics"
MANIFEST_FILE = PICS_DIR / "manifest.json"


# ─── Prompt Templates ─────────────────────────────────────────────────────────
# These are carefully crafted to produce realistic Instagram-style selfie photos
# of European/Slavic-looking young people. Variety is achieved by rotating
# through different lighting, backgrounds, hairstyles, and clothing.

FEMALE_PROMPT_PARTS = {
    "base": [
        "Instagram selfie photo of a young European woman",
        "Casual smartphone selfie of a young Slavic woman",
        "Natural Instagram photo portrait of a young Central European woman",
        "Candid selfie-style photo of a young Eastern European woman",
        "Close-up Instagram portrait of a pretty young European woman",
    ],
    "age": [
        "aged 19", "aged 20", "aged 21", "aged 22", "aged 23",
        "aged 24", "aged 25", "aged 26", "aged 27",
    ],
    "hair": [
        "with light brown hair", "with dark brown hair", "with blonde hair",
        "with dirty blonde hair", "with auburn hair", "with honey blonde hair",
        "with chestnut brown hair", "with dark blonde hair",
        "with long brown hair", "with medium length blonde hair",
        "with shoulder length brown hair", "with long straight dark hair",
        "with wavy brown hair", "with straight blonde hair",
    ],
    "appearance": [
        "natural makeup, clear skin",
        "light natural makeup, blue eyes",
        "minimal makeup, green eyes",
        "subtle makeup, brown eyes",
        "no makeup, natural look",
        "light lip gloss, natural look",
        "casual everyday look",
        "fresh-faced, minimal makeup",
    ],
    "clothing": [
        "wearing a casual t-shirt", "wearing a cozy sweater",
        "wearing a simple blouse", "wearing a hoodie",
        "wearing a casual top", "wearing a summer dress",
        "wearing a denim jacket", "wearing a cardigan",
        "wearing a tank top", "wearing a crop top and jacket",
    ],
    "background": [
        "coffee shop background slightly blurred",
        "outdoor park background with soft bokeh",
        "bedroom mirror selfie with warm lighting",
        "city street background blurred",
        "cozy indoor setting with natural light",
        "sunlit room with soft shadows",
        "restaurant background softly blurred",
        "nature background with trees blurred",
        "balcony with city view blurred",
        "university campus background",
    ],
    "style": [
        "warm natural lighting, realistic photograph, 4k, shot on iPhone",
        "soft golden hour lighting, realistic photo, high quality, smartphone photo",
        "natural daylight, candid shot, realistic, everyday photography",
        "warm indoor lighting, authentic look, realistic photograph",
        "overcast soft lighting, natural colors, realistic phone photo",
    ],
}

MALE_PROMPT_PARTS = {
    "base": [
        "Instagram selfie photo of a young European man",
        "Casual smartphone selfie of a young Slavic man",
        "Natural Instagram photo portrait of a young Central European man",
        "Candid selfie-style photo of a young Eastern European man",
        "Close-up Instagram portrait of a young European guy",
    ],
    "age": [
        "aged 20", "aged 21", "aged 22", "aged 23", "aged 24",
        "aged 25", "aged 26", "aged 27",
    ],
    "hair": [
        "with short brown hair", "with dark hair",
        "with light brown hair", "with short blonde hair",
        "with medium length dark hair", "with buzz cut brown hair",
        "with styled dark hair", "with short dark brown hair",
        "with wavy brown hair", "with clean cut hair",
    ],
    "appearance": [
        "clean shaven, clear skin",
        "light stubble, casual look",
        "short beard, masculine features",
        "clean shaven, athletic build",
        "light facial hair, natural look",
        "clean shaven, blue eyes",
        "stubble, brown eyes",
        "well groomed, casual",
    ],
    "clothing": [
        "wearing a casual t-shirt", "wearing a hoodie",
        "wearing a polo shirt", "wearing a button-down shirt",
        "wearing a simple sweater", "wearing a gym tank top",
        "wearing a denim jacket over t-shirt", "wearing a flannel shirt",
    ],
    "background": [
        "gym background slightly blurred",
        "outdoor setting with natural light",
        "city street background blurred",
        "cozy indoor setting",
        "park or nature background",
        "coffee shop background",
        "car interior selfie",
        "urban rooftop background",
    ],
    "style": [
        "warm natural lighting, realistic photograph, 4k, shot on iPhone",
        "soft natural lighting, realistic photo, high quality, smartphone photo",
        "natural daylight, candid shot, realistic, everyday photography",
        "warm indoor lighting, authentic look, realistic photograph",
    ],
}

NEGATIVE_PROMPT = (
    "cartoon, anime, drawing, painting, illustration, render, 3d, cgi, "
    "deformed, ugly, bad anatomy, extra fingers, extra limbs, blurry face, "
    "asymmetric face, cross-eyed, watermark, text, logo, studio lighting, "
    "professional photography, stock photo, model agency, overly perfect, "
    "plastic surgery look, heavy makeup, glamour shot, airbrushed"
)


def build_prompt(gender, index=0):
    """Build a unique, randomized prompt for a face photo."""
    parts = FEMALE_PROMPT_PARTS if gender == "female" else MALE_PROMPT_PARTS

    # Use index as additional seed for deterministic but varied results
    seed = random.Random(index + hash(gender))

    prompt_pieces = []
    for key in ["base", "age", "hair", "appearance", "clothing", "background", "style"]:
        prompt_pieces.append(seed.choice(parts[key]))

    return ", ".join(prompt_pieces)


def generate_seed(gender, index):
    """Generate a deterministic but unique seed for reproducibility."""
    hash_input = f"{gender}_{index}_hydra_v1"
    return int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)


# ─── API Providers ─────────────────────────────────────────────────────────────

def generate_via_fal(prompt, seed, api_key, image_size="square_hd"):
    """Generate an image using fal.ai FLUX.1 [schnell] API."""
    import json as json_mod

    url = "https://fal.run/fal-ai/flux/schnell"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }
    payload = json_mod.dumps({
        "prompt": prompt,
        "image_size": image_size,  # square_hd = 1024x1024
        "num_inference_steps": 4,
        "seed": seed,
        "num_images": 1,
        "enable_safety_checker": False,
        "output_format": "jpeg",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json_mod.loads(resp.read().decode("utf-8"))

        if "images" in result and len(result["images"]) > 0:
            image_url = result["images"][0]["url"]
            return image_url
        else:
            print(f"  ⚠ Unexpected response: {json_mod.dumps(result)[:200]}")
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.readable() else ""
        print(f"  ❌ HTTP {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def generate_via_replicate(prompt, seed, api_key):
    """Generate an image using Replicate FLUX.1 [schnell] API."""
    import json as json_mod

    # Create prediction
    url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "wait",  # Wait for result synchronously
    }
    payload = json_mod.dumps({
        "input": {
            "prompt": prompt,
            "seed": seed,
            "go_fast": True,
            "num_outputs": 1,
            "aspect_ratio": "1:1",
            "output_format": "jpg",
            "output_quality": 90,
            "num_inference_steps": 4,
            "disable_safety_checker": True,
        }
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json_mod.loads(resp.read().decode("utf-8"))

        # If synchronous response with output
        if result.get("status") == "succeeded" and result.get("output"):
            return result["output"][0] if isinstance(result["output"], list) else result["output"]

        # If we need to poll
        if result.get("urls", {}).get("get"):
            return _poll_replicate(result["urls"]["get"], api_key)

        print(f"  ⚠ Unexpected response: {json_mod.dumps(result)[:200]}")
        return None

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.readable() else ""
        print(f"  ❌ HTTP {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def _poll_replicate(poll_url, api_key, max_wait=120):
    """Poll Replicate for prediction result."""
    import json as json_mod

    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.time()

    while time.time() - start < max_wait:
        req = urllib.request.Request(poll_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json_mod.loads(resp.read().decode("utf-8"))

        status = result.get("status")
        if status == "succeeded":
            output = result.get("output", [])
            return output[0] if isinstance(output, list) else output
        elif status in ("failed", "canceled"):
            print(f"  ❌ Prediction {status}: {result.get('error', 'unknown')}")
            return None

        time.sleep(2)

    print(f"  ❌ Timeout waiting for prediction")
    return None


def download_image(url, save_path):
    """Download image from URL to local file."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(save_path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return False


# ─── Main Generation Pipeline ─────────────────────────────────────────────────

def load_manifest():
    """Load or create the manifest file tracking all generated pictures."""
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"generated": [], "failed": [], "last_updated": None}


def save_manifest(manifest):
    """Save the manifest file."""
    manifest["last_updated"] = datetime.now().isoformat()
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_already_generated(manifest):
    """Get set of already generated filenames."""
    return {entry["filename"] for entry in manifest.get("generated", [])}


def run_generation(provider, api_key, num_female, num_male, dry_run=False,
                   batch_delay=0.5, resume=True):
    """Run the full generation pipeline."""

    # Ensure directories exist
    (PICS_DIR / "female").mkdir(parents=True, exist_ok=True)
    (PICS_DIR / "male").mkdir(parents=True, exist_ok=True)

    manifest = load_manifest() if resume else {"generated": [], "failed": [], "last_updated": None}
    already_done = get_already_generated(manifest)

    # Build task list
    tasks = []
    for i in range(num_female):
        filename = f"f_{i+1:04d}.jpg"
        if filename not in already_done:
            tasks.append(("female", i, filename))

    for i in range(num_male):
        filename = f"m_{i+1:04d}.jpg"
        if filename not in already_done:
            tasks.append(("male", i, filename))

    total = len(tasks)
    skipped = (num_female + num_male) - total

    print(f"\n{'='*70}")
    print(f"PROFILE PICTURE GENERATION — {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*70}")
    print(f"  Provider:  {provider}")
    print(f"  Female:    {num_female}")
    print(f"  Male:      {num_male}")
    print(f"  Total:     {num_female + num_male}")
    print(f"  Skipped:   {skipped} (already generated)")
    print(f"  To generate: {total}")
    if not dry_run:
        est_cost = total * (0.003 if provider == "fal" else 0.003)
        print(f"  Est. cost: ~${est_cost:.2f}")
        est_time = total * 3  # ~3 seconds per image
        print(f"  Est. time: ~{est_time // 60}m {est_time % 60}s")
    print(f"{'='*70}\n")

    if dry_run:
        # Show sample prompts
        for gender, i, filename in tasks[:5]:
            prompt = build_prompt(gender, i)
            print(f"  [{filename}] {prompt[:100]}...")
        if total > 5:
            print(f"\n  ... and {total - 5} more")
        print(f"\nDry run complete. Use without --dry-run to generate.")
        return

    if total == 0:
        print("Nothing to generate — all images already exist!")
        return

    # Generate!
    success = 0
    failed = 0
    start_time = time.time()

    for idx, (gender, i, filename) in enumerate(tasks):
        prompt = build_prompt(gender, i)
        seed = generate_seed(gender, i)
        save_path = PICS_DIR / gender / filename

        print(f"  [{idx+1}/{total}] {filename} ...", end=" ", flush=True)

        if provider == "fal":
            image_url = generate_via_fal(prompt, seed, api_key)
        elif provider == "replicate":
            image_url = generate_via_replicate(prompt, seed, api_key)
        else:
            print(f"Unknown provider: {provider}")
            return

        if image_url:
            if download_image(image_url, save_path):
                size_kb = save_path.stat().st_size / 1024
                print(f"✅ ({size_kb:.0f}KB)")
                manifest["generated"].append({
                    "filename": filename,
                    "gender": gender,
                    "seed": seed,
                    "prompt": prompt[:100],
                    "generated_at": datetime.now().isoformat(),
                })
                success += 1
            else:
                print(f"❌ download failed")
                manifest["failed"].append({"filename": filename, "gender": gender, "error": "download_failed"})
                failed += 1
        else:
            print(f"❌ generation failed")
            manifest["failed"].append({"filename": filename, "gender": gender, "error": "api_failed"})
            failed += 1

        # Save manifest every 10 images (crash recovery)
        if (idx + 1) % 10 == 0:
            save_manifest(manifest)

        # Rate limiting delay
        if idx < total - 1:
            time.sleep(batch_delay)

    # Final save
    save_manifest(manifest)

    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"GENERATION COMPLETE")
    print(f"  ✅ Success: {success}")
    print(f"  ❌ Failed:  {failed}")
    print(f"  ⏱️  Time:    {elapsed:.0f}s ({elapsed/max(success,1):.1f}s per image)")
    if provider == "fal":
        est_cost = success * 0.003
        print(f"  💰 Est. cost: ~${est_cost:.2f}")
    print(f"{'='*70}\n")

    if failed > 0:
        print(f"⚠ {failed} images failed. Re-run the same command to retry (supports resume).\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate profile pictures using AI face generation APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--provider", choices=["fal", "replicate"], default="fal",
                       help="API provider (default: fal)")
    parser.add_argument("--api-key", type=str, default=None,
                       help="API key (or use FAL_KEY / REPLICATE_API_TOKEN env vars)")
    parser.add_argument("--female", type=int, default=650,
                       help="Number of female photos (default: 650)")
    parser.add_argument("--male", type=int, default=274,
                       help="Number of male photos (default: 274)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be generated without actually generating")
    parser.add_argument("--delay", type=float, default=0.5,
                       help="Delay between API calls in seconds (default: 0.5)")
    parser.add_argument("--no-resume", action="store_true",
                       help="Start fresh instead of resuming from manifest")

    args = parser.parse_args()

    # Resolve API key
    api_key = args.api_key
    if not api_key and not args.dry_run:
        if args.provider == "fal":
            api_key = os.environ.get("FAL_KEY")
        elif args.provider == "replicate":
            api_key = os.environ.get("REPLICATE_API_TOKEN")

        if not api_key:
            print(f"❌ No API key provided. Use --api-key or set environment variable.")
            print(f"   For fal.ai: set FAL_KEY=your_key")
            print(f"   For Replicate: set REPLICATE_API_TOKEN=your_token")
            sys.exit(1)

    run_generation(
        provider=args.provider,
        api_key=api_key or "dry-run",
        num_female=args.female,
        num_male=args.male,
        dry_run=args.dry_run,
        batch_delay=args.delay,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
