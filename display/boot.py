# boot.py — Runs before code.py on every boot
# Adds a delay to let power stabilize (helps wall-brick boot)
import time
time.sleep(2)
