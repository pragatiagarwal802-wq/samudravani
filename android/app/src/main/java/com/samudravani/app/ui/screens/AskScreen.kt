package com.samudravani.app.ui.screens

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.samudravani.app.data.ChatMsg
import com.samudravani.app.i18n.LocalLang
import com.samudravani.app.i18n.LocalStrings
import com.samudravani.app.ui.common.Chevron
import com.samudravani.app.ui.common.MicIcon
import com.samudravani.app.ui.common.Speaker
import com.samudravani.app.ui.theme.Sv

/**
 * Voice / text chat. Speech is recognised by the phone's speech service in the current app
 * language; answers come from the server (live data) and are read aloud when enabled.
 * [autoListen] starts the microphone as soon as the screen opens (from the home "Ask" bar).
 */
@Composable
fun AskScreen(chat: List<ChatMsg>, onAsk: (String) -> Unit, onBack: () -> Unit, autoListen: Boolean = false) {
    val s = LocalStrings.current
    val lang = LocalLang.current
    val context = LocalContext.current
    val preview = LocalInspectionMode.current
    var input by rememberSaveable { mutableStateOf("") }
    var notice by remember { mutableStateOf<String?>(null) }
    var speakAloud by rememberSaveable { mutableStateOf(true) }
    val speaker = remember { if (preview) null else runCatching { Speaker(context) }.getOrNull() }
    DisposableEffect(Unit) { onDispose { speaker?.shutdown() } }

    val recognizer = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val text = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (result.resultCode == Activity.RESULT_OK && !text.isNullOrBlank()) onAsk(text)
    }
    fun listen() {
        speaker?.stop()
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang.locale.toLanguageTag())
            .putExtra(RecognizerIntent.EXTRA_PROMPT, s.askListening)
        try {
            recognizer.launch(intent)
        } catch (e: ActivityNotFoundException) {
            notice = s.voiceUnavailable
        }
    }
    fun send(text: String) {
        if (text.isBlank()) return
        onAsk(text)
        input = ""
    }

    var listenedOnOpen by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(autoListen) {
        if (autoListen && !listenedOnOpen && !preview) {
            listenedOnOpen = true
            listen()
        }
    }

    // Read each new answer aloud once.
    var spokenId by rememberSaveable { mutableStateOf(chat.lastOrNull { !it.fromUser && !it.pending }?.id ?: -1L) }
    val latest = chat.lastOrNull()
    LaunchedEffect(latest?.id, latest?.pending) {
        if (latest != null && !latest.fromUser && !latest.pending && latest.id != spokenId) {
            spokenId = latest.id
            val text = if (latest.failed) s.serverUnavailable else latest.text
            if (speakAloud && speaker != null && !speaker.speak(text, lang.locale)) notice = s.ttsUnavailable
        }
    }

    val list = rememberLazyListState()
    LaunchedEffect(chat.size) { if (chat.isNotEmpty()) list.animateScrollToItem(chat.size) }

    Column(Modifier.fillMaxSize().background(Sv.PageBg).imePadding()) {
        Row(
            Modifier.fillMaxWidth().background(Sv.WeatherTile).statusBarsPadding().padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(44.dp).clip(CircleShape).clickable(onClick = onBack), contentAlignment = Alignment.Center) {
                Chevron(Modifier.size(22.dp).rotate(180f), color = Sv.Navy)
            }
            Text(s.ask, fontSize = 19.sp, color = Sv.Navy, modifier = Modifier.weight(1f),
                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
            Text(s.speakAnswers, fontSize = 11.sp, color = Sv.Body, modifier = Modifier.widthIn(max = 110.dp))
            Switch(
                checked = speakAloud,
                onCheckedChange = { speakAloud = it; if (!it) speaker?.stop() },
                colors = SwitchDefaults.colors(checkedTrackColor = Sv.Blue),
                modifier = Modifier.padding(start = 6.dp),
            )
        }

        LazyColumn(
            state = list,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item { Bubble(s.askIntro, fromUser = false) }
            items(chat, key = { it.id }) { m ->
                when {
                    m.pending -> Bubble(s.askThinking, fromUser = false, muted = true)
                    m.failed -> Bubble(s.serverUnavailable, fromUser = false, muted = true)
                    else -> Bubble(m.text, m.fromUser)
                }
            }
        }

        notice?.let {
            Text(it, fontSize = 12.sp, color = Color(0xFF8A1F1F),
                modifier = Modifier.fillMaxWidth().background(Sv.AlertTile).padding(horizontal = 16.dp, vertical = 6.dp)
                    .clickable { notice = null })
        }
        Row(
            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            s.askSuggestions.forEach { q ->
                Box(
                    Modifier.clip(CircleShape).background(Color.White).clickable { send(q) }
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                ) { Text(q, fontSize = 13.sp, color = Sv.Navy) }
            }
        }
        Row(
            Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = input, onValueChange = { input = it },
                placeholder = { Text(s.askHint, fontSize = 14.sp) },
                singleLine = true,
                shape = RoundedCornerShape(24.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { send(input) }),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Sv.Blue),
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.size(8.dp))
            val typing = input.isNotBlank()
            Box(
                Modifier.size(52.dp).clip(CircleShape).background(Sv.Blue)
                    .clickable { if (typing) send(input) else listen() },
                contentAlignment = Alignment.Center,
            ) {
                if (typing) Chevron(Modifier.size(24.dp), color = Color.White)
                else MicIcon(Modifier.size(width = 20.dp, height = 26.dp))
            }
        }
    }
}

@Composable
private fun Bubble(text: String, fromUser: Boolean, muted: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (fromUser) Arrangement.End else Arrangement.Start) {
        Box(
            Modifier
                .widthIn(max = 300.dp)
                .clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp,
                    bottomStart = if (fromUser) 16.dp else 4.dp, bottomEnd = if (fromUser) 4.dp else 16.dp))
                .background(if (fromUser) Sv.Blue else Color.White)
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(text, fontSize = 15.sp, lineHeight = 21.sp,
                color = when { fromUser -> Color.White; muted -> Sv.Body; else -> Sv.Navy })
        }
    }
}
