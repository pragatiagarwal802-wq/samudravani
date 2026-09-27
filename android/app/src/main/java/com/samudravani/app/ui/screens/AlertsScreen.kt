package com.samudravani.app.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.Forecast
import com.samudravani.app.data.Load
import com.samudravani.app.data.Plan
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.Bullet
import com.samudravani.app.ui.common.Card
import com.samudravani.app.ui.common.DemoBanner
import com.samudravani.app.ui.common.LoadContent
import com.samudravani.app.ui.common.ScreenScaffold
import com.samudravani.app.ui.common.SectionTitle
import com.samudravani.app.ui.common.VerdictPill
import com.samudravani.app.ui.common.WarningIcon
import com.samudravani.app.ui.common.dayLabel
import com.samudravani.app.ui.common.kmh
import com.samudravani.app.ui.common.metres
import com.samudravani.app.ui.theme.Sv

/** Current voyage risk (from the plan) and the verdict for each of the next days (from the forecast). */
@Composable
fun AlertsScreen(plan: Load<Plan>, forecast: Load<Forecast>, onBack: (() -> Unit)?, onRetry: () -> Unit) {
    val s = LocalStrings.current
    val lang = LocalLang.current
    ScreenScaffold(s.alertsTitle, onBack, accent = Sv.AlertTile) {
        LoadContent(plan, onRetry) { p ->
            val t = p.text(lang.code)
            DemoBanner(p.isDemo)
            Card(color = Sv.AlertTile, border = Sv.AlertBorder) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    WarningIcon(Modifier.size(width = 40.dp, height = 36.dp))
                    Spacer(Modifier.width(12.dp))
                    Text(s.todayRisk, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Sv.Navy, modifier = Modifier.weight(1f))
                    VerdictPill(p.riskVerdict)
                }
                val rules = t?.triggered.orEmpty()
                if (rules.isEmpty()) {
                    Text(s.noAlerts, fontSize = 15.sp, color = Sv.Green, fontWeight = FontWeight.SemiBold)
                    t?.riskExplanation?.let { Text(it, fontSize = 13.sp, color = Sv.Body) }
                } else {
                    rules.forEach { r ->
                        Row(verticalAlignment = Alignment.Top) {
                            VerdictPill(r.verdict)
                            Spacer(Modifier.width(8.dp))
                            Text(r.message, fontSize = 14.sp, color = Sv.Navy)
                        }
                    }
                }
            }
        }
        SectionTitle(s.outlook)
        LoadContent(forecast, onRetry) { f ->
            f.days.forEach { d ->
                Card(border = if (d.verdict == "SAFE") Sv.CardBorder else Sv.AlertBorder) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(dayLabel(d.date, s, lang), fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Sv.Navy,
                            modifier = Modifier.weight(1f))
                        VerdictPill(d.verdict)
                    }
                    Text("${s.waves} ${metres(d.maxWaveM)} · ${s.wind} ${kmh(d.maxWindMs)} · ${s.gust} ${kmh(d.maxGustMs)}",
                        fontSize = 13.sp, color = Sv.Body)
                    (d.messages[lang.code] ?: d.messages["en"]).orEmpty().forEach { Bullet(it.message, Color(0xFF7A4B4B)) }
                }
            }
        }
    }
}
