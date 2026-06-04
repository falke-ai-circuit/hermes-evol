#!/usr/bin/env python3
"""Self-test for the profiles-root path resolver.

Run after any change to _lib.profiles_root() or _lib.profile_dir().
Prints PASS/FAIL per case and a summary. Exit 0 = all pass, 1 = at least one fail.

Each case sets the env vars, calls profiles_root(), and checks the result.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'phases'))


CASES = []


def add_case(desc, cfg, data, fake_home, expected_suffix):
    """Build a case using a temp dir for fake_home."""
    CASES.append((desc, cfg, data, fake_home, expected_suffix))


def main():
    # We test the resolver logic by monkey-patching the function
    # because importing _lib reads env at import time.
    import importlib
    if 'phases' in sys.path:
        sys.path.remove('phases')
    sys.path.insert(0, str(HERE.parent / 'phases'))

    # Pre-create test cases
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Case 1: HERMES_CONFIG_DIR wins
        cfg_dir = tmp_path / 'cfg'
        cfg_dir.mkdir()
        (cfg_dir / 'profiles').mkdir()
        # Case 2: HERMES_DATA wins when no cfg
        data_dir = tmp_path / 'data'
        (data_dir / 'profiles').mkdir()
        # Case 3: ~/.hermes/profiles exists
        home_a = tmp_path / 'home_a'
        (home_a / '.hermes' / 'profiles').mkdir(parents=True)
        # Case 4: fallback to ~/config_root/profiles (the path doesn't need to exist)

        cases = [
            ('HERMES_CONFIG_DIR explicit wins', {'HERMES_CONFIG_DIR': str(cfg_dir)}, str(cfg_dir / 'profiles')),
            ('HERMES_DATA legacy when no cfg', {'HERMES_DATA': str(data_dir)}, str(data_dir / 'profiles')),
            ('CFG wins over DATA', {'HERMES_CONFIG_DIR': str(cfg_dir), 'HERMES_DATA': str(data_dir)}, str(cfg_dir / 'profiles')),
        ]

        # Use the resolver
        import _lib
        passed = 0
        failed = 0
        for desc, env_overrides, expected in cases:
            # Clear all
            for k in ['HERMES_CONFIG_DIR', 'HERMES_DATA']:
                if k in os.environ:
                    del os.environ[k]
            for k, v in env_overrides.items():
                os.environ[k] = v
            # Force reimport to pick up new env
            importlib.reload(_lib)
            got = str(_lib.profiles_root())
            if got == expected:
                status = 'PASS'
                passed += 1
            else:
                status = 'FAIL'
                failed += 1
            print(f'{status}: {desc}')
            if status == 'FAIL':
                print(f'  expected: {expected}')
                print(f'  got:      {got}')

        # Case: ~/.hermes/profiles exists with no env vars
        for k in ['HERMES_CONFIG_DIR', 'HERMES_DATA']:
            if k in os.environ:
                del os.environ[k]
        os.environ['HOME'] = str(home_a)
        importlib.reload(_lib)
        got = str(_lib.profiles_root())
        expected = str(home_a / '.hermes' / 'profiles')
        if got == expected:
            status = 'PASS'
            passed += 1
        else:
            status = 'FAIL'
            failed += 1
        print(f'{status}: HOME-relative ~/.hermes/profiles when it exists')
        if status == 'FAIL':
            print(f'  expected: {expected}')
            print(f'  got:      {got}')

        # Case: empty env vars fall through to ~/.hermes check
        for k in ['HERMES_CONFIG_DIR', 'HERMES_DATA']:
            os.environ[k] = ''
        importlib.reload(_lib)
        got = str(_lib.profiles_root())
        # Empty HERMES_CONFIG_DIR/HERMES_DATA should NOT take priority over HOME check
        if got == expected:
            status = 'PASS'
            passed += 1
        else:
            status = 'FAIL'
            failed += 1
        print(f'{status}: empty env vars fall through to HOME check')
        if status == 'FAIL':
            print(f'  expected: {expected}')
            print(f'  got:      {got}')

        print()
        print(f'Summary: {passed} pass, {failed} fail')
        sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
