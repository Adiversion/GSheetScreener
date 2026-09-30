# Android App Setup — NSE Signal

## Two Installation Methods

| Method | Effort | Experience | When to Use |
|--------|--------|-----------|------------|
| **PWA** (Chrome shortcut) | Instant | Good — runs in Chrome | Now, before APK is built |
| **Native APK** (Trusted Web Activity) | 30 min setup | Great — native app feel | Recommended for daily use |

---

## Method A — PWA (Instant, Zero Setup)

1. Open **Google Chrome** on Android (must be Chrome, not Samsung Browser)
2. Go to: `https://YOUR_USERNAME.github.io/nse-momentum-engine/`
3. Tap ⋮ (three dots menu) → **"Add to Home screen"**
4. Name it **NSE Signal** → **Add**
5. The icon appears on your home screen

> The browser may show a **"Add NSE Signal to Home screen"** banner automatically.
> If not, use the menu. Some Android versions take 30 seconds on the page first.

---

## Method B — Native APK via GitHub Actions (Recommended)

### B1 — Prerequisites (One-Time)

You need Java's `keytool` command. It comes with any Java JDK installation.

Check if you have it: `keytool -help`

If not, install [Amazon Corretto 17](https://aws.amazon.com/corretto/) (free Java).

### B2 — Generate Signing Keystore (One-Time, ~2 minutes)

Run this in PowerShell or Terminal:

```powershell
keytool -genkey -v `
  -keystore android.keystore `
  -alias nsesignal `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000
```

You'll be prompted to enter:
- Keystore password (choose a strong one, remember it)
- Key password (can be same as keystore password)
- Your name, organization, city, country (can leave most blank, just press Enter)

This creates `android.keystore` in your current folder.

> **⚠️ Keep this file safe!** If lost, you can't update your app without reinstalling.
> Back it up to Google Drive or email to yourself.

### B3 — Encode Keystore to Base64

**PowerShell:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("android.keystore")) | Set-Clipboard
```
This copies the base64 string to your clipboard.

**Or save to file first:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("android.keystore")) | Out-File keystore_b64.txt
```
Then open `keystore_b64.txt` and copy the entire contents.

### B4 — Add GitHub Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions → Secrets**

Click **New repository secret** for each:

| Secret Name | Value |
|-------------|-------|
| `ANDROID_KEYSTORE_B64` | The entire base64 string from step B3 |
| `ANDROID_KEY_ALIAS` | `nsesignal` |
| `ANDROID_KEY_PASSWORD` | The key password you set in step B2 |
| `ANDROID_STORE_PASSWORD` | The keystore password from step B2 |

### B5 — Update Your GitHub Username in TWA Manifest

Open [`android/twa-manifest.json`](../android/twa-manifest.json) and replace all instances of `YOUR_GITHUB_USERNAME`:

```json
{
  "host": "yourusername.github.io",
  "fullScopeUrl": "https://yourusername.github.io/nse-momentum-engine/",
  "webManifestUrl": "https://yourusername.github.io/nse-momentum-engine/manifest.json",
  ...
}
```

Commit and push this change.

### B6 — Run the Build

**Via GitHub Actions UI:**
1. Go to your repo on GitHub
2. Click **Actions** tab
3. Click **Build Android App (TWA → APK)**
4. Click **Run workflow** → **Run workflow**
5. Wait ~10-15 minutes

**Via version tag (for releases):**
```bash
git tag v1.0.0
git push origin v1.0.0
```

### B7 — Download and Install APK

After the workflow completes:

**Option 1 — From Artifacts (any run):**
1. GitHub → Actions → click the completed run
2. Scroll to **Artifacts** section at the bottom
3. Download **NSESignal-APK**
4. Extract the zip → transfer APK to your phone
5. Open it → Install

**Option 2 — From Release (version tags only):**
1. GitHub → **Releases** (right sidebar)
2. Find the latest release → download `.apk` file
3. Open on Android → Install

### B8 — Allow Installation from Unknown Sources

On Android, you'll see a warning when installing an APK not from Play Store.

1. Tap **Settings** when prompted
2. Enable **"Install unknown apps"** for Files/Chrome (wherever you opened the APK from)
3. Go back → **Install**

This is completely safe — it's your own app signed with your own keystore.

### B9 — Paste SHA-256 Fingerprint (Makes App Fullscreen)

After the first successful build, the GitHub Actions log prints:

```
══════════════════════════════════════════════
  COPY THIS SHA-256 → paste into assetlinks.json
══════════════════════════════════════════════
A1:B2:C3:D4:E5:F6:... (64 characters)
══════════════════════════════════════════════
```

1. Copy that fingerprint
2. Open [`app/.well-known/assetlinks.json`](../app/.well-known/assetlinks.json)
3. Replace `PASTE_YOUR_SHA256_FINGERPRINT_HERE` with the copied value
4. Commit and push
5. After GitHub Pages redeploys, open the installed APK → it now runs **fullscreen** (no Chrome address bar)

---

## Updating the App

When you update any `app/` files:

1. Commit and push to `main` branch
2. `deploy_app.yml` automatically redeploys GitHub Pages
3. The installed PWA or APK automatically gets the update next time you open it (via Service Worker)

To release a new APK version:
```bash
git tag v1.1.0
git push origin v1.1.0
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| "Add to Home screen" option missing | Must use Chrome; try visiting the page for 30+ seconds |
| APK build fails — "Keystore not found" | Check `ANDROID_KEYSTORE_B64` secret is set correctly |
| APK installs but shows Chrome toolbar | SHA-256 fingerprint not yet pasted in assetlinks.json |
| App shows "Configure Google Sheet URL" | Open Settings tab → paste published CSV URL |
| App won't update after code change | Clear app data or uninstall and reinstall |
| Service worker errors in console | Bump cache version in `sw.js` to `nse-signal-v2` |
