package com.samudravani.app.ui.common

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/**
 * Reads answers aloud with the phone's text-to-speech engine. [speak] reports false when the
 * engine has no voice for the language (e.g. Gujarati voice data not installed).
 */
class Speaker(context: Context) : TextToSpeech.OnInitListener {
    private val tts = TextToSpeech(context.applicationContext, this)
    private var ready = false
    private var queued: Pair<String, Locale>? = null

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        queued?.let { (text, locale) -> speak(text, locale) }
        queued = null
    }

    /** Speaks [text]; returns false if this language has no installed voice. */
    fun speak(text: String, locale: Locale): Boolean {
        if (!ready) {
            queued = text to locale
            return true
        }
        val ok = tts.setLanguage(locale)
        if (ok == TextToSpeech.LANG_MISSING_DATA || ok == TextToSpeech.LANG_NOT_SUPPORTED) return false
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "samudravani-answer")
        return true
    }

    fun stop() {
        if (ready) tts.stop()
    }

    fun shutdown() = tts.shutdown()
}
