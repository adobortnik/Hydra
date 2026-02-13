"""
Phone Farm Automation Module
=============================
Core automation layer for controlling Android devices via uiautomator2.

Modules:
    device_connection    - Device connection manager with reconnect logic
    instagram_actions    - Core Instagram UI interactions
    login                - Complete login flow with 2FA support
    scheduler            - Task scheduling engine
    bot_engine           - Main bot engine (per device+account)
Action modules (automation/actions/):
    follow   - Follow users from source account follower lists
    unfollow - Unfollow users after configurable delay
    like     - Like posts from feed, hashtags, profiles
    engage   - Story viewing, feed scrolling, warmup
    scrape   - Scrape follower lists for targeting
"""

__version__ = "2.0.0"
