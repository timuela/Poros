package top.hypixice.poros.video

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.pedro.common.ConnectChecker
import com.pedro.common.VideoCodec
import com.pedro.encoder.input.gl.render.filters.BaseFilterRender
import com.pedro.encoder.input.video.CameraHelper
import com.pedro.encoder.input.video.CameraOpenException
import com.pedro.library.util.BitrateAdapter
import com.pedro.rtspserver.RtspServerCamera2
import top.hypixice.poros.video.filters.FilterAdjuster
import top.hypixice.poros.video.filters.FilterRepository
import top.hypixice.poros.video.filters.custom.HorizontalFlipFilterRender
import top.hypixice.poros.video.filters.custom.VerticalFlipFilterRender
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * Publishes the phone camera as an RTSP stream on [PORT].
 *
 * Runs headless: it is driven from a foreground service and never needs a
 * preview view, so the camera keeps streaming while the app is in the
 * background or the screen is off.
 */
class CameraStreamer(
    private val context: Context,
    private val listener: Listener
) : ConnectChecker {

    interface Listener {
        fun onStreamError(title: String, description: String)
        fun onStreamingChanged(streaming: Boolean)
    }

    companion object {
        const val TAG = "PorosCamera"
        const val PORT = 8554
        const val PATH = "live"

        /** Correction sliders are neutral in the middle; see applyCorrectionFilter. */
        const val NEUTRAL_FILTER_VALUE = 50

        /**
         * The phone's LAN address, used to build the RTSP URL the PC dials.
         *
         * Enumerating the interfaces is deliberate: the usual "dial a public
         * address and read the local end" trick picks whatever the default
         * route happens to be, which on a phone with mobile data is the
         * cellular interface - and on a Wi-Fi network with no internet it fails
         * outright. Either way the PC would be handed an address it cannot
         * reach, so prefer the Wi-Fi interface explicitly.
         */
        fun localIpAddress(): String {
            try {
                val wifi = mutableListOf<String>()
                val wired = mutableListOf<String>()
                val other = mutableListOf<String>()

                val interfaces = NetworkInterface.getNetworkInterfaces()
                if (interfaces != null) {
                    for (nif in interfaces) {
                        if (!nif.isUp || nif.isLoopback) continue
                        for (address in nif.inetAddresses) {
                            if (address !is Inet4Address) continue
                            if (address.isLoopbackAddress ||
                                address.isLinkLocalAddress ||
                                address.isMulticastAddress
                            ) {
                                continue
                            }
                            val host = address.hostAddress ?: continue
                            when {
                                nif.name.startsWith("wlan") -> wifi.add(host)
                                nif.name.startsWith("eth") -> wired.add(host)
                                // Skip the mobile-data interface entirely: the
                                // PC is on the LAN, not on the cellular network.
                                nif.name.startsWith("rmnet") ||
                                    nif.name.startsWith("ccmni") -> Unit
                                else -> other.add(host)
                            }
                        }
                    }
                }

                (wifi + wired + other).firstOrNull()?.let { return it }
            } catch (e: Exception) {
                Log.w(TAG, "could not enumerate network interfaces: ${e.message}")
            }
            return "127.0.0.1"
        }
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    // The context constructor is the headless/background variant: no view.
    private val rtspServer = RtspServerCamera2(context, this, PORT)

    var facing: CameraHelper.Facing = CameraHelper.Facing.BACK
        private set
    var width: Int = 1920
        private set
    var height: Int = 1080
        private set
    var fps: Int = 30
        private set
    var bitrate: Int = 6000 * 1024
        private set
    var h265Enabled: Boolean = false
        private set

    private var adaptiveEnabled = false
    // Once the desktop has chosen a bitrate, do not second-guess it when the
    // resolution or frame rate changes.
    private var bitrateFromDesktop = false
    // Focus must be remembered and re-applied: switching camera or restarting
    // the stream resets the camera to its own default, and the desktop's
    // choice would otherwise be silently lost.
    private var focusMode = 0
    private var focusDioptres = 0f
    private var rotation = 0
    private var hFlip: BaseFilterRender? = null
    private var vFlip: BaseFilterRender? = null
    private var effectFilter: BaseFilterRender? = null
    private val correctionFilters = mutableSetOf<BaseFilterRender>()

    private val bitrateAdapter = BitrateAdapter {
        if (adaptiveEnabled) rtspServer.setVideoBitrateOnFly(it)
    }

    /** The URL the desktop should connect to. */
    fun url(host: String): String = "rtsp://$host:$PORT/$PATH"

    fun startPreview() {
        if (!rtspServer.isOnPreview) {
            // Opens the camera into the engine's own surface. Guarded: in
            // background mode there is no view to attach to, so a failure here
            // must not stop the stream from starting.
            runCatching { rtspServer.startPreview(facing, width, height) }
                .onFailure { Log.w(TAG, "headless preview not started: ${it.message}") }
        }
    }

    fun stopPreview() {
        runCatching { rtspServer.stopPreview() }
    }

    /** Begin publishing; resolution/fps changes restart the encoder. */
    fun start(newWidth: Int, newHeight: Int, newFps: Int, newBitrate: Int? = null) {
        width = newWidth
        height = newHeight
        fps = newFps
        bitrate = newBitrate
            ?: (if (bitrateFromDesktop) bitrate else calculateOptimalBitrate(newWidth, newHeight, newFps))

        mainHandler.post {
            if (rtspServer.isOnPreview) rtspServer.stopPreview()
            startPreview()
            startInternal()
        }
    }

    private fun startInternal() {
        if (rtspServer.isStreaming) return
        try {
            // The codec has to be chosen before the encoder is configured.
            rtspServer.setVideoCodec(if (h265Enabled) VideoCodec.H265 else VideoCodec.H264)
            rtspServer.prepareVideo(width, height, fps, bitrate, 0)
            rtspServer.startStream("rtsp://localhost:$PORT/$PATH")
            applyFilters()
            applyBitrateMode()
            // The camera has just been (re)opened, so its own focus default is
            // in force again - put the desktop's choice back.
            applyFocus()
            listener.onStreamingChanged(true)
        } catch (e: Exception) {
            Log.e(TAG, "could not start the stream", e)
            listener.onStreamError(
                "Stream",
                "($width x $height) @${fps}fps could not be encoded"
            )
        }
    }

    private fun applyFilters() {
        runCatching {
            effectFilter?.let { rtspServer.glInterface.addFilter(it) }
            correctionFilters.forEach { rtspServer.glInterface.addFilter(it) }
            hFlip?.let { rtspServer.glInterface.addFilter(it) }
            vFlip?.let { rtspServer.glInterface.addFilter(it) }
            if (rotation != 0) rtspServer.glInterface.setStreamRotation(rotation)
        }
    }

    private fun applyBitrateMode() {
        runCatching {
            if (adaptiveEnabled) {
                bitrateAdapter.setMaxBitrate(bitrate)
                rtspServer.setVideoBitrateOnFly(bitrate)
            } else {
                rtspServer.setVideoBitrateOnFly(bitrate)
            }
        }
    }

    fun restart() {
        mainHandler.post {
            val wasStreaming = rtspServer.isStreaming
            runCatching { rtspServer.stopStream() }
            rtspServer.stopPreview()
            startPreview()
            if (wasStreaming) startInternal()
        }
    }

    fun stop() {
        mainHandler.post {
            runCatching { if (rtspServer.isStreaming) rtspServer.stopStream() }
            rtspServer.stopPreview()
            listener.onStreamingChanged(false)
        }
    }

    fun switchCamera() {
        try {
            rtspServer.switchCamera()
            facing = if (facing == CameraHelper.Facing.BACK) {
                CameraHelper.Facing.FRONT
            } else {
                CameraHelper.Facing.BACK
            }
            // Switching re-opens the camera, which resets focus to the device
            // default; re-apply once the new camera is actually up.
            mainHandler.postDelayed({ applyFocus() }, 800)
        } catch (e: CameraOpenException) {
            listener.onStreamError(
                "Camera",
                "This resolution is not supported by the other camera"
            )
        }
    }

    fun setResolution(newWidth: Int, newHeight: Int) {
        if (width == newWidth && height == newHeight) return
        width = newWidth
        height = newHeight
        if (!bitrateFromDesktop) bitrate = calculateOptimalBitrate(newWidth, newHeight, fps)
        restart()
    }

    fun setFps(newFps: Int) {
        if (fps == newFps) return
        fps = newFps
        if (!bitrateFromDesktop) bitrate = calculateOptimalBitrate(width, height, newFps)
        restart()
    }

    /** [kbps] is the target bitrate in kilobits per second. */
    fun setBitrate(kbps: Int) {
        adaptiveEnabled = false
        bitrateFromDesktop = true
        bitrate = kbps * 1024
        runCatching { rtspServer.setVideoBitrateOnFly(bitrate) }
    }

    /** Adaptive bitrate: the encoder follows the link between [minKbps] and [maxKbps]. */
    fun setAdaptiveBitrate(minKbps: Int, maxKbps: Int) {
        adaptiveEnabled = true
        bitrateFromDesktop = true
        bitrate = maxKbps * 1024
        bitrateAdapter.setMaxBitrate(maxKbps * 1024)
        runCatching { rtspServer.setVideoBitrateOnFly(maxKbps * 1024) }
    }

    fun setH265(enabled: Boolean) {
        if (h265Enabled == enabled) return
        h265Enabled = enabled
        runCatching { rtspServer.setVideoCodec(if (enabled) VideoCodec.H265 else VideoCodec.H264) }
        if (rtspServer.isStreaming) restart()
    }

    fun setFlash(enabled: Boolean) {
        runCatching { if (enabled) rtspServer.enableLantern() else rtspServer.disableLantern() }
    }

    fun setZoom(zoom: Float) {
        runCatching { rtspServer.zoom = zoom.coerceIn(1f, 10f) }
    }

    fun setStabilization(enabled: Boolean) {
        runCatching {
            if (enabled) rtspServer.enableVideoStabilization() else rtspServer.disableVideoStabilization()
        }
    }

    /** [mode] 0 = continuous AF, 1 = fixed/manual. */
    fun setFocus(mode: Int) {
        focusMode = mode
        applyFocus()
    }

    /**
     * Manual focus. [value] runs 0 (far/infinity) to 100 (closest); the camera
     * works in dioptres, and most phones reach about 10.
     */
    fun setFocusDistance(value: Int) {
        focusDioptres = value.coerceIn(0, 100) / 100f * 10f
        if (focusMode != 0) applyFocusDistance()
    }

    /**
     * Push the remembered focus state at the camera. Called after every start
     * and after a camera switch, since both reset the camera's own state.
     */
    private fun applyFocus() {
        runCatching {
            if (focusMode == 0) rtspServer.enableAutoFocus() else rtspServer.disableAutoFocus()
        }
        if (focusMode != 0) applyFocusDistance()
    }

    private fun applyFocusDistance() {
        runCatching { rtspServer.setFocusDistance(focusDioptres) }
    }

    fun rotate(degrees: Int) {
        rotation = (rotation + degrees + 360) % 360
        runCatching { rtspServer.glInterface.setStreamRotation(rotation) }
    }

    fun flip(axis: String) {
        mainHandler.post {
            when (axis.lowercase()) {
                "horizontal" -> hFlip = toggleFlip(hFlip) { HorizontalFlipFilterRender() }
                "vertical" -> vFlip = toggleFlip(vFlip) { VerticalFlipFilterRender() }
                "none" -> {
                    hFlip = clearFilter(hFlip)
                    vFlip = clearFilter(vFlip)
                }
            }
        }
    }

    /** One active effect at a time; "None" removes it. */
    fun applyEffectFilter(name: String) {
        mainHandler.post {
            val category = FilterRepository.getCategory(name)
            if (category == FilterRepository.Category.CORRECTION) return@post
            effectFilter = clearFilter(effectFilter)
            if (category != FilterRepository.Category.NONE) {
                FilterRepository.create(name)?.let {
                    runCatching { rtspServer.glInterface.addFilter(it) }
                    effectFilter = it
                }
            }
        }
    }

    /** Several corrections can be active; an existing one is adjusted in place. */
    fun applyCorrectionFilter(name: String, value: Int) {
        mainHandler.post {
            val category = FilterRepository.getCategory(name)
            val filterClass = FilterRepository.getClass(name) ?: return@post
            if (category != FilterRepository.Category.CORRECTION) return@post

            val existing = correctionFilters.firstOrNull { it::class.java == filterClass }

            if (value == NEUTRAL_FILTER_VALUE) {
                // The middle of the slider is neutral: keeping the filter in the
                // chain would still cost a render pass on every frame, so take
                // it out and give the stream its full frame rate back.
                if (existing != null) {
                    runCatching { rtspServer.glInterface.removeFilter(existing) }
                    correctionFilters.remove(existing)
                }
                return@post
            }

            if (existing != null) {
                runCatching { FilterAdjuster.adjust(existing, value) }
            } else {
                FilterRepository.create(name)?.let {
                    runCatching {
                        FilterAdjuster.adjust(it, value)
                        correctionFilters.add(it)
                        rtspServer.glInterface.addFilter(it)
                    }
                }
            }
        }
    }

    fun resetFilters() {
        mainHandler.post {
            runCatching {
                (correctionFilters.toList() + listOfNotNull(effectFilter)).forEach {
                    rtspServer.glInterface.removeFilter(it)
                }
            }
            correctionFilters.clear()
            effectFilter = null
        }
    }

    private fun toggleFlip(
        current: BaseFilterRender?,
        create: () -> BaseFilterRender
    ): BaseFilterRender? {
        return if (current != null) {
            runCatching { rtspServer.glInterface.removeFilter(current) }
            null
        } else {
            val filter = create()
            runCatching { rtspServer.glInterface.addFilter(filter) }
            filter
        }
    }

    private fun clearFilter(current: BaseFilterRender?): BaseFilterRender? {
        if (current != null) runCatching { rtspServer.glInterface.removeFilter(current) }
        return null
    }

    private fun calculateOptimalBitrate(width: Int, height: Int, fps: Int): Int {
        val targetPixels = width.toLong() * height.toLong() * fps
        val referencePixels = 1920L * 1080L * 30L
        val referenceBitrate = 6000 * 1024L
        val scaled = (targetPixels.toDouble() / referencePixels.toDouble()) * referenceBitrate
        return scaled.toInt().coerceIn(500 * 1024, 12000 * 1024)
    }

    // --- ConnectChecker -------------------------------------------------
    override fun onNewBitrate(bitrate: Long) {
        bitrateAdapter.adaptBitrate(bitrate)
    }

    override fun onAuthError() {}

    override fun onAuthSuccess() {}

    override fun onConnectionFailed(reason: String) {}

    override fun onConnectionStarted(url: String) {}

    override fun onConnectionSuccess() {}

    override fun onDisconnect() {}
}
