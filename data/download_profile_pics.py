#!/usr/bin/env python3
"""
Diverse Profile Picture Downloader & Generator — Hydra Phone Farm

Downloads DIVERSE profile pictures from stock photo APIs (Unsplash, Pexels, Pixabay)
and optionally generates AI photos via fal.ai for face-forward shots.

The KEY insight: real Instagram profile pictures are NOT all face close-ups.
This script downloads a realistic MIX of photo types:

  30% — Face visible (selfie, portrait, various angles)      → AI generation (fal.ai)
  20% — Full body / half body (travel, lifestyle, beach)      → Stock photos
  15% — Aesthetic/artistic (landscapes, coffee, flowers, pets) → Stock photos
  15% — Mirror selfies / gym photos                           → Stock photos  
  10% — Back view / silhouette                                → Stock photos
  10% — Other (pet portraits, abstract, black & white)        → Stock photos

Usage:
    # Download stock photos only (free, no API key needed for Pixabay demo):
    python download_profile_pics.py --source stock --pixabay-key YOUR_KEY

    # Full pipeline: stock + AI faces:
    python download_profile_pics.py --source mixed --pixabay-key PX_KEY --fal-key FAL_KEY

    # Unsplash + Pexels + Pixabay:
    python download_profile_pics.py --source stock --unsplash-key U_KEY --pexels-key P_KEY --pixabay-key PX_KEY

    # Preview what would be downloaded (dry run):
    python download_profile_pics.py --dry-run

Environment variables (alternative to flags):
    UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY, FAL_KEY
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
from io import BytesIO

DATA_DIR = Path(__file__).parent
PICS_DIR = DATA_DIR / "profile_pics"
MANIFEST_FILE = PICS_DIR / "download_manifest.json"

# ─── Photo Categories & Search Terms ──────────────────────────────────────────
# Each category has search terms for stock photo APIs.
# Terms are designed to return photos that look like real IG profile pics.

PHOTO_CATEGORIES = {
    "face_selfie": {
        "description": "Face visible — selfie, portrait, various angles",
        "target_pct": 0.30,
        "source": "ai",  # Best done with AI for uniqueness
        "stock_search_terms": [
            # Fallback if no AI — stock photos of real-looking people
            "young woman selfie casual", "young man selfie natural",
            "girl portrait smile natural light", "guy portrait casual outdoor",
            "woman face portrait natural", "man face portrait outdoor",
            "european woman portrait", "european man portrait casual",
        ],
    },
    "full_body_lifestyle": {
        "description": "Full body / half body from distance (travel, lifestyle, beach)",
        "target_pct": 0.20,
        "source": "stock",
        "search_terms_female": [
            "woman walking city street from behind",
            "girl standing beach sunset",
            "woman travel landmark europe",
            "young woman sitting cafe outdoor",
            "woman hiking mountain view",
            "girl standing field flowers",
            "woman looking at sea",
            "girl sitting stairs old town",
            "woman riding bicycle city",
            "young woman street photography",
            "woman standing autumn forest",
            "girl posing urban wall",
            "woman at viewpoint overlooking city",
            "woman at lake mountains",
            "girl on bridge european city",
        ],
        "search_terms_male": [
            "man standing mountain top view",
            "guy walking city street casual",
            "man travel photography urban",
            "young man sitting bench park",
            "man hiking outdoors adventure",
            "guy beach vacation casual",
            "man sitting cafe urban",
            "young man standing old town",
            "man cycling city",
            "man on rooftop city view",
        ],
    },
    "aesthetic_artistic": {
        "description": "Aesthetic/artistic (landscapes, coffee, flowers, pets, food)",
        "target_pct": 0.15,
        "source": "stock",
        "search_terms": [
            "aesthetic coffee cup latte art",
            "sunset clouds golden hour",
            "cute dog portrait close up",
            "cute cat portrait close up",
            "aesthetic flowers bouquet",
            "mountain landscape dramatic",
            "ocean waves sunset",
            "autumn leaves aesthetic",
            "cozy room aesthetic warm",
            "vinyl record player aesthetic",
            "books coffee cozy aesthetic",
            "plant aesthetic indoor",
            "golden retriever portrait cute",
            "kitten portrait cute",
            "food flat lay aesthetic",
            "sunrise mountains peaceful",
            "snow covered trees winter",
            "cherry blossom tree spring",
            "lavender field purple",
            "beach footprints sand",
            "city lights night rain",
            "polaroid photos aesthetic",
            "candle cozy evening",
            "sunset over water reflection",
            "street lamp fog night",
        ],
    },
    "mirror_selfie_gym": {
        "description": "Mirror selfies / gym photos",
        "target_pct": 0.15,
        "source": "stock",
        "search_terms_female": [
            "woman gym workout fitness",
            "girl gym selfie fitness",
            "woman stretching yoga mat",
            "fitness woman dumbbell",
            "woman running treadmill gym",
            "woman pilates exercise",
            "fitness girl healthy lifestyle",
            "woman gym training",
        ],
        "search_terms_male": [
            "man gym workout muscle",
            "guy gym fitness training",
            "man lifting weights gym",
            "fitness man training gym",
            "man running gym treadmill",
            "man crossfit workout",
            "guy exercise fitness",
            "man gym selfie casual",
        ],
    },
    "back_view_silhouette": {
        "description": "Back view / silhouette photos",
        "target_pct": 0.10,
        "source": "stock",
        "search_terms": [
            "woman silhouette sunset",
            "person looking at mountains from behind",
            "woman back view ocean sunset",
            "silhouette person sunset sky",
            "girl from behind looking at view",
            "person standing cliff edge view",
            "silhouette person sunrise",
            "woman back view city skyline",
            "person walking alone road sunset",
            "woman looking at sunset balcony",
            "man silhouette mountain",
            "person from behind forest path",
            "woman back view field sunset",
            "silhouette beach golden hour",
            "person hiking trail from behind",
        ],
    },
    "other_diverse": {
        "description": "Other (pet as pfp, abstract, cartoon avatar, artsy, b&w)",
        "target_pct": 0.10,
        "source": "stock",
        "search_terms": [
            "small dog cute funny",
            "cat sleeping cute",
            "abstract colorful art wallpaper",
            "black and white street photography",
            "graffiti wall art urban",
            "shoes sneakers flat lay",
            "hands holding coffee cup",
            "car dashboard road trip",
            "skateboard street urban",
            "guitar music instrument close up",
            "headphones music aesthetic",
            "pizza food close up delicious",
            "ice cream cone colorful",
            "sunglasses reflection summer",
            "sneakers feet pavement",
            "neon lights night city",
            "vintage camera retro",
            "bicycle parked european street",
            "old building architecture",
            "hand reaching sky clouds",
        ],
    },
}


# ─── Stock Photo API Clients ──────────────────────────────────────────────────

class UnsplashClient:
    """
    Unsplash API Client
    - Free: 50 requests/hour (demo), 5000/hour (production)
    - API: https://api.unsplash.com/
    - Requires: Access Key (free registration at https://unsplash.com/developers)
    - License: Free for commercial use, no attribution required in apps
    - Note: Must "trigger download" endpoint for each used photo (API guideline)
    """
    BASE_URL = "https://api.unsplash.com"
    
    def __init__(self, access_key):
        self.access_key = access_key
        self.requests_made = 0
    
    def search(self, query, per_page=30, page=1, orientation="squarish"):
        """Search photos. Returns list of photo dicts with download URLs."""
        url = (f"{self.BASE_URL}/search/photos"
               f"?query={urllib.request.quote(query)}"
               f"&per_page={per_page}&page={page}"
               f"&orientation={orientation}")
        
        headers = {
            "Authorization": f"Client-ID {self.access_key}",
            "Accept-Version": "v1",
        }
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.requests_made += 1
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for photo in data.get("results", []):
                    results.append({
                        "id": photo["id"],
                        "url": photo["urls"]["regular"],  # 1080px wide
                        "download_url": photo["links"]["download_location"],
                        "width": photo["width"],
                        "height": photo["height"],
                        "description": photo.get("description", ""),
                        "source": "unsplash",
                        "photographer": photo["user"]["name"],
                    })
                return results
        except Exception as e:
            print(f"    Unsplash error: {e}")
            return []
    
    def trigger_download(self, download_location_url):
        """Trigger download tracking (required by Unsplash API guidelines)."""
        headers = {"Authorization": f"Client-ID {self.access_key}"}
        req = urllib.request.Request(download_location_url, headers=headers)
        try:
            urllib.request.urlopen(req, timeout=10)
        except:
            pass  # Best effort


class PexelsClient:
    """
    Pexels API Client
    - Free: 200 requests/hour, 20,000/month
    - API: https://api.pexels.com/v1/
    - Requires: API Key (free registration at https://www.pexels.com/api/)
    - License: Free for commercial use, no attribution required
    """
    BASE_URL = "https://api.pexels.com/v1"
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.requests_made = 0
    
    def search(self, query, per_page=30, page=1, orientation="square"):
        """Search photos. orientation: landscape/portrait/square"""
        url = (f"{self.BASE_URL}/search"
               f"?query={urllib.request.quote(query)}"
               f"&per_page={per_page}&page={page}"
               f"&orientation={orientation}")
        
        headers = {
            "Authorization": self.api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.requests_made += 1
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for photo in data.get("photos", []):
                    results.append({
                        "id": str(photo["id"]),
                        "url": photo["src"]["large"],  # 940px wide
                        "url_original": photo["src"]["original"],
                        "width": photo["width"],
                        "height": photo["height"],
                        "description": photo.get("alt", ""),
                        "source": "pexels",
                        "photographer": photo.get("photographer", ""),
                    })
                return results
        except Exception as e:
            print(f"    Pexels error: {e}")
            return []


class PixabayClient:
    """
    Pixabay API Client
    - Free: 100 requests/minute
    - API: https://pixabay.com/api/
    - Requires: API Key (free registration at https://pixabay.com/api/docs/)
    - License: Free for commercial use (Pixabay License), no attribution required
    - Note: Must cache results for 24h. Max 500 results per query.
    """
    BASE_URL = "https://pixabay.com/api/"
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.requests_made = 0
    
    def search(self, query, per_page=30, page=1, image_type="photo",
               orientation="all", category=None, min_width=500, min_height=500):
        """Search photos."""
        params = (f"?key={self.api_key}"
                  f"&q={urllib.request.quote(query)}"
                  f"&per_page={per_page}&page={page}"
                  f"&image_type={image_type}"
                  f"&orientation={orientation}"
                  f"&min_width={min_width}&min_height={min_height}"
                  f"&safesearch=true")
        if category:
            params += f"&category={category}"
        
        url = self.BASE_URL + params
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self.requests_made += 1
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for photo in data.get("hits", []):
                    results.append({
                        "id": str(photo["id"]),
                        "url": photo["webformatURL"].replace("_640", "_960"),
                        "url_large": photo.get("largeImageURL", ""),
                        "width": photo.get("webformatWidth", 640),
                        "height": photo.get("webformatHeight", 480),
                        "description": photo.get("tags", ""),
                        "source": "pixabay",
                        "photographer": photo.get("user", ""),
                    })
                return results
        except Exception as e:
            print(f"    Pixabay error: {e}")
            return []


# ─── Image Processing ─────────────────────────────────────────────────────────

def download_image(url, save_path, crop_square=True, target_size=1080):
    """Download image and optionally crop to square."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            image_data = resp.read()
        
        if crop_square:
            image_data = crop_to_square_jpeg(image_data, target_size)
        
        if image_data:
            with open(save_path, "wb") as f:
                f.write(image_data)
            return True
        return False
    except Exception as e:
        print(f"    Download error: {e}")
        return False


def crop_to_square_jpeg(image_data, target_size=1080):
    """
    Crop image to square and resize to target_size.
    Uses PIL/Pillow if available, otherwise saves as-is.
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_data))
        
        # Convert to RGB if needed
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        
        # Crop to square (center crop)
        w, h = img.size
        size = min(w, h)
        left = (w - size) // 2
        top = (h - size) // 2
        img = img.crop((left, top, left + size, top + size))
        
        # Resize to target
        if size != target_size:
            img = img.resize((target_size, target_size), Image.LANCZOS)
        
        # Add slight random adjustments for uniqueness
        # (prevents reverse image search from matching perfectly)
        from PIL import ImageEnhance
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(random.uniform(0.95, 1.05))
        
        output = BytesIO()
        img.save(output, format="JPEG", quality=random.randint(85, 95))
        return output.getvalue()
    except ImportError:
        # No PIL — just save raw
        return image_data
    except Exception as e:
        print(f"    Crop error: {e}")
        return image_data


# ─── Main Download Pipeline ───────────────────────────────────────────────────

def load_manifest():
    """Load or create download manifest."""
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "downloaded": [],
        "failed": [],
        "used_photo_ids": [],
        "last_updated": None,
        "stats": {},
    }


def save_manifest(manifest):
    """Save manifest."""
    manifest["last_updated"] = datetime.now().isoformat()
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def collect_stock_photos(clients, search_terms, needed, used_ids, category_name):
    """
    Search across all available stock photo APIs and collect unique photos.
    Returns list of photo metadata dicts.
    """
    collected = []
    seen_ids = set(used_ids)
    
    # Shuffle search terms for variety
    terms = list(search_terms)
    random.shuffle(terms)
    
    for term in terms:
        if len(collected) >= needed:
            break
        
        for client_name, client in clients.items():
            if len(collected) >= needed:
                break
            
            # Search across multiple pages for variety
            for page in range(1, 4):
                if len(collected) >= needed:
                    break
                
                results = client.search(term, per_page=20, page=page)
                
                for photo in results:
                    if len(collected) >= needed:
                        break
                    
                    uid = f"{photo['source']}_{photo['id']}"
                    if uid not in seen_ids:
                        seen_ids.add(uid)
                        photo["category"] = category_name
                        photo["search_term"] = term
                        collected.append(photo)
                
                # Rate limiting
                time.sleep(0.3)
    
    return collected


def run_stock_download(clients, num_female=650, num_male=274, dry_run=False):
    """
    Download diverse stock photos organized by category.
    Distribution matches real Instagram profile pic variety.
    """
    total = num_female + num_male
    manifest = load_manifest()
    used_ids = set(manifest.get("used_photo_ids", []))
    already_done = {e["filename"] for e in manifest.get("downloaded", [])}
    
    # Calculate how many of each category we need
    category_counts = {}
    for cat_name, cat_config in PHOTO_CATEGORIES.items():
        if cat_config["source"] == "ai":
            # Use stock fallback search terms for AI categories (no AI key available)
            cat_config["_using_stock_fallback"] = True
        count = int(total * cat_config["target_pct"])
        category_counts[cat_name] = count
    
    stock_total = total
    
    print(f"\n{'='*70}")
    print(f"DIVERSE PROFILE PICTURE DOWNLOAD — {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*70}")
    print(f"  Total needed:     {total}")
    print(f"  AI faces (sep.):  {face_count} (use generate_profile_pics.py)")
    print(f"  Stock photos:     {stock_total}")
    print(f"  Already done:     {len(already_done)}")
    print(f"  APIs available:   {', '.join(clients.keys())}")
    print()
    
    for cat_name, count in category_counts.items():
        desc = PHOTO_CATEGORIES[cat_name]["description"]
        print(f"  {cat_name}: {count} photos — {desc}")
    print(f"{'='*70}\n")
    
    if dry_run:
        print("Dry run — showing search terms per category:\n")
        for cat_name, cat_config in PHOTO_CATEGORIES.items():
            if cat_config["source"] == "ai":
                continue
            print(f"  [{cat_name}]")
            # Get search terms
            terms = cat_config.get("search_terms", [])
            terms += cat_config.get("search_terms_female", [])
            terms += cat_config.get("search_terms_male", [])
            for t in terms[:5]:
                print(f"    → \"{t}\"")
            if len(terms) > 5:
                print(f"    ... and {len(terms) - 5} more terms")
            print()
        return
    
    # Create output directories — organized by category, then gender
    for cat_name in category_counts:
        for subdir in ["female", "male", "neutral"]:
            (PICS_DIR / cat_name / subdir).mkdir(parents=True, exist_ok=True)
    
    # Download by category
    global_idx = len(already_done) + 1
    total_downloaded = 0
    total_failed = 0
    
    for cat_name, needed_count in category_counts.items():
        cat_config = PHOTO_CATEGORIES[cat_name]
        print(f"\n📂 Category: {cat_name} ({needed_count} needed)")
        print(f"   {cat_config['description']}")
        
        # Collect search terms — some categories have gender-specific terms
        # For AI categories using stock fallback, use stock_search_terms
        if cat_config.get("_using_stock_fallback"):
            search_terms = cat_config.get("stock_search_terms", [])
        else:
            search_terms = cat_config.get("search_terms", [])
        
        # For gendered categories, mix female and male terms proportionally
        female_terms = cat_config.get("search_terms_female", [])
        male_terms = cat_config.get("search_terms_male", [])
        
        if female_terms or male_terms:
            # 70% female, 30% male
            female_count = int(needed_count * 0.7)
            male_count = needed_count - female_count
            
            # Collect female photos
            if female_terms and female_count > 0:
                print(f"   Searching female photos ({female_count})...")
                female_photos = collect_stock_photos(
                    clients, female_terms, female_count, used_ids, cat_name
                )
                for photo in female_photos:
                    photo["gender_hint"] = "female"
            else:
                female_photos = []
            
            # Collect male photos
            if male_terms and male_count > 0:
                print(f"   Searching male photos ({male_count})...")
                male_photos = collect_stock_photos(
                    clients, male_terms, male_count, used_ids, cat_name
                )
                for photo in male_photos:
                    photo["gender_hint"] = "male"
            else:
                male_photos = []
            
            photos = female_photos + male_photos
        else:
            # Gender-neutral category (aesthetic, back view, etc.)
            print(f"   Searching neutral photos ({needed_count})...")
            photos = collect_stock_photos(
                clients, search_terms, needed_count, used_ids, cat_name
            )
            for photo in photos:
                photo["gender_hint"] = "neutral"
        
        print(f"   Found {len(photos)} photos, downloading...")
        
        # Download each photo
        for i, photo in enumerate(photos):
            gender_dir = photo.get("gender_hint", "neutral")
            filename = f"stock_{cat_name}_{global_idx:04d}.jpg"
            save_path = PICS_DIR / cat_name / gender_dir / filename
            
            if filename in already_done:
                continue
            
            url = photo.get("url_large") or photo.get("url_original") or photo["url"]
            
            success = download_image(url, save_path, crop_square=True, target_size=1080)
            
            if success:
                size_kb = save_path.stat().st_size / 1024
                print(f"   [{i+1}/{len(photos)}] {filename} ✅ ({size_kb:.0f}KB)")
                
                manifest["downloaded"].append({
                    "filename": filename,
                    "category": cat_name,
                    "gender_hint": photo.get("gender_hint", "neutral"),
                    "source": photo["source"],
                    "source_id": photo["id"],
                    "search_term": photo.get("search_term", ""),
                    "photographer": photo.get("photographer", ""),
                    "downloaded_at": datetime.now().isoformat(),
                })
                
                uid = f"{photo['source']}_{photo['id']}"
                used_ids.add(uid)
                manifest["used_photo_ids"] = list(used_ids)
                
                total_downloaded += 1
                
                # Trigger Unsplash download tracking if applicable
                if photo["source"] == "unsplash" and "download_url" in photo:
                    for c in clients.values():
                        if isinstance(c, UnsplashClient):
                            c.trigger_download(photo["download_url"])
            else:
                print(f"   [{i+1}/{len(photos)}] {filename} ❌ FAILED")
                manifest["failed"].append({
                    "filename": filename,
                    "category": cat_name,
                    "url": url,
                    "error": "download_failed",
                })
                total_failed += 1
            
            global_idx += 1
            
            # Save manifest every 20 downloads
            if (total_downloaded + total_failed) % 20 == 0:
                save_manifest(manifest)
            
            # Rate limiting
            time.sleep(0.2)
    
    # Final stats
    manifest["stats"] = {
        "total_downloaded": total_downloaded,
        "total_failed": total_failed,
        "by_category": {
            cat: len([d for d in manifest["downloaded"] if d["category"] == cat])
            for cat in category_counts.keys()
        },
        "by_gender": {
            g: len([d for d in manifest["downloaded"] if d["gender_hint"] == g])
            for g in ["female", "male", "neutral"]
        },
    }
    save_manifest(manifest)
    
    print(f"\n{'='*70}")
    print(f"DOWNLOAD COMPLETE")
    print(f"  ✅ Downloaded: {total_downloaded}")
    print(f"  ❌ Failed:     {total_failed}")
    print(f"  📁 Location:   {PICS_DIR}")
    print(f"{'='*70}\n")
    
    # Summary
    print("Photos by category:")
    for cat, count in manifest["stats"]["by_category"].items():
        print(f"  {cat}: {count}")
    print("\nPhotos by gender folder:")
    for gender, count in manifest["stats"]["by_gender"].items():
        print(f"  {gender}: {count}")
    
    print(f"\n⚠️  Remember: {face_count} AI face photos still needed!")
    print(f"   Run: python generate_profile_pics.py --provider fal --api-key YOUR_KEY")


def main():
    parser = argparse.ArgumentParser(
        description="Download diverse profile pictures from stock photo APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--source", choices=["stock", "mixed"], default="stock",
                       help="Photo source strategy (default: stock)")
    parser.add_argument("--unsplash-key", type=str, default=None,
                       help="Unsplash API access key")
    parser.add_argument("--pexels-key", type=str, default=None,
                       help="Pexels API key")
    parser.add_argument("--pixabay-key", type=str, default=None,
                       help="Pixabay API key")
    parser.add_argument("--fal-key", type=str, default=None,
                       help="fal.ai API key (for AI face generation)")
    parser.add_argument("--female", type=int, default=650,
                       help="Number of female profile pics needed (default: 650)")
    parser.add_argument("--male", type=int, default=274,
                       help="Number of male profile pics needed (default: 274)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be downloaded without downloading")
    args = parser.parse_args()
    
    # Resolve API keys from env if not provided
    unsplash_key = args.unsplash_key or os.environ.get("UNSPLASH_ACCESS_KEY")
    pexels_key = args.pexels_key or os.environ.get("PEXELS_API_KEY")
    pixabay_key = args.pixabay_key or os.environ.get("PIXABAY_API_KEY")
    
    # Build client list
    clients = {}
    if unsplash_key:
        clients["unsplash"] = UnsplashClient(unsplash_key)
        print(f"✅ Unsplash API configured")
    if pexels_key:
        clients["pexels"] = PexelsClient(pexels_key)
        print(f"✅ Pexels API configured")
    if pixabay_key:
        clients["pixabay"] = PixabayClient(pixabay_key)
        print(f"✅ Pixabay API configured")
    
    if not clients and not args.dry_run:
        print("❌ No API keys provided! You need at least one of:")
        print("   --unsplash-key KEY  (get from https://unsplash.com/developers)")
        print("   --pexels-key KEY    (get from https://www.pexels.com/api/)")
        print("   --pixabay-key KEY   (get from https://pixabay.com/api/docs/)")
        print("\n   Or set environment variables:")
        print("   UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY")
        sys.exit(1)
    
    run_stock_download(
        clients=clients,
        num_female=args.female,
        num_male=args.male,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
