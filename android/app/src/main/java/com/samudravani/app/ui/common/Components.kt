package com.samudravani.app.ui.common

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.Load
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.theme.Sv

/** Header (back + title) over a scrolling column, on the page background. */
@Composable
fun ScreenScaffold(
    title: String,
    onBack: (() -> Unit)?,
    accent: Color = Sv.WeatherTile,
    scroll: Boolean = true,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(Modifier.fillMaxSize().background(Sv.PageBg)) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(accent)
                .statusBarsPadding()
                .height(56.dp)
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (onBack != null) {
                Box(
                    Modifier.size(44.dp).clip(CircleShape).clickable(onClick = onBack),
                    contentAlignment = Alignment.Center,
                ) { Chevron(Modifier.size(22.dp).rotate(180f), color = Sv.Navy) }
            } else {
                Spacer(Modifier.width(12.dp))
            }
            Text(title, fontSize = 19.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
        }
        Column(
            Modifier
                .weight(1f)
                .then(if (scroll) Modifier.verticalScroll(rememberScrollState()) else Modifier)
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content,
        )
    }
}

/** Renders [load]: spinner, an error with retry, or [content]. */
@Composable
fun <T> LoadContent(load: Load<T>?, onRetry: () -> Unit, content: @Composable (T) -> Unit) {
    val s = LocalStrings.current
    when (load) {
        null, Load.Loading -> Column(
            Modifier.fillMaxWidth().padding(vertical = 48.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            CircularProgressIndicator(color = Sv.Blue)
            Spacer(Modifier.height(12.dp))
            Text(s.loading, color = Sv.Body, fontSize = 14.sp)
        }
        is Load.Failed -> Card {
            Text(s.serverUnavailable, fontWeight = FontWeight.Bold, color = Sv.Navy, fontSize = 16.sp)
            Text(load.reason, color = Sv.Body, fontSize = 12.sp)
            Spacer(Modifier.height(4.dp))
            Pill(s.retry, Sv.Blue, onClick = onRetry)
        }
        is Load.Ready -> content(load.value)
    }
}

@Composable
fun Card(
    modifier: Modifier = Modifier,
    color: Color = Color.White,
    border: Color = Sv.CardBorder,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val inner: @Composable () -> Unit = {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp), content = content)
    }
    if (onClick != null) {
        Surface(onClick = onClick, modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), color = color,
            border = BorderStroke(1.dp, border), shadowElevation = 1.dp) { inner() }
    } else {
        Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), color = color,
            border = BorderStroke(1.dp, border), shadowElevation = 1.dp) { inner() }
    }
}

fun verdictColor(v: String?): Color = when (v) {
    "SAFE", "PROCEED" -> Color(0xFF1A7F37)
    "CAUTION", "PROCEED_WITH_CAUTION" -> Color(0xFF9A6700)
    "HIGH_RISK", "NOT_RECOMMENDED" -> Color(0xFFBC4C00)
    "DO_NOT_VENTURE" -> Color(0xFFCF222E)
    else -> Color(0xFF57606A)
}

@Composable
fun Pill(text: String, color: Color, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    Box(
        modifier
            .clip(CircleShape)
            .background(color)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 12.dp, vertical = 5.dp),
    ) { Text(text, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun VerdictPill(verdict: String?, modifier: Modifier = Modifier) {
    val s = LocalStrings.current
    Pill(s.verdicts[verdict] ?: s.planStatus[verdict] ?: verdict.orEmpty(), verdictColor(verdict), modifier)
}

@Composable
fun DemoBanner(show: Boolean) {
    if (!show) return
    val s = LocalStrings.current
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFFFFF4D6))
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) { Text(s.demoBanner, fontSize = 12.sp, color = Color(0xFF7A5200)) }
}

/** Label over a big value, used in stat grids. */
@Composable
fun Stat(label: String, value: String, modifier: Modifier = Modifier, sub: String? = null) {
    Column(modifier) {
        Text(label, fontSize = 12.sp, color = Sv.Body)
        Text(value, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
        if (sub != null) Text(sub, fontSize = 11.sp, color = Sv.Body)
    }
}

@Composable
fun SectionTitle(text: String) =
    Text(text, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Sv.Navy, modifier = Modifier.padding(top = 4.dp))

@Composable
fun Bullet(text: String, color: Color = Sv.Body) =
    Row {
        Text("•", color = color, fontSize = 14.sp, modifier = Modifier.width(14.dp), textAlign = TextAlign.Start)
        Text(text, color = color, fontSize = 14.sp)
    }

/** Arrow pointing where the wind blows TO, for a meteorological FROM direction. */
@Composable
fun WindArrow(fromDeg: Double, modifier: Modifier = Modifier, color: Color = Sv.Blue) =
    UpArrow(modifier.rotate((fromDeg + 180).toFloat()), color = color)
