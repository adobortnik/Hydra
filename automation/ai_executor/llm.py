"""
LLM client — model-agnostic brain that turns (goal + screen) into ONE action.

Default provider: DeepSeek (OpenAI-compatible, cheap). Any OpenAI-compatible
endpoint works by changing base_url/model (OpenAI, Gemini via compat, local
Ollama, ...). Vision (Set-of-Marks) is sent only when needed + supported.

The model must reply with a single JSON action, e.g.:
  {"type":"tap","index":3,"reason":"the Sign up button"}
  {"type":"type","index":5,"text":"john@gmail.com"}
  {"type":"swipe","direction":"up"}
  {"type":"recover"}          # background -> return (unstick)
  {"type":"reopen"}           # force-stop + relaunch the app
  {"type":"done","reason":"account created"}
"""

import base64
import json
import os
import re
import urllib.request


# DeepSeek moved to V4 (flash = fast/cheap, pro = stronger reasoning). The old
# `deepseek-chat` alias still resolves but runs the weaker tier — default to pro
# for the agent (better at multi-step reasoning: counting, don't-repeat, etc.).
PROVIDERS = {
    'deepseek': {'base_url': 'https://api.deepseek.com/v1',
                 'model': 'deepseek-v4-flash', 'vision_model': 'deepseek-v4-flash'},
    'openai':   {'base_url': 'https://api.openai.com/v1',
                 'model': 'gpt-4o-mini', 'vision_model': 'gpt-4o-mini'},
}

SYSTEM_PROMPT = """You drive an Android phone to accomplish a GOAL. You see the
current screen as a numbered list of interactive elements (and sometimes a
screenshot with the same numbers drawn on it). Choose exactly ONE next action.

Rules:
- SPEED — BATCH obvious steps: when the next few actions on the SAME screen are
  clear (e.g. a form: type the day, type the year, then tap Next), return them ALL
  at once as {"actions": [ <action>, <action>, ... ]} (a list, same schema each).
  They run in sequence without re-asking you — much faster. Batch straightforward
  field-typing + a final button. Do NOT batch a DROPDOWN's option pick (you must
  see the opened list first), and do NOT batch past a screen you can't predict.
  For a single step, just return the one action object (no list).
- Reply with ONE JSON object only, no prose. Schema:
  {"type": "tap"|"double_tap"|"type"|"key"|"swipe"|"scroll"|"scroll_to_bottom"|
           "pick_dropdown"|"set_date"|"set_username"|"back"|"wait"|"get_phone"|
           "get_sms_code"|"recover"|"reopen"|"done",
   "index": <element number for tap/double_tap/type>,
   "text": "<for type>", "direction": "up|down|left|right",
   "year": <int>, "month": <int 1-12>, "day": <int>, "username": "<for set_username>",
   "key": "enter|back|home", "seconds": <int>, "reason": "<short why>"}
- Prefer tapping by element index. Only the listed numbers exist.
- ACTION NOTES:
  * "double_tap" = double-tap to LIKE a photo/reel (IG's like gesture). With no
    index it double-taps the media area. Prefer this over hunting a tiny heart
    icon when the goal is just to like the current post/reel.
  * "key" with "enter" SUBMITS the current field (e.g. after typing a search
    query or a username) — use it instead of looking for a Search/Go button.
  * "type" auto-clears the field first and is reliable even when the field still
    shows its hint text afterwards (IG hides typed text) — do NOT re-type just
    because you can't see your text; check RECENT ACTIONS instead.
  * "get_phone" RENTS a real phone number and types it into the focused field —
    use it when a screen asks for a PHONE NUMBER to verify/secure a new account.
    Tap the phone field FIRST so it's focused, then {"type":"get_phone"}, then tap
    Next/Send code yourself.
  * "get_sms_code" waits for the SMS to that rented number and types the CODE —
    use it on the "enter confirmation/SMS code" field (tap the code field first).
    Only works after a get_phone in this run.
  * "set_date" sets a NATIVE 3-WHEEL DATE PICKER ("What's your birthday?" -> the
    "Set date" dialog with spinning Month/Day/Year wheels + SET). Do NOT try to
    swipe/scroll the wheels yourself — emit ONE {"type":"set_date","year":Y,
    "month":M,"day":D} and it sets all wheels + taps SET (it guarantees an adult
    age automatically). If the birthday field shows a date but the dialog isn't
    open yet, tap the birthday field first, then set_date.
  * "set_username" handles the "Create a username" screen. IG pre-fills a RANDOM
    suggestion (e.g. duck.46554426) — do NOT accept it. Emit ONE
    {"type":"set_username","username":"<our handle>"} and it clears the suggestion,
    types OUR username, taps Next, and auto-retries a digit-variant if it's taken.
  * "Verify your phone number" screen: tap the BLUE ACTION BUTTON ("Verify" /
    "Next", usually bottom-right) to proceed to the phone-number field — do NOT
    tap the page TITLE/heading text. On the phone field, use {"type":"get_phone"}
    (the action), then tap Next/Verify, then {"type":"get_sms_code"}.
- TAP BUTTONS, NOT HEADINGS: the screen TITLE/heading (big text at the top, e.g.
  "Verify your phone number", "Basic information") is NOT a button — tapping it
  does nothing. To proceed, tap the actual control: a button (Next/Verify/Agree),
  a field, or an option.
- ACCOUNT-SETUP FINAL SCREENS (Privacy & Terms / Google services): these pages are
  LONG and the action button ("I agree"/"Accept"/"Next") is at the very BOTTOM.
  Use ONE {"type":"scroll_to_bottom"} action to jump straight to the bottom (it
  flings down repeatedly until the end), THEN tap the button. Do NOT scroll a
  little at a time — that wastes many slow steps.
- BACKUP TOGGLE = OFF: on the "Google services" / setup screen, if "Back up device
  data" or "Backup account data" is ON/checked, TAP that toggle to turn it OFF
  before tapping Accept — we do NOT want device backup enabled.
- BE PERSISTENT — this is account registration / setup, do NOT give up:
  * If a button seems unresponsive or the screen shows an error / "try again" /
    "something went wrong", tap the relevant button AGAIN.
  * If the screen looks stuck or wrong after a few tries, use {"type":"recover"}
    (go to background and come back) and then continue.
  * As a last resort use {"type":"reopen"} to restart the app, then continue.
- Dismiss blocking popups (Not now / Skip / Allow as appropriate) to keep moving.
- CONTACTS / FIND-FRIENDS — ALWAYS DENY, NEVER allow/sync. On the signup onboarding
  "allow access to your contacts" / "find your friends" / "sync contacts" screen, tap
  Skip / Not Now (NOT "Next" if Next implies syncing — prefer the explicit Skip). On the
  Android system permission dialog "Allow Instagram to access your contacts?" tap
  DENY / Don't allow (NOT Allow). A fresh farm account must never upload the device's
  contacts. Same for "access your location" → Deny. (Only notifications can be Not Now.)
- LOADING / PROGRESS screens: if the screen shows a spinner or text like
  "Checking info", "Loading", "One moment", "Please wait", "Just a sec" (few or no
  buttons), use {"type":"wait","seconds":4} — do NOT press back and do NOT tap.
  It is transient and advances on its own; pressing BACK here EXITS the whole
  flow (e.g. account creation) and you lose progress.
- Do NOT press {"type":"back"} just because a screen looks empty/unfamiliar —
  back navigates AWAY. Prefer wait (if loading) or dismiss a named popup.
- DROPDOWN / PICKER — PREFER {"type":"pick_dropdown","index":N} where N is the
  dropdown element (Month, Gender, ...). It opens the dropdown AND selects an
  option in ONE reliable step (the options are often unlabelled and hard to tap
  individually). For a birthday month or gender the exact value does NOT matter,
  so this is ideal. Use it instead of a separate tap-then-pick.
  (Manual fallback only if pick_dropdown isn't suitable:) tapping the dropdown
  OPENS a list of options. Once it's open, do NOT tap the dropdown label again
  (that just closes it). Instead TAP the OPTION whose text matches your target
  value (e.g. the month name from the GOAL). If your target option is not in the
  visible list, {"type":"scroll","direction":"up"} ONCE to reveal more options,
  then tap it. After you pick, the dropdown closes showing your value — move to
  the next field. Check RECENT ACTIONS: if you've tapped the same dropdown label
  2+ times, STOP re-tapping and tap an option instead.
  * IMPORTANT: a dropdown's options are OFTEN UNLABELLED buttons (no visible
    text) in the open list. If you opened a Month/Gender/etc. dropdown and see
    unlabelled BTN entries where the options should be, just TAP ONE of them
    (any) — for a birthday month or gender the EXACT value does NOT matter, you
    only need a valid selection to proceed. Do NOT scroll hunting for a labelled
    option that isn't there; tap an option and move on.
  * ALREADY SET: if a dropdown FIELD now DISPLAYS a value (e.g. the Month field
    reads "March" / "Ma…", or Gender shows a choice), it is DONE — do NOT tap it
    again (that just re-opens it and loops). Move to the NEXT field (e.g. tap the
    Day field / type the day). Tapping the next field also closes an open dropdown.

- DON'T REPEAT WORK — track what you have already done (see RECENT ACTIONS):
  * TYPING: before typing into a field, LOOK at the element list. If a field
    ALREADY shows your intended text, the text is IN — do NOT type again, move
    on (e.g. tap the Post/Send button). Only re-type if RECENT ACTIONS shows
    your last type was "NOT confirmed". Never type the same field 3+ times.
  * SUBMITTING: after you tap Post / Send / Share / Next and it succeeds (the
    input field becomes EMPTY again, or your text now appears in the
    list/thread above), that item is DONE. Do NOT type it or submit it again.
  * If the goal asked for ONE thing (one comment, one post) and you've done it,
    output {"type":"done"} — do not start a second one.
  * Reels are fine if the feed shows reels instead of posts.

- LIKING a post — target the REAL like control and VERIFY (do NOT count blindly):
  * You can only like an actual POST. The home feed also has stories, ads, and
    "Suggested for you" account cards — those have NO post like button. Scroll
    PAST them; never try to like them.
  * To like: tap the element marked <<POST LIKE BUTTON state="Like">>. On the
    NEXT screen that button must now read state="Liked"/"Unlike" — ONLY THEN is
    the like real and counted. If it still says "Like", tap it again.
  * If it already shows <<POST LIKE BUTTON state="Liked">>, the post is ALREADY
    liked: do NOT tap it (that UNLIKES) and do NOT count it as a like YOU made.
  * NEVER tap a <<LIKE COUNT>>, a username, or a profile picture — those open a
    profile / the likes list, they do NOT like the post.
  * {"double_tap"} (no index) on the media is a FALLBACK only when no like button
    is listed — and you STILL must verify a "Liked" state appears before counting.
- STAY ON THE HOME FEED for a feed task. If you end up on a PROFILE, a COMMENT
  screen, Explore, search, or anything that is NOT the home feed, use
  {"type":"back"} (repeat if needed) to return to the feed BEFORE continuing.
  scroll does NOT leave a profile — use back.
- COUNTING & DONE: only count likes you VERIFIED flipped to "Liked". Do NOT output
  {"done"} until that many likes are confirmed. Never count an unverified
  double_tap or a tap whose result you didn't see.

- BROWSING A FEED (home feed / explore / reels): if the GOAL is to scroll/browse
  and then pick something, SCROLL FIRST and keep scrolling.
  * Use {"type":"scroll","direction":"up"} to move to the NEXT post. Each scroll
    reveals a new post.
  * Do NOT like/comment the very first thing on screen. Scroll at least 2-3 times
    to browse different posts BEFORE you choose one to act on.
  * The element list only shows buttons (Like/Comment/Share), not the post's
    photo/caption — that's normal. Scroll to move through the feed; act when the
    GOAL's condition is met.
- Only output {"type":"done"} when the GOAL is clearly achieved.
"""


def _http_post(url, headers, payload, timeout=90):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _extract_json(text):
    text = (text or '').strip()
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # tolerate trailing commas / minor noise
        cleaned = re.sub(r',\s*}', '}', m.group(0))
        try:
            return json.loads(cleaned)
        except Exception:
            return None


class LLM:
    def __init__(self, provider='deepseek', api_key=None, base_url=None,
                 model=None, vision_model=None):
        cfg = PROVIDERS.get(provider, PROVIDERS['deepseek'])
        self.provider = provider
        self.api_key = api_key or os.environ.get('AI_EXECUTOR_KEY', '')
        self.base_url = (base_url or cfg['base_url']).rstrip('/')
        self.model = model or cfg['model']
        self.vision_model = vision_model or cfg.get('vision_model', self.model)

    def next_action(self, goal, perception_text, history, screenshot_png=None):
        """Ask the model for the next action. Returns a dict (or a safe wait)."""
        user_parts = [
            f'GOAL: {goal}',
            '',
            'RECENT ACTIONS:',
            '\n'.join(history[-8:]) if history else '(none yet)',
            '',
            'CURRENT SCREEN:',
            perception_text,
            '',
            'Respond with ONE JSON action.',
        ]
        user_text = '\n'.join(user_parts)

        if screenshot_png:
            content = [
                {'type': 'text', 'text': user_text},
                {'type': 'image_url', 'image_url': {
                    'url': 'data:image/png;base64,' + base64.b64encode(screenshot_png).decode()}},
            ]
            model = self.vision_model
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': content}]
        else:
            model = self.model
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_text}]

        # Reasoning models (deepseek-v4-pro, *reasoner*, R1, ...) spend tokens on
        # an internal chain-of-thought BEFORE the answer. With a small cap the
        # reasoning eats the whole budget and the real JSON answer (content) comes
        # back empty -> "unparseable reply". Give them lots of room.
        ml = (model or '').lower()
        # DeepSeek V4 — BOTH flash AND pro emit hidden reasoning before the
        # answer, so they need a generous cap or the JSON answer is truncated
        # (finish='length' -> empty content -> "unparseable reply", then it
        # loops). Only plain non-reasoning models (e.g. gpt-4o-mini) stay small.
        big = any(k in ml for k in ('deepseek', 'v4', 'flash', 'pro',
                                    'reason', 'r1', 'think'))
        max_toks = 4096 if big else 512

        headers = {'Content-Type': 'application/json',
                   'Authorization': f'Bearer {self.api_key}'}

        def _post(msgs, mdl):
            return _http_post(self.base_url + '/chat/completions', headers,
                              {'model': mdl, 'messages': msgs,
                               'temperature': 0.2, 'max_tokens': max_toks})

        finish = None
        try:
            resp = _post(messages, model)
        except Exception as e:
            # DeepSeek (and other text-only models) reject image content with a
            # 400 -> retry TEXT-ONLY so the run never stalls on a vision call.
            if screenshot_png:
                try:
                    resp = _post([{'role': 'system', 'content': SYSTEM_PROMPT},
                                  {'role': 'user', 'content': user_text}], self.model)
                except Exception as e2:
                    return {'type': 'wait', 'seconds': 2, 'reason': f'llm error: {e2}'}
            else:
                return {'type': 'wait', 'seconds': 2, 'reason': f'llm error: {e}'}
        msg = resp['choices'][0]['message']
        text = (msg.get('content') or '').strip()
        # fallback: some reasoning models leave the JSON only in reasoning_content
        if not text:
            text = (msg.get('reasoning_content') or '').strip()
        finish = resp['choices'][0].get('finish_reason')

        action = _extract_json(text)
        # batch: {"actions":[...]} — a list of steps to run in sequence
        if action and isinstance(action.get('actions'), list) and action['actions']:
            return action
        if not action or 'type' not in action:
            # surface WHY so it's diagnosable (truncation vs junk vs empty)
            snippet = (text or '')[:160].replace('\n', ' ')
            print(f'[ai-executor] unparseable LLM reply (finish={finish}, '
                  f'model={model}): {snippet!r}')
            return {'type': 'wait', 'seconds': 1,
                    'reason': f'unparseable reply (finish={finish})'}
        return action
