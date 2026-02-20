# Mass Profile Automation Plan V2 — Hydra Phone Farm

**Date:** 2026-02-20  
**Version:** 2.0 — DIVERSE profile strategy  
**Scale:** 77 devices × 12 accounts = **924 accounts**  
**Goal:** Transform generic profiles into believable Slovak/Czech personas  
**Gender Split:** 70% female (647), 30% male (277)

---

## Key Principle: DIVERSITY IS EVERYTHING

V1 generated 924 identical AI face close-ups. **Real Instagram doesn't look like that.**

Real young people use ALL KINDS of profile pictures. Look at any actual person's IG:
- Selfie from arm's length
- Photo from behind looking at a view
- Mirror selfie
- Their dog/cat
- An aesthetic coffee shot
- Full body photo at a landmark
- Silhouette against a sunset
- Just a landscape
- Gym mirror selfie
- A group photo cropped to them

**V2 creates a realistic MIX**, not a grid of 924 AI faces.

---

## 1. Profile Picture Strategy — MIXED SOURCES

### Distribution (924 total)

| Category | % | Count | Source | Description |
|----------|---|-------|--------|-------------|
| Face selfie/portrait | 30% | ~277 | AI (fal.ai FLUX) | Close-up face, selfie angle, natural |
| Full body / lifestyle | 20% | ~185 | Stock (Unsplash/Pexels/Pixabay) | Travel, beach, sitting in cafe, walking |
| Aesthetic / artistic | 15% | ~139 | Stock | Coffee, sunset, flowers, pets, food |
| Mirror selfie / gym | 15% | ~139 | Stock | Gym mirror, workout, fitness |
| Back view / silhouette | 10% | ~92 | Stock | Person from behind, silhouette at sunset |
| Other / diverse | 10% | ~92 | Stock | Pet portrait, abstract, B&W, sneakers |

### Source 1: Stock Photos (free APIs)

Three APIs, all free tier, different strengths:

#### Unsplash API
- **URL:** `https://api.unsplash.com/search/photos`
- **Auth:** `Authorization: Client-ID YOUR_ACCESS_KEY`
- **Rate limit:** 50 req/hr (demo), 5000 req/hr (production — apply free)
- **License:** Free for commercial use, no attribution required in apps
- **Strengths:** High quality, curated, great lifestyle/travel photos
- **Get key:** https://unsplash.com/developers
- **Notes:** Must "trigger download" endpoint for each used photo (API guideline)

#### Pexels API
- **URL:** `https://api.pexels.com/v1/search`
- **Auth:** `Authorization: YOUR_API_KEY`
- **Rate limit:** 200 req/hr, 20,000/month
- **License:** Free for commercial use, no attribution required
- **Strengths:** Good people/lifestyle photos, diverse
- **Get key:** https://www.pexels.com/api/

#### Pixabay API
- **URL:** `https://pixabay.com/api/?key=YOUR_KEY&q=QUERY`
- **Auth:** API key as query parameter
- **Rate limit:** 100 req/minute
- **License:** Free for commercial use (Pixabay License)
- **Strengths:** Huge library, good for aesthetic/nature/abstract
- **Get key:** https://pixabay.com/api/docs/
- **Notes:** Must cache results for 24h. Max 500 results per query.

#### Combined capacity
With all 3 APIs: **~650 unique stock photos per hour** (more than enough)

### Source 2: AI Generation (face category only)

For the 30% face-visible category, AI generation ensures:
- Every face is unique (no risk of using same stock photo twice)
- No reverse image search matches
- Consistent quality

**Provider:** fal.ai FLUX.1 [schnell]
- **Cost:** ~$0.003 per image → ~$0.83 for 277 faces
- **Speed:** ~3 seconds per image
- **Already built:** `generate_profile_pics.py`

### Source 3: Leonardo.AI (optional backup for AI faces)
- **URL:** `https://cloud.leonardo.ai/api/rest/v1/generations`
- **Auth:** `Authorization: Bearer YOUR_API_KEY`
- **Pricing:** Pay-per-use API credits (separate from web app subscription)
- **Strengths:** Multiple models, good face quality

### Implementation Scripts

| Script | Purpose |
|--------|---------|
| `download_profile_pics.py` | Downloads diverse stock photos by category |
| `generate_profile_pics.py` | Generates AI face photos (existing, for face category) |
| `generate_assignments.py` | Assigns pics+bios+usernames to 924 accounts |

---

## 2. Bio Strategy — REALISTIC SIMPLICITY

### V1 Problem
All 199 bios looked the same: "📍City | interest1 | interest2" format.

### V2 Approach
Real young Slovak/Czech IG bios are:
- Often **empty** (many people have no bio at all)
- Ultra-short: just "22" or "BA 📍" or "☕"
- Mostly English or EN/SK mix
- Very few write full sentences
- 1-3 emojis max

### Bio Pool (460+ entries)

| Category | Count | Description |
|----------|-------|-------------|
| Female-specific | 200 | Varied — coffee, travel, humor, quotes, school, lifestyle |
| Male-specific | 102 | Gym, tech, sports, cars, music, simple vibes |
| Gender-neutral | 101 | City names, emojis, generic quotes, "vibes only" |
| Minimal / empty | 60 | Empty strings, single emoji, just age, just city code |
| **Total** | **463** | |

### Bio Assignment Distribution

| Length | % of accounts | Examples |
|--------|-------------|---------|
| Empty (no bio) | ~12-15% | "" |
| Ultra-short (1-5 chars) | ~20% | "22", "BA", "☕", "🇸🇰" |
| Short (one line) | ~40% | "just vibes ✨", "not ur type 💅" |
| Medium (1-2 lines) | ~20% | "22 \| BA\ncoffee & travel ☕✈️" |
| Longer | ~5% | Rare — like a real IG feed |

### Key Bio Characteristics
1. **Mixed language** — Real SK youth switch between EN and SK naturally
2. **Self-deprecating humor** — "milá ale unavená 😴", "prežívam 🫠"
3. **Trending internet language** — "delulu is the solulu", "main character energy"
4. **Real university references** — UK BA, STU FIIT, FMFI UK, FEI TUKE
5. **City abbreviations** — BA, KE, ZA, BB, NR, TN (like real people use)
6. **Low emoji density** — 1-3 emojis, not emoji spam
7. **Gen-Z voice** — "404 bio not found", "chronically online", "espresso depresso"

---

## 3. Username Strategy — NATURAL PATTERNS

### Updated Patterns (36 total, up from 20)

Examples of generated usernames (from test run):
- `adriana.ilavska` — firstname.lastname
- `simonka_03` — nickname + year
- `xnikolkax` — x-wrapped nickname
- `its.simona` — English prefix trend
- `katka_jurcova` — nickname + lastname
- `marikaaa_99` — doubled last char
- `matejj_surka` — male with doubled char
- `patriciaaa_06` — triple letter (common among young people)
- `roman.pavlik` — simple first.last (male)
- `sofia_05` — just first + year

### Username Uniqueness
- **924/924 unique** (100%, 0% collision rate)
- All diacritics properly removed (ž→z, š→s, č→c, etc.)
- All lowercase, only a-z, 0-9, `.`, `_`
- 4-30 characters

---

## 4. Running the Pipeline

### Step 1: Get API Keys (free)

```
1. Pixabay:  https://pixabay.com/api/docs/     → Sign up, get key instantly
2. Pexels:   https://www.pexels.com/api/        → Sign up, get key instantly  
3. Unsplash: https://unsplash.com/developers    → Register app, get access key
4. fal.ai:   https://fal.ai/dashboard/keys      → Sign up, get key, add $5 credit
```

### Step 2: Download Stock Photos (~647 photos)

```bash
# Test with one API first:
python download_profile_pics.py --pixabay-key YOUR_KEY --dry-run
python download_profile_pics.py --pixabay-key YOUR_KEY --female 10 --male 5

# Full download with all APIs:
python download_profile_pics.py \
  --unsplash-key U_KEY \
  --pexels-key P_KEY \
  --pixabay-key PX_KEY \
  --female 650 --male 274
```

### Step 3: Generate AI Faces (~277 photos)

```bash
python generate_profile_pics.py --provider fal --api-key FAL_KEY --female 195 --male 82
```

### Step 4: Generate Assignment Manifest

```bash
python generate_assignments.py --accounts 924 --output profile_assignment_manifest.json
```

### Step 5: Execute Profile Changes (2-3 weeks)

Same as V1 — conservative rate limiting:
- MAX 1 profile change per account per day
- 5-10 min gap between accounts on same device
- Randomize device order and timing
- Don't change username+bio+pic on same day

---

## 5. Cost Estimate

| Item | Cost |
|------|------|
| Stock photo APIs | **$0** (all free tier) |
| fal.ai FLUX faces (~280 images) | **~$0.85** |
| Buffer for re-generations | ~$0.50 |
| **Total** | **~$1.35** |

---

## 6. File Inventory

| File | Status | Description |
|------|--------|-------------|
| `data/sk_cz_bios.json` | ✅ Updated | 463 bios (200F + 102M + 101N + 60min) |
| `data/sk_cz_names.json` | ✅ Updated | 36 username patterns, more natural |
| `data/download_profile_pics.py` | ✅ New | Stock photo downloader (Unsplash/Pexels/Pixabay) |
| `data/generate_profile_pics.py` | ✅ Exists | AI face generator (fal.ai/Replicate) |
| `data/generate_assignments.py` | ✅ Updated | V2 with diverse categories + minimal bios |
| `data/profile_assignment_manifest.json` | ✅ Generated | 924 accounts, all assigned |
| `data/profile_automation_plan.md` | ✅ This file | Strategy document |

---

## 7. Why This Approach Works

1. **Diverse profile pics** — A mix of faces, landscapes, pets, gym shots, silhouettes looks like a real Instagram feed. 924 identical AI selfies does not.

2. **Realistic bios** — 12% empty, 20% ultra-short, lots of one-liners. Real people don't all write structured "📍City | hobby1 | hobby2" bios.

3. **Natural usernames** — Patterns like `lucka_03`, `xnikolkax`, `its.simona` are what real SK/CZ teenagers actually use.

4. **Mixed sources** — Stock photos for non-face categories (no AI detection risk), AI only where uniqueness matters most (faces).

5. **Cheap** — Total cost under $2 for all 924 profile pictures.

6. **Automated** — Three scripts handle everything. No manual work except getting API keys.
