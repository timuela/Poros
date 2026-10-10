package top.hypixice.poros

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.pedro.encoder.input.video.CameraHelper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject
import top.hypixice.poros.data.LocaleHelper
import top.hypixice.poros.signaling.SignalingClient
import top.hypixice.poros.video.CameraStreamer
import top.hypixice.poros.video.getSupportedResolutions
import top.hypixice.poros.webrtc.WebRtcClient

enum class MicPhase { IDLE, CONNECTING, STREAMING, ERROR }

data class MicState(
    val phase: MicPhase = MicPhase.IDLE,
    val muted: Boolean = false,
    val gain: Float = 1f,
    val error: String? = null
)

/**
 * One foreground service owns the whole session: the microphone (WebRTC) and,
 * when the user turns it on, the camera (RTSP). Running both here is what lets
 * the camera keep streaming once the app is backgrounded or the screen is off -
 * there is no activity or preview surface holding it up.
 */
class MicService : Service(), SignalingClient.Listener, WebRtcClient.Listener {

    private val binder = LocalBinder()
    private val _state = MutableStateFlow(MicState())
    val state: StateFlow<MicState> = _state.asStateFlow()

    private val _level = MutableStateFlow(0f)
    val level: StateFlow<Float> = _level.asStateFlow()

    private val _cameraOn = MutableStateFlow(false)
    val cameraOn: StateFlow<Boolean> = _cameraOn.asStateFlow()

    private var signaling: SignalingClient? = null
    private var webRtc: WebRtcClient? = null
    private var camera: CameraStreamer? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    private var cameraResolutions: List<Pair<Int, Int>> = emptyList()

    @Volatile private var muted = false
    @Volatile private var pin = ""
    @Volatile private var cameraEnabled = false
    @Volatile private var cameraStreaming = false

    // A session only exists between beginSession() and teardown(). Callbacks
    // that arrive late (the socket reporting a disconnect, a peer connection
    // reporting "closed") must never resurrect the state of a dead session.
    @Volatile private var active = false
    @Volatile private var desktopOnline = false

    inner class LocalBinder : Binder() {
        fun service(): MicService = this@MicService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                teardown()
                ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }

            ACTION_TOGGLE_MUTE -> {
                if (active) toggleMute()
            }

            ACTION_TOGGLE_CAMERA -> {
                setCameraFromUi(!cameraEnabled)
            }

            else -> {
                val address = intent?.getStringExtra(EXTRA_ADDRESS) ?: ""
                val gain = intent?.getFloatExtra(EXTRA_GAIN, 1f) ?: 1f
                val pin = intent?.getStringExtra(EXTRA_PIN) ?: ""
                updateForeground()
                beginSession(address, gain, pin)
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        teardown()
        super.onDestroy()
    }

    // ------------------------------------------------------------------
    // microphone
    // ------------------------------------------------------------------
    fun setGainFromUi(gain: Float) {
        _state.value = _state.value.copy(gain = gain)
        webRtc?.setGain(gain)
    }

    fun toggleMuteFromUi() {
        if (active) toggleMute()
    }

    private fun toggleMute() {
        muted = !muted
        webRtc?.setMuted(muted)
        _state.value = _state.value.copy(muted = muted)
        notifyState()
    }

    private fun beginSession(address: String, gain: Float, pinCode: String) {
        val parsed = parseAddress(address)
        if (parsed == null) {
            _state.value = MicState(phase = MicPhase.ERROR, gain = gain, error = getString(R.string.error_invalid_address))
            return
        }

        acquireLocks()
        muted = false
        pin = pinCode.trim()
        active = true
        desktopOnline = false
        _state.value = MicState(phase = MicPhase.CONNECTING, gain = gain)

        val (host, port) = parsed
        signaling = SignalingClient(host, port, this).also { it.connect() }
    }

    private fun teardown() {
        active = false
        desktopOnline = false
        signaling?.disconnect()
        signaling = null
        webRtc?.shutdown()
        webRtc = null
        disableCamera()
        releaseLocks()
        muted = false
        _level.value = 0f
        _state.value = MicState(phase = MicPhase.IDLE)
    }

    private fun startWebRtc() {
        webRtc?.shutdown()
        val client = WebRtcClient(applicationContext, this)
        webRtc = client
        // start() queues the track creation first, so gain and mute must be
        // queued after it or they would apply to a track that does not exist.
        client.start()
        client.setGain(_state.value.gain)
        client.setMuted(muted)
    }

    // ------------------------------------------------------------------
    // camera
    // ------------------------------------------------------------------
    fun setCameraFromUi(enabled: Boolean) {
        if (enabled) enableCamera() else disableCamera()
    }

    private fun enableCamera() {
        if (cameraEnabled) return
        cameraEnabled = true
        _cameraOn.value = true

        val streamer = CameraStreamer(applicationContext, cameraListener)
        camera = streamer
        streamer.startPreview()

        if (cameraResolutions.isEmpty()) {
            getSupportedResolutions(applicationContext) { back, front ->
                cameraResolutions = back.ifEmpty { front }
                announceCamera()
            }
        } else {
            announceCamera()
        }

        updateForeground()
        notifyState()
    }

    private fun disableCamera() {
        if (!cameraEnabled) return
        cameraEnabled = false
        _cameraOn.value = false
        camera?.stop()
        camera = null
        cameraStreaming = false
        if (active) {
            signaling?.sendCameraStatus("stopped")
            updateForeground()
            notifyState()
        }
    }

    private fun announceCamera() {
        val streamer = camera ?: return
        val client = signaling ?: return
        if (!active || !client.isConnected()) return

        client.sendCameraDescriptor(
            name = Build.MODEL ?: "Android",
            url = streamer.url(CameraStreamer.localIpAddress()),
            resolutions = cameraResolutions,
            lens = if (streamer.facing == CameraHelper.Facing.BACK) "back" else "front"
        )
    }

    private val cameraListener = object : CameraStreamer.Listener {
        override fun onStreamError(title: String, description: String) {
            if (active) signaling?.sendCameraStatus("error", "$title: $description")
        }

        override fun onStreamingChanged(streaming: Boolean) {
            cameraStreaming = streaming
            if (active) {
                signaling?.sendCameraStatus(if (streaming) "streaming" else "stopped")
            }
        }
    }

    // ------------------------------------------------------------------
    // signalling callbacks
    // ------------------------------------------------------------------
    override fun onSignalingConnected() {
        if (!active) return
        // Our own join makes the server rebroadcast presence, so forget the
        // previous answer and let that decide whether to (re)start WebRTC.
        desktopOnline = false
        signaling?.join(pin)
    }

    override fun onSignalingDisconnected(reason: String?) {
        if (!active) return
        _state.value = _state.value.copy(phase = MicPhase.CONNECTING)
    }

    override fun onPresence(online: Boolean) {
        if (!active) return

        val wasOnline = desktopOnline
        desktopOnline = online

        if (!online) {
            // Host went away. Drop the peer connection so that when it comes
            // back we negotiate a completely fresh session.
            webRtc?.shutdown()
            webRtc = null
            _state.value = _state.value.copy(phase = MicPhase.CONNECTING)
            return
        }

        if (cameraEnabled) announceCamera()

        // Host appeared, or came back after being away: send a fresh offer.
        if (!wasOnline || webRtc == null) {
            startWebRtc()
        }
    }

    override fun onPeerReady() {
        if (cameraEnabled) announceCamera()
    }

    override fun onAudioLevel(level: Float) {
        if (!active) return
        _level.value = level
    }

    override fun onAuthFailed() {
        if (!active) return
        val gain = _state.value.gain
        teardown()
        _state.value = MicState(
            phase = MicPhase.ERROR,
            gain = gain,
            error = getString(R.string.error_pin_wrong)
        )
    }

    override fun onAnswer(answerSdp: String) {
        if (!active) return
        webRtc?.onAnswer(answerSdp)
    }

    override fun onRemoteCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int) {
        if (!active) return
        webRtc?.addRemoteCandidate(candidate, sdpMid, sdpMLineIndex)
    }

    override fun onToggleMute() {
        if (!active) return
        toggleMute()
    }

    override fun onCameraStart(width: Int, height: Int, fps: Int) {
        if (!cameraEnabled) enableCamera()
        camera?.start(width, height, fps)
    }

    override fun onCameraStop() {
        camera?.stop()
    }

    override fun onCameraCommand(op: String, value: Any?) {
        val streamer = camera ?: return
        when (op) {
            "torch" -> streamer.setFlash(value as? Boolean ?: false)
            "flip" -> streamer.flip(value as? String ?: "none")
            "rotate" -> streamer.rotate((value as? Number)?.toInt() ?: 90)
            "swap" -> {
                val want = value as? String
                val isBack = streamer.facing == CameraHelper.Facing.BACK
                if ((want == "back" && !isBack) || (want == "front" && isBack)) {
                    streamer.switchCamera()
                }
            }
            "zoom" -> streamer.setZoom((value as? Number)?.toFloat() ?: 1f)
            "focus" -> streamer.setFocus((value as? Number)?.toInt() ?: 0)
            "focus_distance" -> streamer.setFocusDistance((value as? Number)?.toInt() ?: 0)
            "stabilization" -> streamer.setStabilization(value as? Boolean ?: false)
            "bitrate" -> streamer.setBitrate((value as? Number)?.toInt() ?: 6000)
            "adaptive" -> {
                val obj = value as? JSONObject
                if (obj != null) {
                    streamer.setAdaptiveBitrate(
                        obj.optInt("min", 2000),
                        obj.optInt("max", 12000)
                    )
                }
            }
            "codec" -> streamer.setH265(value == "h265")
            "filter_effect" -> streamer.applyEffectFilter(value as? String ?: "None")
            "filter_reset" -> streamer.resetFilters()
            "filter_param" -> {
                val obj = value as? JSONObject
                if (obj != null) {
                    streamer.applyCorrectionFilter(
                        obj.optString("name"),
                        obj.optInt("value", 50)
                    )
                }
            }
        }
    }

    override fun onLocalSdp(sdp: String) {
        if (!active) return
        signaling?.sendOffer(sdp)
    }

    override fun onLocalCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int) {
        if (!active) return
        signaling?.sendCandidate(candidate, sdpMid, sdpMLineIndex)
    }

    override fun onRtcState(state: WebRtcClient.State) {
        if (!active) return
        val phase = when (state) {
            WebRtcClient.State.CONNECTED -> MicPhase.STREAMING
            WebRtcClient.State.CONNECTING,
            WebRtcClient.State.DISCONNECTED,
            WebRtcClient.State.FAILED -> MicPhase.CONNECTING
        }
        _state.value = _state.value.copy(phase = phase, muted = muted)
    }

    private fun parseAddress(raw: String): Pair<String, Int>? {
        val trimmed = raw.trim().removePrefix("https://").removePrefix("http://").trimEnd('/')
        if (trimmed.isEmpty()) return null

        val parts = trimmed.split(":")
        // A bare IP or hostname is fine; the default port is assumed.
        if (parts.size == 1) {
            val host = parts[0].trim()
            return if (host.isEmpty()) null else host to DEFAULT_PORT
        }

        if (parts.size != 2) return null
        val host = parts[0].trim()
        val port = parts[1].trim().toIntOrNull() ?: return null
        if (host.isEmpty() || port !in 1..65535) return null
        return host to port
    }

    @Suppress("DEPRECATION")
    private fun acquireLocks() {
        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Poros::Mic").apply {
                setReferenceCounted(false)
                acquire()
            }
        }
        if (wifiLock == null) {
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "Poros::Wifi").apply {
                setReferenceCounted(false)
                acquire()
            }
        }
    }

    private fun releaseLocks() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wifiLock = null
    }

    /** Re-declare the foreground types: camera is added only while it is on. */
    private fun updateForeground() {
        var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        if (cameraEnabled) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
        }
        runCatching {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(), types)
        }
    }

    private fun notifyState() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        runCatching { manager.notify(NOTIFICATION_ID, buildNotification()) }
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.notification_channel_desc)
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val contentIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), flags
        )
        val muteIntent = PendingIntent.getService(
            this, 1, Intent(this, MicService::class.java).setAction(ACTION_TOGGLE_MUTE), flags
        )
        val cameraIntent = PendingIntent.getService(
            this, 3, Intent(this, MicService::class.java).setAction(ACTION_TOGGLE_CAMERA), flags
        )
        val stopIntent = PendingIntent.getService(
            this, 2, Intent(this, MicService::class.java).setAction(ACTION_STOP), flags
        )
        val muteLabel = getString(
            if (muted) R.string.notification_action_unmute else R.string.notification_action_mute
        )
        val cameraLabel = getString(
            if (cameraEnabled) R.string.notification_action_camera_off
            else R.string.notification_action_camera_on
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_mic)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(
                getString(
                    if (cameraEnabled) R.string.notification_text_camera
                    else R.string.notification_text
                )
            )
            .setContentIntent(contentIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, muteLabel, muteIntent)
            .addAction(0, cameraLabel, cameraIntent)
            .addAction(0, getString(R.string.disconnect), stopIntent)
            .build()
    }

    companion object {
        const val ACTION_START = "top.hypixice.poros.START"
        const val ACTION_STOP = "top.hypixice.poros.STOP"
        const val ACTION_TOGGLE_MUTE = "top.hypixice.poros.TOGGLE_MUTE"
        const val ACTION_TOGGLE_CAMERA = "top.hypixice.poros.TOGGLE_CAMERA"
        const val EXTRA_ADDRESS = "address"
        const val EXTRA_GAIN = "gain"
        const val EXTRA_PIN = "pin"

        private const val CHANNEL_ID = "poros_mic"
        private const val NOTIFICATION_ID = 1
        private const val DEFAULT_PORT = 5000

        fun start(context: Context, address: String, gain: Float, pin: String) {
            val intent = Intent(context, MicService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_ADDRESS, address)
                putExtra(EXTRA_GAIN, gain)
                putExtra(EXTRA_PIN, pin)
            }
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, MicService::class.java).apply { action = ACTION_STOP }
            runCatching { context.startService(intent) }
        }
    }
}
