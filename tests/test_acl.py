#!/usr/bin/env python3
"""
Test script for AI ACL system — verifies that ACL-listed users bypass other settings.
"""
import asyncio
import os
import sys
import tempfile

# Add parent dir so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.ai_cache import AICache


async def test_acl_system():
    """Test the ACL allowlist logic."""
    # Use a temp database so we don't pollute anything
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = AICache(logdir=tmpdir)

        guild_id = 123456
        allowed_user = 1001
        denied_user = 1002
        admin_user = 1003

        passed = 0
        failed = 0

        def check(name, got, expected):
            nonlocal passed, failed
            if got == expected:
                print(f"  ✅ {name}")
                passed += 1
            else:
                print(f"  ❌ {name}: expected {expected!r}, got {got!r}")
                failed += 1

        # ── acl_is_allowed: explicit allowlist check ────────────────
        print("Test 1: acl_is_allowed — no users added")
        check("empty ACL → not allowed",
              await cache.acl_is_allowed(guild_id, allowed_user), False)

        print("\nTest 2: acl_is_allowed — add user to allowlist")
        await cache.acl_add(guild_id, allowed_user, admin_user)
        check("allowed user on list",
              await cache.acl_is_allowed(guild_id, allowed_user), True)
        check("denied user not on list",
              await cache.acl_is_allowed(guild_id, denied_user), False)

        print("\nTest 3: acl_is_allowed ignores enforcement status")
        # ACL enforcement OFF — acl_is_allowed should still find the user
        await cache.acl_set_enforced(guild_id, False)
        check("enforcement off → allowed user still found",
              await cache.acl_is_allowed(guild_id, allowed_user), True)
        check("enforcement off → denied user still not found",
              await cache.acl_is_allowed(guild_id, denied_user), False)

        # ACL enforcement ON — acl_is_allowed should work the same
        await cache.acl_set_enforced(guild_id, True)
        check("enforcement on → allowed user still found",
              await cache.acl_is_allowed(guild_id, allowed_user), True)
        check("enforcement on → denied user still not found",
              await cache.acl_is_allowed(guild_id, denied_user), False)

        # ── acl_check vs acl_is_allowed difference ──────────────────
        print("\nTest 4: acl_check vs acl_is_allowed behaviour")
        await cache.acl_set_enforced(guild_id, False)
        # acl_check returns True for everyone when enforcement is off
        check("acl_check (enforcement off) → everyone allowed",
              await cache.acl_check(guild_id, denied_user), True)
        # acl_is_allowed still correctly returns False
        check("acl_is_allowed (enforcement off) → denied user still False",
              await cache.acl_is_allowed(guild_id, denied_user), False)

        await cache.acl_set_enforced(guild_id, True)
        check("acl_check (enforcement on) → denied user blocked",
              await cache.acl_check(guild_id, denied_user), False)
        check("acl_check (enforcement on) → allowed user passes",
              await cache.acl_check(guild_id, allowed_user), True)

        # ── acl_remove ──────────────────────────────────────────────
        print("\nTest 5: acl_remove removes from allowlist")
        await cache.acl_remove(guild_id, allowed_user)
        check("removed user → acl_is_allowed returns False",
              await cache.acl_is_allowed(guild_id, allowed_user), False)

        # ── Summary ─────────────────────────────────────────────────
        await cache.close()

        print(f"\n{'='*40}")
        print(f"Results: {passed} passed, {failed} failed")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_acl_system())
