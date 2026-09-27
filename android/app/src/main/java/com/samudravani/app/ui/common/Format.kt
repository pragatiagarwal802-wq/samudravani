package com.samudravani.app.ui.common

import com.samudravani.app.i18n.Lang
import com.samudravani.app.i18n.Strings
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import kotlin.math.roundToInt

val IST: ZoneId = ZoneId.of("Asia/Kolkata")

/** Wind in km/h, as IMD and INCOIS bulletins give it to fishers. */
fun kmh(ms: Double?): String = ms?.let { "${(it * 3.6).roundToInt()} km/h" } ?: "–"
fun metres(m: Double?): String = m?.let { "%.1f m".format(it) } ?: "–"
fun mm(v: Double?): String = v?.let { if (it < 0.05) "0 mm" else "%.1f mm".format(it) } ?: "–"
fun km(v: Double?): String = v?.let { "${it.roundToInt()} km" } ?: "–"
fun celsius(v: Double?): String = v?.let { "%.1f °C".format(it) } ?: "–"
fun nmToKm(nm: Double): Int = (nm * 1.852).roundToInt()

fun hourLabel(t: Instant): String = DateTimeFormatter.ofPattern("HH:mm").format(t.atZone(IST))

fun dayLabel(d: LocalDate, s: Strings, lang: Lang): String {
    val today = LocalDate.now(IST)
    return when (d) {
        today -> s.today
        today.plusDays(1) -> s.tomorrow
        else -> d.dayOfWeek.getDisplayName(TextStyle.FULL, lang.locale) + ", " + d.dayOfMonth
    }
}
