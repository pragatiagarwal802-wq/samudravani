package com.samudravani.app.ui.common

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
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
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polygon
import org.osmdroid.views.overlay.Polyline
import java.io.File

private fun configureOsm(ctx: Context) {
    val cfg = Configuration.getInstance()
    cfg.userAgentValue = BuildConfig.APPLICATION_ID // OSM tile policy: identify the app
    val base = File(ctx.cacheDir, "osmdroid")
    cfg.osmdroidBasePath = base
    cfg.osmdroidTileCache = File(base, "tiles")
}

/**
 * OpenStreetMap view with the home port, fishing zones (circles sized by score) and routes.
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
    labels: (Int) -> String = { "${it + 1}" },
) {
    val ctx = LocalContext.current
    val map = remember {
        configureOsm(ctx)
        MapView(ctx).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            zoomController.setVisibility(org.osmdroid.views.CustomZoomButtonsController.Visibility.SHOW_AND_FADEOUT)
            minZoomLevel = 5.0
            maxZoomLevel = 16.0
        }
    }
    DisposableEffect(Unit) {
        map.onResume()
        onDispose { map.onPause(); map.onDetach() }
    }
    AndroidView(factory = { map }, modifier = modifier, update = { mv ->
        mv.overlays.clear()
        altRoutes.forEach { r ->
            mv.overlays += Polyline(mv).apply {
                setPoints(r.map { GeoPoint(it.lat, it.lon) })
                outlinePaint.color = android.graphics.Color.GRAY
                outlinePaint.strokeWidth = 6f
            }
        }
        if (route.size > 1) {
            mv.overlays += Polyline(mv).apply {
                setPoints(route.map { GeoPoint(it.lat, it.lon) })
                outlinePaint.color = Sv.Blue.toArgb()
                outlinePaint.strokeWidth = 10f
            }
        }
        zones.forEachIndexed { i, z ->
            mv.overlays += Polygon(mv).apply {
                points = Polygon.pointsAsCircle(GeoPoint(z.lat, z.lon), 2500.0 + 5000.0 * z.score)
                fillPaint.color = Sv.ZoneFill.copy(alpha = 0.55f).toArgb()
                outlinePaint.color = Sv.Green.toArgb()
                outlinePaint.strokeWidth = 3f
                title = labels(i)
            }
        }
        mv.overlays += Marker(mv).apply {
            position = GeoPoint(port.lat, port.lon)
            setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
            title = port.label
        }
        destination?.let { d ->
            mv.overlays += Marker(mv).apply {
                position = GeoPoint(d.lat, d.lon)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
            }
        }
        val pts = buildList {
            add(GeoPoint(port.lat, port.lon))
            zones.forEach { add(GeoPoint(it.lat, it.lon)) }
            route.forEach { add(GeoPoint(it.lat, it.lon)) }
            destination?.let { add(GeoPoint(it.lat, it.lon)) }
        }
        mv.post {
            if (focus != null) {
                mv.controller.setZoom(11.0)
                mv.controller.setCenter(GeoPoint(focus.lat, focus.lon))
            } else if (pts.size > 1 && mv.width > 0) {
                mv.zoomToBoundingBox(BoundingBox.fromGeoPoints(pts).increaseByScale(1.4f), false, 40)
            } else {
                mv.controller.setZoom(10.0)
                mv.controller.setCenter(GeoPoint(port.lat, port.lon))
            }
        }
        mv.invalidate()
    })
}
