package top.hypixice.poros.signaling

import io.socket.client.IO
import io.socket.client.Socket
import okhttp3.OkHttpClient
import org.json.JSONObject
import java.net.URI
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class SignalingClient(
    private val host: String,
    private val port: Int,
    private val listener: Listener
) {
    interface Listener {
        fun onSignalingConnected()
        fun onSignalingDisconnected(reason: String?)
        fun onAnswer(answerSdp: String)
        fun onRemoteCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int)
        fun onPeerReady()
        fun onToggleMute()
        fun onPresence(desktopOnline: Boolean)
        fun onAuthFailed()

        // Camera events. A listener that only cares about audio can ignore them.
        fun onCameraStart(width: Int, height: Int, fps: Int) {}
        fun onCameraStop() {}
        fun onCameraCommand(op: String, value: Any?) {}
    }

    private var socket: Socket? = null

    fun isConnected(): Boolean = socket?.connected() == true

    fun connect() {
        if (socket != null) return

        val client = buildTrustAllClient()
        val options = IO.Options().apply {
            reconnection = true
            callFactory = client
            webSocketFactory = client
        }

        val s = IO.socket(URI("https://$host:$port"), options)

        s.on(Socket.EVENT_CONNECT) { _ ->
            listener.onSignalingConnected()
        }
        s.on(Socket.EVENT_DISCONNECT) { args ->
            listener.onSignalingDisconnected(args.firstOrNull() as? String)
        }
        s.on(Socket.EVENT_CONNECT_ERROR) { args ->
            listener.onSignalingDisconnected(args.firstOrNull()?.toString())
        }
        s.on("ready") { _ ->
            listener.onPeerReady()
        }
        s.on("answer") { args ->
            val obj = args.firstOrNull() as? JSONObject
            if (obj != null) {
                val sdp = obj.optString("sdp")
                if (sdp.isNotEmpty()) listener.onAnswer(sdp)
            }
        }
        s.on("ice_candidate") { args ->
            val obj = args.firstOrNull() as? JSONObject
            if (obj != null) {
                val candidate = obj.optString("candidate")
                if (candidate.isNotEmpty()) {
                    val mid = if (obj.isNull("sdpMid")) null else obj.optString("sdpMid", null)
                    listener.onRemoteCandidate(candidate, mid, obj.optInt("sdpMLineIndex", 0))
                }
            }
        }
        s.on("toggle_mute") { _ ->
            listener.onToggleMute()
        }
        s.on("presence") { args ->
            val obj = args.firstOrNull() as? JSONObject
            if (obj != null) {
                listener.onPresence(obj.optBoolean("desktop", false))
            }
        }
        s.on("auth_failed") { _ ->
            listener.onAuthFailed()
        }
        s.on("camera_start") { args ->
            val obj = args.firstOrNull() as? JSONObject ?: return@on
            listener.onCameraStart(
                obj.optInt("width", 1920),
                obj.optInt("height", 1080),
                obj.optInt("fps", 30)
            )
        }
        s.on("camera_stop") { _ ->
            listener.onCameraStop()
        }
        s.on("camera_command") { args ->
            val obj = args.firstOrNull() as? JSONObject ?: return@on
            val op = obj.optString("op")
            val value = if (obj.has("value") && !obj.isNull("value")) obj.get("value") else null
            if (op.isNotEmpty()) listener.onCameraCommand(op, value)
        }

        socket = s
        s.connect()
    }

    fun join(pin: String) {
        socket?.emit("join", JSONObject().put("role", "mobile").put("pin", pin))
    }

    fun sendOffer(sdp: String) {
        socket?.emit("offer", JSONObject().put("type", "offer").put("sdp", sdp))
    }

    fun sendCandidate(candidate: String, sdpMid: String?, sdpMLineIndex: Int) {
        val payload = JSONObject()
            .put("candidate", candidate)
            .put("sdpMid", sdpMid ?: JSONObject.NULL)
            .put("sdpMLineIndex", sdpMLineIndex)
        socket?.emit("ice_candidate", payload)
    }

    /** Tells the desktop this phone can stream video, and at which sizes. */
    fun sendCameraDescriptor(
        name: String,
        url: String,
        resolutions: List<Pair<Int, Int>>,
        lens: String
    ) {
        val sizes = org.json.JSONArray()
        resolutions.forEach { (width, height) ->
            sizes.put(org.json.JSONArray().put(width).put(height))
        }
        socket?.emit(
            "camera_descriptor",
            JSONObject()
                .put("name", name)
                .put("url", url)
                .put("lens", lens)
                .put("resolutions", sizes)
        )
    }

    fun sendCameraStatus(state: String, detail: String = "") {
        socket?.emit(
            "camera_status",
            JSONObject().put("state", state).put("detail", detail)
        )
    }

    fun disconnect() {
        val s = socket
        socket = null
        if (s != null) runCatching { s.disconnect() }
    }

    private fun buildTrustAllClient(): OkHttpClient {
        val trustAll = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        }
        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, arrayOf<TrustManager>(trustAll), SecureRandom())
        return OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAll)
            .hostnameVerifier { _, _ -> true }
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
    }
}
