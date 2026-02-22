"""
Instagram Insights Scraper Module
====================================
Scrapes all available Professional dashboard analytics from a Business profile.

Navigation flow:
  Profile → Professional Dashboard → Views / Interactions / Followers / Content

Uses dump_hierarchy() + regex parsing for reliable value extraction.
Tested on IG clone package com.instagram.androie (2026-02-22).

Functions:
  scrape_insights(d, pkg)          — full scrape with drill-down into each section
  scrape_insights_overview(d, pkg) — quick dashboard-only scrape (no drill-down)
  save_insights_to_db(data, ...)   — persist scraped data to phone_farm.db
"""

import datetime
import json
import logging
import re
import time

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_PKG = 'com.instagram.androie'


def _safe_int(value, default=None):
    """Parse an integer from text, returning default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    value = str(value).strip().replace(',', '').replace(' ', '')
    if value in ('', '--', '-'):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    """Parse a float from text, returning default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().replace(',', '').replace('%', '').replace(' ', '')
    if value in ('', '--', '-'):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _extract_number_from_desc(xml, pattern):
    """Extract a number from content-desc matching a regex pattern.
    
    Example: pattern=r'([\d,]+)\s*Views' matches desc="153 Views" → 153
    """
    match = re.search(pattern, xml, re.IGNORECASE)
    if match:
        return _safe_int(match.group(1))
    return None


def _extract_percentage(xml, label, search_range=500):
    """Extract percentage value near a given label in XML.
    
    Finds the label, then looks for the nearest percentage text within
    search_range characters after it.
    """
    # Find the label position
    label_match = re.search(re.escape(label), xml, re.IGNORECASE)
    if not label_match:
        return None
    
    # Search for percentage in the vicinity after the label
    start = label_match.end()
    end = min(start + search_range, len(xml))
    region = xml[start:end]
    
    pct_match = re.search(r'text="([\d.]+)%"', region)
    if pct_match:
        return _safe_float(pct_match.group(1))
    
    # Also check content-desc
    pct_match = re.search(r'content-desc="([\d.]+)%"', region)
    if pct_match:
        return _safe_float(pct_match.group(1))
    
    return None


def _extract_value_near_label(xml, label, search_range=500):
    """Extract a numeric value from the text element nearest after a label."""
    label_match = re.search(re.escape(label), xml, re.IGNORECASE)
    if not label_match:
        return None
    
    start = label_match.end()
    end = min(start + search_range, len(xml))
    region = xml[start:end]
    
    # Look for text="NNN" where NNN is a number (possibly with commas)
    val_match = re.search(r'text="([\d,]+)"', region)
    if val_match:
        return _safe_int(val_match.group(1))
    
    return None


def _extract_change_pct_near_label(xml, label, search_range=800):
    """Extract change percentage (e.g. "300%") near a label.
    
    Looks for percentage patterns after the label's value.
    """
    label_match = re.search(re.escape(label), xml, re.IGNORECASE)
    if not label_match:
        return None
    
    start = label_match.end()
    end = min(start + search_range, len(xml))
    region = xml[start:end]
    
    # Look for change percentage (could be "0%", "300%", etc.)
    # Skip the first percentage if it's the followers/non-followers split
    pcts = re.findall(r'text="([\d.]+)%"', region)
    if pcts:
        # Return the first percentage found
        return _safe_float(pcts[0])
    
    return None


def _extract_date_range(xml):
    """Extract date range like 'Jan 22 - Feb 20' from XML."""
    # Pattern: Mon DD - Mon DD (e.g., "Jan 22 - Feb 20")
    match = re.search(
        r'text="([A-Z][a-z]{2}\s+\d{1,2}\s*[-–]\s*[A-Z][a-z]{2}\s+\d{1,2})"',
        xml
    )
    if match:
        return match.group(1)
    
    # Also check content-desc
    match = re.search(
        r'content-desc="([A-Z][a-z]{2}\s+\d{1,2}\s*[-–]\s*[A-Z][a-z]{2}\s+\d{1,2})"',
        xml
    )
    if match:
        return match.group(1)
    
    return None


def _extract_comparison_period(xml):
    """Extract comparison period like 'Dec 23 - Jan 21' from 'vs ...' pattern."""
    match = re.search(
        r'text="vs\s+([A-Z][a-z]{2}\s+\d{1,2}\s*[-–]\s*[A-Z][a-z]{2}\s+\d{1,2})"',
        xml, re.IGNORECASE
    )
    if match:
        return match.group(1)
    
    # Also look in content-desc
    match = re.search(
        r'content-desc="vs\s+([^"]+)"',
        xml, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    
    return None


def _wait_for_load(d, timeout=4):
    """Wait for screen to load after navigation."""
    time.sleep(timeout)


def _scroll_down(d):
    """Scroll down to reveal more content."""
    try:
        d.swipe(540, 1500, 540, 600, duration=0.4)
        time.sleep(1.5)
    except Exception as e:
        log.debug("Scroll failed: %s", e)


def _press_back(d):
    """Press back and wait."""
    try:
        d.press('back')
        time.sleep(2)
    except Exception as e:
        log.debug("Back press failed: %s", e)


# ---------------------------------------------------------------------------
# Overview Scraper (dashboard only — no drill-down)
# ---------------------------------------------------------------------------

def scrape_insights_overview(d, pkg=DEFAULT_PKG):
    """Quick scrape of Professional Dashboard overview — no drill-down.
    
    Navigates to Profile → Professional dashboard and extracts:
    - Views, Interactions, New followers, Content shared counts
    - Date range
    
    Args:
        d: uiautomator2 device instance
        pkg: Instagram package name (clone)
    
    Returns:
        dict with overview data, or None on failure
    """
    result = {
        'scraped_at': datetime.datetime.now().isoformat(),
        'date_range': None,
        'overview': {
            'views': None,
            'interactions': None,
            'new_followers': None,
            'content_shared': None,
        },
    }
    
    try:
        # Step 1: Navigate to Profile tab
        log.info("Navigating to Profile tab...")
        profile_btn = d(description="Profile")
        if not profile_btn.exists(timeout=5):
            profile_btn = d(resourceIdMatches=".*profile_tab$")
        
        if profile_btn.exists(timeout=5):
            profile_btn.click()
            time.sleep(3)
        else:
            log.warning("Profile tab not found")
            return None
        
        # Step 2: Tap "Professional dashboard"
        log.info("Opening Professional dashboard...")
        dashboard_btn = d(textContains="Professional dashboard")
        if not dashboard_btn.exists(timeout=5):
            # Try scrolling down on profile to find it
            _scroll_down(d)
            dashboard_btn = d(textContains="Professional dashboard")
        
        if not dashboard_btn.exists(timeout=5):
            log.warning("Professional dashboard not found — account may not be Business")
            return None
        
        dashboard_btn.click()
        _wait_for_load(d, timeout=4)
        
        # Step 3: Dump hierarchy and parse overview
        xml = d.dump_hierarchy()
        
        # Extract date range
        result['date_range'] = _extract_date_range(xml)
        log.info("Date range: %s", result['date_range'])
        
        # Extract overview metrics
        # Views
        result['overview']['views'] = _extract_value_near_label(xml, "Views")
        
        # Interactions
        result['overview']['interactions'] = _extract_value_near_label(xml, "Interactions")
        
        # New followers
        result['overview']['new_followers'] = _extract_value_near_label(xml, "New followers")
        
        # Content shared
        result['overview']['content_shared'] = _extract_value_near_label(
            xml, "Content you shared")
        
        # If primary extraction missed values, try alternative patterns
        if result['overview']['views'] is None:
            # Try matching "NNN" text near Views label using broader search
            views_region = _find_region_around_label(xml, "Views", 300)
            if views_region:
                nums = re.findall(r'text="(\d[\d,]*)"', views_region)
                if nums:
                    result['overview']['views'] = _safe_int(nums[0])
        
        log.info("Overview scraped: %s", result['overview'])
        
        # Navigate back to profile
        _press_back(d)
        
        return result
        
    except Exception as e:
        log.error("Insights overview scrape failed: %s", e)
        return None


def _find_region_around_label(xml, label, chars=300):
    """Get a region of XML around a label for pattern matching."""
    match = re.search(re.escape(label), xml, re.IGNORECASE)
    if match:
        start = max(0, match.start() - chars)
        end = min(len(xml), match.end() + chars)
        return xml[start:end]
    return None


# ---------------------------------------------------------------------------
# Full Insights Scraper (with drill-down)
# ---------------------------------------------------------------------------

def scrape_insights(d, pkg=DEFAULT_PKG):
    """Full scrape of all Professional Dashboard insights with drill-down.
    
    Navigates through each section:
    1. Dashboard overview → Views detail → back
    2. Dashboard → Interactions detail → back
    3. Dashboard → Followers detail → back
    
    Args:
        d: uiautomator2 device instance
        pkg: Instagram package name (clone)
    
    Returns:
        dict with full insights data, or None on failure
    """
    result = {
        'scraped_at': datetime.datetime.now().isoformat(),
        'date_range': None,
        'overview': {
            'views': None,
            'interactions': None,
            'new_followers': None,
            'content_shared': None,
        },
        'views_detail': {
            'total': None,
            'followers_pct': None,
            'non_followers_pct': None,
            'accounts_reached': None,
            'accounts_reached_change_pct': None,
            'content_type': {'reels_pct': None, 'posts_pct': None},
            'profile_visits': None,
            'profile_visits_change_pct': None,
            'external_link_taps': None,
            'comparison_period': None,
        },
        'interactions_detail': {
            'total': None,
            'followers_pct': None,
            'non_followers_pct': None,
            'likes': None,
            'content_type': {'reels_pct': None},
        },
        'followers_detail': {
            'total': None,
            'demographics_available': False,
            'top_cities': None,
            'top_countries': None,
            'age_range': None,
            'gender': None,
            'most_active_times': None,
        },
    }
    
    try:
        # ── Step 1: Navigate to Profile ──
        log.info("[insights] Navigating to Profile tab...")
        profile_btn = d(description="Profile")
        if not profile_btn.exists(timeout=5):
            profile_btn = d(resourceIdMatches=".*profile_tab$")
        
        if profile_btn.exists(timeout=5):
            profile_btn.click()
            time.sleep(3)
        else:
            log.warning("[insights] Profile tab not found")
            return None
        
        # ── Step 2: Open Professional Dashboard ──
        log.info("[insights] Opening Professional dashboard...")
        dashboard_btn = d(textContains="Professional dashboard")
        if not dashboard_btn.exists(timeout=5):
            _scroll_down(d)
            dashboard_btn = d(textContains="Professional dashboard")
        
        if not dashboard_btn.exists(timeout=5):
            log.warning("[insights] Professional dashboard not found")
            return None
        
        dashboard_btn.click()
        _wait_for_load(d, timeout=4)
        
        # ── Step 3: Scrape Overview ──
        log.info("[insights] Scraping dashboard overview...")
        xml = d.dump_hierarchy()
        
        result['date_range'] = _extract_date_range(xml)
        result['overview']['views'] = _extract_value_near_label(xml, "Views")
        result['overview']['interactions'] = _extract_value_near_label(xml, "Interactions")
        result['overview']['new_followers'] = _extract_value_near_label(xml, "New followers")
        result['overview']['content_shared'] = _extract_value_near_label(
            xml, "Content you shared")
        
        log.info("[insights] Overview: %s", result['overview'])
        
        # ── Step 4: Views Detail ──
        log.info("[insights] Drilling into Views detail...")
        result['views_detail'] = _scrape_views_detail(d, xml)
        
        # Navigate back to dashboard
        _press_back(d)
        _wait_for_load(d, timeout=3)
        
        # ── Step 5: Interactions Detail ──
        log.info("[insights] Drilling into Interactions detail...")
        result['interactions_detail'] = _scrape_interactions_detail(d)
        
        # Navigate back to dashboard
        _press_back(d)
        _wait_for_load(d, timeout=3)
        
        # ── Step 6: Followers Detail ──
        log.info("[insights] Drilling into Followers detail...")
        result['followers_detail'] = _scrape_followers_detail(d, result['overview'])
        
        # Navigate back to dashboard and then profile
        _press_back(d)
        _wait_for_load(d, timeout=2)
        _press_back(d)
        
        log.info("[insights] Full scrape complete: views=%s, interactions=%s, followers=%s",
                 result['overview'].get('views'),
                 result['overview'].get('interactions'),
                 result['followers_detail'].get('total'))
        
        return result
        
    except Exception as e:
        log.error("[insights] Full scrape failed: %s", e, exc_info=True)
        # Try to recover navigation
        try:
            _press_back(d)
            time.sleep(1)
            _press_back(d)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Section Scrapers
# ---------------------------------------------------------------------------

def _scrape_views_detail(d, dashboard_xml=None):
    """Drill into Views section and scrape detailed metrics."""
    detail = {
        'total': None,
        'followers_pct': None,
        'non_followers_pct': None,
        'accounts_reached': None,
        'accounts_reached_change_pct': None,
        'content_type': {'reels_pct': None, 'posts_pct': None},
        'profile_visits': None,
        'profile_visits_change_pct': None,
        'external_link_taps': None,
        'comparison_period': None,
    }
    
    try:
        # Tap "Views" to drill in
        views_btn = d(text="Views")
        if not views_btn.exists(timeout=3):
            log.warning("[insights] 'Views' button not found on dashboard")
            return detail
        
        views_btn.click()
        _wait_for_load(d, timeout=4)
        
        # Dump hierarchy
        xml = d.dump_hierarchy()
        
        # Total views from content-desc (e.g., "153 Views")
        total_match = re.search(r'content-desc="([\d,]+)\s*Views?"', xml, re.IGNORECASE)
        if total_match:
            detail['total'] = _safe_int(total_match.group(1))
        else:
            # Fallback: extract from text
            total_match = re.search(r'text="([\d,]+)"[^>]*>.*?text="Views?"', xml[:3000])
            if total_match:
                detail['total'] = _safe_int(total_match.group(1))
        
        # Followers / Non-followers percentages
        detail['followers_pct'] = _extract_percentage(xml, "Followers")
        detail['non_followers_pct'] = _extract_percentage(xml, "Non-followers")
        
        # Accounts reached
        detail['accounts_reached'] = _extract_value_near_label(xml, "Accounts reached")
        detail['accounts_reached_change_pct'] = _extract_change_pct_near_label(
            xml, "Accounts reached")
        
        # Comparison period
        detail['comparison_period'] = _extract_comparison_period(xml)
        
        # Scroll down for more data
        _scroll_down(d)
        xml2 = d.dump_hierarchy()
        
        # Content type breakdown (Reels %, Posts %)
        # Look for percentage values near "Reels" and "Posts" labels
        all_pcts = re.findall(r'text="([\d.]+)%"', xml2)
        if len(all_pcts) >= 2:
            # Usually the content type percentages appear in order: higher first
            pct_values = [_safe_float(p) for p in all_pcts]
            # Find reels and posts percentages
            reels_pct = _extract_percentage(xml2, "Reels")
            posts_pct = _extract_percentage(xml2, "Posts")
            
            if reels_pct is not None:
                detail['content_type']['reels_pct'] = reels_pct
            if posts_pct is not None:
                detail['content_type']['posts_pct'] = posts_pct
            
            # If we couldn't match by label, use the largest values
            if detail['content_type']['reels_pct'] is None and pct_values:
                # Sort descending — Reels usually has higher %
                sorted_pcts = sorted(pct_values, reverse=True)
                if len(sorted_pcts) >= 1:
                    detail['content_type']['reels_pct'] = sorted_pcts[0]
                if len(sorted_pcts) >= 2:
                    detail['content_type']['posts_pct'] = sorted_pcts[1]
        
        # Profile visits
        detail['profile_visits'] = _extract_value_near_label(xml2, "Profile visits")
        if detail['profile_visits'] is None:
            # Try first XML too
            detail['profile_visits'] = _extract_value_near_label(xml, "Profile visits")
        
        detail['profile_visits_change_pct'] = _extract_change_pct_near_label(
            xml2, "Profile visits")
        
        # External link taps
        detail['external_link_taps'] = _extract_value_near_label(xml2, "External link taps")
        if detail['external_link_taps'] is None:
            # Check if it's "--" (no data)
            link_region = _find_region_around_label(xml2, "External link taps", 300)
            if link_region and ('--' in link_region):
                detail['external_link_taps'] = 0
        
        # Try comparison period from scrolled view too
        if detail['comparison_period'] is None:
            detail['comparison_period'] = _extract_comparison_period(xml2)
        
        log.info("[insights] Views detail: total=%s, reached=%s, visits=%s",
                 detail['total'], detail['accounts_reached'], detail['profile_visits'])
        
    except Exception as e:
        log.error("[insights] Views detail scrape failed: %s", e)
    
    return detail


def _scrape_interactions_detail(d):
    """Drill into Interactions section and scrape detailed metrics."""
    detail = {
        'total': None,
        'followers_pct': None,
        'non_followers_pct': None,
        'likes': None,
        'content_type': {'reels_pct': None},
    }
    
    try:
        # Tap "Interactions"
        interactions_btn = d(text="Interactions")
        if not interactions_btn.exists(timeout=3):
            log.warning("[insights] 'Interactions' button not found on dashboard")
            return detail
        
        interactions_btn.click()
        _wait_for_load(d, timeout=4)
        
        # Dump hierarchy
        xml = d.dump_hierarchy()
        
        # Total interactions from content-desc (e.g., "6 Interactions")
        total_match = re.search(
            r'content-desc="([\d,]+)\s*Interactions?"', xml, re.IGNORECASE)
        if total_match:
            detail['total'] = _safe_int(total_match.group(1))
        
        # Followers / Non-followers percentages
        detail['followers_pct'] = _extract_percentage(xml, "Followers")
        detail['non_followers_pct'] = _extract_percentage(xml, "Non-followers")
        
        # Scroll for more data
        _scroll_down(d)
        xml2 = d.dump_hierarchy()
        
        # Likes count
        detail['likes'] = _extract_value_near_label(xml2, "Likes")
        if detail['likes'] is None:
            detail['likes'] = _extract_value_near_label(xml, "Likes")
        
        # Content type — Reels percentage
        reels_pct = _extract_percentage(xml2, "Reels")
        if reels_pct is not None:
            detail['content_type']['reels_pct'] = reels_pct
        else:
            # Try first screen
            reels_pct = _extract_percentage(xml, "Reels")
            if reels_pct is not None:
                detail['content_type']['reels_pct'] = reels_pct
        
        log.info("[insights] Interactions detail: total=%s, likes=%s",
                 detail['total'], detail['likes'])
        
    except Exception as e:
        log.error("[insights] Interactions detail scrape failed: %s", e)
    
    return detail


def _scrape_followers_detail(d, overview=None):
    """Drill into Followers section and scrape detailed metrics."""
    detail = {
        'total': None,
        'demographics_available': False,
        'top_cities': None,
        'top_countries': None,
        'age_range': None,
        'gender': None,
        'most_active_times': None,
    }
    
    try:
        # Tap "New followers"
        followers_btn = d(text="New followers")
        if not followers_btn.exists(timeout=3):
            # Try just "followers"
            followers_btn = d(textContains="followers")
        
        if not followers_btn.exists(timeout=3):
            log.warning("[insights] 'New followers' button not found on dashboard")
            return detail
        
        followers_btn.click()
        _wait_for_load(d, timeout=4)
        
        # Dump hierarchy
        xml = d.dump_hierarchy()
        
        # Total followers from content-desc (e.g., "29 Followers")
        total_match = re.search(
            r'content-desc="([\d,]+)\s*Followers?"', xml, re.IGNORECASE)
        if total_match:
            detail['total'] = _safe_int(total_match.group(1))
        
        # If no content-desc match, try text patterns
        if detail['total'] is None:
            # Look for large number at top of screen
            nums = re.findall(r'text="([\d,]+)"', xml[:2000])
            if nums:
                # Take the largest number found (likely total followers)
                candidates = [_safe_int(n, 0) for n in nums]
                if candidates:
                    detail['total'] = max(candidates)
        
        # Check if demographics are available (need 100+ followers)
        total = detail['total'] or 0
        if total >= 100:
            detail['demographics_available'] = True
            
            # Scroll and look for demographic sections
            _scroll_down(d)
            xml2 = d.dump_hierarchy()
            
            # Top cities
            detail['top_cities'] = _scrape_demographics_section(
                d, xml2, "Top cities", "cities")
            
            # Top countries
            _scroll_down(d)
            xml3 = d.dump_hierarchy()
            detail['top_countries'] = _scrape_demographics_section(
                d, xml3, "Top countries", "countries")
            
            # Age range
            _scroll_down(d)
            xml4 = d.dump_hierarchy()
            detail['age_range'] = _scrape_demographics_section(
                d, xml4, "Age range", "age")
            
            # Gender
            detail['gender'] = _scrape_demographics_section(
                d, xml4, "Gender", "gender")
            
            # Most active times
            _scroll_down(d)
            xml5 = d.dump_hierarchy()
            detail['most_active_times'] = _scrape_demographics_section(
                d, xml5, "Most active times", "times")
        else:
            log.info("[insights] <100 followers (%s) — demographics unavailable", total)
        
        log.info("[insights] Followers detail: total=%s, demographics=%s",
                 detail['total'], detail['demographics_available'])
        
    except Exception as e:
        log.error("[insights] Followers detail scrape failed: %s", e)
    
    return detail


def _scrape_demographics_section(d, xml, section_label, section_type):
    """Scrape a demographics subsection (cities, countries, age, gender, times).
    
    Returns a JSON-serializable dict/list, or None if section not found.
    """
    try:
        # Check if section exists in current XML
        if section_label.lower() not in xml.lower():
            return None
        
        # Find the section region
        region = _find_region_around_label(xml, section_label, 2000)
        if not region:
            return None
        
        if section_type in ('cities', 'countries'):
            # Extract name-value pairs: "City Name" → "XX%"
            # Pattern: text="CityName" ... text="XX%"
            items = {}
            pairs = re.findall(
                r'text="([A-Z][a-zA-Z\s,.-]+)"[^>]*>[^<]*<[^>]*text="([\d.]+%?)"',
                region
            )
            if not pairs:
                # Broader: just find consecutive text elements
                texts = re.findall(r'text="([^"]+)"', region)
                for i in range(len(texts) - 1):
                    if re.match(r'[A-Z]', texts[i]) and re.match(r'[\d.]+%?', texts[i + 1]):
                        items[texts[i]] = texts[i + 1]
            else:
                for name, value in pairs:
                    items[name] = value
            
            return json.dumps(items) if items else None
        
        elif section_type == 'age':
            # Age ranges: "18-24" → "XX%"
            items = {}
            age_matches = re.findall(
                r'text="(\d{1,2}[-–]\d{1,2}(?:\+)?)"[^>]*>[^<]*(?:<[^>]*>)*[^<]*'
                r'text="([\d.]+%?)"',
                region
            )
            if not age_matches:
                texts = re.findall(r'text="([^"]+)"', region)
                for i in range(len(texts) - 1):
                    if re.match(r'\d{1,2}[-–]', texts[i]):
                        items[texts[i]] = texts[i + 1]
            else:
                for age_range, value in age_matches:
                    items[age_range] = value
            
            return json.dumps(items) if items else None
        
        elif section_type == 'gender':
            # Gender: "Men" → "XX%", "Women" → "XX%"
            items = {}
            for gender_label in ['Men', 'Women', 'Non-binary', 'Prefer not to say']:
                pct = _extract_percentage(region, gender_label)
                if pct is not None:
                    items[gender_label] = pct
            
            return json.dumps(items) if items else None
        
        elif section_type == 'times':
            # Most active times — hard to parse reliably, capture raw text
            texts = re.findall(r'text="([^"]+)"', region)
            time_texts = [t for t in texts if re.match(r'\d{1,2}\s*(AM|PM|am|pm)', t)]
            return json.dumps(time_texts) if time_texts else None
        
    except Exception as e:
        log.debug("[insights] Demographics %s scrape failed: %s", section_type, e)
    
    return None


# ---------------------------------------------------------------------------
# Database Persistence
# ---------------------------------------------------------------------------

def save_insights_to_db(data, account_id, device_serial=None, db_path=None):
    """Save scraped insights data to the account_insights table.
    
    Args:
        data: dict from scrape_insights() or scrape_insights_overview()
        account_id: username string
        device_serial: device serial string
        db_path: path to phone_farm.db (auto-detected if None)
    
    Returns:
        inserted row ID, or None on failure
    """
    import sqlite3
    import os
    
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "db", "phone_farm.db"
        )
    
    if data is None:
        log.warning("[insights] No data to save")
        return None
    
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        
        overview = data.get('overview', {})
        views = data.get('views_detail', {})
        interactions = data.get('interactions_detail', {})
        followers = data.get('followers_detail', {})
        content_type_views = views.get('content_type', {})
        content_type_inter = interactions.get('content_type', {})
        
        cursor = conn.execute("""
            INSERT INTO account_insights_v2 (
                account_id, device_serial, scraped_at, date_range,
                views, interactions, new_followers, content_shared,
                accounts_reached, accounts_reached_change_pct,
                views_followers_pct, views_non_followers_pct,
                reels_views_pct, posts_views_pct,
                profile_visits, profile_visits_change_pct,
                external_link_taps, comparison_period,
                interactions_followers_pct, interactions_non_followers_pct,
                likes_count, reels_interactions_pct,
                total_followers, demographics_available,
                top_cities, top_countries, age_range, gender, most_active_times
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            device_serial,
            data.get('scraped_at', datetime.datetime.now().isoformat()),
            data.get('date_range'),
            # Overview
            overview.get('views'),
            overview.get('interactions'),
            overview.get('new_followers'),
            overview.get('content_shared'),
            # Views detail
            views.get('accounts_reached'),
            views.get('accounts_reached_change_pct'),
            views.get('followers_pct'),
            views.get('non_followers_pct'),
            content_type_views.get('reels_pct'),
            content_type_views.get('posts_pct'),
            views.get('profile_visits'),
            views.get('profile_visits_change_pct'),
            views.get('external_link_taps'),
            views.get('comparison_period'),
            # Interactions detail
            interactions.get('followers_pct'),
            interactions.get('non_followers_pct'),
            interactions.get('likes'),
            content_type_inter.get('reels_pct'),
            # Followers detail
            followers.get('total'),
            1 if followers.get('demographics_available') else 0,
            followers.get('top_cities'),
            followers.get('top_countries'),
            followers.get('age_range'),
            followers.get('gender'),
            followers.get('most_active_times'),
        ))
        
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        
        log.info("[insights] Saved insights for @%s (row_id=%d)", account_id, row_id)
        return row_id
        
    except Exception as e:
        log.error("[insights] Failed to save insights: %s", e)
        return None


def get_latest_insights(account_id, db_path=None):
    """Get the most recent insights for an account.
    
    Args:
        account_id: username string
        db_path: path to phone_farm.db
    
    Returns:
        dict with insights data, or None
    """
    import sqlite3
    import os
    
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "db", "phone_farm.db"
        )
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute("""
            SELECT * FROM account_insights_v2
            WHERE account_id = ?
            ORDER BY scraped_at DESC
            LIMIT 1
        """, (account_id,)).fetchone()
        
        conn.close()
        
        if row:
            return dict(row)
        return None
        
    except Exception as e:
        log.error("[insights] Failed to get latest insights: %s", e)
        return None


def get_insights_history(account_id, days=30, db_path=None):
    """Get insights history for an account over N days.
    
    Args:
        account_id: username string
        days: number of days to look back
        db_path: path to phone_farm.db
    
    Returns:
        list of dicts with insights data
    """
    import sqlite3
    import os
    
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "db", "phone_farm.db"
        )
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT * FROM account_insights_v2
            WHERE account_id = ? AND scraped_at >= ?
            ORDER BY scraped_at DESC
        """, (account_id, since)).fetchall()
        
        conn.close()
        return [dict(r) for r in rows]
        
    except Exception as e:
        log.error("[insights] Failed to get insights history: %s", e)
        return []
