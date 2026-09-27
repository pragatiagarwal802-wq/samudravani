package com.samudravani.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
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
import com.samudravani.app.data.Load
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Zone
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.i18n.compassName
import com.samudravani.app.ui.common.Bullet
import com.samudravani.app.ui.common.Card
import com.samudravani.app.ui.common.DemoBanner
import com.samudravani.app.ui.common.FishIcon
import com.samudravani.app.ui.common.LoadContent
import com.samudravani.app.ui.common.Pill
import com.samudravani.app.ui.common.ScreenScaffold
import com.samudravani.app.ui.common.SeaMap
import com.samudravani.app.ui.common.SectionTitle
import com.samudravani.app.ui.theme.Sv

@Composable
fun FishingScreen(plan: Load<Plan>, onBack: () -> Unit, onRetry: () -> Unit, onShowZone: (Zone) -> Unit) {
    val s = LocalStrings.current
    ScreenScaffold(s.fishingTitle, onBack, accent = Sv.FishTile) {
        LoadContent(plan, onRetry) { p ->
            val text = p.text(LocalLang.current.code)
            DemoBanner(p.isDemo)
            Card(color = Sv.FishTile, border = Sv.FishBorder) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    FishIcon(Modifier.size(width = 56.dp, height = 36.dp))
                    Spacer(Modifier.width(12.dp))
                    androidx.compose.foundation.layout.Column {
                        Text(s.fishingChance, fontSize = 13.sp, color = Sv.Green)
                        Text(s.levels.getValue(p.level), fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
                        val lo = p.minKm
                        val hi = p.maxKm
                        if (lo != null && hi != null) {
                            Text(s.fromPort(p.port.name, if (lo == hi) "$lo" else "$lo–$hi"), fontSize = 14.sp, color = Sv.Body)
                        }
                    }
                }
            }
            if (p.status == "DO_NOT_VENTURE" || p.status == "NOT_RECOMMENDED") {
                Warning(s.adviseAgainst)
            }
            if (p.zones.isNotEmpty()) {
                SeaMap(
                    p.port, p.zones, emptyList(),
                    Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(14.dp)),
                    labels = { s.zone(it + 1) },
                )
                SectionTitle(s.zonesTitle)
                p.zones.forEachIndexed { i, z -> ZoneCard(i + 1, z, target = z == p.target, onShow = { onShowZone(z) }) }
            } else {
                Card { Text(s.noZones, fontSize = 15.sp, color = Sv.Navy, fontWeight = FontWeight.SemiBold) }
            }
            val notes = text?.caveats.orEmpty()
            if (notes.isNotEmpty()) {
                SectionTitle(s.notes)
                notes.forEach { Bullet(it) }
            }
        }
    }
}

@Composable
private fun ZoneCard(n: Int, z: Zone, target: Boolean, onShow: () -> Unit) {
    val s = LocalStrings.current
    Card(border = if (target) Sv.Green else Sv.CardBorder, onClick = onShow) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text((if (target) "★ " else "") + s.zone(n), fontSize = 16.sp, fontWeight = FontWeight.Bold,
                color = Sv.Navy, modifier = Modifier.weight(1f))
            Text("${s.score} ${"%.2f".format(z.score)}", fontSize = 13.sp, color = Sv.Body)
        }
        ScoreBar(z.score)
        Text(s.distanceDir(z.distanceKm, s.compassName(z.bearingDeg.toDouble())), fontSize = 14.sp, color = Sv.Navy)
        Text("%.3f° N, %.3f° E".format(z.lat, z.lon), fontSize = 12.sp, color = Sv.Body)
        if (z.reasons.isNotEmpty()) {
            Text(s.why, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Sv.Body)
            z.reasons.forEach { Bullet(it) }
        }
        Pill(s.showOnMap, Sv.Blue, onClick = onShow)
    }
}

@Composable
private fun ScoreBar(score: Double) {
    Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Color(0xFFE3EBF3))) {
        Box(Modifier.fillMaxWidth(score.toFloat().coerceIn(0f, 1f)).height(8.dp).clip(RoundedCornerShape(4.dp)).background(Sv.Green))
    }
}

@Composable
fun Warning(text: String) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Sv.AlertTile)
            .padding(12.dp),
    ) { Text(text, color = Color(0xFF8A1F1F), fontSize = 14.sp, fontWeight = FontWeight.SemiBold) }
}
