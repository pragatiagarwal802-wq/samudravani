package com.samudravani.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Client for the SamudraVani FastAPI backend. [candidates] are tried in order until one accepts a
 * connection; the one that worked is reused until it stops answering.
 */
class SamudraApi(private val candidates: () -> List<String>) {
    @Volatile private var working: String? = null

    /** Address of the server the last successful call used, if any. */
    val connectedTo: String? get() = working

    /** `POST /api/v1/voyage/plan`: fishing zones + route from the port, or a route to [destination]. */
    suspend fun plan(port: Port, destination: LatLon? = null, hours: Long = 24): Plan = withContext(Dispatchers.IO) {
        val now = LocalDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.HOURS)
        val body = JSONObject()
            .put("origin", JSONObject().put("lat", port.lat).put("lon", port.lon).put("name", port.name))
            .put("window", JSONObject().put("start", now.toString()).put("end", now.plusHours(hours).toString()))
            .put("search_radius_deg", 1.0)
            .put("max_candidates", 3)
        if (destination != null) body.put("destination", JSONObject().put("lat", destination.lat).put("lon", destination.lon))
        parsePlan(JSONObject(request("POST", "/api/v1/voyage/plan", body.toString())), port, destination)
    }

    /** `GET /api/v1/forecast`: hourly conditions and a verdict per day at the port. */
    suspend fun forecast(port: Port, days: Int = 5): Forecast = withContext(Dispatchers.IO) {
        parseForecast(JSONObject(request("GET", "/api/v1/forecast?lat=${port.lat}&lon=${port.lon}&days=$days", null)), port)
    }

    /** `POST /api/v1/ask`: answer to a typed or spoken question, in [lang], from live data. */
    suspend fun ask(question: String, lang: String, port: Port): String = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("question", question)
            .put("lang", lang)
            .put("origin", JSONObject().put("lat", port.lat).put("lon", port.lon).put("name", port.name))
        JSONObject(request("POST", "/api/v1/ask", body.toString())).getString("answer")
    }

    private fun request(method: String, path: String, body: String?): String {
        val urls = listOfNotNull(working) + candidates().filter { it != working }
        var last: Exception? = null
        for (base in urls) {
            try {
                return request(base, method, path, body).also { working = base }
            } catch (e: java.net.ConnectException) {
                last = e // nothing listening there: try the next address
            } catch (e: java.net.SocketTimeoutException) {
                if (e.message?.contains("connect", ignoreCase = true) != true) throw e // server slow, not absent
                last = e
            } catch (e: java.net.UnknownHostException) {
                last = e
            }
        }
        working = null
        throw last ?: IllegalStateException("no server address configured")
    }

    private fun request(base: String, method: String, path: String, body: String?): String {
        val conn = (URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 4_000
            readTimeout = 5 * 60_000 // a plan fetches several data sources
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
        }
        try {
            if (body != null) conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode != 200) error("HTTP ${conn.responseCode}")
            return conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        fun parsePlan(js: JSONObject, port: Port, destination: LatLon? = null): Plan {
            val p = js.getJSONObject("plan")
            fun zone(z: JSONObject) = Zone(
                lat = z.getDouble("lat"), lon = z.getDouble("lon"), score = z.getDouble("score"),
                reasons = z.optJSONArray("reasons").strings(),
                distanceKm = haversineKm(port.lat, port.lon, z.getDouble("lat"), z.getDouble("lon")).roundToInt(),
                bearingDeg = bearing(port.lat, port.lon, z.getDouble("lat"), z.getDouble("lon")),
            )
            val text = js.optJSONObject("localized")?.let { loc ->
                loc.keys().asSequence().associateWith { lang -> planText(loc.getJSONObject(lang), p) }
            }.orEmpty()
            return Plan(
                port = port,
                destination = destination,
                status = p.getString("status"),
                riskVerdict = p.optJSONObject("risk")?.optString("verdict"),
                zones = js.optJSONArray("fishing_zones").objects().map(::zone),
                target = p.optJSONObject("target_zone")?.let(::zone),
                route = p.optJSONObject("route")?.let(::route),
                alternates = p.optJSONArray("alternates").objects().mapNotNull { it.optJSONObject("route")?.let(::route) },
                text = text,
                dataStatus = p.optJSONObject("data_status")?.let { ds -> ds.keys().asSequence().associateWith { ds.getString(it) } }.orEmpty(),
            )
        }

        private fun planText(l: JSONObject, plan: JSONObject): PlanText {
            val raw = plan.optJSONObject("risk")?.optJSONArray("triggered").objects().associateBy { it.getString("rule_id") }
            return PlanText(
                statusText = l.optString("status_text"),
                summary = l.optString("summary"),
                refusalReason = l.optNullableString("refusal_reason"),
                riskText = l.optNullableString("risk_text"),
                riskExplanation = l.optNullableString("risk_explanation"),
                triggered = l.optJSONArray("triggered").objects().map { t ->
                    val r = raw[t.getString("rule_id")]
                    Rule(t.getString("rule_id"), t.getString("verdict"), t.getString("message"),
                        r?.optDouble("value") ?: Double.NaN, r?.optDouble("threshold") ?: Double.NaN)
                },
                explanation = l.optJSONArray("explanation").strings(),
                caveats = l.optJSONArray("caveats").strings(),
            )
        }

        private fun route(r: JSONObject) = RouteInfo(
            found = r.getBoolean("found"),
            reason = r.optNullableString("reason"),
            waypoints = r.optJSONArray("waypoints").objects().map { LatLon(it.getDouble("lat"), it.getDouble("lon")) },
            distanceNm = r.optDouble("distance_nm", 0.0),
            durationH = r.optDouble("duration_h", 0.0),
            fuelL = r.optDouble("fuel_l", 0.0),
            maxWaveM = r.optNullableDouble("max_wave_m"),
            maxHeadwindMs = r.optNullableDouble("max_headwind_ms"),
            landMaskUsed = r.optBoolean("land_mask_used"),
        )

        fun parseForecast(js: JSONObject, port: Port): Forecast = Forecast(
            port = port,
            hours = js.optJSONArray("hours").objects().map { h ->
                ForecastHour(
                    time = LocalDateTime.parse(h.getString("time")).toInstant(ZoneOffset.UTC),
                    windMs = h.optNullableDouble("wind_speed"), gustMs = h.optNullableDouble("wind_gust"),
                    windFromDeg = h.optNullableDouble("wind_from_deg"), waveM = h.optNullableDouble("wave_height"),
                    wavePeriodS = h.optNullableDouble("wave_period"), rainMm = h.optNullableDouble("rain_mm"),
                    visibilityKm = h.optNullableDouble("visibility_km"), currentMs = h.optNullableDouble("current_speed"),
                    sstC = h.optNullableDouble("sst"),
                )
            },
            days = js.optJSONArray("days").objects().map { d ->
                DayOutlook(
                    date = LocalDate.parse(d.getString("date")),
                    verdict = d.getString("verdict"),
                    maxWaveM = d.optNullableDouble("max_wave_m"), maxWindMs = d.optNullableDouble("max_wind_ms"),
                    maxGustMs = d.optNullableDouble("max_gust_ms"), rainMm = d.optNullableDouble("rain_mm"),
                    minVisibilityKm = d.optNullableDouble("min_visibility_km"),
                    messages = d.optJSONObject("messages")?.let { m ->
                        m.keys().asSequence().associateWith { lang ->
                            m.getJSONArray(lang).objects().map {
                                Rule(it.getString("rule_id"), it.getString("verdict"), it.getString("message"), Double.NaN, Double.NaN)
                            }
                        }
                    }.orEmpty(),
                )
            },
            bestDay = js.optNullableString("best_day")?.let(LocalDate::parse),
        )

        private fun JSONArray?.objects(): List<JSONObject> =
            if (this == null) emptyList() else (0 until length()).map { getJSONObject(it) }

        private fun JSONArray?.strings(): List<String> =
            if (this == null) emptyList() else (0 until length()).map { getString(it) }

        private fun JSONObject.optNullableDouble(key: String): Double? =
            if (isNull(key)) null else optDouble(key).takeIf { !it.isNaN() }

        private fun JSONObject.optNullableString(key: String): String? =
            if (isNull(key)) null else optString(key).ifEmpty { null }

        fun haversineKm(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
            val dLat = Math.toRadians(lat2 - lat1)
            val dLon = Math.toRadians(lon2 - lon1)
            val a = sin(dLat / 2).pow(2) + cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2).pow(2)
            return 2 * 6371.0 * asin(sqrt(a))
        }

        fun bearing(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Int {
            val p1 = Math.toRadians(lat1)
            val p2 = Math.toRadians(lat2)
            val dl = Math.toRadians(lon2 - lon1)
            val y = sin(dl) * cos(p2)
            val x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
            return ((Math.toDegrees(atan2(y, x)) + 360) % 360).roundToInt()
        }
    }
}
