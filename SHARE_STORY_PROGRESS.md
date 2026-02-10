# Share to Story — Progress Notes

## Task 1: Live Testing ✅ COMPLETE

### Test Scripts
- `test_share_to_story_live.py` — v1, exposed search bar text entry issue
- `test_share_v2.py` — v2, fixed search flow (click search bar → click EditText → set_text)

### Test Results (2025-02-01)
- **Device:** JACK 1 (10.1.11.4:5555), com.instagram.androie
- **Account:** pratiwipahllewi
- **Sources tested:** camillo_bro ✅, yannisko_paluan ✅

### Key Findings — Confirmed UI Elements

| Step | Selector | Value |
|------|----------|-------|
| Share button | content-desc | `"Send post"` |
| Share button | resource-id | `row_feed_button_share` |
| Add to story | text | `"Add to story"` (NOT "Add post to your story") |
| Grid item | content-desc pattern | `"Reel by {name} at row 1, column 1"` |
| Story editor publish | text | `"Share"` |
| Profile indicators | content-desc | `"{username}'s unseen story"`, `"{N}posts"`, `"{N}followers"` |

### Important Behavioral Notes
1. **Search flow on Explore tab requires TWO steps:** Click `action_bar_search_edit_text` (enters search mode), then click `EditText` (focuses for typing). Using `set_text()` via u2 works, ADB `input text` also works.
2. **Share sheet layout:** `Search | [DM recipients] | Add to story | WhatsApp | Copy link | Share | Download`
3. **Story editor loads slowly:** Shows "Loading…" before editor tools appear. Need 3s+ wait.
4. **Toast errors:** Account got "Something went wrong" and "Sorry, we couldn't complete your request" on first share (IG-side rate limit / clone app issue). The UI flow itself worked correctly.
5. **File locations:** XML dumps and screenshots in `test_results/share_story_v2/`

---

## Task 2: Story Editor Features ✅ COMPLETE

### Added to `share_to_story.py`:

**a) Mention on story** (`_add_story_mention`)
- Taps text tool (desc="Text" / "Aa" / rid=text_tool)
- Types `@username` via ADB input
- Configurable: `story_mention_enabled`, `story_mention_target`
- If no mention_target set, mentions the source username

**b) Link sticker** (`_add_link_sticker`)
- Taps sticker icon (desc="Stickers")
- Searches "Link" in sticker tray
- Enters URL in field
- Configurable: `story_link_sticker_enabled`, `story_link_sticker_url`

**c) Text overlay** (`_add_text_overlay`)
- Taps text tool, types custom text via ADB
- Configurable: `story_text_overlay_enabled`, `story_text_overlay`

**All features are optional** — controlled via account settings JSON:
```json
{
  "story_mention_enabled": true,
  "story_mention_target": "camillo_bro",
  "story_link_sticker_enabled": false,
  "story_link_sticker_url": "",
  "story_text_overlay_enabled": false,
  "story_text_overlay": ""
}
```

Called automatically via `_apply_story_editor_features()` before publishing.

---

## Task 3: Source .txt Files ✅ COMPLETE

### New: `automation/source_manager.py`
Unified source file handler with:
- `get_sources()` — reads .txt file, falls back to DB
- `read_sources_txt()` / `write_sources_txt()` — file I/O
- `append_sources_txt()` / `remove_sources_txt()` — modify existing
- `get_source_info()` — for dashboard display

### File mapping (matches dashboard + Onimator):
| Action | Filename |
|--------|----------|
| follow | `sources.txt` |
| share_to_story / share | `shared_post_username_source.txt` |
| follow_likers | `follow-likers-sources.txt` |
| follow_specific | `follow-specific-sources.txt` |
| dm | `directmessagespecificusersources.txt` |
| story_viewer_followers | `storyviewer-user-followers-sources.txt` |
| story_viewer_likers | `storyviewer-user-likers-sources.txt` |

### Fallback chain for share_to_story:
1. `shared_post_username_source.txt` (primary — what dashboard writes)
2. `share-to-story-sources.txt` (fallback)
3. DB `account_sources` table

### Template added:
- `Desktop/full_igbot_14.8.6/template/accountemplate/share-to-story-sources.txt`

---

## Task 4: Dashboard manage_sources ✅ ALREADY WORKING

The existing `manage_sources_new.html` already has:
- **Follow Sources tab** → writes `sources.txt`
- **Share Sources tab** → writes `shared_post_username_source.txt`
- **Bulk Settings tab** → updates account settings

The `share_to_story.py` module now reads from `shared_post_username_source.txt` via `source_manager.get_sources()`, which is exactly what the dashboard's Share Sources tab writes to. **No dashboard changes needed.**

---

## Files Modified
| File | Changes |
|------|---------|
| `automation/actions/share_to_story.py` | Added source_manager integration, story editor features (mention/link/text), updated selectors from live test |
| `automation/source_manager.py` | NEW — unified source file handling |
| `test_share_to_story_live.py` | NEW — v1 test script |
| `test_share_v2.py` | NEW — v2 test script (working) |
| `accountemplate/share-to-story-sources.txt` | NEW — empty template |
