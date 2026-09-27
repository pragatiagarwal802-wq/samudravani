package com.samudravani.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.Load
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Port
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.LoadContent
import com.samudravani.app.ui.common.SeaMap
import com.samudravani.app.ui.theme.Sv

/** Map tab: home port, fishing zones and the recommended route. [focus] centres on a zone. */
@Composable
fun MapScreen(port: Port, plan: Load<Plan>, focus: LatLon?, onRetry: () -> Unit) {
    val s = LocalStrings.current
    Box(Modifier.fillMaxSize().background(Sv.PageBg)) {
        when (plan) {
            is Load.Ready -> {
                val p = plan.value
                SeaMap(
                    port, p.zones, p.route?.takeIf { it.found }?.waypoints.orEmpty(), Modifier.fillMaxSize(),
                    altRoutes = p.alternates.filter { it.found }.map { it.waypoints }, focus = focus,
                    labels = { s.zone(it + 1) },
                )
            }
            else -> Column(Modifier.statusBarsPadding().padding(16.dp)) { LoadContent(plan, onRetry) {} }
        }
        Row(
            Modifier
                .align(Alignment.BottomStart)
                .padding(10.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Color.White.copy(alpha = 0.92f))
                .padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Legend(Sv.Navy, s.legendPort)
            Legend(Sv.ZoneFill, s.legendZone)
            Legend(Sv.Blue, s.legendRoute)
            Text(s.osmCredit, fontSize = 9.sp, color = Sv.Body)
        }
    }
}

@Composable
private fun Legend(color: Color, label: String) = Row(verticalAlignment = Alignment.CenterVertically) {
    Box(Modifier.size(10.dp).clip(CircleShape).background(color))
    Text(" $label", fontSize = 11.sp, color = Sv.Navy)
}
