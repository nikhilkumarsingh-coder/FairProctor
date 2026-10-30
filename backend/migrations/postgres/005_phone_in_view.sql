-- Phone in view: share of seconds since the previous frame in which the device's own detector saw a phone.
-- NULL = the detector did not run (slow link or unsupported browser): no evidence.
ALTER TABLE frame_stats ADD COLUMN phone REAL;
