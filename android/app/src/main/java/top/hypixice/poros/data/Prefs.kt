package top.hypixice.poros.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class HostProfile(
    val name: String,
    val address: String,
    val description: String = ""
)

class Prefs(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    var address: String
        get() = prefs.getString(KEY_ADDRESS, "") ?: ""
        set(value) = prefs.edit().putString(KEY_ADDRESS, value).apply()

    var gain: Float
        get() = prefs.getFloat(KEY_GAIN, 1f)
        set(value) = prefs.edit().putFloat(KEY_GAIN, value).apply()

    var language: String
        get() = prefs.getString(KEY_LANGUAGE, "en") ?: "en"
        set(value) = prefs.edit().putString(KEY_LANGUAGE, value).apply()

    var pin: String
        get() = prefs.getString(KEY_PIN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_PIN, value).apply()

    fun profiles(): List<HostProfile> {
        val raw = prefs.getString(KEY_PROFILES, null) ?: return emptyList()
        return try {
            val array = JSONArray(raw)
            (0 until array.length()).mapNotNull { index ->
                val obj = array.optJSONObject(index) ?: return@mapNotNull null
                val address = obj.optString("address", "")
                if (address.isEmpty()) {
                    null
                } else {
                    HostProfile(
                        name = obj.optString("name", address),
                        address = address,
                        description = obj.optString("description", "")
                    )
                }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun saveProfiles(profiles: List<HostProfile>) {
        val array = JSONArray()
        profiles.forEach { profile ->
            array.put(
                JSONObject()
                    .put("name", profile.name)
                    .put("address", profile.address)
                    .put("description", profile.description)
            )
        }
        prefs.edit().putString(KEY_PROFILES, array.toString()).apply()
    }

    companion object {
        private const val FILE = "poros_prefs"
        private const val KEY_ADDRESS = "address"
        private const val KEY_GAIN = "gain"
        private const val KEY_LANGUAGE = "language"
        private const val KEY_PIN = "pin"
        private const val KEY_PROFILES = "host_profiles"
    }
}
