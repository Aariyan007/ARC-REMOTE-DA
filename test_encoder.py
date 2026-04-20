import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from core.fast_intent import initialize, classify

print('Initializing intent engine with cross-encoder...')
try:
    initialize()
except ModuleNotFoundError as e:
    if e.name == "sentence_transformers":
        print("\nMissing dependency: sentence_transformers")
        print("Install project dependencies first with: pip install -r requirements.txt")
        raise SystemExit(1)
    raise

print('\n--- CRITICAL TESTS ---')
tests = [
    ('tell me what is on my screen',           'take_screenshot'),
    ('what am i seeing on my screen right now', 'take_screenshot'),
    ('increase the screen brightness',         'brightness_up'),
    ('make the screen brighter',               'brightness_up'),
    ('tell me all the details about open claw', 'answer_question'),
    ('what all conversations did we have',      'general_chat'),
    ('move this vscode to the left',            'move_window'),
    ('open chrome',                             'open_app'),
    ('take a screenshot',                       'take_screenshot'),
]

passed = 0
for text, expected in tests:
    result = classify(text)
    status = 'PASS' if result.action == expected else 'FAIL'
    if status == 'PASS': passed += 1
    print(f'  [{status}] "{text[:45]}"')
    print(f'         got={result.action} (conf={result.confidence:.3f}) expected={expected}')

print(f'\n{passed}/{len(tests)} passed')
