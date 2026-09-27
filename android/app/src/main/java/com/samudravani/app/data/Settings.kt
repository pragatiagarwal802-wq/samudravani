package com.samudravani.app.data

import android.content.Context
import com.samudravani.app.BuildConfig
import com.samudravani.app.i18n.Lang

/** Small persisted user settings (SharedPreferences). */
class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("samudravani", Context.MODE_PRIVATE)

    /** Address typed in Profile; empty = automatic (USB link, then emulator). */
    var serverUrl: String
        get() = prefs.getString("server_url", null) ?: ""
        set(v) = prefs.edit().putString("server_url", v.trim().trimEnd('/')).apply()

    /**
     * Addresses to try, in order: the saved one; localhost, which reaches the laptop over USB after
     * `adb reverse tcp:8000 tcp:8000`; the build default (10.0.2.2 = the host, from the emulator).
     */
    fun serverCandidates(): List<String> =
        listOf(serverUrl, "http://localhost:8000", BuildConfig.API_BASE_URL).filter { it.isNotBlank() }.distinct()

    var lang: Lang
        get() = runCatching { Lang.valueOf(prefs.getString("lang", Lang.HI.name)!!) }.getOrDefault(Lang.HI)
        set(v) = prefs.edit().putString("lang", v.name).apply()

    var portName: String?
        get() = prefs.getString("port", null)
        set(v) = prefs.edit().putString("port", v).apply()
}
