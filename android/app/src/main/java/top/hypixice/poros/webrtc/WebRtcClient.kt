package top.hypixice.poros.webrtc

import android.content.Context
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RTCStatsCollectorCallback
import org.webrtc.RTCStatsReport
import org.webrtc.RtpSender
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.audio.JavaAudioDeviceModule
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException

class WebRtcClient(
    context: Context,
    private val listener: Listener
) {
    interface Listener {
        fun onLocalSdp(sdp: String)
        fun onLocalCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int)
        fun onRtcState(state: State)
        fun onAudioLevel(level: Float)
    }

    enum class State { CONNECTING, CONNECTED, DISCONNECTED, FAILED }

    private val appContext = context.applicationContext
    private val executor = Executors.newSingleThreadExecutor()

    private var factory: PeerConnectionFactory? = null
    private var audioDeviceModule: JavaAudioDeviceModule? = null
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var peerConnection: PeerConnection? = null
    private var audioSender: RtpSender? = null
    private var hasOffer = false
    @Volatile private var closed = false

    private val mainHandler = Handler(Looper.getMainLooper())
    @Volatile private var levelPolling = false

    private val candidateLock = Any()
    private var remoteDescriptionSet = false
    private val pendingRemoteCandidates = ArrayDeque<IceCandidate>()

    private fun submit(block: () -> Unit) {
        if (closed) return
        try {
            executor.execute { block() }
        } catch (e: RejectedExecutionException) {
            closed = true
        }
    }

    fun start() {
        submit {
            ensureFactory()
            createPeerConnection()
            createOffer(iceRestart = false)
        }
    }

    fun setMuted(muted: Boolean) {
        submit { audioTrack?.setEnabled(!muted) }
    }

    fun setGain(gain: Float) {
        submit { audioTrack?.setVolume(gain.toDouble()) }
    }

    fun onAnswer(sdp: String) {
        submit {
            val pc = peerConnection ?: return@submit
            pc.setRemoteDescription(object : SimpleSdpObserver() {
                override fun onSetSuccess() {
                    val ready = synchronized(candidateLock) {
                        remoteDescriptionSet = true
                        val queued = pendingRemoteCandidates.toList()
                        pendingRemoteCandidates.clear()
                        queued
                    }
                    ready.forEach { pc.addIceCandidate(it) }
                }
            }, SessionDescription(SessionDescription.Type.ANSWER, sdp))
        }
    }

    fun addRemoteCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int) {
        submit {
            val pc = peerConnection ?: return@submit
            val ice = IceCandidate(sdpMid, sdpMLineIndex, candidate)
            val applyNow = synchronized(candidateLock) {
                if (remoteDescriptionSet) {
                    true
                } else {
                    pendingRemoteCandidates.add(ice)
                    false
                }
            }
            if (applyNow) pc.addIceCandidate(ice)
        }
    }

    fun renegotiate() {
        submit {
            if (peerConnection != null) createOffer(iceRestart = true)
        }
    }

    fun stop() {
        stopLevelPolling()
        submit {
            audioTrack?.setEnabled(false)
            peerConnection?.close()
            peerConnection?.dispose()
            peerConnection = null
            audioSender = null
            audioTrack?.dispose()
            audioTrack = null
            audioSource?.dispose()
            audioSource = null
            factory?.dispose()
            factory = null
            audioDeviceModule?.release()
            audioDeviceModule = null
            hasOffer = false
            synchronized(candidateLock) {
                remoteDescriptionSet = false
                pendingRemoteCandidates.clear()
            }
        }
    }

    fun shutdown() {
        stop()
        closed = true
        executor.shutdown()
    }

    private fun ensureFactory() {
        if (factory != null) return
        if (!initialized) {
            PeerConnectionFactory.initialize(
                PeerConnectionFactory.InitializationOptions.builder(appContext)
                    .createInitializationOptions()
            )
            initialized = true
        }
        val adm = JavaAudioDeviceModule.builder(appContext)
            .setAudioSource(MediaRecorder.AudioSource.VOICE_COMMUNICATION)
            .setUseHardwareAcousticEchoCanceler(true)
            .setUseHardwareNoiseSuppressor(true)
            .createAudioDeviceModule()
        audioDeviceModule = adm
        factory = PeerConnectionFactory.builder()
            .setAudioDeviceModule(adm)
            .createPeerConnectionFactory()
    }

    private fun createPeerConnection() {
        val f = factory ?: return
        val config = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
            iceTransportsType = PeerConnection.IceTransportsType.ALL
        }
        peerConnection = f.createPeerConnection(config, observer)
        synchronized(candidateLock) {
            remoteDescriptionSet = false
            pendingRemoteCandidates.clear()
        }

        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl", "false"))
            mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googHighpassFilter", "true"))
        }
        audioSource = f.createAudioSource(constraints)
        audioTrack = f.createAudioTrack("poros_audio", audioSource)
        audioTrack?.let { track ->
            audioSender = peerConnection?.addTrack(track, listOf(STREAM_ID))
        }
        startLevelPolling()
        listener.onRtcState(State.CONNECTING)
    }

    private fun startLevelPolling() {
        if (levelPolling) return
        levelPolling = true
        mainHandler.post(levelPoll)
    }

    private fun stopLevelPolling() {
        if (!levelPolling) return
        levelPolling = false
        mainHandler.removeCallbacks(levelPoll)
        listener.onAudioLevel(0f)
    }

    private val levelPoll = object : Runnable {
        override fun run() {
            if (!levelPolling) return
            val pc = peerConnection
            val sender = audioSender
            if (pc != null && sender != null) {
                pc.getStats(sender, RTCStatsCollectorCallback { report ->
                    listener.onAudioLevel(extractAudioLevel(report))
                })
            }
            mainHandler.postDelayed(this, LEVEL_POLL_MS)
        }
    }

    /** Pulls the outbound audio level (0..1) out of the WebRTC stats report. */
    private fun extractAudioLevel(report: RTCStatsReport): Float {
        var level = 0f
        for (stat in report.statsMap.values) {
            for ((key, value) in stat.members) {
                val name = key.lowercase()
                val isLevel = name.contains("audiolevel") ||
                    (name.contains("audio") && name.contains("level"))
                if (!isLevel) continue
                val d = (value as? Number)?.toDouble() ?: continue
                if (d > level) level = d.toFloat()
            }
        }
        return level.coerceIn(0f, 1f)
    }

    private fun createOffer(iceRestart: Boolean) {
        val pc = peerConnection ?: return
        if (iceRestart) pc.restartIce()
        val constraints = MediaConstraints().apply {
            if (iceRestart) mandatory.add(MediaConstraints.KeyValuePair("IceRestart", "true"))
        }
        pc.createOffer(object : SimpleSdpObserver() {
            override fun onCreateSuccess(sdp: SessionDescription) {
                pc.setLocalDescription(SimpleSdpObserver(), sdp)
                hasOffer = true
                listener.onLocalSdp(sdp.description)
            }
        }, constraints)
    }

    private val observer = object : PeerConnection.Observer {
        override fun onSignalingChange(newState: PeerConnection.SignalingState) {}

        override fun onIceConnectionChange(newState: PeerConnection.IceConnectionState) {
            when (newState) {
                PeerConnection.IceConnectionState.CONNECTED,
                PeerConnection.IceConnectionState.COMPLETED ->
                    listener.onRtcState(State.CONNECTED)

                PeerConnection.IceConnectionState.DISCONNECTED ->
                    listener.onRtcState(State.DISCONNECTED)

                PeerConnection.IceConnectionState.FAILED -> {
                    listener.onRtcState(State.FAILED)
                    if (hasOffer) renegotiate()
                }

                else -> {}
            }
        }

        override fun onIceConnectionReceivingChange(receiving: Boolean) {}

        override fun onIceGatheringChange(newState: PeerConnection.IceGatheringState) {}

        override fun onIceCandidate(candidate: IceCandidate) {
            listener.onLocalCandidate(candidate.sdp, candidate.sdpMid, candidate.sdpMLineIndex)
        }

        override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) {}

        override fun onAddStream(stream: MediaStream) {}

        override fun onRemoveStream(stream: MediaStream) {}

        override fun onDataChannel(dataChannel: DataChannel) {}

        override fun onRenegotiationNeeded() {}
    }

    companion object {
        private const val STREAM_ID = "poros_stream"
        private const val LEVEL_POLL_MS = 100L
        @Volatile private var initialized = false
    }
}

private open class SimpleSdpObserver : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription) {}
    override fun onSetSuccess() {}
    override fun onCreateFailure(error: String) {}
    override fun onSetFailure(error: String) {}
}
