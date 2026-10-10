package top.hypixice.poros.ui

import android.app.Application
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import top.hypixice.poros.MicPhase
import top.hypixice.poros.MicService
import top.hypixice.poros.MicState
import top.hypixice.poros.data.HostProfile
import top.hypixice.poros.data.Prefs

class MicViewModel(application: Application) : AndroidViewModel(application) {

    private val prefs = Prefs(application)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    var address by mutableStateOf(prefs.address)
        private set

    var gain by mutableFloatStateOf(prefs.gain)
        private set

    var profiles by mutableStateOf(prefs.profiles())
        private set

    var language by mutableStateOf(prefs.language)
        private set

    var pin by mutableStateOf(prefs.pin)
        private set

    private val _state = MutableStateFlow(MicState(gain = prefs.gain))
    val state: StateFlow<MicState> = _state.asStateFlow()

    private val _level = MutableStateFlow(0f)
    val level: StateFlow<Float> = _level.asStateFlow()

    private val _cameraOn = MutableStateFlow(false)
    val cameraOn: StateFlow<Boolean> = _cameraOn.asStateFlow()

    private var service: MicService? = null
    private var bound = false
    private var collectJob: Job? = null

    fun bind() {
        if (bound) return
        bound = getApplication<Application>().bindService(
            Intent(getApplication(), MicService::class.java),
            connection,
            Context.BIND_AUTO_CREATE
        )
    }

    fun unbind() {
        collectJob?.cancel()
        collectJob = null
        if (bound) {
            runCatching { getApplication<Application>().unbindService(connection) }
            bound = false
        }
        service = null
    }

    fun onAddressChange(value: String) {
        address = value
    }

    fun onPinChange(value: String) {
        pin = value
        prefs.pin = value
    }

    fun selectProfile(profile: HostProfile) {
        address = profile.address
    }

    fun addProfile(name: String, address: String, description: String) {
        val target = address.trim()
        if (target.isEmpty()) return
        val label = name.trim().ifEmpty { target }
        val updated = profiles.filterNot { it.address == target } +
            HostProfile(label, target, description.trim())
        profiles = updated
        prefs.saveProfiles(updated)
    }

    fun updateProfile(
        original: HostProfile,
        name: String,
        address: String,
        description: String
    ) {
        val target = address.trim()
        if (target.isEmpty()) return
        val label = name.trim().ifEmpty { target }
        val edited = HostProfile(label, target, description.trim())
        val updated = profiles
            .map { if (it.address == original.address) edited else it }
            .distinctBy { it.address }
        profiles = updated
        prefs.saveProfiles(updated)
        // Keep the selection on the host that was just edited.
        if (this.address.trim() == original.address) {
            this.address = target
        }
    }

    fun deleteProfile(profile: HostProfile) {
        val updated = profiles.filterNot { it.address == profile.address }
        profiles = updated
        prefs.saveProfiles(updated)
    }

    fun onGainChange(value: Float) {
        gain = value
        prefs.gain = value
        service?.setGainFromUi(value)
    }

    fun selectLanguage(code: String) {
        language = code
        prefs.language = code
    }

    fun connect() {
        val target = address.trim()
        prefs.address = target
        prefs.pin = pin
        MicService.start(getApplication(), target, gain, pin)
    }

    fun disconnect() {
        MicService.stop(getApplication())
    }

    fun toggleMute() {
        service?.toggleMuteFromUi()
    }

    /** Camera is hosted by the running service; nothing to toggle before that. */
    fun toggleCamera() {
        service?.setCameraFromUi(!_cameraOn.value)
    }

    override fun onCleared() {
        unbind()
        scope.cancel()
        super.onCleared()
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            val svc = (binder as? MicService.LocalBinder)?.service() ?: return
            service = svc
            collectJob?.cancel()
            collectJob = scope.launch {
                launch { svc.state.collect { _state.value = it } }
                launch { svc.level.collect { _level.value = it } }
                launch { svc.cameraOn.collect { _cameraOn.value = it } }
            }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            service = null
            _cameraOn.value = false
            _state.value = MicState(phase = MicPhase.IDLE, gain = gain)
        }
    }
}
