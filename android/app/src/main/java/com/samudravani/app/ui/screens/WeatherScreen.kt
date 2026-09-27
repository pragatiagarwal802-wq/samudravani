package com.samudravani.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
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
import com.samudravani.app.data.DayOutlook
import com.samudravani.app.data.Forecast
import com.samudravani.app.data.ForecastHour
import com.samudravani.app.data.Load
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.i18n.compassName
import com.samudravani.app.ui.common.Card
import com.samudravani.app.ui.common.LoadContent
import com.samudravani.app.ui.common.ScreenScaffold
import com.samudravani.app.ui.common.SectionTitle
import com.samudravani.app.ui.common.Stat
import com.samudravani.app.ui.common.VerdictPill
import com.samudravani.app.ui.common.WeatherIcon
import com.samudravani.app.ui.common.WindArrow
import com.samudravani.app.ui.common.celsius
import com.samudravani.app.ui.common.dayLabel
import com.samudravani.app.ui.common.hourLabel
import com.samudravani.app.ui.common.km
import com.samudravani.app.ui.common.kmh
import com.samudravani.app.ui.common.metres
import com.samudravani.app.ui.common.mm
import com.samudravani.app.ui.theme.Sv

@Composable
fun WeatherScreen(forecast: Load<Forecast>, onBack: () -> Unit, onRetry: () -> Unit) {
    val s = LocalStrings.current
    ScreenScaffold(s.weatherTitle, onBack, accent = Sv.WeatherTile) {
        LoadContent(forecast, onRetry) { f ->
            val now = f.hours.firstOrNull()
            if (now != null) NowCard(now, f.port.label)
            SectionTitle(s.next24h)
            HourStrip(f.hours.take(25).filterIndexed { i, _ -> i % 3 == 0 })
            SectionTitle(s.nextDays)
            BestDay(f)
            f.days.forEach { DayRow(it, best = it.date == f.bestDay) }
        }
    }
}

@Composable
private fun NowCard(h: ForecastHour, place: String) {
    val s = LocalStrings.current
    Card(color = Sv.WeatherTile, border = Sv.WeatherBorder) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            WeatherIcon(Modifier.size(width = 56.dp, height = 46.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("${s.now} · $place", fontSize = 13.sp, color = Sv.Body)
                Text("${s.wind} ${kmh(h.windMs)}", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
                h.windFromDeg?.let { Text(s.windFrom(s.compassName(it)), fontSize = 13.sp, color = Sv.Body) }
            }
            h.windFromDeg?.let { WindArrow(it, Modifier.size(36.dp)) }
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth()) {
            Stat(s.waves, metres(h.waveM), Modifier.weight(1f), sub = h.wavePeriodS?.let { "${s.period} %.0f s".format(it) })
            Stat(s.gust, kmh(h.gustMs), Modifier.weight(1f))
            Stat(s.rain, mm(h.rainMm), Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth()) {
            Stat(s.visibility, km(h.visibilityKm), Modifier.weight(1f))
            Stat(s.current, kmh(h.currentMs), Modifier.weight(1f))
            Stat(s.seaTemp, celsius(h.sstC), Modifier.weight(1f))
        }
    }
}

@Composable
private fun HourStrip(hours: List<ForecastHour>) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        hours.forEach { h ->
            Column(
                Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color.White)
                    .padding(horizontal = 12.dp, vertical = 10.dp)
                    .width(64.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(hourLabel(h.time), fontSize = 12.sp, color = Sv.Body)
                h.windFromDeg?.let { WindArrow(it, Modifier.size(20.dp)) }
                Text(kmh(h.windMs).removeSuffix(" km/h"), fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
                Text("km/h", fontSize = 10.sp, color = Sv.Body)
                Text(metres(h.waveM), fontSize = 12.sp, color = Sv.Blue)
                if ((h.rainMm ?: 0.0) >= 0.1) Text(mm(h.rainMm), fontSize = 11.sp, color = Color(0xFF3D8FE0))
            }
        }
    }
}

@Composable
private fun BestDay(f: Forecast) {
    val s = LocalStrings.current
    val d = f.bestDay ?: return
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Sv.FishTile)
            .padding(12.dp),
    ) {
        Column {
            Text("★ ${s.bestDay}", fontSize = 13.sp, color = Sv.Green, fontWeight = FontWeight.Bold)
            Text(s.bestDayHint(dayLabel(d, s, LocalLang.current)), fontSize = 15.sp, color = Sv.Navy)
        }
    }
}

@Composable
private fun DayRow(d: DayOutlook, best: Boolean) {
    val s = LocalStrings.current
    val lang = LocalLang.current
    Card(border = if (best) Sv.Green else Sv.CardBorder) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text((if (best) "★ " else "") + dayLabel(d.date, s, lang), fontSize = 15.sp, fontWeight = FontWeight.Bold,
                color = Sv.Navy, modifier = Modifier.weight(1f))
            VerdictPill(d.verdict)
        }
        Row(Modifier.fillMaxWidth()) {
            Stat(s.waves, metres(d.maxWaveM), Modifier.weight(1f))
            Stat(s.wind, kmh(d.maxWindMs), Modifier.weight(1f))
            Stat(s.rain, mm(d.rainMm), Modifier.weight(1f))
        }
        (d.messages[lang.code] ?: d.messages["en"]).orEmpty().forEach {
            Text(it.message, fontSize = 13.sp, color = Color(0xFF7A4B4B))
        }
    }
}
