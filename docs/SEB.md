# Safe Exam Browser (optional, laptop and iPad sittings)

[Safe Exam Browser](https://safeexambrowser.org) (SEB) locks a Windows/Mac computer or an iPad to the test: no other
apps, websites, copy-paste or screen sharing. FairProctor can require it per sitting, **on laptops and desktops only**. SEB has no Android version, so phones
and tablets are detected automatically and let in with the full-screen kiosk mode instead (a browser that only
pretends to be a phone gets a "device check" flag for the reviewer; see the README). The behaviour signals (silent
pauses, timing, answer matching, camera numbers) work with or without it, and they are what catch a second phone or a
helper, which SEB cannot see.

## How the check works

SEB proves it runs with the sitting's settings through the **Config Key** (CK). For a page at URL *u* it computes
`SHA256(u without #fragment + CK)` and sends it in the header `X-SafeExamBrowser-ConfigKeyHash`; the page can read the
same value as `SafeExamBrowser.security.configKey`. The React app sends that value, with the page URL it belongs to,
on every API call. The server (`backend/services/seb.py`) recomputes it with the Config Key the admin entered and
refuses to start the test, take answers or submit without a match (`403 seb_required`). Behind an HTTPS tunnel
(ngrok, cloudflared) the forwarded scheme and host are taken into account.

It stops casual bypass (opening the test in Chrome). Someone who extracts the key from the .seb file could still forge
the value, which is why it is a barrier, not proof; see SEB's own notes on the Browser Exam Key for stronger setups.

## Set it up

1. Install SEB and open the **SEB Config Tool** (Windows) or SEB's preferences (Mac).
2. **Start URL:** your FairProctor address, e.g. `https://abc.ngrok.app/login`.
3. **Exam → "Use Browser Exam Key and Config Key"** (send the keys) on.
4. **Browser:** allow the camera (*video capture*) and microphone off; use the modern browser engine (Edge WebView2 on
   Windows). FairProctor requires the camera, so check it in SEB before the test day.
5. **Quit password** and the URL filter (allow only your FairProctor address) as you like.
6. Save the configuration as a `.seb` file and copy the **Config Key** shown in the tool.
7. In FairProctor: **Admin → the sitting → Safe Exam Browser**: tick *Require*, paste the Config Key, upload the `.seb`
   file, **Save**. (Any change to the SEB settings changes the Config Key: paste the new one.)

Candidates then see *"This test opens only in Safe Exam Browser"* with install steps, an **Open in Safe Exam Browser**
button (`seb://` / `sebs://` link to `/api/seb/<token>.seb`) and a download of the file. Inside SEB they log in again
and the test starts normally; the home page shows *Safe Exam Browser: checked*.

## Test before the real sitting

Run a practice sitting with SEB required on the actual laptops: consent, pre-check (camera), a few answers, submit.
`e2e/seb.mjs` checks the web side with SEB's JavaScript API simulated; it cannot run the real SEB.
