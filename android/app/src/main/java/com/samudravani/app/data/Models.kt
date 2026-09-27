package com.samudravani.app.data

import com.samudravani.app.i18n.FishingLevel
import java.time.Instant
import java.time.LocalDate

/** A home port. Coordinates are offshore approach points: the router needs a sea cell to start from. */
data class Port(val name: String, val nameHi: String, val nameGu: String, val region: String, val lat: Double, val lon: Double) {
    val label get() = "$name, $region"
    fun localName(lang: String) = when (lang) { "hi" -> nameHi; "gu" -> nameGu; else -> name }
}

val PORTS = listOf(
    Port("Veraval", "वेरावल", "વેરાવળ", "Gujarat", 20.80, 70.25),
    Port("Porbandar", "पोरबंदर", "પોરબંદર", "Gujarat", 21.45, 69.45),
    Port("Mangrol", "मांगरोल", "માંગરોળ", "Gujarat", 21.08, 70.00),
    Port("Diu", "दीव", "દીવ", "Diu", 20.64, 70.95),
)

data class LatLon(val lat: Double, val lon: Double)

data class Zone(
    val lat: Double,
    val lon: Double,
    val score: Double,
    val reasons: List<String>,
    val distanceKm: Int,
    val bearingDeg: Int,
)

data class RouteInfo(
    val found: Boolean,
    val reason: String?,
    val waypoints: List<LatLon>,
    val distanceNm: Double,
    val durationH: Double,
    val fuelL: Double,
    val maxWaveM: Double?,
    val maxHeadwindMs: Double?,
    val landMaskUsed: Boolean,
)

data class Rule(val ruleId: String, val verdict: String, val message: String, val value: Double, val threshold: Double)

/** Plan text in one language, as returned by the API's `localized` block (numbers unchanged). */
data class PlanText(
    val statusText: String,
    val summary: String,
    val refusalReason: String?,
    val riskText: String?,
    val riskExplanation: String?,
    val triggered: List<Rule>,
    val explanation: List<String>,
    val caveats: List<String>,
)

/** One voyage plan, everything the screens need. */
data class Plan(
    val port: Port,
    val destination: LatLon?,
    val status: String,            // PROCEED, PROCEED_WITH_CAUTION, NOT_RECOMMENDED, DO_NOT_VENTURE, REFUSED
    val riskVerdict: String?,      // SAFE, CAUTION, HIGH_RISK, DO_NOT_VENTURE, INSUFFICIENT_DATA
    val zones: List<Zone>,
    val target: Zone?,
    val route: RouteInfo?,
    val alternates: List<RouteInfo>,
    val text: Map<String, PlanText>, // "hi" / "en" / "gu"
    val dataStatus: Map<String, String>,
) {
    val level: FishingLevel get() = levelFor(zones.maxOfOrNull { it.score })
    /** The best zones (top 3 by score) are what the distance range on the home card describes. */
    private val topZones: List<Zone> get() = zones.sortedByDescending { it.score }.take(3)
    val minKm: Int? get() = topZones.minOfOrNull { it.distanceKm }
    val maxKm: Int? get() = topZones.maxOfOrNull { it.distanceKm }
    fun text(lang: String): PlanText? = text[lang] ?: text["en"]
}

data class ForecastHour(
    val time: Instant,
    val windMs: Double?,
    val gustMs: Double?,
    val windFromDeg: Double?,
    val waveM: Double?,
    val wavePeriodS: Double?,
    val rainMm: Double?,
    val visibilityKm: Double?,
    val currentMs: Double?,
    val sstC: Double?,
)

data class DayOutlook(
    val date: LocalDate,
    val verdict: String,
    val maxWaveM: Double?,
    val maxWindMs: Double?,
    val maxGustMs: Double?,
    val rainMm: Double?,
    val minVisibilityKm: Double?,
    val messages: Map<String, List<Rule>>, // lang -> triggered rules, translated
)

data class Forecast(
    val port: Port,
    val hours: List<ForecastHour>,
    val days: List<DayOutlook>,
    val bestDay: LocalDate?,
)

/** One line of the ask/chat conversation. [failed] = no answer (server unreachable). */
data class ChatMsg(
    val id: Long,
    val fromUser: Boolean,
    val text: String,
    val lang: String,
    val pending: Boolean = false,
    val failed: Boolean = false,
)

/** Loading state of one API call. */
sealed interface Load<out T> {
    data object Loading : Load<Nothing>
    data class Ready<T>(val value: T) : Load<T>
    data class Failed(val reason: String) : Load<Nothing>
}

/** Fishing-zone score (0..1) bands shown to the user. */
fun levelFor(bestScore: Double?): FishingLevel = when {
    bestScore == null -> FishingLevel.NONE
    bestScore >= 0.7 -> FishingLevel.HIGH
    bestScore >= 0.5 -> FishingLevel.MEDIUM
    else -> FishingLevel.LOW
}

/** Worst-to-best order of the voyage verdicts. */
fun verdictRank(v: String?): Int = when (v) {
    "SAFE" -> 0; "CAUTION" -> 1; "HIGH_RISK" -> 2; "DO_NOT_VENTURE" -> 3; else -> 4
}
