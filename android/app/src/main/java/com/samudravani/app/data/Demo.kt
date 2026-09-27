package com.samudravani.app.data

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlin.math.PI
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Sample data shown only by debug builds when the API cannot be reached, so every screen can be
 * reviewed. Screens always label it as demo data; release builds never use it.
 */
object Demo {
    private val IST = ZoneId.of("Asia/Kolkata")

    fun plan(port: Port, destination: LatLon? = null): Plan {
        val zones = listOf(
            Triple(-0.10, -0.08, 0.64), Triple(-0.13, 0.02, 0.58), Triple(-0.05, -0.15, 0.52),
        ).map { (dLat, dLon, s) ->
            val lat = port.lat + dLat
            val lon = port.lon + dLon
            Zone(lat, lon, s, listOf("SST front: gradient 0.041 degC/km", "Chl-a 0.84 mg/m3 within preferred band"),
                SamudraApi.haversineKm(port.lat, port.lon, lat, lon).roundToInt(), SamudraApi.bearing(port.lat, port.lon, lat, lon))
        }
        val goal = destination ?: LatLon(zones[0].lat, zones[0].lon)
        val wps = (0..6).map { i ->
            val f = i / 6.0
            LatLon(port.lat + (goal.lat - port.lat) * f - 0.01 * sin(PI * f), port.lon + (goal.lon - port.lon) * f)
        }
        val nm = SamudraApi.haversineKm(port.lat, port.lon, goal.lat, goal.lon) / 1.852 * 1.04
        val route = RouteInfo(true, null, wps, nm, nm / 8.0, nm / 8.0 * 23.0, 1.2, 4.1, landMaskUsed = true)
        val target = if (destination == null) zones[0] else null
        val en = PlanText(
            statusText = "PROCEED", summary = "PROCEED: sample plan (server not connected).", refusalReason = null,
            riskText = "SAFE", riskExplanation = "SAFE: no rule triggered for current_speed, visibility, wave_height, wind_speed.",
            triggered = emptyList(),
            explanation = listOf("Why this zone: SST front and chlorophyll in the preferred band."),
            caveats = listOf("Demo data: connect to the SamudraVani server for live advice."),
        )
        val hi = en.copy(
            statusText = "PROCEED (आगे बढ़ें)", summary = "PROCEED: नमूना योजना (सर्वर से जुड़ा नहीं)।",
            riskText = "SAFE (सुरक्षित)", riskExplanation = "SAFE: धारा, दृश्यता, लहर और हवा के लिए कोई नियम सक्रिय नहीं हुआ।",
            explanation = listOf("यह क्षेत्र क्यों: SST फ्रंट और पसंदीदा सीमा में क्लोरोफिल।"),
            caveats = listOf("डेमो डेटा: लाइव सलाह के लिए SamudraVani सर्वर से जोड़ें।"),
        )
        val gu = en.copy(
            statusText = "PROCEED (જઈ શકો છો)", summary = "PROCEED: નમૂના યોજના (સર્વર સાથે જોડાયેલ નથી).",
            riskText = "SAFE (સુરક્ષિત)", riskExplanation = "SAFE: પ્રવાહ, દૃશ્યતા, મોજાં અને પવન માટે કોઈ નિયમ સક્રિય થયો નથી.",
            explanation = listOf("આ વિસ્તાર શા માટે: SST ફ્રન્ટ અને પસંદગીની મર્યાદામાં ક્લોરોફિલ."),
            caveats = listOf("ડેમો ડેટા: લાઇવ સલાહ માટે SamudraVani સર્વર સાથે જોડો."),
        )
        return Plan(port, destination, "PROCEED", "SAFE", if (destination == null) zones else emptyList(), target, route,
            emptyList(), mapOf("en" to en, "hi" to hi, "gu" to gu), emptyMap(), isDemo = true)
    }

    fun forecast(port: Port): Forecast {
        val start = Instant.now().truncatedTo(ChronoUnit.HOURS)
        val hours = (0 until 120).map { i ->
            val t = start.plus(i.toLong(), ChronoUnit.HOURS)
            val bump = if (i in 40..60) 1.6 else 0.0 // a windy spell on day 3
            ForecastHour(
                time = t, windMs = 5.5 + 2.0 * sin(i / 24.0 * 2 * PI) + bump * 3.5, gustMs = 8.0 + bump * 5.0,
                windFromDeg = 250.0, waveM = 1.1 + 0.2 * sin(i / 12.0) + bump, wavePeriodS = 7.0,
                rainMm = if (i in 44..50) 1.5 else 0.0, visibilityKm = 12.0, currentMs = 0.5, sstC = 28.6,
            )
        }
        val days = hours.groupBy { it.time.atZone(IST).toLocalDate() }.map { (d, hs) ->
            val wave = hs.maxOf { it.waveM!! }
            val verdict = if (wave >= 2.5) "CAUTION" else "SAFE"
            val msg = if (verdict == "CAUTION") listOf(
                Rule("wave_caution", "CAUTION", "Significant wave height %.1f m >= 2.5 m (moderate sea).".format(wave), wave, 2.5),
            ) else emptyList()
            val msgHi = msg.map { it.copy(message = "सार्थक तरंग ऊँचाई %.1f m >= 2.5 m (मध्यम समुद्र)।".format(wave)) }
            DayOutlook(d, verdict, wave, hs.maxOf { it.windMs!! }, hs.maxOf { it.gustMs!! }, hs.sumOf { it.rainMm!! }, 12.0,
                mapOf("en" to msg, "hi" to msgHi, "gu" to msg))
        }
        val best = days.filter { it.verdict == "SAFE" }.minByOrNull { it.maxWaveM ?: 9.0 }?.date
        return Forecast(port, hours, days, best ?: LocalDate.now(IST), isDemo = true)
    }
}
