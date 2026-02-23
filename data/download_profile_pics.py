#!/usr/bin/env python3
"""
Diverse Profile Picture Downloader & Generator — Hydra Phone Farm

Downloads DIVERSE profile pictures from stock photo APIs (Unsplash, Pexels, Pixabay)
and optionally generates AI photos via fal.ai for face-forward shots.

The KEY insight: real Instagram profile pictures are NOT all face close-ups.
This script downloads a realistic MIX of photo types:

  30% — Face visible (selfie, portrait, various angles)      -> AI generation (fal.ai)
  20% — Full body / half body (travel, lifestyle, beach)      -> Stock photos
  15% — Aesthetic/artistic (landscapes, coffee, flowers, pets) -> Stock photos
  15% — Mirror selfies / gym photos                           -> Stock photos  
  10% — Back view / silhouette                                -> Stock photos
  10% — Other (pet portraits, abstract, black & white)        -> Stock photos

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
        "description": "Face visible — selfie, portrait, candid angles",
        "target_pct": 0.30,
        "source": "ai",  # Best done with AI for uniqueness
        "stock_search_terms": [
            # Natural-looking portraits — not studio, but still nice
            "young woman selfie natural light", "young man selfie outdoor casual",
            "girl portrait casual smile", "guy portrait outdoor natural",
            "woman face close up natural", "man portrait casual daylight",
            "european young woman portrait candid", "european young man casual portrait",
            "girl selfie golden hour", "guy casual portrait city",
            "young woman candid cafe", "young woman portrait window light",
            "casual portrait young man park", "girl natural portrait outdoor",
            "woman portrait soft light", "man casual headshot outdoor",
        ],
    },
    "full_body_lifestyle": {
        "description": "Full body / half body from distance — candid travel, casual life",
        "target_pct": 0.20,
        "source": "stock",
        "search_terms_female": [
            "girl walking street candid from behind",
            "woman beach casual vacation amateur",
            "candid photo woman tourist europe",
            "young woman sitting cafe candid",
            "girl hiking casual phone photo",
            "woman standing field natural",
            "candid girl looking at sea",
            "girl sitting old town stairs casual",
            "casual woman bicycle city",
            "candid street photography woman young",
            "girl autumn park natural candid",
            "casual photo girl urban wall",
            "woman friend taking photo travel",
            "candid lake mountain casual woman",
            "girl bridge european city casual photo",
        ],
        "search_terms_male": [
            "guy standing mountain casual photo",
            "man walking city street candid",
            "candid travel photo young man",
            "guy sitting bench park casual",
            "man hiking outdoors casual",
            "guy beach vacation amateur photo",
            "man sitting cafe candid street",
            "young man old town casual",
            "casual guy rooftop city",
            "man friend photo casual outdoor",
        ],
    },
    "aesthetic_artistic": {
        "description": "Aesthetic/artistic — phone photos, casual shots of things",
        "target_pct": 0.15,
        "source": "stock",
        "search_terms": [
            "coffee cup phone photo casual",
            "sunset phone photo amateur",
            "cute dog amateur photo phone",
            "cat sleeping casual photo",
            "flowers casual phone photo",
            "mountain view phone camera",
            "ocean waves casual",
            "autumn leaves ground casual",
            "cozy room casual photo",
            "vinyl record casual aesthetic",
            "book and coffee casual photo",
            "indoor plant phone photo",
            "dog portrait amateur cute",
            "kitten cute phone photo",
            "food plate casual restaurant photo",
            "sunrise blurry phone photo",
            "snow casual phone photo",
            "cherry blossom phone photo",
            "field flowers amateur photo",
            "beach footprints casual",
            "city night rain phone photo",
            "polaroid vintage casual",
            "candle cozy casual",
            "sunset water phone photo",
            "foggy street phone photo",
        ],
    },
    "mirror_selfie_gym": {
        "description": "Mirror selfies / gym — amateur phone selfie style",
        "target_pct": 0.15,
        "source": "stock",
        "search_terms_female": [
            "woman gym selfie mirror phone",
            "girl gym casual workout phone",
            "woman yoga mat casual",
            "fitness woman casual gym",
            "woman gym amateur photo",
            "girl workout casual photo",
            "girl healthy lifestyle casual",
            "woman gym locker room selfie",
        ],
        "search_terms_male": [
            "man gym selfie mirror phone",
            "guy gym casual workout",
            "man lifting weights casual",
            "fitness man casual gym photo",
            "man treadmill casual",
            "guy crossfit amateur photo",
            "man exercise casual",
            "gym selfie amateur male",
        ],
    },
    "back_view_silhouette": {
        "description": "Back view / silhouette — casual from-behind shots",
        "target_pct": 0.10,
        "source": "stock",
        "search_terms": [
            "woman silhouette sunset casual",
            "person from behind mountains casual",
            "woman back view ocean casual photo",
            "silhouette person sunset amateur",
            "girl from behind looking at view casual",
            "person standing cliff casual",
            "silhouette sunrise amateur phone",
            "woman back view city casual",
            "person walking road casual",
            "woman sunset balcony phone photo",
            "man silhouette mountain amateur",
            "person from behind forest casual",
            "woman field sunset casual phone",
            "silhouette beach casual",
            "person hiking trail from behind casual",
        ],
    },
    "other_diverse": {
        "description": "Other — pets, objects, casual random shots",
        "target_pct": 0.10,
        "source": "stock",
        "search_terms": [
            "small dog funny amateur photo",
            "cat sleeping casual phone photo",
            "abstract colorful casual",
            "black and white candid street",
            "graffiti wall casual photo",
            "sneakers feet casual photo",
            "hands coffee cup casual",
            "car dashboard road trip phone",
            "skateboard street casual",
            "guitar casual photo amateur",
            "headphones casual desk photo",
            "pizza casual food phone photo",
            "ice cream casual summer",
            "sunglasses casual selfie",
            "sneakers pavement casual",
            "neon lights casual night",
            "vintage camera casual",
            "bicycle european street casual",
            "old building phone photo",
            "sky clouds casual phone photo",
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
        """Search photos with retry. orientation: landscape/portrait/square"""
        import requests as _req
        for attempt in range(3):
            try:
                resp = _req.get(
                    f"{self.BASE_URL}/search",
                    params={"query": query, "per_page": per_page, "page": page, "orientation": orientation},
                    headers={"Authorization": self.api_key},
                    timeout=15,
                )
                if resp.status_code == 401 and attempt < 2:
                    # Cloudflare rate limit — wait and retry
                    time.sleep(3 + attempt * 2)
                    continue
                resp.raise_for_status()
                self.requests_made += 1
                data = resp.json()
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
                if attempt < 2:
                    time.sleep(2)
                    continue
                print(f"    Pexels error: {e}")
                return []
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
        import requests as _req
        resp = _req.get(url, timeout=30)
        resp.raise_for_status()
        image_data = resp.content
        
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
        
        # Subtle random adjustments for uniqueness
        # Goal: still a nice photo, just not identical to stock original
        from PIL import ImageEnhance
        
        # Very slight brightness variation
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(random.uniform(0.96, 1.04))
        
        # Very slight contrast tweak
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(random.uniform(0.95, 1.05))
        
        # Subtle saturation shift
        color = ImageEnhance.Color(img)
        img = color.enhance(random.uniform(0.93, 1.07))
        
        # JPEG quality — good but not lossless (like a normal phone export)
        output = BytesIO()
        img.save(output, format="JPEG", quality=random.randint(82, 93))
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
                
                # Rate limiting — Pexels Cloudflare needs breathing room
                time.sleep(1.5)
    
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
                print(f"    -> \"{t}\"")
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
        print(f"\n[DIR] Category: {cat_name} ({needed_count} needed)")
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
                print(f"   [{i+1}/{len(photos)}] {filename} [OK] ({size_kb:.0f}KB)")
                
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
                print(f"   [{i+1}/{len(photos)}] {filename} [FAIL] FAILED")
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
    print(f"  [OK] Downloaded: {total_downloaded}")
    print(f"  [FAIL] Failed:     {total_failed}")
    print(f"  [DIR] Location:   {PICS_DIR}")
    print(f"{'='*70}\n")
    
    # Summary
    print("Photos by category:")
    for cat, count in manifest["stats"]["by_category"].items():
        print(f"  {cat}: {count}")
    print("\nPhotos by gender folder:")
    for gender, count in manifest["stats"]["by_gender"].items():
        print(f"  {gender}: {count}")
    
    print(f"\nDone!")


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
        print(f"[OK] Unsplash API configured")
    if pexels_key:
        clients["pexels"] = PexelsClient(pexels_key)
        print(f"[OK] Pexels API configured")
    if pixabay_key:
        clients["pixabay"] = PixabayClient(pixabay_key)
        print(f"[OK] Pixabay API configured")
    
    if not clients and not args.dry_run:
        print("[FAIL] No API keys provided! You need at least one of:")
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

