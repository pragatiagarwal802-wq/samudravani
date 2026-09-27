package com.samudravani.app.ui.common

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.withTransform
import com.samudravani.app.ui.theme.Sv

/*
 * Illustrations and icons for the home screen, drawn in code so they stay sharp at every
 * density. Each one is authored in a fixed design box (e.g. 100 x 100) and scaled to fit.
 */

private inline fun DrawScope.designBox(w: Float, h: Float, block: DrawScope.() -> Unit) {
    val s = minOf(size.width / w, size.height / h)
    withTransform({
        translate((size.width - w * s) / 2f, (size.height - h * s) / 2f)
        scale(s, s, Offset.Zero)
    }) { block() }
}

private fun path(block: Path.() -> Unit) = Path().apply(block)

// --- tile icons -------------------------------------------------------------------

@Composable
fun WeatherIcon(modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(100f, 80f) {
        val sun = Offset(62f, 30f)
        for (i in 0 until 8) {
            val a = Math.toRadians(i * 45.0 - 90)
            val c = kotlin.math.cos(a).toFloat()
            val s = kotlin.math.sin(a).toFloat()
            drawLine(Sv.Sun, Offset(sun.x + c * 22f, sun.y + s * 22f), Offset(sun.x + c * 30f, sun.y + s * 30f),
                strokeWidth = 5f, cap = StrokeCap.Round)
        }
        drawCircle(Sv.Sun, 16f, sun)
        val cloud = Brush.verticalGradient(listOf(Color(0xFF5AA7EE), Sv.Cloud), startY = 30f, endY = 76f)
        drawCircle(cloud, 17f, Offset(30f, 52f))
        drawCircle(cloud, 21f, Offset(50f, 44f))
        drawCircle(cloud, 14f, Offset(68f, 56f))
        drawRoundRect(cloud, Offset(14f, 52f), Size(68f, 22f), CornerRadius(11f))
    }
}

@Composable
fun FishIcon(modifier: Modifier = Modifier, color: Color = Sv.Blue) = Canvas(modifier) {
    designBox(100f, 60f) {
        drawPath(path { // tail
            moveTo(30f, 30f); lineTo(4f, 10f); quadraticTo(12f, 30f, 4f, 50f); close()
        }, color)
        drawPath(path { // top fin
            moveTo(45f, 14f); quadraticTo(56f, 0f, 70f, 8f); lineTo(64f, 16f); close()
        }, color)
        drawPath(path { // body
            moveTo(24f, 30f)
            cubicTo(40f, 6f, 78f, 4f, 96f, 30f)
            cubicTo(78f, 56f, 40f, 54f, 24f, 30f)
            close()
        }, color)
        drawCircle(Color.White, 5.5f, Offset(76f, 25f))
        drawCircle(Sv.Navy, 2.8f, Offset(77f, 25f))
    }
}

@Composable
fun WarningIcon(modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(100f, 90f) {
        val tri = path {
            moveTo(44f, 6f); quadraticTo(50f, -2f, 56f, 6f)
            lineTo(97f, 76f); quadraticTo(101f, 86f, 90f, 86f)
            lineTo(10f, 86f); quadraticTo(-1f, 86f, 3f, 76f); close()
        }
        drawPath(tri, Brush.verticalGradient(listOf(Color(0xFFF0443F), Color(0xFFCC2320))))
        drawRoundRect(Color.White, Offset(45f, 26f), Size(10f, 34f), CornerRadius(5f))
        drawCircle(Color.White, 6f, Offset(50f, 72f))
    }
}

@Composable
fun RouteIcon(modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(100f, 70f) {
        val navy = Color(0xFF1B3C84)
        drawPath(path {
            moveTo(20f, 52f); cubicTo(40f, 66f, 60f, 60f, 80f, 44f)
        }, navy, style = Stroke(3.5f, cap = StrokeCap.Round, pathEffect = PathEffect.dashPathEffect(floatArrayOf(7f, 6f))))
        pin(Offset(20f, 44f), 13f, navy)
        pin(Offset(80f, 26f), 13f, navy)
    }
}

private fun DrawScope.pin(tip: Offset, r: Float, color: Color) {
    // teardrop: circle of radius r whose bottom tapers to `tip`
    val c = Offset(tip.x, tip.y - r * 1.9f)
    drawPath(path {
        moveTo(tip.x, tip.y)
        cubicTo(tip.x - r * 0.4f, tip.y - r * 0.6f, c.x - r, c.y + r * 0.6f, c.x - r, c.y)
        arcTo(androidx.compose.ui.geometry.Rect(c.x - r, c.y - r, c.x + r, c.y + r), 180f, 180f, false)
        cubicTo(c.x + r, c.y + r * 0.6f, tip.x + r * 0.4f, tip.y - r * 0.6f, tip.x, tip.y)
        close()
    }, color)
    drawCircle(Color.White, r * 0.42f, c)
}

@Composable
fun PinIcon(modifier: Modifier = Modifier, color: Color = Sv.Blue) = Canvas(modifier) {
    designBox(40f, 44f) { pin(Offset(20f, 42f), 13f, color) }
}

// --- small UI glyphs ----------------------------------------------------------------

@Composable
fun Chevron(modifier: Modifier = Modifier, color: Color = Sv.Navy, down: Boolean = false) = Canvas(modifier) {
    designBox(24f, 24f) {
        val p = if (down) path { moveTo(6f, 9f); lineTo(12f, 15f); lineTo(18f, 9f) }
        else path { moveTo(9f, 5f); lineTo(16f, 12f); lineTo(9f, 19f) }
        drawPath(p, color, style = Stroke(2.4f, cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

@Composable
fun MicIcon(modifier: Modifier = Modifier, color: Color = Color.White) = Canvas(modifier) {
    designBox(40f, 48f) {
        val st = Stroke(3.6f, cap = StrokeCap.Round)
        drawRoundRect(color, Offset(12f, 2f), Size(16f, 28f), CornerRadius(8f))
        drawPath(path { moveTo(5f, 22f); cubicTo(5f, 42f, 35f, 42f, 35f, 22f) }, color, style = st)
        drawLine(color, Offset(20f, 38f), Offset(20f, 46f), 3.6f, StrokeCap.Round)
        drawLine(color, Offset(12f, 46f), Offset(28f, 46f), 3.6f, StrokeCap.Round)
    }
}

/** Arrow pointing up (north); rotate it to show a direction. */
@Composable
fun UpArrow(modifier: Modifier = Modifier, color: Color = Sv.Blue) = Canvas(modifier) {
    designBox(24f, 24f) {
        drawLine(color, Offset(12f, 21f), Offset(12f, 5f), 2.6f, StrokeCap.Round)
        drawPath(path { moveTo(12f, 2f); lineTo(18.5f, 10f); lineTo(5.5f, 10f); close() }, color)
    }
}

enum class NavGlyph { HOME, MAP, BELL, PERSON }

@Composable
fun NavIcon(glyph: NavGlyph, color: Color, modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(24f, 24f) {
        val st = Stroke(1.8f, cap = StrokeCap.Round, join = StrokeJoin.Round)
        when (glyph) {
            NavGlyph.HOME -> {
                drawPath(path {
                    moveTo(3f, 11f); lineTo(12f, 3f); lineTo(21f, 11f); lineTo(19f, 11f); lineTo(19f, 21f)
                    lineTo(14.5f, 21f); lineTo(14.5f, 15f); lineTo(9.5f, 15f); lineTo(9.5f, 21f); lineTo(5f, 21f)
                    lineTo(5f, 11f); close()
                }, color)
            }
            NavGlyph.MAP -> {
                drawPath(path {
                    moveTo(3f, 5.5f); lineTo(9f, 3.5f); lineTo(15f, 5.5f); lineTo(21f, 3.5f); lineTo(21f, 18.5f)
                    lineTo(15f, 20.5f); lineTo(9f, 18.5f); lineTo(3f, 20.5f); close()
                    moveTo(9f, 3.5f); lineTo(9f, 18.5f); moveTo(15f, 5.5f); lineTo(15f, 20.5f)
                }, color, style = st)
            }
            NavGlyph.BELL -> {
                drawPath(path {
                    moveTo(6f, 17f); lineTo(6f, 11f); cubicTo(6f, 7f, 8.5f, 4.5f, 12f, 4.5f)
                    cubicTo(15.5f, 4.5f, 18f, 7f, 18f, 11f); lineTo(18f, 17f); lineTo(20f, 19f); lineTo(4f, 19f); close()
                    moveTo(10f, 21.5f); lineTo(14f, 21.5f); moveTo(12f, 2.5f); lineTo(12f, 4.5f)
                }, color, style = st)
            }
            NavGlyph.PERSON -> {
                drawCircle(color, 4.2f, Offset(12f, 8f), style = st)
                drawPath(path { moveTo(4f, 21f); cubicTo(4f, 15.5f, 8f, 13.8f, 12f, 13.8f); cubicTo(16f, 13.8f, 20f, 15.5f, 20f, 21f); close() },
                    color, style = st)
            }
        }
    }
}

// --- hero ---------------------------------------------------------------------------

@Composable
fun FishingBoat(modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(200f, 160f) {
        val rope = Color(0xFF55606E)
        val thin = 1.1f
        // wake / reflection
        drawOval(Color.White.copy(alpha = 0.55f), Offset(14f, 136f), Size(178f, 10f))
        drawOval(Color(0xFF3E7FB8).copy(alpha = 0.25f), Offset(30f, 142f), Size(150f, 8f))
        // masts and rigging (behind the cabin)
        drawLine(Color(0xFF2B2F36), Offset(118f, 14f), Offset(118f, 104f), 2.6f)
        drawLine(Color(0xFF2B2F36), Offset(62f, 52f), Offset(62f, 108f), 2f)
        drawLine(Color(0xFF2B2F36), Offset(104f, 34f), Offset(132f, 34f), 1.8f)
        listOf(Offset(22f, 110f), Offset(40f, 110f), Offset(62f, 56f), Offset(186f, 100f), Offset(168f, 104f), Offset(150f, 104f))
            .forEach { drawLine(rope, Offset(118f, 16f), it, thin) }
        drawLine(rope, Offset(62f, 54f), Offset(22f, 110f), thin)
        drawLine(rope, Offset(62f, 54f), Offset(96f, 106f), thin)
        drawPath(path { moveTo(118f, 14f); lineTo(118f, 4f); lineTo(130f, 8f); lineTo(118f, 11f) }, Sv.Red)
        // cabin
        drawRect(Color(0xFFF7F9FC), Offset(96f, 76f), Size(52f, 32f))
        drawRect(Color(0xFF2E5E99), Offset(92f, 70f), Size(60f, 7f))
        drawRect(Color(0xFFF7F9FC), Offset(108f, 58f), Size(28f, 13f))
        drawRect(Color(0xFF2E5E99), Offset(105f, 54f), Size(34f, 5f))
        for (i in 0 until 4) drawRect(Color(0xFF3A6EA8), Offset(100f + i * 12f, 82f), Size(8f, 8f))
        drawRect(Color(0xFF3A6EA8), Offset(112f, 61f), Size(7f, 6f))
        drawRect(Color(0xFF3A6EA8), Offset(124f, 61f), Size(7f, 6f))
        // hull: blue topsides, white sheer line, red bottom band
        val hull = path {
            moveTo(10f, 104f); lineTo(192f, 96f); lineTo(176f, 140f); quadraticTo(110f, 146f, 36f, 142f); close()
        }
        drawPath(hull, Brush.verticalGradient(listOf(Color(0xFF2F6DB3), Color(0xFF1E4F8C)), startY = 96f, endY = 142f))
        clipPath(hull) {
            drawRect(Color(0xFFC9432F), Offset(0f, 128f), Size(200f, 20f))
            drawRect(Color.White, Offset(0f, 124f), Size(200f, 4f))
        }
        drawLine(Color.White, Offset(10f, 104f), Offset(192f, 96f), 3f)
        for (i in 0 until 9) drawLine(Color.White.copy(alpha = 0.8f), Offset(24f + i * 18f, 106f - i * 0.8f), Offset(24f + i * 18f, 96f - i * 0.8f), 1.2f)
        drawLine(Color.White, Offset(20f, 97f - 0f), Offset(186f, 90f), 1.4f)
    }
}

@Composable
fun Birds(modifier: Modifier = Modifier) = Canvas(modifier) {
    designBox(120f, 50f) {
        val st = Stroke(2.2f, cap = StrokeCap.Round, join = StrokeJoin.Round)
        val c = Color(0xFF2F3B4C)
        fun bird(x: Float, y: Float, s: Float) = drawPath(path {
            moveTo(x - 8f * s, y - 2f * s); quadraticTo(x - 4f * s, y - 5f * s, x, y)
            quadraticTo(x + 4f * s, y - 5f * s, x + 8f * s, y - 2f * s)
        }, c, style = st)
        bird(12f, 32f, 1f)
        bird(28f, 40f, 0.8f)
        bird(104f, 10f, 1.1f)
    }
}

/** Stylised coastline with a highlighted fishing zone, as in the mockup's summary card. */
@Composable
fun MapThumbnail(modifier: Modifier = Modifier) = Canvas(modifier) {
    val w = size.width
    val h = size.height
    drawRect(Brush.linearGradient(listOf(Color(0xFF9ED3F2), Sv.MapSea), Offset(0f, 0f), Offset(w, h)))
    // land on the left with a ragged coast
    drawPath(path {
        moveTo(0f, 0f); lineTo(w * 0.36f, 0f)
        cubicTo(w * 0.30f, h * 0.18f, w * 0.26f, h * 0.30f, w * 0.20f, h * 0.44f)
        cubicTo(w * 0.15f, h * 0.60f, w * 0.14f, h * 0.78f, w * 0.06f, h); lineTo(0f, h); close()
    }, Sv.Land)
    drawPath(path { // coast shading
        moveTo(w * 0.36f, 0f)
        cubicTo(w * 0.30f, h * 0.18f, w * 0.26f, h * 0.30f, w * 0.20f, h * 0.44f)
        cubicTo(w * 0.15f, h * 0.60f, w * 0.14f, h * 0.78f, w * 0.06f, h)
    }, Color(0xFFD9C79C), style = Stroke(2f))
    listOf(0.2f to 0.1f, 0.1f to 0.35f, 0.05f to 0.62f).forEach { (x, y) ->
        drawLine(Color(0xFFE7B96C), Offset(w * x, h * y), Offset(w * (x + 0.12f), h * (y + 0.1f)), 1.5f)
    }
    // fishing zone
    val zone = path {
        moveTo(w * 0.38f, h * 0.62f)
        cubicTo(w * 0.40f, h * 0.36f, w * 0.60f, h * 0.18f, w * 0.80f, h * 0.10f)
        cubicTo(w * 0.86f, h * 0.30f, w * 0.72f, h * 0.62f, w * 0.60f, h * 0.76f)
        cubicTo(w * 0.52f, h * 0.84f, w * 0.40f, h * 0.84f, w * 0.38f, h * 0.62f)
        close()
    }
    drawPath(zone, Sv.ZoneFill.copy(alpha = 0.9f))
    drawPath(zone, Color(0xFF3B8A2E), style = Stroke(2f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 4f))))
    // route: port -> zone -> boat
    val port = Offset(w * 0.20f, h * 0.36f)
    drawPath(path {
        moveTo(port.x, port.y); lineTo(w * 0.50f, h * 0.44f); lineTo(w * 0.70f, h * 0.70f)
    }, Color.White, style = Stroke(2f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(5f, 4f))))
    drawCircle(Color.White, 5f, port)
    drawCircle(Color(0xFF1B3C84), 3.4f, port)
    // fish in the zone
    withTransform({ translate(w * 0.47f, h * 0.36f); scale(h / 150f, h / 150f, Offset.Zero) }) {
        drawPath(path { moveTo(20f, 20f); lineTo(0f, 6f); lineTo(0f, 34f); close() }, Color(0xFF1F5A3A))
        drawOval(Color(0xFF1F5A3A), Offset(14f, 4f), Size(46f, 32f))
        drawCircle(Color.White, 3.2f, Offset(48f, 16f))
    }
    // small boat
    withTransform({ translate(w * 0.67f, h * 0.68f); scale(h / 170f, h / 170f, Offset.Zero) }) {
        drawRect(Color.White, Offset(10f, 0f), Size(18f, 14f))
        drawRect(Color(0xFF1B3C84), Offset(14f, 4f), Size(10f, 5f))
        drawPath(path { moveTo(0f, 14f); lineTo(38f, 14f); lineTo(32f, 26f); lineTo(6f, 26f); close() }, Color(0xFF1B3C84))
        drawLine(Color(0xFF1B3C84), Offset(19f, 0f), Offset(19f, -10f), 2.5f)
    }
}
