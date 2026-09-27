package com.samudravani.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.Load
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Port
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.Bullet
import com.samudravani.app.ui.common.Card
import com.samudravani.app.ui.common.DemoBanner
import com.samudravani.app.ui.common.LoadContent
import com.samudravani.app.ui.common.ScreenScaffold
import com.samudravani.app.ui.common.SeaMap
import com.samudravani.app.ui.common.SectionTitle
import com.samudravani.app.ui.common.Stat
import com.samudravani.app.ui.common.VerdictPill
import com.samudravani.app.ui.common.kmh
import com.samudravani.app.ui.common.metres
import com.samudravani.app.ui.common.nmToKm
import com.samudravani.app.ui.theme.Sv
import kotlin.math.roundToInt

/**
 * Safest route: to the recommended fishing zone (main plan), or port-to-port.
 * [portRoute] is the plan for [routeTo] when a port is chosen.
 */
@Composable
fun RouteScreen(
    home: Port,
    plan: Load<Plan>,
    routeTo: Port?,
    portRoute: Load<Plan>?,
    onChooseDestination: (Port?) -> Unit,
    onBack: () -> Unit,
    onRetry: () -> Unit,
) {
    val s = LocalStrings.current
    ScreenScaffold(s.routeTitle, onBack, accent = Sv.RouteTile) {
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Choice(s.routeToZone, routeTo == null) { onChooseDestination(null) }
            PORTS.filter { it != home }.forEach { p ->
                Choice(p.localName(LocalLang.current.code), routeTo == p) { onChooseDestination(p) }
            }
        }
        LoadContent(if (routeTo == null) plan else portRoute, onRetry) { p -> RouteDetails(p) }
    }
}

@Composable
private fun Choice(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .clip(CircleShape)
            .background(if (selected) Sv.Blue else Color.White)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 7.dp),
    ) { Text(label, fontSize = 13.sp, color = if (selected) Color.White else Sv.Navy, fontWeight = FontWeight.SemiBold) }
}

@Composable
private fun RouteDetails(p: Plan) {
    val s = LocalStrings.current
    val t = p.text(LocalLang.current.code)
    val r = p.route
    DemoBanner(p.isDemo)
    Card(color = Sv.RouteTile, border = Sv.RouteBorder) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(t?.summary ?: "", fontSize = 14.sp, color = Sv.Navy, modifier = Modifier.weight(1f))
        }
        Row { VerdictPill(p.status) }
    }
    if (r == null || !r.found) {
        Card {
            Text(s.noRoute, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
            (t?.refusalReason ?: r?.reason)?.let { Text(it, fontSize = 14.sp, color = Sv.Body) }
        }
    } else {
        val dest = p.destination ?: p.target?.let { LatLon(it.lat, it.lon) }
        SeaMap(
            p.port, listOfNotNull(p.target), r.waypoints,
            Modifier.fillMaxWidth().height(260.dp).clip(RoundedCornerShape(14.dp)),
            altRoutes = p.alternates.filter { it.found }.map { it.waypoints },
            destination = dest,
        )
        Card {
            Row(Modifier.fillMaxWidth()) {
                Stat(s.distance, "${nmToKm(r.distanceNm)} km", Modifier.weight(1f), sub = "%.1f nm".format(r.distanceNm))
                Stat(s.duration, "%.1f %s".format(r.durationH, s.hoursUnit), Modifier.weight(1f))
                Stat(s.fuel, "${r.fuelL.roundToInt()} L", Modifier.weight(1f))
            }
            Text(s.roundTrip((2 * r.fuelL).roundToInt()), fontSize = 13.sp, color = Sv.Body)
            Row(Modifier.fillMaxWidth()) {
                Stat(s.maxWave, metres(r.maxWaveM), Modifier.weight(1f))
                Stat(s.headwind, kmh(r.maxHeadwindMs), Modifier.weight(1f))
            }
        }
        if (!r.landMaskUsed) Warning(s.notLandChecked)
    }
    val notes = t?.caveats.orEmpty()
    if (notes.isNotEmpty()) {
        SectionTitle(s.notes)
        notes.forEach { Bullet(it) }
    }
}
