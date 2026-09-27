package com.samudravani.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.samudravani.app.data.ChatMsg
import com.samudravani.app.data.Forecast
import com.samudravani.app.data.LatLon
import com.samudravani.app.data.Load
import com.samudravani.app.data.PORTS
import com.samudravani.app.data.Plan
import com.samudravani.app.data.Port
import com.samudravani.app.data.SamudraApi
import com.samudravani.app.data.Settings
import com.samudravani.app.i18n.Lang
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * App state: selected port and language, the fishing plan from that port, the 5-day forecast,
 * and an optional port-to-port route. Everything shown comes from the server; when it cannot be
 * reached the screens say so (with a retry) rather than showing substitute values.
 */
class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val settings = Settings(app)
    private val api = SamudraApi { settings.serverCandidates() }

    private val _port = MutableStateFlow(PORTS.firstOrNull { it.name == settings.portName } ?: PORTS.first())
    val port: StateFlow<Port> = _port.asStateFlow()

    private val _lang = MutableStateFlow(settings.lang)
    val lang: StateFlow<Lang> = _lang.asStateFlow()

    private val _serverUrl = MutableStateFlow(settings.serverUrl)
    val serverUrl: StateFlow<String> = _serverUrl.asStateFlow()

    private val _plan = MutableStateFlow<Load<Plan>>(Load.Loading)
    val plan: StateFlow<Load<Plan>> = _plan.asStateFlow()

    private val _forecast = MutableStateFlow<Load<Forecast>>(Load.Loading)
    val forecast: StateFlow<Load<Forecast>> = _forecast.asStateFlow()

    /** Route to another port; null destination means "route to the best fishing zone" (the main plan). */
    private val _routeTo = MutableStateFlow<Port?>(null)
    val routeTo: StateFlow<Port?> = _routeTo.asStateFlow()
    private val _portRoute = MutableStateFlow<Load<Plan>?>(null)
    val portRoute: StateFlow<Load<Plan>?> = _portRoute.asStateFlow()

    private val _chat = MutableStateFlow<List<ChatMsg>>(emptyList())
    val chat: StateFlow<List<ChatMsg>> = _chat.asStateFlow()
    private var nextId = 0L

    private var jobs = listOf<Job>()
    private var routeJob: Job? = null

    init {
        refresh()
    }

    fun setLang(lang: Lang) {
        _lang.value = lang
        settings.lang = lang
    }

    fun selectPort(port: Port) {
        if (port == _port.value) return
        _port.value = port
        settings.portName = port.name
        _routeTo.value = null
        _portRoute.value = null
        refresh()
    }

    fun setServerUrl(url: String) {
        settings.serverUrl = url
        _serverUrl.value = settings.serverUrl
        refresh()
    }

    fun refresh() {
        jobs.forEach { it.cancel() }
        val port = _port.value
        _plan.value = Load.Loading
        _forecast.value = Load.Loading
        jobs = listOf(
            viewModelScope.launch { _plan.value = load { api.plan(port) } },
            viewModelScope.launch { _forecast.value = load { api.forecast(port) } },
        )
        _routeTo.value?.let { routeToPort(it) }
    }

    fun routeToPort(dest: Port?) {
        routeJob?.cancel()
        _routeTo.value = dest
        if (dest == null) {
            _portRoute.value = null
            return
        }
        val port = _port.value
        val goal = LatLon(dest.lat, dest.lon)
        _portRoute.value = Load.Loading
        routeJob = viewModelScope.launch { _portRoute.value = load { api.plan(port, goal) } }
    }

    /** Ask a question; the answer replaces a pending placeholder. */
    fun ask(question: String) {
        val q = question.trim()
        if (q.isEmpty()) return
        val lang = _lang.value.code
        val port = _port.value
        val answerId = nextId + 1
        _chat.value = _chat.value + ChatMsg(nextId, true, q, lang) + ChatMsg(answerId, false, "", lang, pending = true)
        nextId += 2
        viewModelScope.launch {
            val reply = try {
                ChatMsg(answerId, false, api.ask(q, lang, port), lang)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                ChatMsg(answerId, false, "", lang, failed = true)
            }
            _chat.value = _chat.value.map { if (it.id == answerId) reply else it }
        }
    }

    private suspend fun <T> load(call: suspend () -> T): Load<T> = try {
        Load.Ready(call())
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: Exception) {
        Load.Failed(e.message ?: e.javaClass.simpleName)
    }
}
