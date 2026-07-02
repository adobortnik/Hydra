"""
Executor — the agent loop. Perceive -> decide (LLM) -> act -> repeat, with a
hard, model-independent safety net for getting unstuck (the operator's
"keep clicking / background and come back / reopen" behaviour).

Usage:
    from automation.ai_executor import Executor, LLM
    ex = Executor(device, package="com.instagram.androim",
                  llm=LLM(provider="deepseek", api_key=KEY))
    result = ex.run("Create a new Instagram account with email {email}",
                    variables={"email": "x@gmail.com"})
"""

import os
import random
import time

from .perception import perceive, set_of_marks
from .actions import Actions
from .recipe import screen_signature, find_by_identity


class StepLog:
    def __init__(self, i, action, result, state_hash, shot_path=None):
        self.i = i
        self.action = action
        self.result = result
        self.state_hash = state_hash
        self.shot_path = shot_path


class Executor:
    def __init__(self, device, package=None, llm=None, log=print,
                 max_steps=60, stuck_limit=3, screenshot_dir=None,
                 vision_when_sparse=True, on_step=None, stop_flag=None,
                 recipe=None, record=False, phone_client=None, phone_service=None,
                 phone_mode='verification'):
        self.d = device
        self.package = package
        self.llm = llm
        self.log = log
        self.max_steps = max_steps
        self.stuck_limit = stuck_limit          # consecutive no-change steps
        self.vision_when_sparse = vision_when_sparse
        self.actions = Actions(device, package=package, log=log,
                               phone_client=phone_client, phone_service=phone_service,
                               phone_mode=phone_mode)
        self.screenshot_dir = screenshot_dir
        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)
        self.steps = []
        self.on_step = on_step          # callback(dict) for live UI
        self.stop_flag = stop_flag      # callable -> True to abort
        # ── record / replay ──
        self.recipe = recipe            # Recipe to replay (None = pure AI)
        self.record = record            # capture steps so the run can be saved
        self.recorded_steps = []        # [{sig, action(template), llm, note}]
        self.replay_count = 0           # steps served from the recipe (free)
        self.llm_count = 0              # steps that needed the LLM (cost)
        self._pending = []              # queued actions from a multi-action batch
        self._replay_idx = 0            # pointer into recipe.steps (sequential replay)
        self.variables = {}             # per-run data (name/username/...) for
                                        # templating typed text -> {var} -> value

    # ── record/replay helpers ──
    def _template(self, action, perception):
        """Turn an executed action into a storable template — element targets are
        kept as IDENTITY (rid/label/class), not pixel coords. Typed text that
        equals a run variable is stored as a {var} PLACEHOLDER so the recipe is
        reusable across accounts (don't bake in one account's name/password)."""
        t = {'type': action.get('type')}
        for k in ('text', 'direction', 'key', 'seconds', 'reason'):
            if action.get(k) is not None:
                t[k] = action.get(k)
        if t.get('text') and self.variables:
            txt = str(t['text'])
            for name, val in self.variables.items():
                if val and len(val) >= 3 and val in txt:
                    txt = txt.replace(val, '{' + name + '}')
            t['text'] = txt
        idx = action.get('index')
        if idx is not None:
            el = perception.by_idx(idx)
            if el:
                t['target'] = el.identity()
        return t

    def _resolve(self, template, perception):
        """Turn a stored template into a runnable action against the CURRENT
        screen. Substitutes {var} placeholders in typed text with this run's
        variables. Returns None if a targeted element can't be re-found
        (deviation -> fall back to the LLM)."""
        a = dict(template)
        if a.get('text') and self.variables:
            txt = str(a['text'])
            for name, val in self.variables.items():
                txt = txt.replace('{' + name + '}', val)
            a['text'] = txt
        target = template.get('target')
        if target:
            el = find_by_identity(perception, target)
            if el is None:
                return None
            a['index'] = el.idx
        a.pop('target', None)
        return a

    def _grab_png(self):
        """Best-effort current screenshot as PNG bytes (for the live view)."""
        from .perception import grab_png
        return grab_png(self.d)

    def _emit(self, **ev):
        if self.on_step:
            try:
                if 'screenshot' not in ev:
                    ev['screenshot'] = self._grab_png()
                self.on_step(ev)
            except Exception:
                pass

    def _save_shot(self, i, png):
        if not (self.screenshot_dir and png):
            return None
        p = os.path.join(self.screenshot_dir, f'step_{i:03d}.png')
        try:
            with open(p, 'wb') as f:
                f.write(png)
            return p
        except Exception:
            return None

    def run(self, goal, variables=None):
        """Drive the device until the LLM says done or budgets run out."""
        self.variables = {k: str(v) for k, v in (variables or {}).items()}
        for k, v in self.variables.items():
            goal = goal.replace('{' + k + '}', v)
        # lock portrait so a stray gesture / WebView can't flip to landscape
        try:
            self.actions.force_portrait()
        except Exception:
            pass
        if self.package:
            # Explicit app requested -> open it directly.
            try:
                self.d.app_start(self.package)
                time.sleep(3)
            except Exception as e:
                self.log(f'app_start failed: {e}')
        else:
            # No app specified -> start from the HOME SCREEN so the AI navigates
            # to whatever the GOAL asks for (e.g. "open clone 6"). Do NOT
            # auto-open some default app, or the goal's app choice is ignored.
            try:
                self.d.press('home')
                time.sleep(1.5)
            except Exception:
                pass

        history = []
        last_hash = None
        stuck = 0
        escalation = 0  # 0=none, 1=tried background, 2=tried reopen

        self._emit(step=0, action='start', reason=f'Goal: {goal}', changed=True)

        for i in range(1, self.max_steps + 1):
            if self.stop_flag and self.stop_flag():
                self._emit(step=i, action='stopped', reason='stopped by user', changed=False)
                return self._finish(False, 'stopped by user', i)
            # keep portrait every step (auto-rotate sneaks back on; cheap adb)
            try:
                self.actions.force_portrait(full=False)
            except Exception:
                pass
            p = perceive(self.d)

            # ── model-independent SAFETY NET ──
            # If the screen hasn't changed for `stuck_limit` steps, stop asking
            # the model and force recovery, escalating each time.
            if last_hash is not None and p.state_hash == last_hash:
                stuck += 1
            else:
                stuck = 0
                escalation = 0
            last_hash = p.state_hash

            if stuck >= self.stuck_limit:
                if escalation == 0:
                    self.log(f'[{i}] STUCK x{stuck} -> background/return')
                    self.actions.recover_background()
                    escalation = 1
                elif escalation == 1:
                    self.log(f'[{i}] STILL STUCK -> reopen app')
                    self.actions.reopen_app()
                    escalation = 2
                else:
                    self.log(f'[{i}] STILL STUCK after reopen -> pressing back to break out')
                    self.actions.back()
                    escalation = 0
                stuck = 0
                last_hash = None
                continue

            # ── DECIDE: replay a recorded step first (free), else ask LLM ──
            sig = screen_signature(p)
            action = None
            template = None
            used_llm = False
            src = 'ai'

            # 1) a queued action from a previous BATCH (no LLM call → fast)
            while self._pending and action is None:
                tmpl = self._pending.pop(0)
                resolved = self._resolve(tmpl, p)
                if resolved is not None:
                    action, template, src = resolved, tmpl, 'batch'
                else:
                    self._pending = []   # element gone → batch stale, re-plan

            # 2) recipe replay — follow the recorded SEQUENCE (a screen can need
            # several actions that share the same signature, e.g. type first name,
            # type last name, tap Next — a sig->action MAP would loop on the first;
            # a sequential pointer runs them in order).
            if action is None and self.recipe is not None:
                steps = self.recipe.steps
                idx = self._replay_idx
                j = None
                if idx < len(steps):
                    if (steps[idx].get('sig') == sig):
                        j = idx                       # next expected step matches
                    else:                              # find the next step ahead for this screen
                        j = next((k for k in range(idx, len(steps))
                                  if steps[k].get('sig') == sig), None)
                if j is not None:
                    tmpl = steps[j].get('action')
                    resolved = self._resolve(tmpl, p)
                    if resolved is not None:
                        action, template, src = resolved, tmpl, 'replay'
                        self._replay_idx = j + 1
                        self.replay_count += 1

            # 3) LLM — may return ONE action or a {"actions":[...]} batch
            shot = None
            if action is None:
                if not self.llm:
                    self.log('No LLM configured — aborting.')
                    return {'success': False, 'reason': 'no llm', 'steps': i,
                            'log': self.steps}
                if self.vision_when_sparse and p.is_sparse():
                    shot = set_of_marks(self.d, p)
                llm_action = self.llm.next_action(goal, p.to_prompt(), history,
                                                  screenshot_png=shot)
                used_llm = True
                self.llm_count += 1
                batch = llm_action.get('actions') if isinstance(llm_action, dict) else None
                if isinstance(batch, list) and batch:
                    # template every step vs THIS screen; run the first now, queue
                    # the rest (each re-resolved against a fresh screen when it runs)
                    tmpls = [self._template(a, p) for a in batch]
                    self._pending = tmpls[1:]
                    template = tmpls[0]
                    action = self._resolve(template, p) or batch[0]
                else:
                    action = llm_action
                    template = self._template(action, p)

            reason = action.get('reason', '')
            tag = {'replay': '<<replay', 'batch': 'batch', 'ai': 'ai'}.get(src, 'ai')
            self.log(f'[{i}] {tag} {action.get("type")} {action.get("index","")} '
                     f'{str(action.get("text","") or "")[:30]} :: {reason}')

            shot_path = self._save_shot(i, shot)

            # capture step for saving / self-heal (replay runs learn new screens)
            if self.record or self.recipe is not None:
                self.recorded_steps.append({'sig': sig, 'action': template,
                                            'llm': used_llm})

            if action.get('type') == 'done':
                self.steps.append(StepLog(i, action, 'done', p.state_hash, shot_path))
                self._emit(step=i, action='done', reason=reason or 'done',
                           changed=False, src=src)
                return self._finish(True, reason or 'done', i)

            result = self.actions.execute(action, p)
            self.steps.append(StepLog(i, action, str(result), p.state_hash, shot_path))
            self._emit(step=i, action=action.get('type'), index=action.get('index'),
                       text=action.get('text', ''), reason=reason,
                       changed=result.changed, note=result.note, src=src)
            desc = action.get('type')
            if action.get('text'):
                desc += f' "{str(action["text"])[:30]}"'
            if action.get('index') is not None:
                desc += f' #{action.get("index")}'
            outcome = result.note or ('changed' if result.changed else 'no-change')
            history.append(f'{desc} -> {outcome}')

            # light, varied think-time (just enough jitter to not be perfectly
            # robotic — the real slowness was wasted dropdown re-taps, now fixed
            # by the SELECTED annotation, NOT this pause)
            time.sleep(random.uniform(0.3, 0.9))

        return self._finish(False, 'max steps reached', self.max_steps)

    def _finish(self, success, reason, steps):
        return {'success': success, 'reason': reason, 'steps': steps,
                'log': self.steps, 'recorded_steps': self.recorded_steps,
                'replay_count': self.replay_count, 'llm_count': self.llm_count}
