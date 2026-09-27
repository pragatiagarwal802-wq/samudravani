package com.samudravani.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.SamudraApi
import com.samudravani.app.i18n.FishingLevel
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

@RunWith(AndroidJUnit4::class)
@Config(sdk = [35])
class SamudraApiTest {
    private val veraval = PORTS.first { it.name == "Veraval" }
    private val porbandar = PORTS.first { it.name == "Porbandar" }

    private fun fixture(name: String) = JSONObject(javaClass.classLoader!!.getResource(name).readText())

    @Test
    fun parsesZonesIntoLevelAndDistanceRange() {
        val js = JSONObject(
            """
            {"plan": {"status": "PROCEED", "risk": {"verdict": "SAFE", "triggered": []}},
             "fishing_zones": [
               {"lat": 20.90, "lon": 70.25, "score": 0.62, "reasons": ["SST front"]},
               {"lat": 20.95, "lon": 70.30, "score": 0.55, "reasons": []}
             ]}
            """,
        )
        val p = SamudraApi.parsePlan(js, veraval)
        assertEquals(FishingLevel.MEDIUM, p.level)
        assertEquals(11, p.minKm) // 0.10 deg of latitude ~ 11 km
        assertEquals(17, p.maxKm)
        assertEquals(0, p.zones[0].bearingDeg) // due north
        assertEquals("SAFE", p.riskVerdict)
    }

    @Test
    fun parsesRealRoutePlanResponse() {
        val p = SamudraApi.parsePlan(fixture("plan_route.json"), porbandar, LatLon(20.80, 70.25))
        val r = p.route!!
        assertTrue(r.found && r.landMaskUsed)
        assertTrue(r.waypoints.size > 2 && r.distanceNm > 50)
        assertEquals(setOf("en", "hi", "gu"), p.text.keys)
        assertTrue(p.text("hi")!!.summary.isNotBlank())
        assertEquals("OK", p.dataStatus["openmeteo"])
    }

    @Test
    fun parsesRealForecastResponse() {
        val f = SamudraApi.parseForecast(fixture("forecast.json"), veraval)
        assertTrue(f.hours.size > 24)
        assertEquals(5, f.days.size)
        assertNotNull(f.bestDay)
        assertTrue(f.hours.first().windMs != null && f.hours.first().waveM != null)
        assertTrue(f.days.all { it.messages.containsKey("hi") })
    }

    @Test
    fun refusalWithoutZonesHasNoLevel() {
        val js = JSONObject("""{"plan": {"status": "REFUSED", "risk": {"verdict": "INSUFFICIENT_DATA"}}, "fishing_zones": []}""")
        val p = SamudraApi.parsePlan(js, veraval)
        assertEquals(FishingLevel.NONE, p.level)
        assertNull(p.minKm)
        assertNull(p.route)
        assertEquals("REFUSED", p.status)
    }
}
