"""
CLI test harness for the AI executor.

    python -m automation.ai_executor.run <serial> "<goal>" \
        [--package com.instagram.androim] [--provider deepseek] [--key sk-...]
    python -m automation.ai_executor.run <serial> --perceive-only   # safe dry run

--perceive-only just dumps what the executor SEES (no AI, no actions) so you can
validate perception on a real screen before spending any tokens.
"""

import argparse
import json
import os
import sys

import uiautomator2 as u2

from .perception import perceive, set_of_marks
from .executor import Executor
from .llm import LLM


def _load_key(provider, explicit):
    if explicit:
        return explicit
    env = os.environ.get('AI_EXECUTOR_KEY')
    if env:
        return env
    # try Hydra global_settings.json
    here = os.path.dirname(os.path.abspath(__file__))
    gs = os.path.join(here, '..', '..', 'dashboard', 'global_settings.json')
    try:
        with open(gs, encoding='utf-8') as f:
            data = json.load(f)
        # Reuse the Hydra assistant's configured key (global_settings.ai_chat)
        chat = data.get('ai_chat', {})
        if chat.get('api_key') and (not provider or chat.get('provider') == provider
                                    or provider == 'deepseek'):
            return chat['api_key']
        ai = data.get('ai', {})
        return (ai.get(f'{provider}_api_key')
                or ai.get('deepseek_api_key')
                or ai.get('openai_api_key') or '')
    except Exception:
        return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('serial', help='device serial (10.1.11.4:5555 or _ form)')
    ap.add_argument('goal', nargs='?', default='', help='natural-language goal')
    ap.add_argument('--package', default=None)
    ap.add_argument('--provider', default='deepseek')
    ap.add_argument('--key', default=None)
    ap.add_argument('--model', default=None)
    ap.add_argument('--max-steps', type=int, default=60)
    ap.add_argument('--shots', default=None, help='dir to save step screenshots')
    ap.add_argument('--perceive-only', action='store_true')
    args = ap.parse_args()

    serial = args.serial.replace('_', ':')
    print(f'Connecting to {serial} ...')
    d = u2.connect(serial)

    if args.perceive_only or not args.goal:
        p = perceive(d)
        print('=' * 60)
        print(p.to_prompt())
        print('=' * 60)
        print(f'current package: {p.current_pkg} | elements: {len(p.elements)} '
              f'| sparse: {p.is_sparse()} | state: {p.state_hash[:8]}')
        if args.shots:
            png = set_of_marks(d, p)
            if png:
                os.makedirs(args.shots, exist_ok=True)
                outp = os.path.join(args.shots, 'set_of_marks.png')
                with open(outp, 'wb') as f:
                    f.write(png)
                print(f'Set-of-Marks screenshot -> {outp}')
        return

    key = _load_key(args.provider, args.key)
    if not key:
        print('No API key. Pass --key, set AI_EXECUTOR_KEY, or add it to '
              'dashboard/global_settings.json under ai.deepseek_api_key')
        sys.exit(1)

    llm = LLM(provider=args.provider, api_key=key, model=args.model)
    ex = Executor(d, package=args.package, llm=llm,
                  max_steps=args.max_steps, screenshot_dir=args.shots)
    result = ex.run(args.goal)
    print('=' * 60)
    print('RESULT:', {k: v for k, v in result.items() if k != 'log'})


if __name__ == '__main__':
    main()
