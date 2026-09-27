package com.samudravani.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Palette sampled from the SamudraVani home-screen mockup. */
object Sv {
    val Navy = Color(0xFF14284B)          // headings
    val Body = Color(0xFF4B5A73)          // secondary text
    val Blue = Color(0xFF1F6BC1)          // primary: toggle, icons, nav
    val BlueDark = Color(0xFF17579F)
    val PageBg = Color(0xFFF4F8FC)
    val CardBorder = Color(0xFFDDE7F2)
    val NavIdle = Color(0xFF6B7A90)

    val SkyTop = Color(0xFFCFE6F7)
    val SkyBottom = Color(0xFFDDEFFA)
    val SeaTop = Color(0xFF6FB1E0)
    val SeaBottom = Color(0xFFB4D9F0)

    val WeatherTile = Color(0xFFEAF3FC)
    val WeatherBorder = Color(0xFFD5E5F5)
    val FishTile = Color(0xFFE7F4EC)
    val FishBorder = Color(0xFFD1E9DA)
    val AlertTile = Color(0xFFFCEAEA)
    val AlertBorder = Color(0xFFF4D3D3)
    val RouteTile = Color(0xFFEDEBFA)
    val RouteBorder = Color(0xFFDCD8F3)

    val Green = Color(0xFF2E9E4F)
    val Red = Color(0xFFE0322E)
    val Sun = Color(0xFFFFC12E)
    val Cloud = Color(0xFF3D8FE0)
    val Land = Color(0xFFF1E3C0)
    val MapSea = Color(0xFF7CC0E8)
    val ZoneFill = Color(0xFF8ED36A)
}

@Composable
fun SamudraVaniTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Sv.Blue,
            onPrimary = Color.White,
            background = Sv.PageBg,
            surface = Color.White,
            onSurface = Sv.Navy,
        ),
        content = content,
    )
}
