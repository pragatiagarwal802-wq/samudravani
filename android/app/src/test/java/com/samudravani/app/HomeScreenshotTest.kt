package com.samudravani.app

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.github.takahirom.roborazzi.captureRoboImage
import com.samudravani.app.data.ChatMsg
import com.samudravani.app.data.Demo
import com.samudravani.app.data.Load
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.SamudraApi
import com.samudravani.app.i18n.Lang
import com.samudravani.app.ui.AppActions
import com.samudravani.app.ui.AppState
import com.samudravani.app.ui.SamudraVaniContent
import com.samudravani.app.ui.Tab
import com.samudravani.app.ui.home.HomeDestination
import com.samudravani.app.ui.theme.SamudraVaniTheme
import org.json.JSONObject
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Renders screens to PNG (app/build/outputs/roborazzi/) for review against the design.
 * Run: gradlew :app:recordRoborazziDebug
 */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w411dp-h820dp-xxhdpi")
class HomeScreenshotTest {
    @get:Rule
    val compose = createComposeRule()

    private val port = PORTS.first()
    private val plan = Demo.plan(port).copy(isDemo = false)
    private val forecast by lazy {
        SamudraApi.parseForecast(JSONObject(javaClass.classLoader!!.getResource("forecast.json").readText()), port)
    }

    private fun capture(name: String, lang: Lang = Lang.HI, at: HomeDestination? = null, tab: Tab = Tab.HOME,
                        state: AppState = AppState(port, lang, "http://10.0.2.2:8000", Load.Ready(plan), Load.Ready(forecast))) {
        compose.setContent {
            SamudraVaniTheme { SamudraVaniContent(state.copy(lang = lang), AppActions(), startAt = at, startTab = tab) }
        }
        compose.onRoot().captureRoboImage("build/outputs/roborazzi/$name.png")
    }

    @Test fun homeHindi() = capture("home_hi")
    @Test fun homeEnglish() = capture("home_en", Lang.EN)
    @Test fun homeGujarati() = capture("home_gu", Lang.GU)
    @Test fun weatherGujarati() = capture("weather_gu", Lang.GU, at = HomeDestination.WEATHER)
    @Test fun alertsGujarati() = capture("alerts_gu", Lang.GU, at = HomeDestination.ALERTS)
    @Test fun homeLoading() = capture("home_loading", state = AppState(port, Lang.HI, "", Load.Loading, Load.Loading))
    @Test fun weather() = capture("weather_hi", at = HomeDestination.WEATHER)
    @Test fun weatherEnglish() = capture("weather_en", Lang.EN, at = HomeDestination.WEATHER)
    @Test fun alerts() = capture("alerts_hi", at = HomeDestination.ALERTS)
    @Test fun profile() = capture("profile_hi", tab = Tab.PROFILE)

    private val chatHi = listOf(
        ChatMsg(0, true, "आज मौसम कैसा है?", "hi"),
        ChatMsg(1, false, "आज Veraval के पास: हवा 25 km/h (दक्षिण-पश्चिम से, झोंके 32 km/h तक), लहरें 1.2 मीटर तक, बारिश 0.0 mm। समुद्र: सुरक्षित।", "hi"),
        ChatMsg(2, true, "मछली कहाँ मिलेगी?", "hi"),
        ChatMsg(3, false, "", "hi", pending = true),
    )

    @Test fun ask() = capture("ask_hi", at = HomeDestination.ASK,
        state = AppState(port, Lang.HI, "", Load.Ready(plan), Load.Ready(forecast), chat = chatHi))
}
