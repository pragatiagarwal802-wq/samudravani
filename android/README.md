# SamudraVani Android app

Kotlin + Jetpack Compose client for the SamudraVani API. The home screen follows the design on
the Technical Approach slide (Hindi / English toggle, port selector, four feature tiles,
fishing-potential summary, "Ask" bar, bottom navigation).

## Open and run

1. Android Studio -> **Open** -> this `android` folder. Let Gradle sync finish.
2. Start the backend from the repo root: `uvicorn main:app --host 0.0.0.0 --port 8000`
3. Run the `app` configuration on an emulator. The app calls `http://10.0.2.2:8000`
   (the emulator's address for your computer).
   On a real phone, build with your computer's LAN IP:
   `gradlew installDebug -PapiBaseUrl=http://192.168.x.x:8000` and add that IP to
   `app/src/main/res/xml/network_security_config.xml`.

If the API can't be reached, **debug** builds show the mockup's sample values marked "डेमो डेटा /
Demo data"; release builds show "not available" instead of made-up numbers.

## Screenshots

`gradlew :app:recordRoborazziDebug` renders the home screen (Hindi, English, loading) to
`app/build/outputs/roborazzi/` without an emulator.

## Status

Done:
- Home screen, language toggle, port selector (Veraval, Porbandar, Mangrol, Diu)
- आज का मौसम: current wind/gusts/waves/rain/visibility/current/sea temp, next 24 h, 5-day outlook with best day
- मछली पकड़ने की संभावना: fishing level, zones with distance/direction/reasons, map
- चेतावनी और जोखिम: next-24-h risk with triggered rules, per-day risk for 5 days
- सबसे सुरक्षित मार्ग: land-safe route to the best zone or another port, distance/time/fuel, map
- Map tab (OpenStreetMap), Profile tab (language, home port, server address)

Next: voice/chat "Ask" screen, push alerts.

## Phone + laptop

On the phone: Profile -> Server address -> `http://<laptop Wi-Fi IP>:8000` -> Save.
Find the laptop IP with `ipconfig` (IPv4 Address). Allow Python through Windows Firewall when asked.
