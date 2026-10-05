# ARC Remote — mobile app

Vite web UI wrapped with [Capacitor](https://capacitorjs.com) for iOS and Android. The same code also runs as a PWA served by the daemon.

## Develop (browser)

```bash
npm install
npm run dev -- --host     # proxies API calls to localhost:8000
npm test                  # unit tests
```

Mock mode (fake server responses) exists only in dev builds; production builds never fall back to fake data.

## Build the native apps

Requires Node 22+. iOS needs Xcode + CocoaPods; Android needs Android Studio.

```bash
npm install
npm run cap:add:ios        # once
npm run cap:add:android    # once
npm run cap:ios            # builds the web UI, syncs, opens Xcode
npm run cap:android        # builds the web UI, syncs, opens Android Studio
```

The native projects are generated, not committed, and have not been built or run on a device yet. After adding them:

- **iOS** (`ios/App/App/Info.plist`): add `NSCameraUsageDescription` ("Scan the ARC pairing QR code"). To pair over plain `http://` on your LAN also add an App Transport Security exception; `https://` via Tailscale needs none. For the `arc://` deep link add a URL scheme `arc`.
- **Android** (`AndroidManifest.xml`): add an intent filter for scheme `arc`, host `pair`, for deep links. Camera permission is requested at runtime. `allowMixedContent` is on so LAN `http://` servers work; prefer HTTPS.
- App icon: `resources/icon.png` (1024px) is the source for `@capacitor/assets` if you want generated icon sets.

## Pairing

1. Run the daemon on your computer (`python -m remote.server`) and make it reachable (see the main README — Tailscale recommended).
2. `python -m remote.pair` prints a QR code.
3. In the app tap **Scan QR code** (or enter the server address + 6-digit code).

The token is stored in the iOS Keychain / Android Keystore. The app reconnects dropped streams automatically (resuming from the last event), when it returns to the foreground, and when the network comes back; recent jobs persist across restarts.

## Not built yet

- **Push notifications** (needs your own FCM/APNs credentials; the server stores device push tokens but does not send yet).
- **File transfer** for "find and send me this file" (the server has no download endpoint).
