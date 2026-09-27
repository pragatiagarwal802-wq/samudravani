package com.samudravani.app.ui.common

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.samudravani.app.BuildConfig
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.Port
import com.samudravani.app.data.Zone
import com.samudravani.app.ui.theme.Sv
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.CopyrightOverlay
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polygon
import org.osmdroid.views.overlay.Polyline
import org.osmdroid.views.overlay.ScaleBarOverlay
import java.io.File

enum class MapStyle { STREET, SATELLITE }

/** False in screenshot tests (no network / tile cache there): maps render as the stylised thumbnail. */
val LocalLiveMaps = staticCompositionLocalOf { true }

/** Esri World Imagery (satellite). Tile URLs are z/y/x. Attribution is shown on the map. */
private object EsriImagery : OnlineTileSourceBase(
    "EsriWorldImagery", 0, 18, 256, "",
    arrayOf("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/"),
    "Imagery © Esri, Maxar, Earthstar Geographics",
) {
    override fun getTileURLString(index: Long): String =
        baseUrl + MapTileIndex.getZoom(index) + "/" + MapTileIndex.getY(index) + "/" + MapTileIndex.getX(index)
}

private fun configureOsm(ctx: Context) {
    val cfg = Configuration.getInstance()
    cfg.userAgentValue = BuildConfig.APPLICATION_ID // OSM tile policy: identify the app
    val base = File(ctx.cacheDir, "osmdroid")
    cfg.osmdroidBasePath = base
    cfg.osmdroidTileCache = File(base, "tiles")
}

// --- marker icons (drawn, so they stay crisp and need no image assets) -------------------------

private fun bitmap(ctx: Context, sizeDp: Float, draw: Canvas.(px: Float) -> Unit): Drawable {
    val px = sizeDp * ctx.resources.displayMetrics.density
    val bmp = Bitmap.createBitmap(px.toInt(), px.toInt(), Bitmap.Config.ARGB_8888)
    Canvas(bmp).draw(px)
    return BitmapDrawable(ctx.resources, bmp)
}

private fun zoneIcon(ctx: Context, label: String, best: Boolean): Drawable = bitmap(ctx, if (best) 34f else 28f) { px ->
    val r = px / 2f
    val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (best) 0xFF1A7F37.toInt() else 0xFF2E9E4F.toInt() }
    val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE; style = Paint.Style.STROKE; strokeWidth = px * 0.09f }
    drawCircle(r, r, r * 0.9f, fill)
    drawCircle(r, r, r * 0.86f, ring)
    val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.WHITE; textSize = px * 0.46f; typeface = Typeface.DEFAULT_BOLD; textAlign = Paint.Align.CENTER
    }
    drawText(label, r, r - (text.descent() + text.ascent()) / 2f, text)
}

private fun portIcon(ctx: Context): Drawable = bitmap(ctx, 36f) { px ->
    val cx = px / 2f
    val head = px * 0.36f
    val blue = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Sv.Blue.toArgb() }
    val path = android.graphics.Path().apply {
        moveTo(cx, px * 0.98f)
        cubicTo(cx - head * 0.4f, px * 0.75f, cx - head, px * 0.62f, cx - head, head + px * 0.02f)
        arcTo(cx - head, px * 0.02f, cx + head, px * 0.02f + 2 * head, 180f, 180f, false)
        cubicTo(cx + head, px * 0.62f, cx + head * 0.4f, px * 0.75f, cx, px * 0.98f)
        close()
    }
    drawPath(path, blue)
    drawPath(path, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE; style = Paint.Style.STROKE; strokeWidth = px * 0.05f })
    drawCircle(cx, head + px * 0.02f, head * 0.42f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE })
}

private fun flagIcon(ctx: Context): Drawable = bitmap(ctx, 30f) { px ->
    val pole = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Sv.Navy.toArgb(); strokeWidth = px * 0.08f }
    drawLine(px * 0.25f, px * 0.1f, px * 0.25f, px * 0.95f, pole)
    val flag = android.graphics.Path().apply { moveTo(px * 0.27f, px * 0.1f); lineTo(px * 0.9f, px * 0.28f); lineTo(px * 0.27f, px * 0.46f); close() }
    drawPath(flag, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Sv.Red.toArgb() })
}

/**
 * Map with the home port, fishing zones (numbered; the best one highlighted and its area shaded)
 * and routes. [interactive] = false gives a static preview (home card): no gestures, no controls.
 * [focus] centres the map on one point; otherwise it fits everything shown.
 */
@Composable
fun SeaMap(
    port: Port,
    zones: List<Zone>,
    route: List<LatLon>,
    modifier: Modifier = Modifier,
    altRoutes: List<List<LatLon>> = emptyList(),
    destination: LatLon? = null,
    focus: LatLon? = null,
    best: Zone? = null,
    style: MapStyle = MapStyle.STREET,
    interactive: Boolean = true,
    labels: (Int) -> String = { "${it + 1}" },
) {
    if (!LocalLiveMaps.current) {
        MapThumbnail(modifier)
        return
    }
    val ctx = LocalContext.current
    val map = remember {
        configureOsm(ctx)
        MapView(ctx).apply {
            setMultiTouchControls(interactive)
            isClickable = interactive
            zoomController.setVisibility(
                if (interactive) CustomZoomButtonsController.Visibility.SHOW_AND_FADEOUT
                else CustomZoomButtonsController.Visibility.NEVER,
            )
            minZoomLevel = 5.0
            maxZoomLevel = 17.0
            isTilesScaledToDpi = true
            if (!interactive) setOnTouchListener { _, _ -> true } // static preview: ignore gestures
        }
    }
    DisposableEffect(Unit) {
        map.onResume()
        onDispose { map.onPause(); map.onDetach() }
    }
    val icons = remember { Triple(portIcon(ctx), flagIcon(ctx), mutableMapOf<String, Drawable>()) }
    Box(modifier) {
        AndroidView(factory = { map }, modifier = Modifier.fillMaxSize(), update = { mv ->
            mv.setTileSource(if (style == MapStyle.SATELLITE) EsriImagery else TileSourceFactory.MAPNIK)
            mv.overlays.clear()
            fun line(points: List<LatLon>, color: Int, width: Float) = Polyline(mv).apply {
                setPoints(points.map { GeoPoint(it.lat, it.lon) })
                outlinePaint.color = color
                outlinePaint.strokeWidth = width
                outlinePaint.strokeCap = Paint.Cap.ROUND
                infoWindow = null
            }
            altRoutes.filter { it.size > 1 }.forEach { r ->
                mv.overlays += line(r, 0x99FFFFFF.toInt(), 9f)
                mv.overlays += line(r, 0xFF8C959F.toInt(), 5f)
            }
            if (route.size > 1) {
                mv.overlays += line(route, android.graphics.Color.WHITE, 14f) // casing keeps the line visible on imagery
                mv.overlays += line(route, Sv.Blue.toArgb(), 8f)
            }
            best?.let { z ->
                mv.overlays += Polygon(mv).apply {
                    points = Polygon.pointsAsCircle(GeoPoint(z.lat, z.lon), 5000.0)
                    fillPaint.color = Sv.ZoneFill.copy(alpha = 0.35f).toArgb()
                    outlinePaint.color = Sv.Green.toArgb()
                    outlinePaint.strokeWidth = 3f
                    infoWindow = null
                }
            }
            zones.forEachIndexed { i, z ->
                val isBest = z == best
                mv.overlays += Marker(mv).apply {
                    position = GeoPoint(z.lat, z.lon)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                    icon = icons.third.getOrPut("${i + 1}-$isBest") { zoneIcon(ctx, "${i + 1}", isBest) }
                    title = labels(i)
                    if (!interactive) infoWindow = null
                }
            }
            destination?.takeIf { d -> zones.none { it.lat == d.lat && it.lon == d.lon } }?.let { d ->
                mv.overlays += Marker(mv).apply {
                    position = GeoPoint(d.lat, d.lon)
                    setAnchor(0.25f, Marker.ANCHOR_BOTTOM)
                    icon = icons.second
                    infoWindow = null
                }
            }
            mv.overlays += Marker(mv).apply {
                position = GeoPoint(port.lat, port.lon)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                icon = icons.first
                title = port.label
                if (!interactive) infoWindow = null
            }
            if (interactive) {
                mv.overlays += ScaleBarOverlay(mv).apply { setAlignBottom(true); setCentred(true); setScaleBarOffset(mv.width / 2, 12) }
            }
            mv.overlays += CopyrightOverlay(ctx).apply { setTextSize(if (interactive) 9 else 7) }

            val pts = buildList {
                add(GeoPoint(port.lat, port.lon))
                zones.forEach { add(GeoPoint(it.lat, it.lon)) }
                route.forEach { add(GeoPoint(it.lat, it.lon)) }
                destination?.let { add(GeoPoint(it.lat, it.lon)) }
            }
            mv.post {
                when {
                    focus != null -> {
                        mv.controller.setZoom(11.5)
                        mv.controller.setCenter(GeoPoint(focus.lat, focus.lon))
                    }
                    pts.size > 1 && mv.width > 0 ->
                        mv.zoomToBoundingBox(BoundingBox.fromGeoPoints(pts).increaseByScale(1.35f), false, if (interactive) 48 else 16)
                    else -> {
                        mv.controller.setZoom(10.0)
                        mv.controller.setCenter(GeoPoint(port.lat, port.lon))
                    }
                }
            }
            mv.invalidate()
        })
    }
}

