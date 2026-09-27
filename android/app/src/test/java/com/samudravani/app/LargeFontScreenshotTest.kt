package com.samudravani.app

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.github.takahirom.roborazzi.captureRoboImage
import com.samudravani.app.data.Load
import com.samudravani.app.data.PORTS
import com.samudravani.app.i18n.Lang
import com.samudravani.app.ui.AppActions
import com.samudravani.app.ui.AppState
import com.samudravani.app.ui.SamudraVaniContent
import com.samudravani.app.ui.common.LocalLiveMaps
import com.samudravani.app.ui.theme.SamudraVaniTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Home screen with the phone's text size turned up, which used to clip tile subtitles. */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w393dp-h780dp-xxhdpi", fontScale = 1.3f)
class LargeFontScreenshotTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun homeEnglishLargeFont() {
        val port = PORTS.first { it.name == "Mangrol" }
        val state = AppState(port, Lang.EN, "", Load.Ready(Demo.plan(port)), Load.Loading)
        compose.setContent {
            CompositionLocalProvider(LocalLiveMaps provides false) {
                SamudraVaniTheme { SamudraVaniContent(state, AppActions()) }
            }
        }
        compose.onRoot().captureRoboImage("build/outputs/roborazzi/home_en_large_font.png")
    }
}
