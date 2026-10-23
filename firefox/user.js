// Firefox reads these preferences on each networking lab profile startup.
// Use TCP-based HTTP instead of HTTP/3 over QUIC.
user_pref("network.http.http3.enable", false);
// Permit the authors' plain HTTP exercises in normal windows.
user_pref("dom.security.https_only_mode", false);
// Do not try HTTPS first for the plain HTTP exercises.
user_pref("dom.security.https_first", false);
// Explicitly disable Firefox DNS over HTTPS; use the system resolver.
user_pref("network.trr.mode", 5);

// Clear browsing/download history and the HTTP cache when the lab Firefox quits.
// Keep caching enabled during each exercise. Downloaded files are not deleted.
user_pref("privacy.sanitize.sanitizeOnShutdown", true);
// Use Firefox's current categories without migration from legacy defaults.
user_pref("privacy.sanitize.clearOnShutdown.hasMigratedToNewPrefs3", true);
user_pref("privacy.clearOnShutdown_v2.browsingHistoryAndDownloads", true);
user_pref("privacy.clearOnShutdown_v2.cache", true);
// Preserve cookies, site storage, active logins, form data and site permissions.
user_pref("privacy.clearOnShutdown_v2.cookiesAndStorage", false);
user_pref("privacy.clearOnShutdown_v2.formdata", false);
user_pref("privacy.clearOnShutdown_v2.siteSettings", false);
