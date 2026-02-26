# DEV DEVICE — READ THIS FIRST

## CRITICAL: Only ONE device is safe for testing

**Device:** `10.1.11.4:5555` (DB serial: `10.1.11.4_5555`)
**Name:** JACK 1
**Purpose:** Development and testing ONLY

## Rules

1. **NEVER** connect to, screenshot, or send commands to any other device
2. **ALL** other devices are running production workloads
3. Hardcode `10.1.11.4_5555` in any test script
4. If a script takes a device serial as input, validate it is JACK 1 before executing
5. Batch operations (connect-all, etc.) must be disabled or filtered to JACK 1 only

## Quick Reference

```python
DEV_DEVICE_SERIAL = "10.1.11.4_5555"   # DB format
DEV_DEVICE_ADB = "10.1.11.4:5555"      # ADB format
DEV_DEVICE_NAME = "JACK 1"
```
