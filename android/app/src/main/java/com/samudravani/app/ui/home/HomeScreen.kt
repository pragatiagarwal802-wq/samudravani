package com.samudravani.app.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.R
import com.samudravani.app.data.Load
import com.samudravani.app.data.Plan
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.Port
import com.samudravani.app.i18n.FishingLevel
import com.samudravani.app.i18n.LANG_LABELS
import com.samudravani.app.i18n.Lang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.Birds
import com.samudravani.app.ui.common.Chevron
import com.samudravani.app.ui.common.FishIcon
import com.samudravani.app.ui.common.FishingBoat
import com.samudravani.app.ui.common.MapThumbnail
import com.samudravani.app.ui.common.MicIcon
import com.samudravani.app.ui.common.PinIcon
import com.samudravani.app.ui.common.RouteIcon
import com.samudravani.app.ui.common.WarningIcon
import com.samudravani.app.ui.common.WeatherIcon
import com.samudravani.app.ui.theme.Sv

enum class HomeDestination { WEATHER, FISHING, ALERTS, ROUTE, SUMMARY, ASK }

// Smallest sizes (dp) of the blocks below the hero, from the mockup at 411 dp width.
private const val ROW1_DP = 112f
private const val ROW2_DP = 106f
private const val CARD_DP = 106f
private const val ASK_DP = 66f
private const val GAP_DP = 12f

@Composable
fun HomeScreen(
    state: Load<Plan>,
    port: Port,
    lang: Lang,
    onLangChange: (Lang) -> Unit,
    onPortChange: (Port) -> Unit,
    onOpen: (HomeDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    // When the screen is tall enough, the two tile rows and the summary card share the spare
    // height in the mockup's proportions, so the layout fills the screen like the design and the
    // ask bar sits just above the bottom navigation. Shorter screens scroll at the design sizes.
    BoxWithConstraints(modifier.fillMaxSize().background(Sv.PageBg)) {
        val inset = with(LocalDensity.current) { WindowInsets.statusBars.getTop(this).toDp() }
        val needed = inset + (HERO_DP + ROW1_DP + ROW2_DP + CARD_DP + ASK_DP + 5 * GAP_DP + 14f).dp
        val fill = maxHeight >= needed
        Column(if (fill) Modifier.fillMaxSize() else Modifier.verticalScroll(rememberScrollState())) {
            Hero(port, lang, onLangChange, onPortChange)
            Column(
                Modifier
                    .padding(start = 16.dp, end = 16.dp, bottom = 14.dp)
                    .then(if (fill) Modifier.weight(1f) else Modifier),
                verticalArrangement = Arrangement.spacedBy(GAP_DP.dp),
            ) {
                fun ColumnScope.block(weight: Float, min: Float) =
                    if (fill) Modifier.weight(weight) else Modifier.height(min.dp)
                TileRow(block(ROW1_DP, ROW1_DP)) {
                    WeatherTile(Modifier.weight(1f), onOpen)
                    FishingTile(Modifier.weight(1f), onOpen)
                }
                TileRow(block(ROW2_DP, ROW2_DP)) {
                    AlertsTile(Modifier.weight(1f), onOpen)
                    RouteTile(Modifier.weight(1f), onOpen)
                }
                SummaryCard(state, port, block(CARD_DP, CARD_DP), onClick = { onOpen(HomeDestination.SUMMARY) })
                Spacer(Modifier.height(GAP_DP.dp))
                AskBar(onClick = { onOpen(HomeDestination.ASK) })
            }
        }
    }
}

// --- hero -----------------------------------------------------------------------------

// Hero geometry in dp below the status bar, measured from the mockup at 411 dp width.
private const val HORIZON_DP = 146f
private const val HERO_DP = 232f

@Composable
private fun Hero(port: Port, lang: Lang, onLangChange: (Lang) -> Unit, onPortChange: (Port) -> Unit) {
    val s = LocalStrings.current
    val density = LocalDensity.current
    val inset = WindowInsets.statusBars.getTop(density).toFloat()
    Box(
        Modifier
            .fillMaxWidth()
            .drawBehind {
                val dp = density.density
                val horizon = inset + HORIZON_DP * dp
                val h = size.height
                drawRect(Brush.verticalGradient(listOf(Sv.SkyTop, Sv.SkyBottom), 0f, horizon), size = size.copy(height = horizon))
                drawRect(
                    Brush.verticalGradient(
                        0f to Color(0xFFC4E1F4), 0.4f to Sv.SeaTop, 0.62f to Color(0xFF8CC4EA), 1f to Sv.PageBg,
                        startY = horizon, endY = h,
                    ),
                    topLeft = Offset(0f, horizon), size = size.copy(height = h - horizon),
                )
                // light glints on the water
                listOf(0.08f to 14f, 0.30f to 26f, 0.52f to 10f, 0.66f to 34f, 0.90f to 20f, 0.18f to 44f, 0.78f to 52f)
                    .forEach { (x, y) ->
                        val yy = horizon + y * dp
                        drawLine(Color.White.copy(alpha = 0.35f), Offset(size.width * x, yy), Offset(size.width * x + 26 * dp, yy), 1.2f * dp)
                    }
            },
    ) {
        Box(Modifier.windowInsetsPadding(WindowInsets.statusBars).fillMaxWidth().height(HERO_DP.dp)) {
            // distant headland on the horizon
            Box(
                Modifier
                    .align(Alignment.TopEnd)
                    .offset(x = 30.dp, y = (HORIZON_DP - 12).dp)
                    .size(width = 190.dp, height = 12.dp)
                    .clip(RoundedCornerShape(topStart = 90.dp, topEnd = 40.dp))
                    .background(Color(0xFFA9CBE4)),
            )
            Birds(
                Modifier
                    .align(Alignment.TopEnd)
                    .offset(x = (-24).dp, y = 76.dp)
                    .size(width = 140.dp, height = 40.dp),
            )
            FishingBoat(
                Modifier
                    .align(Alignment.TopEnd)
                    .offset(x = (-42).dp, y = 90.dp)
                    .size(width = 112.dp, height = 90.dp),
            )

            Image(
                painterResource(R.drawable.logo_samudravani),
                contentDescription = "SamudraVani",
                modifier = Modifier
                    .offset(x = 22.dp, y = 20.dp)
                    .size(width = 92.dp, height = 92.dp),
            )
            LanguageToggle(
                lang, onLangChange,
                Modifier
                    .align(Alignment.TopEnd)
                    .offset(x = (-14).dp, y = 26.dp),
            )
            Text(
                s.tagline,
                style = TextStyle(fontSize = 18.5.sp, lineHeight = 23.sp, fontWeight = FontWeight.Bold, color = Sv.Navy),
                modifier = Modifier
                    .offset(x = 20.dp, y = 118.dp)
                    .width(230.dp),
            )
            PortSelector(port, onPortChange, Modifier.offset(x = 16.dp, y = 176.dp))
        }
    }
}

@Composable
private fun LanguageToggle(lang: Lang, onChange: (Lang) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .shadow(3.dp, CircleShape)
            .clip(CircleShape)
            .background(Color.White)
            .border(1.dp, Color(0xFFD7E3F0), CircleShape),
    ) {
        LANG_LABELS.forEach { (l, label) ->
            val on = l == lang
            Box(
                Modifier
                    .clip(CircleShape)
                    .background(if (on) Sv.Blue else Color.Transparent)
                    .clickable { onChange(l) }
                    .padding(horizontal = 12.dp, vertical = 4.dp),
            ) {
                Text(label, fontSize = 13.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (on) Color.White else Sv.Body)
            }
        }
    }
}

@Composable
private fun PortSelector(port: Port, onChange: (Port) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Row(
            Modifier
                .shadow(6.dp, RoundedCornerShape(26.dp), ambientColor = Color(0x331F6BC1), spotColor = Color(0x331F6BC1))
                .clip(RoundedCornerShape(26.dp))
                .background(Color.White)
                .clickable { open = true }
                .width(214.dp)
                .height(44.dp)
                .padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PinIcon(Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text(port.label, fontSize = 15.sp, fontWeight = FontWeight.Medium, color = Sv.Navy, modifier = Modifier.weight(1f))
            Chevron(Modifier.size(20.dp), down = true)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            PORTS.forEach { p ->
                DropdownMenuItem(text = { Text(p.label) }, onClick = { open = false; onChange(p) })
            }
        }
    }
}

// --- feature tiles ---------------------------------------------------------------------

@Composable
private fun TileRow(modifier: Modifier, content: @Composable RowScope.() -> Unit) =
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), content = content)

@Composable
private fun WeatherTile(modifier: Modifier, onOpen: (HomeDestination) -> Unit) {
    val s = LocalStrings.current
    Tile(s.weatherTitle, s.weatherSub, Sv.WeatherTile, Sv.WeatherBorder, Sv.Body, modifier,
        { onOpen(HomeDestination.WEATHER) }) { WeatherIcon(Modifier.size(width = 54.dp, height = 44.dp)) }
}

@Composable
private fun FishingTile(modifier: Modifier, onOpen: (HomeDestination) -> Unit) {
    val s = LocalStrings.current
    Tile(s.fishingTitle, s.fishingSub, Sv.FishTile, Sv.FishBorder, Sv.Body, modifier,
        { onOpen(HomeDestination.FISHING) }) { FishIcon(Modifier.size(width = 64.dp, height = 40.dp)) }
}

@Composable
private fun AlertsTile(modifier: Modifier, onOpen: (HomeDestination) -> Unit) {
    val s = LocalStrings.current
    Tile(s.alertsTitle, s.alertsSub, Sv.AlertTile, Sv.AlertBorder, Color(0xFF7A4B4B), modifier,
        { onOpen(HomeDestination.ALERTS) }) { WarningIcon(Modifier.size(width = 48.dp, height = 42.dp)) }
}

@Composable
private fun RouteTile(modifier: Modifier, onOpen: (HomeDestination) -> Unit) {
    val s = LocalStrings.current
    Tile(s.routeTitle, s.routeSub, Sv.RouteTile, Sv.RouteBorder, Color(0xFF55557A), modifier,
        { onOpen(HomeDestination.ROUTE) }) { RouteIcon(Modifier.size(width = 64.dp, height = 44.dp)) }
}

@Composable
private fun Tile(
    title: String,
    subtitle: String,
    bg: Color,
    border: Color,
    subColor: Color,
    modifier: Modifier,
    onClick: () -> Unit,
    icon: @Composable () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(14.dp),
        color = bg,
        border = BorderStroke(1.dp, border),
        shadowElevation = 1.dp,
        modifier = modifier.fillMaxHeight(),
    ) {
        Column(
            Modifier.fillMaxHeight().padding(start = 12.dp, end = 8.dp, top = 12.dp, bottom = 12.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Box(Modifier.height(42.dp), contentAlignment = Alignment.CenterStart) { icon() }
            Column {
                Spacer(Modifier.height(10.dp))
                BasicText(
                    title,
                    style = TextStyle(fontWeight = FontWeight.Bold, color = Sv.Navy),
                    maxLines = 1,
                    autoSize = TextAutoSize.StepBased(minFontSize = 12.sp, maxFontSize = 16.sp, stepSize = 0.5.sp),
                )
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(subtitle, fontSize = 12.5.sp, lineHeight = 17.sp, color = subColor, modifier = Modifier.weight(1f),
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Chevron(Modifier.size(18.dp))
                }
            }
        }
    }
}

// --- summary + ask -------------------------------------------------------------------------

@Composable
private fun SummaryCard(state: Load<Plan>, port: Port, modifier: Modifier, onClick: () -> Unit) {
    val s = LocalStrings.current
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(14.dp),
        color = Color.White,
        border = BorderStroke(1.dp, Sv.CardBorder),
        shadowElevation = 1.dp,
        modifier = modifier.fillMaxWidth(),
    ) {
        Row(Modifier.fillMaxSize().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            MapThumbnail(
                Modifier
                    .width(162.dp)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(10.dp)),
            )
            Box(Modifier.padding(horizontal = 12.dp).width(1.dp).fillMaxHeight(0.8f).background(Sv.CardBorder))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(Sv.Green))
                    Spacer(Modifier.width(6.dp))
                    Text(s.fishingChance, fontSize = 12.sp, color = Sv.Green, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Spacer(Modifier.height(4.dp))
                when (state) {
                    Load.Loading -> Text(s.loading, fontSize = 13.sp, color = Sv.Body)
                    is Load.Failed -> {
                        Text(s.levels.getValue(FishingLevel.NONE), fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Sv.Navy)
                        Text(s.serverUnavailable, fontSize = 12.sp, color = Sv.Body)
                    }
                    is Load.Ready -> SummaryValues(state.value, port)
                }
            }
            Chevron(Modifier.size(20.dp))
        }
    }
}

@Composable
private fun SummaryValues(d: Plan, port: Port) {
    val s = LocalStrings.current
    Text(s.levels.getValue(d.level), fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Sv.Navy,
        maxLines = 1, overflow = TextOverflow.Ellipsis)
    Spacer(Modifier.height(2.dp))
    val lo = d.minKm
    val hi = d.maxKm
    if (lo != null && hi != null) {
        val range = if (lo == hi) "$lo" else "$lo–$hi"
        Text(s.fromPort(port.name, range), fontSize = 14.sp, color = Sv.Body)
    }
    if (d.isDemo) {
        Text(s.demo, fontSize = 10.sp, color = Color(0xFF9A6700), modifier = Modifier.padding(top = 2.dp))
    }
}

@Composable
private fun AskBar(onClick: () -> Unit) {
    val s = LocalStrings.current
    Row(
        Modifier
            .fillMaxWidth()
            .shadow(6.dp, CircleShape, ambientColor = Sv.Blue, spotColor = Sv.Blue)
            .clip(CircleShape)
            .background(Brush.horizontalGradient(listOf(Sv.BlueDark, Sv.Blue, Color(0xFF2A78CC))))
            .clickable(onClick = onClick)
            .height(66.dp)
            .padding(start = 28.dp, end = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        MicIcon(Modifier.size(width = 26.dp, height = 32.dp))
        Spacer(Modifier.width(22.dp))
        Column(Modifier.weight(1f)) {
            Text(s.ask, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White)
            Text(s.askSub, fontSize = 13.sp, color = Color.White.copy(alpha = 0.85f))
        }
        Chevron(Modifier.size(22.dp), color = Color.White)
    }
}
