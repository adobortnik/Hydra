# Instagram Account Self-Creation at Scale — Research Report

**Date:** February 2026  
**Context:** Phone farm with 100+ Android devices, residential/mobile proxies, email accounts, captcha solving APIs, ADB/UIAutomator automation  
**Goal:** Replace purchased accounts with self-created ones for higher quality, full control, and lower compromise rate

---

## Table of Contents

1. [Registration Methods](#1-registration-methods)
2. [Phone Number Strategy](#2-phone-number-strategy)
3. [Account Warming](#3-account-warming)
4. [Anti-Detection](#4-anti-detection)
5. [2FA Setup & Access Control](#5-2fa-setup--access-control)
6. [Email Strategy](#6-email-strategy)
7. [Cost Analysis](#7-cost-analysis)
8. [Tools & Services](#8-tools--services)
9. [Recommended Pipeline](#9-recommended-pipeline)
10. [Risk Assessment](#10-risk-assessment)

---

## 1. Registration Methods

### 1.1 Registration Paths Available

Instagram offers three registration pathways:

| Method | Verification Required | Trust Level | Difficulty |
|--------|----------------------|-------------|------------|
| **Email only** | Email verification code | Low | Easy |
| **Phone number** | SMS verification code | Medium-High | Medium |
| **Facebook SSO** | Existing FB account | High (inherited) | Complex |

### 1.2 Email-First Registration (Recommended Primary Path)

**How it works:** Register with email → verify email code → IG may or may not ask for phone later.

**Pros:**
- Cheapest method — email accounts cost pennies or are free (self-hosted)
- No SMS service dependency
- Faster registration flow
- Can scale to thousands with catch-all domains
- Email is easier to maintain long-term control over

**Cons:**
- Lower initial trust score — IG assigns new email-only accounts a lower trust tier
- May trigger phone verification challenge within first 24-48 hours (especially if fingerprint/IP is suspicious)
- Higher chance of "suspicious activity" challenges during warm-up
- Some features may be restricted until phone is added

**Current state (2025-2026):** Instagram has increasingly pushed phone verification even for email registrations. About 30-50% of email-only registrations will be asked for a phone number within the first week, depending on IP quality and device fingerprint. However, starting with email and adding phone later is still viable.

### 1.3 Phone-First Registration

**How it works:** Register with phone number → SMS verification → optionally add email later.

**Pros:**
- Higher initial trust level
- Less likely to be challenged immediately after creation
- Accounts start with more permissions (higher rate limits)
- IG treats phone-verified accounts as more legitimate

**Cons:**
- Each account needs a unique phone number
- SMS services cost $0.10-$2.00+ per number for IG
- Number recycling risk — if the number is reused, someone else can recover "your" account
- VoIP numbers increasingly detected and rejected
- Real SIM numbers are the gold standard but expensive at scale

### 1.4 Facebook SSO Registration

**Not recommended for mass creation.** Requires pre-existing Facebook accounts, and Facebook has even stricter mass-creation detection. You'd be doubling your problem, not solving it.

### 1.5 Best Approach: Hybrid Email-First → Phone-Verify

**Register via email, then add phone verification within 24-72 hours during warm-up.**

This gives you:
- Full email control from day 1
- Phone verification boost during warm-up phase
- Option to remove/change phone later while keeping email as primary recovery
- Lower upfront cost (can batch phone verifications)

---

## 2. Phone Number Strategy

### 2.1 Phone Number Sources Compared

| Source | Cost/Number | IG Success Rate | Reuse Risk | Scalability | Recommended |
|--------|-------------|-----------------|------------|-------------|-------------|
| **Real SIM cards (local)** | $1-5 + monthly | 95%+ | Very Low | Low (physical) | ✅ Best quality |
| **eSIMs (data-only with SMS)** | $2-10 | 85-90% | Low | Medium | ✅ Good |
| **SMS-Activate (real SIMs)** | $0.15-0.50 | 70-85% | Medium | High | ✅ Primary |
| **SmsPva** | $0.10-0.40 | 65-80% | Medium | High | ✅ Primary |
| **GrizzlySMS** | $0.10-0.50 | 65-80% | Medium | High | ⚠️ Test first |
| **Tiger SMS** | $0.03-0.30 | 50-70% | High | High | ⚠️ Hit or miss |
| **5sim.net** | $0.05-0.50 | 60-75% | Medium-High | High | ⚠️ Variable |
| **Free VoIP (Google Voice, TextNow)** | Free | 10-20% | Very High | Low | ❌ Don't bother |
| **Twilio/Vonage VoIP** | $1-2/mo | 15-30% | Low | High | ❌ Mostly blocked |

### 2.2 SMS Verification Services — What Actually Works with IG

**Tier 1 — Most Reliable:**
- **SMS-Activate.org** — Largest provider. Has both real SIM and virtual numbers. For IG, use their "real SIM" numbers from countries like India, Indonesia, Philippines, Brazil. Success rate 70-85%. API available for automation. Cost: $0.15-$0.50/number for IG.
- **SmsPva.com** — 1.5M+ users. Real SIM-based and virtual numbers from 60+ countries. Good API. Similar pricing. Claims 99% delivery on real SIM numbers.
- **SMSHUB.org** — Good inventory, competitive pricing, API support.

**Tier 2 — Decent but Variable:**
- **GrizzlySMS** — Large inventory, reasonable prices, but quality varies by country/operator.
- **Tiger SMS** — Very cheap ($0.03+) but lower success rates. Good for testing.
- **Daisysms** — Newer, focused on quality. Worth testing.

**Tier 3 — Avoid for IG:**
- **Free SMS sites** (receive-smss.com etc.) — Numbers are public, already blacklisted
- **TextNow/Google Voice** — VoIP ranges detected by IG
- **Twilio/Plivo** — Programmatic VoIP, almost always rejected

### 2.3 Country Selection for SMS Numbers

**Best countries for IG SMS verification (high success, low cost):**
1. **India** — Massive inventory, cheap ($0.10-0.20), high success rate
2. **Indonesia** — Large supply, cheap, IG popular there
3. **Philippines** — Good success rate, affordable
4. **Brazil** — IG's 2nd largest market, numbers trusted
5. **Vietnam** — Cheap, decent success
6. **Russia/CIS** — Huge inventory but may raise flags if paired with non-Russian IP
7. **USA/UK** — Higher trust but 3-5x more expensive

**Important:** Match phone number country to proxy/device location when possible. An Indian phone number with a US IP is a yellow flag.

### 2.4 Avoiding Number Recycling/Compromise

**The #1 risk with SMS services:** The same number gets sold to someone else later, who can then use it to recover/steal your account.

**Mitigation strategies:**
1. **Add email as primary recovery** immediately after registration
2. **Enable TOTP 2FA** (not SMS 2FA) as soon as possible
3. **Change the phone number** to a number you control permanently (your own SIM) or remove it entirely after the trust period
4. **Use "rental" numbers** (available on SMS-Activate, SmsPva) for 4-24 hours instead of one-time numbers — allows you to receive follow-up verification
5. **Never use the phone number as the sole recovery method**
6. **Consider keeping a pool of permanent SIMs** just for recovery — rotate accounts through them after initial warm-up

### 2.5 Using Your Own Devices' SIMs

**If your phone farm devices have SIM slots:**

**Pros:**
- Highest trust level (real mobile number on real device)
- Mobile carrier IP (if using cellular data) = highest IP trust
- Full control — number never gets recycled
- Can receive SMS directly on device via ADB/automation

**Cons:**
- SIM cards cost money (prepaid: $1-10/SIM + minimum top-up)
- Many countries require KYC for SIM purchase (limits scale)
- 100+ SIM cards = significant ongoing cost if they need monthly top-ups
- Carrier may flag accounts with many SIMs registered to same identity
- Physical management overhead

**Hybrid approach:** Use SIM cards in 10-20 "primary" devices for highest-value accounts. Use SMS services for the bulk. Rotate SIM numbers through multiple accounts over time (register with SMS service number, later change to your SIM for permanent control).

---

## 3. Account Warming

### 3.1 Why Warming Matters

Instagram's anti-spam systems assign a trust score to every account. New accounts start at a very low score. Mass-created accounts that jump straight into following/DMing/posting get flagged immediately. The warm-up process gradually builds trust.

**Without warming:** 60-80% of accounts get action-blocked or banned within the first week.  
**With proper warming:** Survival rate jumps to 80-95%+ after 30 days.

### 3.2 Warm-Up Timeline

#### Phase 1: Creation Day (Day 0)
- Register the account
- Set profile photo (unique, AI-generated or stock — NOT the same photo on multiple accounts)
- Set display name (realistic, varied)
- Write a short bio
- **DO NOTHING ELSE** for 2-4 hours minimum
- If on mobile app: scroll the feed for 5-10 minutes passively

#### Phase 2: Days 1-3 (Passive Engagement)
- Open app 2-3x per day
- Scroll feed for 5-15 minutes each session
- Watch Reels (2-5 per session)
- Like 3-5 posts per session (from Explore page)
- **DO NOT follow anyone yet**
- **DO NOT post anything yet**
- **DO NOT DM anyone**
- Read notifications passively

#### Phase 3: Days 4-7 (Light Activity)
- Follow 3-5 accounts per day (popular/verified accounts first — celebrities, brands)
- Like 10-15 posts per day (spread across sessions)
- Leave 1-2 genuine-looking comments (2+ words, not generic)
- Save 2-3 posts
- Watch Stories from accounts you follow
- Optional: Upload first post (something generic/aesthetic)

#### Phase 4: Days 8-14 (Moderate Activity)
- Follow 5-10 accounts per day
- Like 15-30 posts per day
- Comment on 3-5 posts per day
- Post 1 piece of content every 2-3 days
- Watch 5-10 Reels per day
- Start using Story feature (view and post)
- Can start following niche-specific accounts

#### Phase 5: Days 15-30 (Ramping Up)
- Follow 10-20 accounts per day
- Like 30-50 posts per day
- Comment on 5-10 posts per day
- Post 1 piece of content every 1-2 days
- DM 1-2 people (if needed for your use case) — keep it natural
- Use Explore page regularly
- Engage with Reels (like, comment, share)

#### Phase 6: Day 30+ (Operational)
- Account is now considered "aged" by most IG systems
- Can gradually increase activity toward operational targets
- Still respect rate limits (see below)
- Continue posting regularly to maintain activity score

### 3.3 Rate Limits for New Accounts (2025-2026 Estimates)

| Action | Day 1-7 | Day 8-14 | Day 15-30 | Day 30+ |
|--------|---------|----------|-----------|---------|
| Follows/day | 5-10 | 10-20 | 20-40 | 50-100 |
| Unfollows/day | 0 | 5-10 | 15-30 | 50-80 |
| Likes/day | 10-20 | 30-50 | 50-100 | 100-300 |
| Comments/day | 2-5 | 5-10 | 10-20 | 20-50 |
| DMs/day | 0 | 1-3 | 3-10 | 10-30 |
| Story views/day | 20-50 | 50-100 | 100-200 | 200-500 |
| Posts/day | 0-1 | 1 | 1-2 | 2-3 |

**Critical:** These are SAFE limits. You CAN do more, but risk increases exponentially. Better to stay under these and have accounts survive than push limits and lose them.

### 3.4 Warm-Up Automation Tips

- **Randomize everything** — session times, scroll duration, like patterns, follow counts
- **Use realistic delays** — humans don't like 50 posts in 2 seconds. Space actions 3-15 seconds apart with random variance
- **Vary session lengths** — short sessions (2-5 min), medium (10-20 min), long (30+ min)
- **Time of day matters** — most activity should be during "waking hours" for the account's supposed timezone
- **Rest periods** — accounts should "sleep" (no activity for 6-8 hours per day)
- **Weekend patterns** — slightly different activity on weekends vs weekdays
- **Content diversity** — don't just like photos in one niche; browse broadly like a real user

---

## 4. Anti-Detection

### 4.1 What Instagram Looks For

Instagram uses multiple signals to detect mass account creation and phone farms:

#### Device Fingerprinting
- **Android ID** — unique per device/factory reset. IG stores this.
- **Google Advertising ID (GAID)** — resettable but tracked
- **Hardware serial numbers** — build fingerprint, CPU info, sensor data
- **Screen resolution & DPI**
- **Installed apps list** — IG can see what else is on the device
- **Device model/manufacturer** — 100 identical Redmi Note 10s is suspicious
- **SIM/carrier info** — IMEI, ICCID, carrier name
- **WiFi MAC address** — shared WiFi networks = linked accounts
- **Battery patterns** — all phones at same charge level = farm
- **Accelerometer/gyroscope data** — lack of movement patterns = bot or farm device sitting on a shelf

#### Network/IP Signals
- **IP reputation** — datacenter IPs are instant death. Even "residential" proxies from cheap providers may be flagged
- **IP-to-geolocation consistency** — IP in New York but phone language is Hindi?
- **Multiple accounts per IP** — biggest red flag. Even residential IPs get flagged if 20+ accounts register from the same one
- **ASN reputation** — some residential proxy ASNs are well-known to IG
- **TLS fingerprint** — IG app has a known TLS fingerprint; custom HTTP clients may differ
- **Connection patterns** — 100 devices all connecting at the exact same times

#### Behavioral Signals
- **Registration velocity** — many accounts created in short time from similar IPs/devices
- **Identical profile patterns** — similar bios, similar usernames, same photo styles
- **Action patterns** — all accounts following the same people in the same order
- **Content patterns** — same images reposted across accounts
- **Session patterns** — identical session lengths, identical time-between-actions
- **Growth patterns** — unnatural follower/following ratios

#### Phone Number Signals
- **VoIP detection** — IG maintains databases of VoIP number ranges
- **Number reputation** — numbers previously used for spam
- **Country mismatch** — Indian number + US IP + Spanish device language
- **Carrier type** — prepaid vs postpaid (postpaid = higher trust)
- **Number age** — recently activated numbers are lower trust

### 4.2 Minimizing Detection Risk

#### Device-Level
1. **Use diverse device models** — don't buy 100 of the same phone. Mix brands/models
2. **Factory reset between account cycles** — if reusing a device for a new account, full factory reset + new Google account
3. **Reset Android ID** after factory reset (happens automatically)
4. **Reset Google Advertising ID** before each new account
5. **Use different wallpapers/themes** — IG can fingerprint visual settings via screenshots
6. **Install varied "civilian" apps** — each device should have a slightly different app mix
7. **Use Xposed/LSPosed modules** for device fingerprint spoofing (risky — can trigger SafetyNet failures)
8. **Consider rooted devices with fingerprint spoofing** — BUT IG detects root on some devices
9. **Magisk + DenyList** to hide root from IG while maintaining spoofing capability

#### Network-Level
1. **One account per IP** — or at most 2-3 per residential IP
2. **Use mobile/4G proxies** — highest trust because they're real carrier IPs
3. **Rotate IPs per account, not per action** — each account should consistently use the same IP (sticky sessions)
4. **Match IP geolocation to phone number country** when possible
5. **Use residential proxies from reputable providers** (Bright Data, Smartproxy, IPRoyal, Soax)
6. **Avoid free/cheap proxy providers** — their IPs are burned
7. **If using mobile proxies on-device** (cellular data): best possible setup, but expensive for 100+ SIMs with data plans
8. **Test IP reputation** before use — check on ipqualityscore.com, scamalytics.com

#### Behavioral-Level
1. **Randomize EVERYTHING** — timing, action counts, content, session patterns
2. **No two accounts should follow the same sequence of users**
3. **Use different content sources per account** — don't repost the same images
4. **Vary username patterns** — don't use sequential or templated usernames
5. **Human-like delays** — 3-30 second random delays between actions
6. **Scroll before acting** — don't just open app → like → close. Simulate browsing
7. **Use the app natively** (via UIAutomator/ADB tap) rather than API calls — IG detects unofficial API usage
8. **Vary registration details** — different names, bios, profile photos per account
9. **Stagger creation** — don't create 50 accounts in one day. Spread over weeks.

### 4.3 Registration Velocity Recommendations

- **Per IP:** Maximum 1 account per IP per 24 hours (ideally per week)
- **Per device:** Maximum 1 account per device (factory reset between)
- **Total farm output:** With 100 devices, create 5-10 accounts per day maximum (not all 100 at once)
- **Stagger creation times** — spread across the day, not all at 9 AM
- **Cool-down period per device:** After creating an account, that device should only run that account for at least 30 days

---

## 5. 2FA Setup & Access Control

### 5.1 Why 2FA Matters for Self-Created Accounts

Without 2FA:
- If the phone number gets recycled, someone can take over via SMS recovery
- If the email is compromised, the account is gone
- IG may force security checkpoints that require verification you can't complete

With proper 2FA:
- You control access via TOTP (time-based one-time password)
- Even if phone number changes hands, account is protected
- Backup codes give you emergency access

### 5.2 TOTP 2FA (Recommended)

**Setup process:**
1. Go to Settings → Security → Two-Factor Authentication
2. Choose "Authentication App"
3. IG generates a secret key (TOTP seed)
4. **CRITICAL:** Save this seed/QR code — this is the key to the account
5. Enter the 6-digit code to confirm

**For mass management:**
- Use a TOTP library (Python: `pyotp`) to generate codes programmatically
- Store seeds in a secure database: `account_id → totp_seed`
- Never rely on a single authenticator app — seeds in database = access from anywhere
- Can generate codes on the fly during automated login

**Example (Python):**
```python
import pyotp

# Store this seed when setting up 2FA
seed = "JBSWY3DPEHPK3PXP"  # from IG's setup flow
totp = pyotp.TOTP(seed)
code = totp.now()  # "492039" — valid for 30 seconds
```

### 5.3 SMS 2FA (Avoid if possible)

**Problems:**
- Tied to phone number — if number gets recycled, attacker can receive your 2FA codes
- Can't easily automate (need SMS reception for every login)
- Some SMS services don't keep numbers available long enough
- More expensive (ongoing SMS reception costs)

**Only use SMS 2FA if:**
- You have permanent SIM cards you control
- You can receive SMS on those SIMs indefinitely
- You have a fallback (backup codes stored)

### 5.4 Backup Codes

**ALWAYS generate and store backup codes:**
1. Go to Settings → Security → Two-Factor Authentication → Backup Codes
2. IG gives you 5 single-use codes
3. **Store these in your database alongside the account**
4. These are your emergency access if TOTP seed is lost

### 5.5 Account Recovery Setup Checklist

For every self-created account, ensure:
- [ ] Email verified and accessible
- [ ] TOTP 2FA enabled with seed stored in database
- [ ] Backup codes generated and stored
- [ ] Phone number either: (a) your permanent SIM, or (b) removed after warm-up
- [ ] If using SMS service number: change to permanent number or remove within 7 days

---

## 6. Email Strategy

### 6.1 Email Provider Comparison

| Provider | Trust Level | Cost | Scalability | Automation | Recommended |
|----------|-------------|------|-------------|------------|-------------|
| **Self-hosted (catch-all)** | Medium | $5-20/mo for domain + server | Unlimited | Easy | ✅ Primary |
| **Gmail** | High | Free (but needs phone) | Low-Medium | Hard (2FA, CAPTCHA) | ⚠️ For high-value accounts |
| **Outlook/Hotmail** | High | Free | Medium | Medium | ⚠️ Good but risky at scale |
| **Yahoo** | Medium | Free | Medium | Medium | ⚠️ OK |
| **ProtonMail** | Medium | Free tier limited | Low | Hard | ❌ Not scalable |
| **Temp mail services** | Very Low | Free | Unlimited | Easy | ❌ IG blocks most |
| **Yandex** | Medium-Low | Free | Medium | Easy | ⚠️ OK for non-critical |
| **Rambler/Mail.ru** | Low | Free | Medium | Easy | ❌ Often flagged |

### 6.2 Self-Hosted Email (Recommended for Scale)

**Setup:**
1. **Buy multiple domains** — don't use one domain for 500 accounts
   - Get 10-20 domains, spread accounts across them
   - Use realistic-looking domains (not `fakeemail123.xyz`)
   - Mix TLDs: `.com`, `.net`, `.org`, `.co`, `.io`
   - Aged domains (1+ year old) are better than fresh ones

2. **Configure catch-all**
   - Any address @yourdomain.com gets caught
   - Create unique addresses: `john.smith.2847@domain.com`, `sarah.k.wilson@domain.com`
   - Looks more natural than `user1@domain.com`, `user2@domain.com`

3. **Email server options:**
   - **Mailcow** (self-hosted, Docker-based) — full control, free
   - **iRedMail** — simpler setup
   - **Zoho Mail** (hosted, 5 free users per domain, then $1/user/mo)
   - **ImprovMX** (catch-all forwarding only, $9/mo)
   - **Cloudflare Email Routing** (free catch-all → forward to central inbox)

4. **DNS records** — Set up SPF, DKIM, DMARC properly so emails from IG don't bounce and your domain looks legitimate

**Best practice:** Use Cloudflare Email Routing (free) to catch all emails for your domains and forward to a central mailbox. Programmatically parse incoming verification codes.

### 6.3 Gmail/Outlook Accounts

**For high-value accounts that need maximum trust:**
- Gmail accounts with Google Workspace ($6/user/mo) are the gold standard
- Outlook.com accounts are free but Microsoft makes mass creation very difficult
- Both require phone verification for creation (circular problem)

**Gmail dot trick:** `john.smith@gmail.com` = `j.o.h.n.s.m.i.t.h@gmail.com` = `johnsmith@gmail.com`. Gmail ignores dots. ONE account, infinite variations. But IG may be wise to this — use with caution.

**Gmail plus trick:** `user+tag1@gmail.com`, `user+tag2@gmail.com` all route to `user@gmail.com`. Definitely detected by IG — avoid.

### 6.4 How IG Treats Different Providers

- **Gmail/Outlook:** Highest trust. IG treats these as "real person" indicators
- **Self-hosted/custom domains:** Neutral to slightly lower trust. Not a red flag unless the domain itself is new/suspicious
- **Temp mail domains (guerrillamail, tempmail, etc.):** IG maintains blacklists. These get rejected instantly
- **Russian providers (mail.ru, yandex):** Not blocked but lower trust, especially with non-Russian IPs
- **ISP emails (comcast, att, etc.):** High trust but impossible to create at scale

### 6.5 Email Strategy Recommendation

**Two-tier approach:**

**Tier 1 (high-value accounts, 20-30%):**
- Use Gmail or Outlook accounts (pre-purchased or self-created)
- Or use well-aged custom domain emails with good reputation

**Tier 2 (bulk accounts, 70-80%):**
- Self-hosted catch-all across 10-20 domains
- Unique, realistic-looking email addresses per account
- Domains purchased 30+ days before use (aging)
- Proper DNS (SPF/DKIM/DMARC)

---

## 7. Cost Analysis

### 7.1 Buying Accounts (Current Approach)

| Item | Cost |
|------|------|
| IG account (aged, phone-verified) | $0.50 - $3.00 per account |
| Replacement rate (compromised/banned) | 30-50% within 30 days |
| **Effective cost per surviving account** | **$1.00 - $6.00** |
| Time investment | Low (just buy and load) |
| Control level | Low (shared credentials, recycled numbers) |

**Total for 100 accounts/month: $100-$600**

### 7.2 Self-Creation Costs

| Item | Cost (Monthly) | Notes |
|------|---------------|-------|
| SMS verification (virtual) | $0.15-0.50 × accounts | Per account, one-time |
| Email domains (10-20) | $10-20/mo total | Amortized across all accounts |
| Email hosting/routing | $0-20/mo | Cloudflare routing = free |
| Proxy costs | Already have | No additional cost |
| Captcha solving | $2-3 per 1000 | Minimal for registration |
| Electricity/devices | Already have | No additional cost |
| Staff time for monitoring | 2-4 hrs/week | $0 if automated well |
| **Total variable cost per account** | **$0.20-0.75** | |
| **Survival rate (with warming)** | 80-95% | Much higher than purchased |
| **Effective cost per surviving account** | **$0.25-0.85** | |

**Total for 100 accounts/month: $25-$85**

### 7.3 Self-Creation with Premium Numbers (Real SIMs)

| Item | Cost |
|------|------|
| Prepaid SIM cards | $2-5 each (one-time) |
| Minimum top-up | $1-5 per SIM |
| Per account cost | $3-10 |
| Survival rate | 90-98% |
| **Effective cost per surviving account** | **$3.50-$11.00** |

More expensive per account, but highest quality and survival rate.

### 7.4 Cost Summary

| Method | Cost/Account | Survival Rate | Control | Quality |
|--------|-------------|---------------|---------|---------|
| Buying from suppliers | $1-6 effective | 50-70% | Low | Low-Medium |
| Self-create (SMS service) | $0.25-0.85 effective | 80-95% | Full | Medium-High |
| Self-create (real SIMs) | $3.50-11 effective | 90-98% | Full | Highest |
| Hybrid (SMS service + later SIM) | $0.50-2.00 effective | 85-95% | Full | High |

**Conclusion:** Self-creation with SMS services is 3-10x cheaper than buying AND produces higher-quality accounts with full control. Even the premium SIM approach is competitive when you factor in the much higher survival rate.

---

## 8. Tools & Services

### 8.1 SMS Verification Services

| Service | URL | API | IG Price Range | Notes |
|---------|-----|-----|---------------|-------|
| SMS-Activate | sms-activate.org | Yes | $0.15-0.50 | Largest, most reliable |
| SmsPva | smspva.com | Yes | $0.10-0.40 | Good API, 1.5M+ users |
| GrizzlySMS | grizzlysms.com | Yes | $0.10-0.50 | Large inventory |
| Tiger SMS | tiger-sms.com | Yes | $0.03-0.30 | Cheapest, variable quality |
| SMSHUB | smshub.org | Yes | $0.10-0.60 | Good for CIS numbers |
| Daisysms | daisysms.com | Yes | $0.20-0.60 | Quality focus |

### 8.2 Proxy Services

| Service | Type | Cost | IG Suitability |
|---------|------|------|---------------|
| **Bright Data** | Residential/Mobile | $12.75/GB+ | Best, but expensive |
| **Smartproxy** | Residential | $8/GB+ | Good, cheaper |
| **Soax** | Residential/Mobile | $6.60/GB+ | Good value |
| **IPRoyal** | Residential | $5.50/GB+ | Budget-friendly |
| **Proxidize** | Mobile (self-built) | Hardware cost only | Best for phone farms |
| **Your own 4G modems** | Mobile | Data plan cost | Optimal if you can set up |

**Note:** Since you have proxies already, focus on ensuring they're residential or mobile (not datacenter) and that IPs aren't burned for IG specifically.

### 8.3 Android Automation Tools

| Tool | Type | Best For | Notes |
|------|------|----------|-------|
| **UIAutomator2** | Native Android testing | App interaction | Your current approach — solid |
| **Appium** | Cross-platform automation | Complex flows | Heavy but powerful |
| **ADB shell input** | Direct ADB commands | Simple taps/swipes | Lightweight |
| **Frida** | Dynamic instrumentation | API hooking, fingerprint spoofing | Advanced |
| **scrcpy** | Screen mirroring + control | Remote management | Good for monitoring |
| **Python + uiautomator2** | Python bindings | Scripted automation | Recommended |

### 8.4 Anti-Detect / Fingerprint Spoofing

| Tool | Platform | Cost | Notes |
|------|----------|------|-------|
| **Multilogin** | Desktop browser | $99/mo+ | Not relevant for phone farm |
| **GoLogin** | Desktop browser | $49/mo+ | Not relevant for phone farm |
| **Xposed/LSPosed** | Android (root) | Free | Fingerprint spoofing modules |
| **Magisk + modules** | Android (root) | Free | Hide root, spoof device IDs |
| **Device ID changer apps** | Android | Free-$5 | Change Android ID, IMEI (root) |

**For your phone farm setup:** Xposed/LSPosed + Magisk is more relevant than desktop anti-detect browsers since you're using real Android devices.

### 8.5 Email Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **Cloudflare Email Routing** | Free catch-all forwarding | No inbox, just forwarding |
| **Mailcow** | Self-hosted mail server | Docker-based, full control |
| **iRedMail** | Self-hosted mail server | Simpler than Mailcow |
| **Zoho Mail** | Hosted email for domains | Free for 5 users |
| **Python imaplib/imapclient** | Programmatic email reading | Parse verification codes |

### 8.6 Account Management

| Tool | Purpose | Notes |
|------|---------|-------|
| **Custom database** | Central account registry | Store credentials, TOTP seeds, status |
| **Airtable/Notion** | Account tracking | Good for smaller operations |
| **Custom dashboard** | Monitor farm status | Build with your existing infra |

---

## 9. Recommended Pipeline

Given your setup (100+ Android devices, residential/mobile proxies, automation capability), here's the optimal step-by-step pipeline:

### Phase 0: Infrastructure Preparation (One-time, 1-2 weeks)

1. **Set up email infrastructure**
   - Purchase 15-20 domains from different registrars (NameCheap, Cloudflare, Porkbun)
   - Point all MX records to Cloudflare Email Routing (free)
   - Set up catch-all → forward to central inbox
   - Configure SPF/DKIM/DMARC for all domains
   - Set up Python script to monitor inbox and extract verification codes (IMAP)
   - Let domains age for at least 2-4 weeks before using

2. **Set up SMS service integration**
   - Create accounts on SMS-Activate + SmsPva (have a backup)
   - Load balance ($50-100 initial deposit on each)
   - Write API integration to request numbers, receive codes, release numbers
   - Test with 5-10 manual IG registrations to verify success rates
   - Document which countries/operators work best

3. **Prepare account database**
   - Create database schema:
     ```
     accounts:
       - id, username, password, email, phone_number
       - totp_seed, backup_codes[]
       - device_id, proxy_ip
       - status (created/warming/active/banned/flagged)
       - created_at, last_active, trust_level
       - registration_method, phone_source
     ```

4. **Prepare devices**
   - Ensure diverse device models across the farm
   - Root devices with Magisk (if not already)
   - Install LSPosed for fingerprint spoofing
   - Set up proxy per device (SOCKS5 or WireGuard tunnel)
   - Ensure each device has a unique: Android ID, GAID, device name, Google account
   - Install IG app from Play Store (not sideloaded APK — IG checks)

5. **Set up automation scripts**
   - Registration flow (UIAutomator)
   - Email verification code retrieval
   - SMS verification code retrieval (via SMS service API)
   - Warm-up activity scripts (scrolling, liking, following)
   - 2FA setup flow
   - Health check script (verify accounts are still alive)

### Phase 1: Registration (Ongoing, 5-10 accounts/day)

**Daily process:**

1. **Select device + proxy combo** — each fresh device + IP that hasn't been used for IG registration recently
2. **Generate account details:**
   - Unique realistic username (use a name generator + random numbers)
   - Unique email from one of your catch-all domains
   - Strong password
   - AI-generated profile photo (use StyleGAN/DALL-E or stock photos)
3. **Execute registration via UIAutomator:**
   - Open IG app → Sign up with email
   - Enter email → retrieve verification code from inbox
   - Enter code → set username → set password
   - Add profile photo → fill bio
   - Skip all "find friends" prompts
4. **Phone verification (if prompted):**
   - Request number from SMS service API
   - Enter number in IG
   - Retrieve SMS code via API
   - Enter code
   - Release number
5. **Record everything in database:**
   - All credentials
   - Device ID and proxy used
   - Phone number used (and source)
   - Timestamp
6. **Initial session:** Scroll feed for 5-10 minutes passively, then close
7. **Leave device assigned to this account for warm-up period**

**Daily target:** 5-10 new accounts across your 100+ devices. This is intentionally conservative. Speed of creation is your enemy — quality and stealth is your friend.

### Phase 2: Warm-Up (Days 1-30)

**Automated warm-up schedule per account:**

Run the warm-up bot on each device with its assigned account:

```
Day 1-3:   2-3 sessions/day, 5-15 min each
           - Scroll feed
           - Watch 2-5 Reels
           - Like 3-5 posts
           
Day 3-7:   3 sessions/day
           - Add phone number (if not done during registration)
           - Follow 3-5 popular accounts
           - Like 10-15 posts
           - 1-2 comments
           - Enable TOTP 2FA → save seed to DB
           - Generate backup codes → save to DB
           
Day 7-14:  3-4 sessions/day
           - Follow 5-10 accounts (mix popular + niche)
           - Like 15-30 posts
           - 3-5 comments
           - Post first content
           - Watch Stories
           - Remove SMS service phone number (replace with permanent or remove)
           
Day 14-30: 3-4 sessions/day
           - Follow 10-20 accounts
           - Like 30-50 posts
           - 5-10 comments
           - Post every 2-3 days
           - DM 1-2 people (if needed)
           - Full feature usage
```

### Phase 3: Graduation & Operational Use (Day 30+)

1. **Health check:** Verify account is alive, not restricted
2. **Update status in DB:** `warming` → `active`
3. **Account is ready for operational use**
4. **Continue maintenance activity** even during operational use (minimum 1 session/day of "organic" activity)
5. **Device can be freed for next registration cycle** (factory reset → new account)

### Pipeline Throughput Estimates

With 100 devices and conservative pacing:

| Metric | Value |
|--------|-------|
| New registrations/day | 5-10 |
| Warm-up period | 30 days |
| Devices dedicated to warming | 150-300 (overlapping) |
| Steady-state output | 150-300 ready accounts/month |
| Expected survival rate | 85-95% |
| Net usable accounts/month | ~130-285 |

**With 100 devices, you can realistically produce 100-200 fully warmed, operational accounts per month** by rotating devices through the create → warm → graduate → reset cycle.

### Phase 4: Maintenance & Recovery

1. **Daily health checks:** Bot checks if each account can still log in, post, follow
2. **Challenge response:** If IG challenges an account (selfie, phone, email), respond automatically or flag for manual review
3. **Replace lost accounts:** Feed device back into Phase 1
4. **Rotate proxies:** If an IP gets associated with banned accounts, rotate it out
5. **Database hygiene:** Track metrics (ban rate, challenge rate) per device, proxy, phone source — optimize based on data

---

## 10. Risk Assessment

### 10.1 Legal Risks

- **Terms of Service violation** — Creating fake/multiple accounts violates IG's ToS. This can result in permanent bans and potential legal action (though Meta rarely pursues individuals)
- **CAN-SPAM / GDPR** — If accounts are used for unsolicited messaging, additional legal exposure
- **Computer Fraud and Abuse Act** — In the US, automated access to platforms can technically fall under CFAA
- **KYC requirements** — Bulk SIM purchases may trigger regulatory flags in some countries

### 10.2 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Mass ban wave | Medium | High — lose many accounts at once | Diversify creation methods, don't rush |
| IG algorithm update | Medium | Medium — current methods may stop working | Stay in communities, adapt quickly |
| SMS service shutdown | Low | Medium — need to switch providers | Have 2+ SMS services integrated |
| Email domain blacklisted | Low-Medium | Medium — new accounts from that domain fail | Use multiple domains, rotate |
| Device fingerprint detection improvement | Medium | High — farm devices get blacklisted | Fingerprint spoofing, device diversity |
| Proxy IP burns | Medium | Medium — accounts on that IP get flagged | Monitor IP reputation, rotate |
| Phone number recycled → account takeover | Medium | High per account | TOTP 2FA + email recovery |

### 10.3 Operational Risks

- **Staff knowledge concentration** — ensure multiple people understand the pipeline
- **Single point of failure** — if main database is lost, all account credentials are gone (backup!)
- **Cost creep** — SMS services, domains, proxies add up. Monitor ROI
- **Quality vs quantity trap** — resist the urge to speed up. The pipeline works because it's slow and careful

### 10.4 IG's Evolving Defenses (2025-2026 Trends)

- **AI-based behavioral analysis** — IG is investing heavily in ML models that detect bot-like patterns
- **Selfie verification** — increasingly used for suspicious accounts (hard to automate)
- **Video selfie verification** — emerging, nearly impossible to automate
- **Device attestation** — Google Play Integrity API may be leveraged to verify genuine devices
- **Cross-platform signals** — Meta shares data between FB/IG/WhatsApp for fraud detection
- **Network graph analysis** — detecting clusters of accounts that interact with each other

---

## Appendix A: Quick Reference Card

### Must-Do Checklist for Every Account

- [ ] Unique device (or factory-reset between accounts)
- [ ] Unique residential/mobile IP
- [ ] Unique email from varied domains
- [ ] Realistic username (not sequential/templated)
- [ ] Unique profile photo
- [ ] Phone verification (real SIM or quality SMS service)
- [ ] 30-day warm-up before operational use
- [ ] TOTP 2FA enabled with seed stored
- [ ] Backup codes stored
- [ ] SMS service phone number removed/replaced after warm-up
- [ ] All credentials backed up in database

### Emergency Procedures

**If account gets challenged:**
1. Try email verification first
2. If phone requested: use stored phone number or SMS service rental
3. If selfie requested: flag for manual review
4. If action-blocked: reduce activity, wait 24-48 hours
5. If permanently banned: mark in DB, recycle device, start new account

### Key Numbers to Remember

- Max 1 account per IP per week
- Max 5-10 new accounts per day across entire farm
- 30-day warm-up minimum
- 3-15 second delays between automated actions
- 6-8 hours "sleep" per account per day
- 85-95% expected survival rate with proper process

---

## Appendix B: Recommended First Steps

**Week 1:**
1. Set up 5 catch-all domains with Cloudflare Email Routing
2. Create accounts on SMS-Activate and SmsPva, deposit $25 each
3. Write email verification code parser
4. Write SMS API integration
5. Manually create 5 test accounts to validate the flow

**Week 2:**
1. Automate the registration flow with UIAutomator
2. Create the account database
3. Start warming up the 5 test accounts manually
4. Observe behavior — note any challenges or issues

**Week 3-4:**
1. Automate the warm-up flow
2. Scale to 5 accounts/day
3. Monitor survival rates
4. Iterate on timing, delays, and activity patterns based on results

**Month 2:**
1. Scale to 10 accounts/day
2. Optimize based on data (which phone countries work best, which IPs are cleanest)
3. Set up monitoring dashboard
4. Begin graduating first batch of accounts to operational use

---

*This document should be treated as a living guide. Update it as Instagram's detection methods evolve and as you gather data from your own operations.*
