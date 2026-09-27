package com.samudravani.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.Load
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Port
import com.samudravani.app.i18n.LANG_LABELS
import com.samudravani.app.i18n.Lang
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.Card
import com.samudravani.app.ui.common.Pill
import com.samudravani.app.ui.common.ScreenScaffold
import com.samudravani.app.ui.common.SectionTitle
import com.samudravani.app.ui.common.verdictColor
import com.samudravani.app.ui.theme.Sv

@Composable
fun ProfileScreen(
    port: Port,
    serverUrl: String,
    plan: Load<Plan>,
    onLang: (Lang) -> Unit,
    onPort: (Port) -> Unit,
    onServerUrl: (String) -> Unit,
) {
    val s = LocalStrings.current
    val lang = LocalLang.current
    ScreenScaffold(s.navProfile, onBack = null) {
        SectionTitle(s.language)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LANG_LABELS.forEach { (l, label) -> Choice(label, lang == l) { onLang(l) } }
        }
        SectionTitle(s.homePort)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PORTS.forEach { p -> Choice(p.localName(lang.code), p == port) { onPort(p) } }
        }
        SectionTitle(s.server)
        var url by remember(serverUrl) { mutableStateOf(serverUrl) }
        OutlinedTextField(
            value = url, onValueChange = { url = it }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            modifier = Modifier.fillMaxWidth(),
        )
        Text(s.serverHint, fontSize = 12.sp, color = Sv.Body)
        Pill(s.save, Sv.Blue, onClick = { onServerUrl(url) })

        if (plan is Load.Ready && plan.value.dataStatus.isNotEmpty()) {
            SectionTitle(s.dataStatus)
            Card {
                plan.value.dataStatus.forEach { (provider, status) ->
                    Row {
                        Text(provider, fontSize = 14.sp, color = Sv.Navy, modifier = Modifier.weight(1f))
                        Text(status, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                            color = if (status == "OK") verdictColor("SAFE") else verdictColor(null))
                    }
                }
            }
        }
        Text(s.about, fontSize = 12.sp, color = Sv.Body, modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun Choice(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .clip(CircleShape)
            .background(if (selected) Sv.Blue else Color.White)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    ) { Text(label, fontSize = 14.sp, color = if (selected) Color.White else Sv.Navy, fontWeight = FontWeight.SemiBold) }
}
