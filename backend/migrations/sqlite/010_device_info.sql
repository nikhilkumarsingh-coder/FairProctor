-- The device the test was written on (decided automatically) and the device check: mobile / SEB / kiosk mode,
-- SEB exemption for phones, and a mismatch between what the browser says and what the page measured.
ALTER TABLE sessions ADD COLUMN device_info TEXT
