package com.samudravani.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.samudravani.app.data.ChatMsg
import com.samudravani.app.data.Forecast
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.Load
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Port
import com.samudravani.app.i18n.Lang
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.i18n.stringsFor
import com.samudravani.app.ui.common.NavGlyph
import com.samudravani.app.ui.common.NavIcon
import com.samudravani.app.ui.home.HomeDestination
import com.samudravani.app.ui.home.HomeScreen
import com.samudravani.app.ui.screens.AlertsScreen
import com.samudravani.app.ui.screens.AskScreen
import com.samudravani.app.ui.screens.FishingScreen
import com.samudravani.app.ui.screens.MapScreen
import com.samudravani.app.ui.screens.ProfileScreen
import com.samudravani.app.ui.screens.RouteScreen
import com.samudravani.app.ui.screens.WeatherScreen
import com.samudravani.app.ui.theme.Sv

enum class Tab { HOME, MAP, ALERTS, PROFILE }

/** Everything the UI shows; produced by [AppViewModel]. */
data class AppState(
    val port: Port,
    val lang: Lang,
    val serverUrl: String,
    val plan: Load<Plan>,
    val forecast: Load<Forecast>,
    val routeTo: Port? = null,
    val portRoute: Load<Plan>? = null,
    val chat: List<ChatMsg> = emptyList(),
)

/** User actions, forwarded to [AppViewModel]. */
data class AppActions(
    val setLang: (Lang) -> Unit = {},
    val selectPort: (Port) -> Unit = {},
    val setServerUrl: (String) -> Unit = {},
    val refresh: () -> Unit = {},
    val routeToPort: (Port?) -> Unit = {},
    val ask: (String) -> Unit = {},
)

@Composable
fun SamudraVaniApp(vm: AppViewModel = viewModel()) {
    val state = AppState(
        port = vm.port.collectAsStateWithLifecycle().value,
        lang = vm.lang.collectAsStateWithLifecycle().value,
        serverUrl = vm.serverUrl.collectAsStateWithLifecycle().value,
        plan = vm.plan.collectAsStateWithLifecycle().value,
        forecast = vm.forecast.collectAsStateWithLifecycle().value,
        routeTo = vm.routeTo.collectAsStateWithLifecycle().value,
        portRoute = vm.portRoute.collectAsStateWithLifecycle().value,
        chat = vm.chat.collectAsStateWithLifecycle().value,
    )
    SamudraVaniContent(state, AppActions(vm::setLang, vm::selectPort, vm::setServerUrl, vm::refresh, vm::routeToPort, vm::ask))
}

/** Stateless shell (bottom navigation + screens), also used by the screenshot tests. */
@Composable
fun SamudraVaniContent(state: AppState, actions: AppActions, startAt: HomeDestination? = null, startTab: Tab = Tab.HOME) {
    var tab by rememberSaveable { mutableStateOf(startTab) }
    var detail by rememberSaveable { mutableStateOf(startAt) }
    var mapFocus by rememberSaveable { mutableStateOf<Pair<Double, Double>?>(null) }
    CompositionLocalProvider(LocalStrings provides stringsFor(state.lang), LocalLang provides state.lang) {
        val s = LocalStrings.current
        Column(Modifier.fillMaxSize().background(Sv.PageBg)) {
            Box(Modifier.weight(1f)) {
                val open = detail
                val back = { detail = null }
                if (open != null) BackHandler(onBack = back) else if (tab != Tab.HOME) BackHandler { tab = Tab.HOME }
                when {
                    open == HomeDestination.WEATHER -> WeatherScreen(state.forecast, back, actions.refresh)
                    open == HomeDestination.FISHING || open == HomeDestination.SUMMARY ->
                        FishingScreen(state.plan, back, actions.refresh) { z ->
                            mapFocus = z.lat to z.lon
                            detail = null
                            tab = Tab.MAP
                        }
                    open == HomeDestination.ALERTS -> AlertsScreen(state.plan, state.forecast, back, actions.refresh)
                    open == HomeDestination.ROUTE -> RouteScreen(
                        state.port, state.plan, state.routeTo, state.portRoute, actions.routeToPort, back, actions.refresh,
                    )
                    open == HomeDestination.ASK -> AskScreen(state.chat, actions.ask, back, autoListen = true)
                    tab == Tab.HOME -> HomeScreen(state.plan, state.port, state.lang, actions.setLang, actions.selectPort,
                        onOpen = { detail = it })
                    tab == Tab.MAP -> MapScreen(state.port, state.plan, mapFocus?.let { LatLon(it.first, it.second) }, actions.refresh)
                    tab == Tab.ALERTS -> AlertsScreen(state.plan, state.forecast, null, actions.refresh)
                    else -> ProfileScreen(state.port, state.serverUrl, state.plan, actions.setLang, actions.selectPort,
                        actions.setServerUrl)
                }
            }
            BottomNav(tab) {
                tab = it
                detail = null
                if (it != Tab.MAP) mapFocus = null
            }
        }
    }
}

@Composable
private fun BottomNav(selected: Tab, onSelect: (Tab) -> Unit) {
    val s = LocalStrings.current
    Column(Modifier.background(Color.White).windowInsetsPadding(WindowInsets.navigationBars)) {
        HorizontalDivider(color = Sv.CardBorder)
        Row(Modifier.fillMaxWidth().height(70.dp), horizontalArrangement = Arrangement.SpaceAround) {
            listOf(
                Triple(Tab.HOME, NavGlyph.HOME, s.navHome),
                Triple(Tab.MAP, NavGlyph.MAP, s.navMap),
                Triple(Tab.ALERTS, NavGlyph.BELL, s.navAlerts),
                Triple(Tab.PROFILE, NavGlyph.PERSON, s.navProfile),
            ).forEach { (t, glyph, label) ->
                val on = t == selected
                val color = if (on) Sv.Blue else Sv.NavIdle
                Column(
                    Modifier
                        .weight(1f)
                        .clickable { onSelect(t) }
                        .padding(top = 10.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    NavIcon(glyph, color, Modifier.size(26.dp))
                    Spacer(Modifier.height(4.dp))
                    Text(label, fontSize = 12.5.sp, color = color, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
                    Spacer(Modifier.height(4.dp))
                    Box(
                        Modifier
                            .width(34.dp)
                            .height(3.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(if (on) Sv.Blue else Color.Transparent),
                    )
                }
            }
        }
    }
}
